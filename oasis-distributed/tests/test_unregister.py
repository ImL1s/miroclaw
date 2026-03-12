"""
TDD RED Tests for Worker Unregister and Action Hash Logging

Tests:
  1. handle_worker_unregister() exists in CoordinatorEnv
  2. Unregistered worker's agents become orphaned
  3. Unregistered worker removed from active_workers
  4. Action hash logged in SendAction (source check)
  5. errors.py module exists with SimulationAbortError
"""
import asyncio
import os
import sqlite3
import sys
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from oasis.network.coordinator_env import CoordinatorEnv
from oasis.network.channel_server import CoordinatorChannel


@pytest.fixture
def mock_platform(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE user (agent_id INTEGER PRIMARY KEY, num_followers INTEGER, num_followings INTEGER, user_name TEXT)")
    conn.commit()
    conn.close()

    platform = MagicMock()
    platform.db_path = db_path
    platform.channel = CoordinatorChannel()
    platform.recsys_type = "mock"
    platform.sandbox_clock = MagicMock()
    platform.update_rec_table = AsyncMock()
    return platform


@pytest.fixture
def coordinator(mock_platform):
    env = CoordinatorEnv(mock_platform, token="test-token", port=50096)
    env.total_rounds = 3
    return env


class TestWorkerUnregister:
    """Tests for handle_worker_unregister()."""

    def test_unregister_method_exists(self, coordinator):
        assert hasattr(coordinator, 'handle_worker_unregister'), \
            "CoordinatorEnv should have handle_worker_unregister method"

    @pytest.mark.asyncio
    async def test_unregister_orphans_agents(self, coordinator):
        """Unregistered worker's agents should be moved to orphaned_agents."""
        coordinator.active_workers = {"w1": True, "w2": True}
        coordinator.registered_workers_agents = {
            "w1": [0, 1, 2],
            "w2": [3, 4, 5],
        }

        await coordinator.handle_worker_unregister("w2")

        assert 3 in coordinator.orphaned_agents
        assert 4 in coordinator.orphaned_agents
        assert 5 in coordinator.orphaned_agents

    @pytest.mark.asyncio
    async def test_unregister_removes_worker(self, coordinator):
        """Unregistered worker should be removed from active_workers."""
        coordinator.active_workers = {"w1": True, "w2": True}
        coordinator.registered_workers_agents = {
            "w1": [0, 1],
            "w2": [2, 3],
        }

        await coordinator.handle_worker_unregister("w2")

        assert "w2" not in coordinator.active_workers
        assert "w1" in coordinator.active_workers


class TestActionHashLogging:
    """Tests for action hash in SendAction."""

    def test_channel_server_has_hashlib(self):
        """channel_server.py should import hashlib for action hashing."""
        source_path = os.path.join(
            os.path.dirname(__file__), '..', 'oasis', 'network', 'channel_server.py'
        )
        source = open(source_path).read()
        assert 'hashlib' in source, \
            "channel_server.py should import hashlib for action hash logging"

    def test_channel_server_logs_hash(self):
        """channel_server.py should log action hash in SendAction."""
        source_path = os.path.join(
            os.path.dirname(__file__), '..', 'oasis', 'network', 'channel_server.py'
        )
        source = open(source_path).read()
        assert 'action_hash' in source or 'sha256' in source, \
            "channel_server.py should compute and log action hash"


class TestErrorsModule:
    """Tests for errors.py module."""

    def test_errors_module_exists(self):
        from oasis.network.errors import SimulationAbortError
        assert issubclass(SimulationAbortError, Exception)

    def test_simulation_abort_error_message(self):
        from oasis.network.errors import SimulationAbortError
        err = SimulationAbortError("test message")
        assert str(err) == "test message"
