#!/usr/bin/env python3
"""
Worker entry point for distributed OASIS simulation.

Connects to the Coordinator via gRPC (TLS), registers, and enters the
main execution loop processing assigned agents each round.

Environment variables:
  COORDINATOR_ADDR        — Coordinator gRPC address (e.g. coordinator:50051)
  WORKER_ID               — Unique worker identifier (auto-derived from hostname if not set)
  MIROFISH_CLUSTER_TOKEN  — Shared cluster authentication token
  CLUSTER_CERT_PATH       — TLS certificate path (default: .cluster.crt)
  LOG_FORMAT              — 'json' for structured logging, 'text' for human-readable
"""
import asyncio
import json
import logging
import os
import socket
import sys
import time

# Ensure oasis package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from oasis.network.worker_runtime import WorkerRuntime


def setup_logging(worker_id: str):
    log_format = os.environ.get('LOG_FORMAT', 'text')
    if log_format == 'json':
        class JsonFormatter(logging.Formatter):
            def format(self, record):
                log_entry = {
                    'ts': self.formatTime(record),
                    'level': record.levelname,
                    'logger': record.name,
                    'worker': worker_id,
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
            format=f'%(asctime)s [{worker_id}] [%(name)s] %(levelname)s: %(message)s'
        )


class MockAgent:
    """Mock agent for Phase 2 Docker testing — no real LLM calls."""
    def __init__(self, agent_id: int):
        self.agent_id = agent_id
        self.channel = None

    async def perform_action_by_llm(self):
        """Simulates an LLM action with a short delay."""
        await asyncio.sleep(0.05)  # 50ms simulated LLM latency


class MockAgentGraph:
    """Mock agent graph for Phase 2 Docker testing."""
    def __init__(self, agents):
        self.agents = agents


async def main():
    # Read configuration from environment
    coordinator_addr = os.environ.get('COORDINATOR_ADDR', 'localhost:50051')
    worker_id = os.environ.get('WORKER_ID', f'worker-{socket.gethostname()[:12]}')
    token = os.environ.get('MIROFISH_CLUSTER_TOKEN', 'default-dev-token')
    cert_path = os.environ.get('CLUSTER_CERT_PATH', '.cluster.crt')

    setup_logging(worker_id)
    logger = logging.getLogger("worker")

    logger.info(f"Worker {worker_id} starting — coordinator={coordinator_addr}")

    # Wait for TLS cert to be available (coordinator generates it)
    logger.info(f"Waiting for TLS certificate at {cert_path}...")
    for attempt in range(60):
        if os.path.exists(cert_path):
            break
        await asyncio.sleep(1)
    else:
        logger.error(f"TLS certificate not found at {cert_path} after 60s. Exiting.")
        return

    logger.info("TLS certificate found.")

    # Create a placeholder agent graph — agents will be assigned during registration
    graph = MockAgentGraph([])

    # Create WorkerRuntime
    worker = WorkerRuntime(coordinator_addr, token, worker_id, graph)

    # Register and get agent assignments
    logger.info("Connecting to Coordinator and registering...")

    # Patch generate_custom_agents to create mock agents based on assigned IDs
    import oasis.network.worker_runtime as wrt
    async def mock_generate(channel, agent_graph):
        """Creates MockAgents based on assigned agent IDs from registration."""
        agents = [MockAgent(aid) for aid in worker.assigned_agents]
        for agent in agents:
            agent.channel = channel
        agent_graph.agents = agents
        return agent_graph
    
    original_gen = wrt.generate_custom_agents
    wrt.generate_custom_agents = mock_generate

    try:
        success = await worker.initialize(use_tls=True)
        if not success:
            logger.error("Failed to register with Coordinator. Exiting.")
            return

        logger.info(f"Registered! Assigned agents: {worker.assigned_agents}")
        logger.info("Entering execution loop...")

        await worker.run_loop()
    except KeyboardInterrupt:
        logger.info("Received interrupt, shutting down...")
    except Exception as e:
        logger.error(f"Worker failed: {e}", exc_info=True)
    finally:
        wrt.generate_custom_agents = original_gen
        await worker.close()
        logger.info("Worker shutdown complete.")


if __name__ == "__main__":
    asyncio.run(main())
