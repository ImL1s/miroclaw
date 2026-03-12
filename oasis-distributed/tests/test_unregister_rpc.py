"""Test that Unregister RPC exists in proto stubs and works end-to-end."""
import os
import sys
import pytest
import grpc

from oasis.network.proto import channel_pb2, channel_pb2_grpc
from oasis.network.channel_server import CoordinatorChannel, CoordinatorService, serve
from oasis.network.channel_client import WorkerNetworkChannel


class MockEnvForUnregister:
    def __init__(self):
        self.registered_workers = []
        self.unregistered_workers = []

    async def handle_worker_registration(self, worker_id, max_capacity):
        self.registered_workers.append(worker_id)
        return channel_pb2.WorkerConfig(
            accepted=True,
            assigned_agents=[1, 2, 3],
            total_rounds=10
        )

    async def get_agent_context(self, agent_id):
        return [], [], []

    async def handle_worker_round_complete(self, worker_id, round_num):
        pass

    def handle_worker_unregister(self, worker_id):
        self.unregistered_workers.append(worker_id)


def test_stub_has_unregister():
    """CoordinatorServiceStub should have Unregister RPC method."""
    import inspect
    source = inspect.getsource(channel_pb2_grpc.CoordinatorServiceStub.__init__)
    assert 'Unregister' in source, "Stub should have Unregister RPC"


def test_servicer_has_unregister():
    """CoordinatorServiceServicer should have Unregister method."""
    assert hasattr(channel_pb2_grpc.CoordinatorServiceServicer, 'Unregister'), \
        "Servicer should have Unregister method"


@pytest.mark.asyncio
async def test_unregister_rpc_e2e():
    """Full gRPC round-trip: Register → Unregister → verify env received it."""
    coord_channel = CoordinatorChannel()
    env = MockEnvForUnregister()
    server, service = await serve(coord_channel, env, token="TEST_TOKEN", port=50070, use_tls=True)
    try:
        from oasis.network.security import get_client_credentials
        creds = get_client_credentials()
        channel = grpc.aio.secure_channel('localhost:50070', creds)
        stub = channel_pb2_grpc.CoordinatorServiceStub(channel)

        # Register first
        reg_req = channel_pb2.WorkerInfo(worker_id="w-test", max_capacity=5, token="TEST_TOKEN")
        await stub.Register(reg_req)
        assert "w-test" in env.registered_workers

        # Unregister
        unreg_req = channel_pb2.WorkerId(worker_id="w-test", token="TEST_TOKEN")
        await stub.Unregister(unreg_req)
        assert "w-test" in env.unregistered_workers

        await channel.close()
    finally:
        await server.stop(grace=0)


@pytest.mark.asyncio
async def test_client_unregister_method():
    """WorkerNetworkChannel should have unregister() method."""
    coord_channel = CoordinatorChannel()
    env = MockEnvForUnregister()
    server, service = await serve(coord_channel, env, token="TEST_TOKEN", port=50071, use_tls=True)
    try:
        from oasis.network.security import get_client_credentials
        creds = get_client_credentials()
        channel = grpc.aio.secure_channel('localhost:50071', creds)
        stub = channel_pb2_grpc.CoordinatorServiceStub(channel)
        worker_channel = WorkerNetworkChannel(stub, token="TEST_TOKEN", worker_id="w-test2")

        # Register first
        reg_req = channel_pb2.WorkerInfo(worker_id="w-test2", max_capacity=5, token="TEST_TOKEN")
        await stub.Register(reg_req)

        # Unregister via client
        assert hasattr(worker_channel, 'unregister'), "WorkerNetworkChannel should have unregister()"
        await worker_channel.unregister()
        assert "w-test2" in env.unregistered_workers

        await channel.close()
    finally:
        await server.stop(grace=0)
