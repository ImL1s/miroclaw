import asyncio
import sqlite3
import pytest
import pytest_asyncio
import sys
from unittest.mock import AsyncMock, patch, MagicMock

from oasis.network.coordinator_env import CoordinatorEnv
from oasis.network.worker_runtime import WorkerRuntime
from oasis.network.channel_server import CoordinatorChannel
from oasis.social_platform.platform import Platform

# Mocking AgentGraph to avoid complex logic
class MockAgent:
    def __init__(self, agent_id):
        self.agent_id = agent_id
        self.channel = None
        self.perform_action_by_llm = AsyncMock()

class MockAgentGraph:
    def __init__(self, agents):
        self.agents = agents

def setup_mock_db(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS user 
                      (agent_id INTEGER PRIMARY KEY, num_followers INTEGER, num_followings INTEGER)''')
    cursor.execute("INSERT OR REPLACE INTO user (agent_id, num_followers, num_followings) VALUES (1, 100, 50)")
    cursor.execute("INSERT OR REPLACE INTO user (agent_id, num_followers, num_followings) VALUES (2, 200, 10)")
    conn.commit()
    conn.close()

@pytest_asyncio.fixture
async def platform(tmp_path):
    db_path = str(tmp_path / "test.db")
    setup_mock_db(db_path)
    
    channel = CoordinatorChannel()
    plat = MagicMock(spec=Platform)
    plat.db_path = db_path
    plat.channel = channel
    plat.update_rec_table = AsyncMock()
    plat.running = AsyncMock()
    plat.recsys_type = "dummy"
    plat.sandbox_clock = MagicMock()
    plat.sandbox_clock.time_step = 0
    return plat

@pytest.mark.asyncio
async def test_full_distributed_loop(platform):
    token = "test_token"
    port = 50055

    # 1. Setup Coordinator
    coordinator = CoordinatorEnv(platform, token, port=port)
    coordinator.registered_workers_agents = {"worker_1": [1], "worker_2": [2]}
    # Start server in insecure mode for faster testing without certs, wait we used TLS by default for security
    # Actually, TLS works locally too because we have security.py generating them. Let's use use_tls=True
    await coordinator.start_server(use_tls=True)

    # 2. Setup Workers
    agents_1 = [MockAgent(1)]
    graph_1 = MockAgentGraph(agents_1)
    worker_1 = WorkerRuntime("localhost:50055", token, "worker_1", graph_1)

    agents_2 = [MockAgent(2)]
    graph_2 = MockAgentGraph(agents_2)
    worker_2 = WorkerRuntime("localhost:50055", token, "worker_2", graph_2)

    # Mock generate_custom_agents because we don't want to run the real one
    with patch("oasis.network.worker_runtime.generate_custom_agents", new_callable=AsyncMock) as mock_gen:
        mock_gen.side_effect = lambda channel, agent_graph: agent_graph # Just return the graph transparently

        assert await worker_1.initialize(use_tls=True)
        assert await worker_2.initialize(use_tls=True)

        # 3. Test Context RPC through WorkerNetworkChannel
        ctx = await worker_1.channel.get_context(1)
        assert ctx["num_followers"] == 100
        assert ctx["num_followings"] == 50

        # 4. Run Step concurrently with worker loops
        worker_task_1 = asyncio.create_task(worker_1.run_loop())
        worker_task_2 = asyncio.create_task(worker_2.run_loop())

        # Coordinator triggers a step
        await coordinator.step(timeout_seconds=2)
        
        # Verify agents were called
        agents_1[0].perform_action_by_llm.assert_called_once()
        agents_2[0].perform_action_by_llm.assert_called_once()
        
        # Step twice
        await coordinator.step(timeout_seconds=2)
        assert agents_1[0].perform_action_by_llm.call_count == 2
        
        # 5. Shutdown
        await coordinator.close()
        await worker_task_1
        await worker_task_2
