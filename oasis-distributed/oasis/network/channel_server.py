import asyncio
import hashlib
import logging
import pickle
from oasis.network.safe_pickle import restricted_loads
import time
import grpc

from oasis.network.proto import channel_pb2, channel_pb2_grpc

logger = logging.getLogger(__name__)

class CoordinatorChannel:
    """
    Channel interface used by the Coordinator's Platform.
    It works exactly like the original Channel but integrates with gRPC events.
    """
    def __init__(self):
        self.receive_queue = asyncio.Queue()
        self.send_dict = {}
        self.message_events = {}

    async def receive_from(self):
        """Platform calls this to get incoming actions"""
        return await self.receive_queue.get()

    async def send_to(self, message):
        """Platform calls this to send back action responses"""
        message_id = message[0]
        self.send_dict[message_id] = message
        if message_id in self.message_events:
            self.message_events[message_id].set()

    async def process_action(self, action_info: dict, message_id: str, timeout: float = 60.0):
        """Called by gRPC service to inject a worker's action and wait for Platform response"""
        event = asyncio.Event()
        self.message_events[message_id] = event
        
        await self.receive_queue.put((message_id, action_info))
        
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            self.message_events.pop(message_id, None)
            raise
        
        result = self.send_dict.pop(message_id)
        self.message_events.pop(message_id, None)
        return result


class CoordinatorService(channel_pb2_grpc.CoordinatorServiceServicer):
    """
    gRPC Server handling worker connections and propagating actions/sync.
    """
    def __init__(self, channel: CoordinatorChannel, env_ref, token: str):
        self.channel = channel
        self.env = env_ref
        self.token = token
        
        self.workers = {}  # worker_id -> WorkerConfig
        self.worker_heartbeats = {}  # worker_id -> last heartbeat timestamp
        
        # Round Synchronization
        self.round_events = {}  # worker_id -> asyncio.Event() waiting for next round signal
        self.round_data = {}  # worker_id -> channel_pb2.RoundInfo
        self.completed_workers_this_round = set()
        self.all_workers_done_event = asyncio.Event()

    async def _verify_token(self, token, context):
        if token != self.token:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid cluster token")

    async def Register(self, request, context):
        await self._verify_token(request.token, context)
        t0 = time.monotonic()
        logger.info(f"Register(worker={request.worker_id}, capacity={request.max_capacity})")
        config = await self.env.handle_worker_registration(request.worker_id, request.max_capacity)
        self.workers[request.worker_id] = config
        
        if request.worker_id not in self.round_events:
            self.round_events[request.worker_id] = asyncio.Event()
        
        elapsed = (time.monotonic() - t0) * 1000
        logger.info(f"Register(worker={request.worker_id}) completed in {elapsed:.1f}ms — "
                    f"total workers: {len(self.workers)}")
        return config

    async def Heartbeat(self, request, context):
        await self._verify_token(request.token, context)
        self.worker_heartbeats[request.worker_id] = asyncio.get_running_loop().time()
        return channel_pb2.Empty()

    async def WaitForRound(self, request, context):
        await self._verify_token(request.token, context)
        worker_id = request.worker_id
        if worker_id not in self.round_events:
            self.round_events[worker_id] = asyncio.Event()
        
        # Wait until the CoordinatorEnv signals the start of the next round
        await self.round_events[worker_id].wait()
        self.round_events[worker_id].clear() # Reset for next round
        
        return self.round_data[worker_id]

    async def GetContext(self, request, context):
        await self._verify_token(request.token, context)
        t0 = time.monotonic()
        followers, followings, group_msgs = await self.env.get_agent_context(request.agent_id)
        context_data = pickle.dumps((followers, followings, group_msgs))
        elapsed = (time.monotonic() - t0) * 1000
        logger.debug(f"GetContext(worker={request.worker_id}, agent={request.agent_id}) in {elapsed:.1f}ms")
        return channel_pb2.ContextResponse(context_data=context_data)

    async def SendAction(self, request, context):
        await self._verify_token(request.token, context)
        action_data = request.action_data
        action_hash = hashlib.sha256(action_data).hexdigest()[:16]
        logger.info("Action(agent=%s, hash=%s)", request.agent_id, action_hash)
        action_info = restricted_loads(action_data)
        
        # This will block until the Local Platform processes it
        try:
            result = await self.channel.process_action(action_info, request.message_id)
            result_data = pickle.dumps(result)
            return channel_pb2.ActionResponse(
                message_id=request.message_id,
                agent_id=request.agent_id,
                result_data=result_data,
                success=True
            )
        except Exception as e:
            logger.error(f"Error processing action for agent {request.agent_id}: {e}")
            return channel_pb2.ActionResponse(
                message_id=request.message_id,
                agent_id=request.agent_id,
                success=False,
                error_message=str(e)
            )

    async def RoundComplete(self, request, context):
        await self._verify_token(request.token, context)
        self.completed_workers_this_round.add(request.worker_id)
        logger.info(f"RoundComplete(worker={request.worker_id}, round={request.round_num}) — "
                    f"{len(self.completed_workers_this_round)}/{len(self.workers)} done")
        await self.env.handle_worker_round_complete(request.worker_id, request.round_num)
        return channel_pb2.Empty()

    async def Unregister(self, request, context):
        """Graceful worker unregistration."""
        await self._verify_token(request.token, context)
        result = self.env.handle_worker_unregister(request.worker_id)
        if asyncio.iscoroutine(result):
            await result
        logger.info(f"Worker {request.worker_id} unregistered gracefully.")
        return channel_pb2.Empty()

async def serve(coordinator_channel, env_ref, token: str, port: int = 50051, use_tls: bool = True):
    server = grpc.aio.server()
    service = CoordinatorService(coordinator_channel, env_ref, token)
    channel_pb2_grpc.add_CoordinatorServiceServicer_to_server(service, server)
    
    if use_tls:
        from oasis.network.security import get_server_credentials
        creds = get_server_credentials()
        server.add_secure_port(f'[::]:{port}', creds)
        logger.info(f"Coordinator gRPC server starting on secure port {port} with TLS...")
    else:
        server.add_insecure_port(f'[::]:{port}')
        logger.info(f"Coordinator gRPC server starting on insecure port {port}...")
        
    await server.start()
    return server, service
