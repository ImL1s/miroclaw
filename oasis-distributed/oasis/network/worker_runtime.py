from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from oasis.network.channel_client import WorkerNetworkChannel

if TYPE_CHECKING:
    from oasis.social_agent.agent_graph import AgentGraph

# Lazy import — may not be available in slim worker Docker image
generate_custom_agents = None

def _load_agents_generator():
    global generate_custom_agents
    if generate_custom_agents is None:
        try:
            from oasis.social_agent.agents_generator import generate_custom_agents as _gen
            generate_custom_agents = _gen
        except ImportError:
            raise ImportError(
                "generate_custom_agents not available. In slim worker mode, "
                "monkey-patch oasis.network.worker_runtime.generate_custom_agents "
                "before calling initialize()."
            )


worker_log = logging.getLogger("oasis.worker_runtime")

class WorkerRuntime:
    def __init__(self, coordinator_addr: str, token: str, worker_id: str, agent_graph: AgentGraph):
        self.coordinator_addr = coordinator_addr
        self.token = token
        self.worker_id = worker_id
        
        # We will build the full AgentGraph on this node, but only execute actions for assigned_agents
        self.agent_graph = agent_graph
        self.channel = None
        self.assigned_agents = []

    async def initialize(self, use_tls=True):
        """Connects to Coordinator and registers."""
        self.channel = WorkerNetworkChannel(self.coordinator_addr, self.token, self.worker_id, use_tls=use_tls)
        await self.channel.connect()
        
        config = await self.channel.register()
        if not config or not config.accepted:
            worker_log.error("Failed to register with Coordinator. Exiting.")
            return False
            
        self.assigned_agents = list(config.assigned_agents)
        worker_log.info(f"Registered successfully. Assigned agents: {self.assigned_agents}")
        
        # Build the agents locally. generate_custom_agents attaches the channel to them
        _load_agents_generator()
        self.agent_graph = await generate_custom_agents(
            channel=self.channel, agent_graph=self.agent_graph)
            
        return True

    async def _perform_llm_action(self, agent):
        """Send the request to the llm model and execute the action."""
        try:
            await agent.perform_action_by_llm()
            worker_log.info(f"Agent {agent.agent_id} completed action.")
        except Exception as e:
            worker_log.error(f"Agent {agent.agent_id} failed action: {e}")

    async def run_loop(self):
        """Main execution loop waiting for rounds."""
        worker_log.info(f"Worker {self.worker_id} entering execution loop...")
        while True:
            worker_log.debug("Waiting for next round...")
            round_info = await self.channel.wait_for_round()
            
            if not round_info:
                worker_log.error("Lost connection to coordinator or round info empty.")
                break
                
            if round_info.simulation_complete:
                worker_log.info("Coordinator signaled simulation completion. Exiting.")
                break
                
            round_num = round_info.round_num
            active_agent_ids = list(round_info.active_agent_ids)
            
            worker_log.info(f"--- Processing Round {round_num} for active agents: {active_agent_ids} ---")
            
            tasks = []
            for agent in self.agent_graph.agents:
                if agent.agent_id in active_agent_ids:
                    tasks.append(self._perform_llm_action(agent))
                    
            if tasks:
                await asyncio.gather(*tasks)
            else:
                worker_log.info("No agents assigned for this round. Waiting...")
                
            # Signal completion
            worker_log.info(f"Round {round_num} processed. Sending RoundComplete.")
            await self.channel.round_complete(round_num)
            
    async def close(self):
        if self.channel:
            try:
                await self.channel.unregister()
            except Exception as e:
                worker_log.warning(f"Unregister failed during shutdown: {e}")
            await self.channel.close()
