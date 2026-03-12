import asyncio
import pickle
import pytest
import grpc
from oasis.network.channel_server import CoordinatorChannel, CoordinatorService, serve
from oasis.network.channel_client import WorkerNetworkChannel
from oasis.network.proto import channel_pb2, channel_pb2_grpc

import pytest_asyncio

class MockEnv:
    def __init__(self):
        self.registered_workers = []
        self.completed_rounds = []
        
    async def handle_worker_registration(self, worker_id, max_capacity):
        self.registered_workers.append(worker_id)
        return channel_pb2.WorkerConfig(
            accepted=True,
            assigned_agents=[1, 2, 3],
            total_rounds=10
        )
        
    async def get_agent_context(self, agent_id):
        return [10, 11], [20, 21], ["hello", "world"]
        
    async def handle_worker_round_complete(self, worker_id, round_num):
        self.completed_rounds.append((worker_id, round_num))


async def _make_server_and_client(port):
    """Helper to create paired gRPC server + client on a unique port."""
    coord_channel = CoordinatorChannel()
    env = MockEnv()
    server, service = await serve(coord_channel, env, token="TEST_TOKEN", port=port, use_tls=True)

    from oasis.network.security import get_client_credentials
    creds = get_client_credentials()
    channel = grpc.aio.secure_channel(f'localhost:{port}', creds)
    stub = channel_pb2_grpc.CoordinatorServiceStub(channel)
    worker_channel = WorkerNetworkChannel(stub, token="TEST_TOKEN", worker_id="worker-1")

    return server, coord_channel, env, channel, worker_channel, stub


@pytest.mark.asyncio
async def test_worker_registration():
    server, coord_channel, env, channel, worker_channel, stub = await _make_server_and_client(50060)
    try:
        req = channel_pb2.WorkerInfo(worker_id="worker-1", max_capacity=10, token="TEST_TOKEN")
        res = await stub.Register(req)
        
        assert res.accepted is True
        assert list(res.assigned_agents) == [1, 2, 3]
        assert "worker-1" in env.registered_workers
    finally:
        await channel.close()
        await server.stop(grace=0)

@pytest.mark.asyncio
async def test_get_context():
    server, coord_channel, env, channel, worker_channel, stub = await _make_server_and_client(50061)
    try:
        req = channel_pb2.ContextRequest(worker_id="worker-1", agent_id=1, round_num=1, token="TEST_TOKEN")
        res = await stub.GetContext(req)
        
        followers, followings, group_msgs = pickle.loads(res.context_data)
        assert followers == [10, 11]
        assert followings == [20, 21]
        assert group_msgs == ["hello", "world"]
    finally:
        await channel.close()
        await server.stop(grace=0)

@pytest.mark.asyncio
async def test_send_action():
    server, coord_channel, env, channel, worker_channel, stub = await _make_server_and_client(50062)
    try:
        # 1. Background task to simulate the Local Platform responding to the action
        async def mock_platform():
            msg_id, action_info = await coord_channel.receive_from()
            assert action_info["do"] == "something"
            # Reply to the worker
            await coord_channel.send_to((msg_id, {"status": "success"}))
            
        task = asyncio.create_task(mock_platform())
        
        # 2. Worker makes the action request
        msg_id = await worker_channel.write_to_receive_queue({"agent_id": 1, "action_type": "post", "do": "something"})
        
        # 3. Worker reads back the result mapped to msg_id
        res = await worker_channel.read_from_send_queue(msg_id)
        assert res == (msg_id, {"status": "success"})
        
        await task
    finally:
        await channel.close()
        await server.stop(grace=0)

@pytest.mark.asyncio
async def test_process_action_timeout():
    """process_action should raise TimeoutError if Platform never responds."""
    ch = CoordinatorChannel()
    with pytest.raises(asyncio.TimeoutError):
        await ch.process_action({"action": "test"}, "msg-timeout", timeout=0.1)

@pytest.mark.asyncio
async def test_wait_for_round_cancellation():
    """WaitForRound should be cancellable via task cancellation."""
    ch = CoordinatorChannel()
    env = MockEnv()
    service = CoordinatorService(ch, env, "tok")
    service.round_events["w-1"] = asyncio.Event()

    from unittest.mock import MagicMock
    context = MagicMock()
    request = MagicMock()
    request.worker_id = "w-1"
    request.token = "tok"

    task = asyncio.create_task(service.WaitForRound(request, context))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
