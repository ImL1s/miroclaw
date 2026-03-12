#!/usr/bin/env python3
"""
Coordinator entry point for distributed OASIS simulation.

Initializes the Platform (SQLite), generates TLS certs, starts the gRPC server,
waits for workers to register, runs N simulation rounds, and shuts down.

Environment variables:
  MIROFISH_CLUSTER_TOKEN  — Shared cluster authentication token
  COORDINATOR_PORT        — gRPC listen port (default: 50051)
  CLUSTER_CERT_PATH       — TLS certificate path (default: .cluster.crt)
  CLUSTER_KEY_PATH        — TLS private key path (default: .cluster.key)
  TOTAL_ROUNDS            — Number of simulation rounds (default: 3)
  EXPECTED_WORKERS        — Number of workers to wait for before starting (default: 2)
  OASIS_REAL_PLATFORM     — 'true' to use real OASIS Platform, 'false' for mock (default: false)
  RESUME_FROM_ROUND       — Resume simulation from this round number (default: 0 = start fresh)
  LOG_FORMAT              — 'json' for structured logging, 'text' for human-readable
"""
import asyncio
import json
import logging
import os
import sqlite3
import sys
import time

# Ensure oasis package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from oasis.network.coordinator_env import CoordinatorEnv
from oasis.network.channel_server import CoordinatorChannel
from oasis.network.security import generate_self_signed_cert


def setup_logging():
    log_format = os.environ.get('LOG_FORMAT', 'text')
    if log_format == 'json':
        class JsonFormatter(logging.Formatter):
            def format(self, record):
                log_entry = {
                    'ts': self.formatTime(record),
                    'level': record.levelname,
                    'logger': record.name,
                    'msg': record.getMessage(),
                }
                if record.exc_info and record.exc_info[0]:
                    log_entry['exception'] = self.formatException(record.exc_info)
                return json.dumps(log_entry)

        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logging.root.handlers = [handler]
        logging.root.setLevel(logging.INFO)
    else:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
        )


def setup_mock_db(db_path: str, num_agents: int = 10):
    """Creates a test SQLite database with mock user data."""
    os.makedirs(os.path.dirname(db_path) or '.', exist_ok=True)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS user 
                      (agent_id INTEGER PRIMARY KEY, 
                       num_followers INTEGER, 
                       num_followings INTEGER,
                       user_name TEXT)''')
    for i in range(num_agents):
        cursor.execute(
            "INSERT OR REPLACE INTO user (agent_id, num_followers, num_followings, user_name) "
            "VALUES (?, ?, ?, ?)",
            (i, 100 + i * 10, 50 + i * 5, f"agent_{i}")
        )
    conn.commit()
    conn.close()


class MockPlatform:
    """
    Lightweight Platform mock for Phase 2 Docker testing.
    Replaces the full OASIS Platform (which requires camel-ai, igraph, etc.)
    """
    def __init__(self, db_path: str, channel):
        self.db_path = db_path
        self.channel = channel
        self.recsys_type = "mock"
        self.sandbox_clock = type('Clock', (), {'time_step': 0})()

    async def update_rec_table(self):
        """No-op in mock mode."""
        pass

    async def running(self):
        """No-op in mock mode."""
        pass


async def main():
    setup_logging()
    logger = logging.getLogger("coordinator")

    # Read configuration from environment
    token = os.environ.get('MIROFISH_CLUSTER_TOKEN', 'default-dev-token')
    port = int(os.environ.get('COORDINATOR_PORT', '50051'))
    cert_path = os.environ.get('CLUSTER_CERT_PATH', '.cluster.crt')
    key_path = os.environ.get('CLUSTER_KEY_PATH', '.cluster.key')
    total_rounds = int(os.environ.get('TOTAL_ROUNDS', '3'))
    expected_workers = int(os.environ.get('EXPECTED_WORKERS', '2'))

    logger.info(f"Coordinator starting — port={port}, rounds={total_rounds}, expected_workers={expected_workers}")

    # 1. Generate TLS certificates
    generate_self_signed_cert(cert_path, key_path)
    logger.info(f"TLS certificates ready at {cert_path}")

    # 2. Setup mock database
    db_path = "/app/data/simulation.db"
    num_agents = expected_workers * 5  # 5 agents per worker
    setup_mock_db(db_path, num_agents)
    logger.info(f"Mock database created at {db_path} with {num_agents} agents")

    # 3. Create Platform and CoordinatorEnv
    use_real_platform = os.environ.get('OASIS_REAL_PLATFORM', 'false').lower() == 'true'
    channel = CoordinatorChannel()

    if use_real_platform:
        try:
            from oasis.social_platform.platform import Platform
            platform = Platform(db_path, channel)
            await platform.running()
            logger.info("Using REAL OASIS Platform")
        except ImportError as e:
            logger.warning(f"Cannot import real Platform: {e}. Falling back to MockPlatform.")
            platform = MockPlatform(db_path, channel)
    else:
        platform = MockPlatform(db_path, channel)
        logger.info("Using MockPlatform (OASIS_REAL_PLATFORM not set)")
    
    coordinator = CoordinatorEnv(platform, token, port=port)
    coordinator.total_rounds = total_rounds

    # 4. Start gRPC server
    await coordinator.start_server(use_tls=True)
    logger.info(f"gRPC server listening on port {port} with TLS")

    # 6. Wait for all workers to register (workers self-register with their own IDs)
    logger.info(f"Waiting for {expected_workers} workers to register...")
    timeout = 120  # 2 minutes
    start_time = time.time()
    while len(coordinator.active_workers) < expected_workers:
        if time.time() - start_time > timeout:
            logger.error(f"Timeout waiting for workers. Got {len(coordinator.active_workers)}/{expected_workers}")
            await coordinator.close()
            return
        await asyncio.sleep(1)
    
    # Distribute agents round-robin to registered workers
    worker_ids = list(coordinator.active_workers)
    agents_per_worker = num_agents // len(worker_ids)
    for i, wid in enumerate(worker_ids):
        start = i * agents_per_worker
        end = start + agents_per_worker if i < len(worker_ids) - 1 else num_agents
        coordinator.registered_workers_agents[wid] = list(range(start, end))
        logger.info(f"Assigned agents {start}-{end - 1} to {wid}")
    
    coordinator.total_agent_count = num_agents
    
    logger.info(f"All {expected_workers} workers registered! Starting simulation...")

    # 7. Run simulation rounds (with optional resume)
    resume_round = int(os.environ.get('RESUME_FROM_ROUND', '0'))
    if resume_round > 0:
        logger.info(f"Resuming from round {resume_round}")
        coordinator.current_round = resume_round

    start_round = resume_round
    for round_num in range(start_round, total_rounds):
        logger.info(f"=== Starting Round {round_num + 1}/{total_rounds} ===")
        round_start = time.time()
        await coordinator.step(timeout_seconds=60)
        round_elapsed = time.time() - round_start
        logger.info(f"=== Round {round_num + 1} completed in {round_elapsed:.2f}s ===")

    # 8. Shutdown
    summary = coordinator.get_summary()
    logger.info(f"Simulation summary: {json.dumps(summary)}")
    logger.info("Simulation complete! Shutting down...")
    await coordinator.close()
    logger.info("Coordinator shutdown complete.")


if __name__ == "__main__":
    asyncio.run(main())
