"""Test WorkerRuntime graceful shutdown."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from oasis.network.worker_runtime import WorkerRuntime


@pytest.mark.asyncio
async def test_close_calls_unregister():
    """close() should call channel.unregister() before channel.close()."""
    graph = MagicMock()
    worker = WorkerRuntime("localhost:50051", "tok", "w1", graph)
    worker.channel = AsyncMock()
    worker.channel.unregister = AsyncMock()
    worker.channel.close = AsyncMock()

    await worker.close()

    worker.channel.unregister.assert_called_once()
    worker.channel.close.assert_called_once()


@pytest.mark.asyncio
async def test_close_handles_unregister_failure():
    """close() should still close channel even if unregister fails."""
    graph = MagicMock()
    worker = WorkerRuntime("localhost:50051", "tok", "w1", graph)
    worker.channel = AsyncMock()
    worker.channel.unregister = AsyncMock(side_effect=Exception("conn lost"))
    worker.channel.close = AsyncMock()

    await worker.close()  # Should not raise

    worker.channel.close.assert_called_once()


@pytest.mark.asyncio
async def test_close_noop_without_channel():
    """close() should be safe to call without channel."""
    graph = MagicMock()
    worker = WorkerRuntime("localhost:50051", "tok", "w1", graph)
    worker.channel = None

    await worker.close()  # Should not raise
