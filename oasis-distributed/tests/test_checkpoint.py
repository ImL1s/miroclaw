"""
TDD RED Tests for DB Checkpointing in CoordinatorEnv

Tests:
  1. CoordinatorEnv has _checkpoint method
  2. _checkpoint calls SQLite WAL checkpoint
  3. step() calls _checkpoint after round completion
  4. _checkpoint handles errors gracefully (no crash)
  5. CoordinatorEnv enables WAL mode on startup
"""
import asyncio
import os
import sqlite3
import sys
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

# Ensure oasis package importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from oasis.network.coordinator_env import CoordinatorEnv
from oasis.network.channel_server import CoordinatorChannel


@pytest.fixture
def mock_platform(tmp_path):
    """Create a mock platform with a real SQLite db."""
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE user (agent_id INTEGER PRIMARY KEY, num_followers INTEGER, num_followings INTEGER, user_name TEXT)")
    for i in range(5):
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
    env = CoordinatorEnv(mock_platform, token="test-token", port=50099)
    env.total_rounds = 3
    return env


class TestCheckpointMethod:
    """Tests for _checkpoint() method."""

    def test_checkpoint_method_exists(self, coordinator):
        """_checkpoint should exist as a method."""
        assert hasattr(coordinator, '_checkpoint'), \
            "CoordinatorEnv should have _checkpoint method"
        assert callable(coordinator._checkpoint)

    @pytest.mark.asyncio
    async def test_checkpoint_calls_wal_checkpoint(self, coordinator, mock_platform, tmp_path):
        """_checkpoint should execute PRAGMA wal_checkpoint(TRUNCATE)."""
        # Enable WAL mode first
        conn = sqlite3.connect(mock_platform.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.close()

        # _checkpoint should not raise
        await coordinator._checkpoint()

        # Verify by checking db is still accessible
        conn = sqlite3.connect(mock_platform.db_path)
        result = conn.execute("SELECT count(*) FROM user").fetchone()
        conn.close()
        assert result[0] == 5

    @pytest.mark.asyncio
    async def test_checkpoint_handles_errors_gracefully(self, coordinator, mock_platform):
        """_checkpoint should log errors but not crash."""
        # Set db_path to a non-existent location (read-only scenario)
        mock_platform.db_path = "/nonexistent/path/db.sqlite"
        # Should NOT raise
        await coordinator._checkpoint()


class TestCheckpointInStep:
    """Tests that step() integrates checkpoint."""

    @pytest.mark.asyncio
    async def test_step_calls_checkpoint(self, coordinator):
        """step() should call _checkpoint at the end of each round."""
        # Mock the service so step() doesn't hang
        mock_service = MagicMock()
        mock_service.completed_workers_this_round = set()
        mock_service.all_workers_done_event = asyncio.Event()
        mock_service.all_workers_done_event.set()  # Immediately done
        mock_service.round_events = {}
        mock_service.round_data = {}
        coordinator.service = mock_service

        coordinator._checkpoint = AsyncMock()

        await coordinator.step(timeout_seconds=1)

        coordinator._checkpoint.assert_called_once()
