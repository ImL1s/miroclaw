"""
TDD RED Tests for Agent Migration, Abort Threshold, and Simulation Summary

Tests:
  1. _migrate_orphaned_agents exists
  2. Orphaned agents are redistributed round-robin to active workers
  3. orphaned_agents list is cleared after migration
  4. No crash when no active workers remain
  5. total_agent_count attribute exists
  6. orphan_abort_ratio attribute exists (default 0.1)
  7. SimulationAbortError raised when orphan ratio exceeds threshold
  8. No error when orphan ratio is below threshold
  9. get_summary() returns correct structure
  10. step() calls _migrate_orphaned_agents after timeout
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
    env = CoordinatorEnv(mock_platform, token="test-token", port=50097)
    env.total_rounds = 5
    return env


class TestAgentMigration:
    """Tests for _migrate_orphaned_agents()."""

    def test_migrate_method_exists(self, coordinator):
        assert hasattr(coordinator, '_migrate_orphaned_agents'), \
            "CoordinatorEnv should have _migrate_orphaned_agents method"
        assert callable(coordinator._migrate_orphaned_agents)

    def test_orphaned_agents_redistributed(self, coordinator):
        """Orphaned agents should be round-robin distributed to active workers."""
        coordinator.active_workers = {"w1": True, "w2": True}
        coordinator.registered_workers_agents = {"w1": [0, 1], "w2": [2, 3]}
        coordinator.orphaned_agents = [4, 5, 6, 7]

        coordinator._migrate_orphaned_agents()

        # 4 agents distributed to 2 workers: w1 gets 4,6  w2 gets 5,7
        assert 4 in coordinator.registered_workers_agents["w1"]
        assert 6 in coordinator.registered_workers_agents["w1"]
        assert 5 in coordinator.registered_workers_agents["w2"]
        assert 7 in coordinator.registered_workers_agents["w2"]

    def test_orphaned_list_cleared_after_migration(self, coordinator):
        """orphaned_agents should be empty after migration."""
        coordinator.active_workers = {"w1": True}
        coordinator.registered_workers_agents = {"w1": [0]}
        coordinator.orphaned_agents = [1, 2, 3]

        coordinator._migrate_orphaned_agents()

        assert len(coordinator.orphaned_agents) == 0

    def test_no_crash_when_no_workers(self, coordinator):
        """Should not crash when no active workers remain."""
        coordinator.active_workers = {}
        coordinator.orphaned_agents = [1, 2, 3]

        # Should not raise
        coordinator._migrate_orphaned_agents()
        # Agents remain orphaned
        assert len(coordinator.orphaned_agents) == 3


class TestAbortThreshold:
    """Tests for orphan abort ratio."""

    def test_total_agent_count_exists(self, coordinator):
        assert hasattr(coordinator, 'total_agent_count'), \
            "CoordinatorEnv should have total_agent_count attribute"

    def test_orphan_abort_ratio_default(self, coordinator):
        assert hasattr(coordinator, 'orphan_abort_ratio'), \
            "CoordinatorEnv should have orphan_abort_ratio attribute"
        assert coordinator.orphan_abort_ratio == 0.1

    def test_abort_when_threshold_exceeded(self, coordinator):
        """Should raise SimulationAbortError when orphan ratio exceeds threshold."""
        from oasis.network.errors import SimulationAbortError

        coordinator.total_agent_count = 10
        coordinator.orphan_abort_ratio = 0.1
        coordinator.orphaned_agents = list(range(5))  # 50% orphaned

        with pytest.raises(SimulationAbortError):
            coordinator._check_orphan_threshold()

    def test_no_abort_below_threshold(self, coordinator):
        """Should NOT raise when orphan ratio is within threshold."""
        coordinator.total_agent_count = 100
        coordinator.orphan_abort_ratio = 0.1
        coordinator.orphaned_agents = [0]  # 1%, well below 10%

        # Should not raise
        coordinator._check_orphan_threshold()


class TestSimulationSummary:
    """Tests for get_summary()."""

    def test_get_summary_exists(self, coordinator):
        assert hasattr(coordinator, 'get_summary'), \
            "CoordinatorEnv should have get_summary method"

    def test_get_summary_structure(self, coordinator):
        coordinator.current_round = 3
        coordinator.total_rounds = 5
        coordinator.total_agent_count = 55
        coordinator.orphaned_agents = [10, 11]
        coordinator.active_workers = {"w1": True, "w2": True}

        summary = coordinator.get_summary()

        assert summary["total_rounds"] == 5
        assert summary["completed_rounds"] == 3
        assert summary["total_agents"] == 55
        assert summary["orphaned_count"] == 2
        assert summary["active_workers"] == 2
        assert summary["completed"] is False

    def test_summary_completed_flag(self, coordinator):
        coordinator.current_round = 5
        coordinator.total_rounds = 5
        coordinator.total_agent_count = 10
        coordinator.orphaned_agents = []
        coordinator.active_workers = {"w1": True}

        summary = coordinator.get_summary()
        assert summary["completed"] is True
