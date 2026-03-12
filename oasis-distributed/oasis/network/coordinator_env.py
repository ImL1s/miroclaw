import asyncio
import logging
import os
import sqlite3

from oasis.social_platform.platform import Platform
from oasis.social_platform.typing import DefaultPlatformType, RecsysType
from oasis.network.channel_server import serve, CoordinatorChannel
from oasis.network.proto import channel_pb2
from oasis.network.errors import SimulationAbortError

env_log = logging.getLogger("oasis.coordinator_env")

class CoordinatorEnv:
    def __init__(self, platform: Platform, token: str, port: int = 50051):
        self.platform = platform
        self.channel = platform.channel # Expecting a CoordinatorChannel
        self.token = token
        self.port = port
        self.server = None
        
        # Round Management
        self.current_round = 0
        self.total_rounds = 0
        self.active_workers = {}
        self.orphaned_agents = []  # Agents whose workers timed out
        self.total_agent_count = 0  # Set at simulation start
        self.orphan_abort_ratio = float(os.environ.get('ORPHAN_ABORT_RATIO', '0.1'))
        
        self.registered_workers_agents = {} # worker_id -> list of agent_ids

    async def start_server(self, use_tls=True):
        """Starts the gRPC Server"""
        self.server, self.service = await serve(self.channel, self, self.token, self.port, use_tls=use_tls)
        
    async def handle_worker_registration(self, worker_id, max_capacity):
        """Called by channel_server when a worker connects"""
        self.active_workers[worker_id] = True
        
        # For this prototype, we just return all agents if asked, or we can statically assign.
        # This will be refined in static round-robin logic.
        assigned_agents = self.registered_workers_agents.get(worker_id, [])
        
        return channel_pb2.WorkerConfig(
            accepted=True,
            assigned_agents=assigned_agents,
            total_rounds=self.total_rounds
        )

    async def handle_worker_round_complete(self, worker_id, round_num):
        """Called by channel_server when a worker finishes its active agents for the round"""
        # If all known working agents/workers reported back
        if len(self.service.completed_workers_this_round) >= len(self.active_workers):
            self.service.all_workers_done_event.set()

    async def get_agent_context(self, agent_id: int):
        """Called by channel_server to serve GetContext RPC."""
        # 1. Followers / Followings
        num_followers = 0
        num_followings = 0
        try:
            conn = sqlite3.connect(self.platform.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT num_followers FROM user WHERE agent_id = ?", (agent_id, ))
            res = cursor.fetchone()
            if res: num_followers = res[0]
            
            cursor.execute("SELECT num_followings FROM user WHERE agent_id = ?", (agent_id, ))
            res = cursor.fetchone()
            if res: num_followings = res[0]
            conn.close()
        except Exception as e:
            env_log.error(f"Error fetching followers for agent {agent_id}: {e}")

        followers_list = [num_followers]
        followings_list = [num_followings]
        group_msgs = []
        
        return followers_list, followings_list, group_msgs

    async def step(self, timeout_seconds=None):
        """
        Progresses the simulation by one round.
        Instead of calling LLMs locally, it signals all workers to start and waits.
        
        If timeout_seconds is None, calculates dynamic timeout:
          num_agents * 30s, max 600s
        """
        self.current_round += 1
        env_log.info(f"--- Starting Round {self.current_round} ---")
        
        # Dynamic timeout calculation
        if timeout_seconds is None:
            total_agents = sum(len(a) for a in self.registered_workers_agents.values())
            timeout_seconds = min(total_agents * 30, 600)
            env_log.info(f"Dynamic timeout: {timeout_seconds}s for {total_agents} agents")
        
        # 1. Update RecSys Platform (Centralized)
        await self.platform.update_rec_table()
        env_log.info("Platform rec table updated.")
        
        # 2. Reset gRPC service completion sets for the new round
        self.service.completed_workers_this_round.clear()
        self.service.all_workers_done_event.clear()
        
        # 3. Broadcast StartRound to all connected workers
        for worker_id, worker_event in self.service.round_events.items():
            assigned = self.registered_workers_agents.get(worker_id, [])
            self.service.round_data[worker_id] = channel_pb2.RoundInfo(
                round_num=self.current_round,
                active_agent_ids=assigned,
                simulation_complete=False
            )
            worker_event.set()
        
        # 4. Wait for all workers to reply with RoundComplete
        try:
            await asyncio.wait_for(self.service.all_workers_done_event.wait(), timeout=timeout_seconds)
            env_log.info(f"All workers completed round {self.current_round}.")
        except asyncio.TimeoutError:
            env_log.warning(f"Timeout waiting for workers to complete round {self.current_round}!")
            # Mark timed-out workers' agents as orphaned
            completed = self.service.completed_workers_this_round
            for wid in list(self.active_workers):
                if wid not in completed:
                    orphaned = self.registered_workers_agents.pop(wid, [])
                    self.orphaned_agents.extend(orphaned)
                    del self.active_workers[wid]
                    env_log.warning(
                        f"Worker {wid} timed out. {len(orphaned)} agents orphaned. "
                        f"Total orphaned: {len(self.orphaned_agents)}"
                    )
            # Check abort threshold, then migrate survivors
            self._check_orphan_threshold()
            self._migrate_orphaned_agents()
            
        # 5. Platform clock ticks
        if self.platform.recsys_type != RecsysType.REDDIT:
            self.platform.sandbox_clock.time_step += 1
        
        # 6. Checkpoint after every round
        await self._checkpoint()

    async def _checkpoint(self):
        """Round-level DB checkpoint using WAL mode."""
        try:
            conn = sqlite3.connect(self.platform.db_path)
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.close()
            env_log.info(f"DB checkpoint after round {self.current_round}")
        except Exception as e:
            env_log.error(f"Checkpoint failed: {e}")

    def _migrate_orphaned_agents(self):
        """Redistribute orphaned agents to surviving workers (round-robin)."""
        if not self.orphaned_agents or not self.active_workers:
            return
        worker_ids = list(self.active_workers.keys())
        for i, agent_id in enumerate(self.orphaned_agents):
            target = worker_ids[i % len(worker_ids)]
            self.registered_workers_agents.setdefault(target, []).append(agent_id)
        migrated = len(self.orphaned_agents)
        self.orphaned_agents.clear()
        env_log.info(f"Migrated {migrated} orphaned agents to {len(worker_ids)} workers")

    def _check_orphan_threshold(self):
        """Raise SimulationAbortError if orphan ratio exceeds threshold."""
        if self.total_agent_count == 0:
            return
        orphan_ratio = len(self.orphaned_agents) / self.total_agent_count
        if orphan_ratio > self.orphan_abort_ratio:
            raise SimulationAbortError(
                f"Orphaned ratio {orphan_ratio:.1%} exceeds threshold "
                f"{self.orphan_abort_ratio:.0%}. Aborting simulation."
            )

    async def handle_worker_unregister(self, worker_id):
        """Called when a worker gracefully exits."""
        orphaned = self.registered_workers_agents.pop(worker_id, [])
        self.orphaned_agents.extend(orphaned)
        self.active_workers.pop(worker_id, None)
        env_log.info(
            f"Worker {worker_id} unregistered. {len(orphaned)} agents orphaned."
        )

    def get_summary(self):
        """Return a simulation summary dict."""
        return {
            "total_rounds": self.total_rounds,
            "completed_rounds": self.current_round,
            "total_agents": self.total_agent_count,
            "orphaned_count": len(self.orphaned_agents),
            "active_workers": len(self.active_workers),
            "completed": self.current_round >= self.total_rounds,
        }

    async def close(self):
        """Signals workers to stop and shuts down the coordinator"""
        for worker_id, worker_event in self.service.round_events.items():
            self.service.round_data[worker_id] = channel_pb2.RoundInfo(
                round_num=self.current_round,
                simulation_complete=True
            )
            worker_event.set()

        # Give workers a moment to receive the completion signal
        await asyncio.sleep(0.1)

        if self.server:
            await self.server.stop(grace=5)
        env_log.info("Simulation finished! Coordinator shutdown.")

    async def running(self):
        self.platform_task = asyncio.create_task(self.platform.running())
