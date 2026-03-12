import uuid
import grpc
import pickle
from oasis.network.safe_pickle import restricted_loads
import logging

from oasis.network.proto import channel_pb2, channel_pb2_grpc

logger = logging.getLogger(__name__)

class WorkerNetworkChannel:
    """
    Acts as a drop-in replacement for the OASIS 'Channel' class, but injected into the Worker's Agents.
    When the Agent writes an action, this channel executes a blocking gRPC unary call to the Coordinator,
    waits for the result, and stages it so the Agent's subsequent 'read_from_send_queue' call returns instantly.
    
    Supports two init modes:
    1. Address-based: WorkerNetworkChannel(addr, token, worker_id, use_tls=True) — creates its own connection
    2. Stub-based (legacy tests): WorkerNetworkChannel(stub, worker_id=..., token=...) — takes a pre-built stub
    """
    def __init__(self, addr_or_stub, token: str = None, worker_id: str = None, use_tls: bool = True):
        if isinstance(addr_or_stub, str):
            # Address-based mode
            self._addr = addr_or_stub
            self._use_tls = use_tls
            self._grpc_channel = None
            self.stub = None
        else:
            # Stub-based mode (legacy)
            self._addr = None
            self._use_tls = False
            self._grpc_channel = None
            self.stub = addr_or_stub

        self.worker_id = worker_id or "unknown"
        self.token = token or ""
        
        self.current_round_num = 0
        self.pending_results = {}


    async def connect(self):
        """Creates a gRPC channel and stub. Only needed in address-based mode."""
        if self._addr is None:
            return  # Already have a stub
        if self._use_tls:
            from oasis.network.security import get_client_credentials
            creds = get_client_credentials()
            self._grpc_channel = grpc.aio.secure_channel(self._addr, creds)
        else:
            self._grpc_channel = grpc.aio.insecure_channel(self._addr)
        self.stub = channel_pb2_grpc.CoordinatorServiceStub(self._grpc_channel)

    async def close(self):
        """Closes the gRPC channel."""
        if self._grpc_channel:
            await self._grpc_channel.close()

    async def register(self):
        """Registers this worker with the Coordinator."""
        req = channel_pb2.WorkerInfo(
            worker_id=self.worker_id,
            max_capacity=10,
            token=self.token
        )
        try:
            res = await self.stub.Register(req)
            return res
        except grpc.RpcError as e:
            logger.error(f"Registration failed: {e.details()}")
            return None

    async def wait_for_round(self):
        """Long-polls the Coordinator for the next round signal."""
        req = channel_pb2.WorkerId(worker_id=self.worker_id, token=self.token)
        try:
            res = await self.stub.WaitForRound(req)
            return res
        except grpc.RpcError as e:
            logger.error(f"WaitForRound failed: {e.details()}")
            return None

    async def get_context(self, agent_id: int):
        """Fetches the agent's context (followers, followings, etc) from Coordinator."""
        req = channel_pb2.ContextRequest(
            worker_id=self.worker_id,
            agent_id=agent_id,
            round_num=self.current_round_num,
            token=self.token
        )
        try:
            res = await self.stub.GetContext(req)
            context_data = restricted_loads(res.context_data)
            # context_data is (followers_list, followings_list, group_msgs)
            followers, followings, group_msgs = context_data
            num_followers = followers[0] if followers else 0
            num_followings = followings[0] if followings else 0
            return {"num_followers": num_followers, "num_followings": num_followings}
        except grpc.RpcError as e:
            logger.error(f"GetContext failed for agent {agent_id}: {e.details()}")
            return {"num_followers": 0, "num_followings": 0}

    async def round_complete(self, round_num: int):
        """Signals that this worker finished all agents for the round."""
        req = channel_pb2.RoundResult(
            worker_id=self.worker_id,
            round_num=round_num,
            token=self.token
        )
        try:
            await self.stub.RoundComplete(req)
        except grpc.RpcError as e:
            logger.error(f"RoundComplete failed: {e.details()}")

    def set_round_num(self, round_num: int):
        self.current_round_num = round_num

    async def write_to_receive_queue(self, action_info: dict):
        message_id = str(uuid.uuid4())
        
        agent_id = action_info.get("agent_id", -1)
        action_type = action_info.get("action_type", "unknown")
        
        request = channel_pb2.ActionRequest(
            worker_id=self.worker_id,
            message_id=message_id,
            agent_id=agent_id,
            round_num=self.current_round_num,
            action_type=action_type,
            action_data=pickle.dumps(action_info),
            token=self.token
        )
        
        try:
            response = await self.stub.SendAction(request)
            if response.success:
                result = restricted_loads(response.result_data)
                self.pending_results[message_id] = result
            else:
                logger.error(f"Action failed on Coordinator: {response.error_message}")
                self.pending_results[message_id] = (message_id, {"success": False, "error": response.error_message})
        except Exception as e:
            logger.error(f"gRPC SendAction failed: {e}")
            self.pending_results[message_id] = (message_id, {"success": False, "error": str(e)})

        return message_id

    async def read_from_send_queue(self, message_id: str):
        return self.pending_results.pop(message_id, None)

    async def unregister(self):
        """Gracefully unregister this worker from the Coordinator."""
        req = channel_pb2.WorkerId(worker_id=self.worker_id, token=self.token)
        try:
            await self.stub.Unregister(req)
            logger.info(f"Worker {self.worker_id} unregistered successfully.")
        except grpc.RpcError as e:
            logger.error(f"Unregister failed: {e.details()}")

