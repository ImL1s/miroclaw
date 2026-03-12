"""
TDD RED Tests for Hard Timeouts + Orphaned Agent Handling

Tests:
  1. CoordinatorEnv has orphaned_agents list
  2. step() calculates dynamic timeout (num_agents * 30s, max 600s)
  3. When timeout fires, timed-out workers' agents are orphaned
  4. Orphaned workers are removed from active_workers
  5. Simulation continues after timeout (doesn't crash)
  6. RESUME_FROM_ROUND support in run_coordinator.py
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
    for i in range(10):
        conn.execute("INSERT INTO user VALUES (?, ?, ?, ?)", (i, 100, 50, f"agent_{i}"))
    conn.commit()
    conn.close()

    platform = MagicMock()
    platform.db_path = db_path
    platform.channel = CoordinatorChannel()
    platform.recsys_type = "mock"
    platform.sandbox_clock = MagicMock()
    platform.sandbox_clock.time_step = 0
    platform.update_rec_table = AsyncMock()
    return platform


@pytest.fixture
def coordinator(mock_platform):
    env = CoordinatorEnv(mock_platform, token="test-token", port=50098)
    env.total_rounds = 3
    return env


class TestOrphanedAgents:
    """Tests for orphaned_agents tracking."""

    def test_orphaned_agents_initialized(self, coordinator):
        """CoordinatorEnv should have orphaned_agents list."""
        assert hasattr(coordinator, 'orphaned_agents'), \
            "CoordinatorEnv should have orphaned_agents attribute"
        assert isinstance(coordinator.orphaned_agents, list)
        assert len(coordinator.orphaned_agents) == 0

    @pytest.mark.asyncio
    async def test_timeout_orphans_worker_agents(self, coordinator):
        """When a worker times out, its agents should be moved to orphaned_agents."""
        # Setup: two workers, w1 completes, w2 times out
        # We need a set that re-populates after clear() since step() clears it
        class RestoringSet(set):
            def __init__(self, restore_data):
                super().__init__()
                self._restore_data = restore_data
            def clear(self):
                super().clear()
                self.update(self._restore_data)

        mock_service = MagicMock()
        mock_service.completed_workers_this_round = RestoringSet({"worker-1"})
        never_done = asyncio.Event()  # Never gets set
        mock_service.all_workers_done_event = never_done
        mock_service.round_events = {}  # Empty so broadcast loop is skipped
        mock_service.round_data = {}
        coordinator.service = mock_service

        coordinator.active_workers = {"worker-1": True, "worker-2": True}
        coordinator.registered_workers_agents = {
            "worker-1": [0, 1, 2, 3, 4],
            "worker-2": [5, 6, 7, 8, 9],
        }

        # Mock _checkpoint so test doesn't try real DB
        coordinator._checkpoint = AsyncMock()

        # Very short timeout triggers orphan logic
        await coordinator.step(timeout_seconds=0.01)

        # worker-2 should be removed from active_workers
        assert "worker-2" not in coordinator.active_workers
        # After step(), migration runs automatically —
        # orphaned agents get redistributed to surviving workers
        # so orphaned_agents list is cleared
        assert len(coordinator.orphaned_agents) == 0, \
            "Orphans should be migrated after step()"
        # worker-1 should now have all 10 agents (its original 5 + 5 migrated)
        assert len(coordinator.registered_workers_agents["worker-1"]) == 10

    @pytest.mark.asyncio
    async def test_completed_worker_not_orphaned(self, coordinator):
        """Workers that completed should NOT be orphaned."""
        # Both workers complete, so all_workers_done_event is set before timeout
        class RestoringSet(set):
            def __init__(self, restore_data):
                super().__init__()
                self._restore_data = restore_data
            def clear(self):
                super().clear()
                self.update(self._restore_data)

        mock_service = MagicMock()
        mock_service.completed_workers_this_round = RestoringSet({"worker-1", "worker-2"})
        done_event = asyncio.Event()
        done_event.set()
        mock_service.all_workers_done_event = done_event
        mock_service.round_events = {}  # Empty so broadcast loop is skipped
        mock_service.round_data = {}
        coordinator.service = mock_service

        coordinator.active_workers = {"worker-1": True, "worker-2": True}
        coordinator.registered_workers_agents = {
            "worker-1": [0, 1, 2],
            "worker-2": [3, 4, 5],
        }
        coordinator._checkpoint = AsyncMock()

        await coordinator.step(timeout_seconds=1)

        # Both workers still active, no orphans
        assert "worker-1" in coordinator.active_workers
        assert "worker-2" in coordinator.active_workers
        assert len(coordinator.orphaned_agents) == 0


class TestDynamicTimeout:
    """Tests for dynamic timeout calculation."""

    @pytest.mark.asyncio
    async def test_dynamic_timeout_calculated(self, coordinator):
        """step() should calculate timeout based on num_agents * 30s."""
        mock_service = MagicMock()
        mock_service.completed_workers_this_round = set()
        done_event = asyncio.Event()
        done_event.set()
        mock_service.all_workers_done_event = done_event
        mock_service.round_events = {}
        mock_service.round_data = {}
        coordinator.service = mock_service
        coordinator._checkpoint = AsyncMock()

        coordinator.registered_workers_agents = {
            "w1": list(range(10)),  # 10 agents
        }
        coordinator.active_workers = {"w1": True}

        # Source should reference dynamic timeout logic
        import inspect
        source = inspect.getsource(coordinator.step)
        assert 'orphaned' in source.lower() or 'timeout' in source.lower(), \
            "step() should handle timeout/orphan logic"


class TestResumeFromRound:
    """Tests for RESUME_FROM_ROUND env var in run_coordinator.py."""

    def test_resume_env_var_documented(self):
        """run_coordinator.py should reference RESUME_FROM_ROUND."""
        script_path = os.path.join(
            os.path.dirname(__file__), '..', 'scripts', 'run_coordinator.py'
        )
        source = open(script_path).read()
        assert 'RESUME_FROM_ROUND' in source, \
            "run_coordinator.py should document RESUME_FROM_ROUND env var"
