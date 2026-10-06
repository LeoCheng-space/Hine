"""Single-instance BA: messaging, receipts and synchronization with BB authority."""
import asyncio
import contextlib
import hashlib
import hmac
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from uuid import uuid4

import aiohttp
from aiohttp import web
from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff
from redis.exceptions import RedisError

from . import presence, receipts, synchronization
from . import protocol as p
from .config import Settings
from .internal import Fault, InternalClient
from .invalidation import Invalidations

LOG = logging.getLogger("hine_realtime")
RUNTIME = web.AppKey("realtime", object)
# PUBLISH happens before the completed marker, within one Redis operation.
# Failed/denied PUBLISH cannot poison notice_id idempotence. Store only hashes,
# not committed text, C1, tokens, or recipients; Redis is not a message store.
PUBLISH_ONCE = """
local done = redis.call('GET', KEYS[1])
if done then
  if done ~= ARGV[1] then return -1 end
  return 0
end
redis.call('PUBLISH', ARGV[2], ARGV[3])
redis.call('SET', KEYS[1], ARGV[1])
return 1
"""


@dataclass
class Outgoing:
    raw: str
    size: int
    position: int | None = None
    authorize: bool = False
    conversation: str | None = None
    message_id: str | None = None
    membership_version: int | None = None
    self_removal: bool = False
    sync_guard: object | None = None
    presence_guard: object | None = None


class Connection:
    def __init__(self, runtime, ws, request):
        self.runtime = runtime
        self.ws = ws
        self.transport = request.transport
        self.binding = None
        self.invalid = False
        self.closed = False
        self.queue = asyncio.Queue(runtime.settings.max_outgoing_frames)
        self.queue_bytes = 0
        self.write_lock = asyncio.Lock()
        self.last_heartbeat = time.monotonic()
        self.auth_deadline = self.last_heartbeat + runtime.settings.auth_timeout
        self.nonces = set()
        self.removed_versions = {}
        self.tokens = float(runtime.settings.frame_burst)
        self.token_time = self.last_heartbeat
        self.writer = asyncio.create_task(self.write_loop())
        self.timer = asyncio.create_task(self.lifetime())
        self.closer = None

    def valid(self):
        return not self.invalid and not self.closed and self.binding is not None and time.monotonic() < self.binding["expires_monotonic"] and time.time() < self.binding["expires_unix"]

    def clear_queue(self):
        while not self.queue.empty():
            outgoing = self.queue.get_nowait()
            if outgoing.presence_guard is not None:
                outgoing.presence_guard.release()
        self.queue_bytes = 0

    def invalidate(self, failure=None):
        if self.invalid or self.closed:
            return
        self.invalid = True
        self.clear_queue()
        self.closer = asyncio.create_task(self.close(failure or Fault("UNAUTHENTICATED", False, user_session=True)))

    async def close(self, failure=None):
        if self.closed:
            return
        # If a slow write owns the connection, abort it rather than waiting for
        # backpressure while revoked/expired data remains queued.
        if self.write_lock.locked():
            if self.transport is not None:
                self.transport.close()
        elif failure is not None:
            with contextlib.suppress(aiohttp.ClientError, ConnectionError, TimeoutError, RuntimeError):
                async with asyncio.timeout(0.2):
                    await self.control(p.event("error", failure.payload()))
        self.closed = True
        self.invalid = True
        self.clear_queue()
        with contextlib.suppress(aiohttp.ClientError, ConnectionError, TimeoutError, RuntimeError):
            async with asyncio.timeout(0.5):
                await self.ws.close(code=1008 if failure else 1001)
        if self.transport is not None and not self.ws.closed:
            self.transport.close()

    async def control(self, frame):
        if self.closed:
            return
        async with self.write_lock:
            async with asyncio.timeout(self.runtime.settings.send_timeout):
                await self.ws.send_str(p.dumps(frame))

    async def error(self, failure, correlation=None):
        if failure.user_session:
            # Stop new/queued data immediately, before a control write can wait
            # for socket backpressure; do not emit a second unrelated W17.
            self.invalid = True
            self.clear_queue()
        try:
            await self.control(p.event("error", failure.payload(), correlation=correlation))
        finally:
            if failure.user_session:
                if self.closer is None:
                    self.closer = asyncio.create_task(self.close())
                self.runtime.request_catchup()

    def apply_group_removal(self, conversation, version):
        previous = self.removed_versions.get(conversation)
        if previous is not None:
            self.removed_versions[conversation] = max(previous, version)
        elif len(self.removed_versions) < self.runtime.settings.max_group_removals:
            self.removed_versions[conversation] = version
        else:
            # Never silently evict an exclusion that may protect a queued or
            # in-flight frame. Metadata exhaustion uses existing connection
            # resource cleanup; ordinary group removal does not close a socket.
            self.invalidate(Fault())

    def group_allows(self, outgoing):
        if outgoing.self_removal:
            return True
        removed_version = self.removed_versions.get(outgoing.conversation)
        return removed_version is None or (outgoing.membership_version is not None and outgoing.membership_version > removed_version)

    def enqueue(self, frame, position=None, authorize=False, membership_version=None, self_removal=False, sync_guard=None, presence_guard=None):
        if self.invalid or self.closed:
            return False
        if not self.valid() or not self.runtime.invalidations.fresh():
            return False
        raw = p.dumps(frame)
        size = len(raw)
        if self.queue.full() or self.queue_bytes + size > self.runtime.settings.max_outgoing_bytes:
            self.invalidate(Fault("DEPENDENCY_UNAVAILABLE"))
            return False
        self.queue_bytes += size
        message_id = frame["payload"]["message_id"] if frame["event"] in {"message.created", "message.status"} else None
        self.queue.put_nowait(Outgoing(raw, size, position, authorize, frame.get("conversation_id"), message_id, membership_version, self_removal, sync_guard, presence_guard))
        return True

    async def write_loop(self):
        try:
            while True:
                outgoing = await self.queue.get()
                self.queue_bytes -= outgoing.size
                try:
                    await self.write_outgoing(outgoing)
                finally:
                    if outgoing.presence_guard is not None:
                        outgoing.presence_guard.release()
        except (aiohttp.ClientError, ConnectionError, TimeoutError, RuntimeError):
            self.invalidate(Fault())

    async def write_outgoing(self, outgoing):
        if not self.valid():
            return
        if not self.runtime.invalidations.fresh() or not self.group_allows(outgoing):
            if outgoing.sync_guard is not None:
                await self.error(Fault(), outgoing.sync_guard.correlation)
            return
        if outgoing.position is not None and not await self.runtime.invalidations.gate(outgoing.position):
            return
        if outgoing.sync_guard is not None:
            try:
                await outgoing.sync_guard.authorize(self)
            except Fault as failure:
                await self.error(failure, outgoing.sync_guard.correlation)
                return
            except (p.Invalid, TypeError, KeyError):
                await self.error(Fault(), outgoing.sync_guard.correlation)
                return
        if outgoing.authorize:
            try:
                resource_type = "message" if outgoing.message_id is not None else "conversation"
                resource_id = outgoing.message_id if outgoing.message_id is not None else outgoing.conversation
                result = await self.runtime.client.call("authorize", {**self.session_binding(), "action": "receive", "resource_type": resource_type, "resource_id": resource_id})
                p.check("allowed" in result and "authorization_version" in result)
                p.boolean(result["allowed"])
                p.string(result["authorization_version"], True)
                if not result["allowed"]:
                    return
            except Fault as failure:
                if failure.user_session:
                    await self.error(failure)
                return
            except (p.Invalid, TypeError, KeyError):
                LOG.warning("invalid_authorization_response")
                return
        try:
            async with self.write_lock:
                raw = outgoing.raw
                if outgoing.presence_guard is not None:
                    raw = await outgoing.presence_guard.prepare(self)
                    if raw is None:
                        return
                # No await between the final checks and starting send_str.
                # Presence's C2/contact read is after acquiring this lock.
                if self.invalid or self.closed:
                    return
                if not self.valid():
                    return
                blocked = (not self.runtime.invalidations.fresh() or not self.group_allows(outgoing)
                           or (outgoing.position is not None and outgoing.position > self.runtime.invalidations.applied_position)
                           or (outgoing.sync_guard is not None and not outgoing.sync_guard.allows(self))
                           or (outgoing.presence_guard is not None and not outgoing.presence_guard.allows(self)))
                if blocked:
                    if outgoing.sync_guard is None:
                        return
                    # The socket lock is held: never reacquire it via control.
                    raw = p.dumps(p.event("error", Fault().payload(), correlation=outgoing.sync_guard.correlation))
                async with asyncio.timeout(self.runtime.settings.send_timeout):
                    await self.ws.send_str(raw)
                if outgoing.presence_guard is not None:
                    outgoing.presence_guard.sent(self)
        except Fault as failure:
            if failure.user_session:
                await self.error(failure)
        except (p.Invalid, TypeError, KeyError):
            LOG.warning("invalid_presence_authorization_response")

    async def lifetime(self):
        while not self.closed and not self.invalid:
            current = time.monotonic()
            if self.binding is None:
                deadline = self.auth_deadline
            else:
                deadline = min(self.binding["expires_monotonic"], self.last_heartbeat + self.runtime.settings.heartbeat_timeout)
            if current >= deadline or (self.binding is not None and time.time() >= self.binding["expires_unix"]):
                # Expiry/heartbeat is an absolute transport cleanup bound, not
                # something deferred behind pending HTTP or output writes.
                self.invalid = True
                self.clear_queue()
                if self.transport is not None:
                    self.transport.close()
                await self.close()
                return
            await asyncio.sleep(min(deadline - current, 0.25))

    def session_binding(self):
        return {key: self.binding[key] for key in ["subject_id", "device_id", "session_id", "session_generation"]}

    def frame_allowed(self):
        current = time.monotonic()
        self.tokens = min(self.runtime.settings.frame_burst, self.tokens + (current - self.token_time) * self.runtime.settings.frame_rate)
        self.token_time = current
        if self.tokens < 1:
            return False
        self.tokens -= 1
        return True

    async def dispose(self):
        self.invalid = True
        self.closed = True
        self.clear_queue()
        self.removed_versions.clear()
        for task in [self.writer, self.timer, self.closer]:
            if task is not None and task is not asyncio.current_task():
                task.cancel()
        for task in [self.writer, self.timer, self.closer]:
            if task is not None and task is not asyncio.current_task():
                with contextlib.suppress(asyncio.CancelledError):
                    await task


class Runtime:
    def __init__(self, settings):
        self.settings = settings
        self.connections = set()
        self.pending_handshakes = 0
        self.session = None
        self.client = None
        self.redis = None
        self.invalidations = None
        self.subscribed = False
        self.presence = None
        self.tasks = []
        self.catchup_task = None
        self.seen = OrderedDict()
        self.notice_queue = asyncio.Queue(256)
        self.channel = settings.prefix + ":notices"

    async def start(self):
        if not self.settings.valid:
            return
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.settings.dependency_timeout), trust_env=False, auto_decompress=False)
        self.client = InternalClient(self.settings, self.session)
        self.invalidations = Invalidations(self.settings, self.client, self.connections)
        self.redis = Redis.from_url(self.settings.redis_url, decode_responses=False, protocol=2, socket_connect_timeout=1, socket_timeout=2, retry=Retry(NoBackoff(), 0), max_connections=32)
        self.presence = presence.Presence(self)
        self.tasks = [asyncio.create_task(self.poll()), asyncio.create_task(self.subscribe()), asyncio.create_task(self.consume()), asyncio.create_task(self.presence.run())]

    async def stop(self):
        for connection in tuple(self.connections):
            await connection.close()
        tasks = self.tasks + ([self.catchup_task] if self.catchup_task is not None else [])
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if self.redis is not None:
            await self.redis.aclose()
        if self.session is not None:
            await self.session.close()

    def request_catchup(self):
        if self.invalidations is not None and (self.catchup_task is None or self.catchup_task.done()):
            self.catchup_task = asyncio.create_task(self.catchup_safely())

    async def catchup_safely(self):
        try:
            await self.invalidations.catchup()
        except Fault:
            LOG.warning("invalidation_catchup_failed")

    async def poll(self):
        while True:
            await self.catchup_safely()
            await asyncio.sleep(self.settings.poll_seconds)

    async def subscribe(self):
        while True:
            try:
                async with self.redis.pubsub() as pubsub:
                    await pubsub.subscribe(self.channel)
                    while True:
                        message = await pubsub.get_message(ignore_subscribe_messages=False, timeout=1)
                        if message is None:
                            continue
                        if message["type"] == "subscribe":
                            self.subscribed = True
                            continue
                        if message["type"] != "message":
                            continue
                        raw = message["data"]
                        if not isinstance(raw, bytes) or len(raw) > 1048576:
                            LOG.warning("invalid_redis_notice")
                            continue
                        try:
                            value = p.notice(p.loads(raw))
                            if value["type"] == "session_invalidation":
                                if self.already_seen(value["notice_id"]):
                                    continue
                                # Invalidation must not wait behind data fanout
                                # or a slow BB catchup held for another notice.
                                await self.invalidations.apply(value["session_invalidation"])
                                self.request_catchup()
                            else:
                                self.apply_group_removals(value)
                                self.notice_queue.put_nowait(value)
                        except asyncio.QueueFull:
                            LOG.warning("notice_queue_full_sync_required")
                        except (p.Invalid, Fault, TypeError, KeyError):
                            LOG.warning("invalid_redis_notice")
            except (RedisError, OSError, TimeoutError):
                LOG.warning("redis_subscription_unavailable")
            finally:
                self.subscribed = False
            await asyncio.sleep(1)

    async def publish(self, value):
        if self.redis is None:
            raise Fault()
        raw = p.dumps(value)
        if len(raw) > 1048576:
            raise Fault("INVALID_ARGUMENT", False)
        digest = hashlib.sha256(raw.encode("ascii")).hexdigest()
        try:
            result = await self.redis.eval(PUBLISH_ONCE, 1, self.settings.prefix + ":published:" + value["notice_id"], digest, self.channel, raw)
            if result == -1:
                raise Fault("INVALID_ARGUMENT", False)
            if result not in {0, 1}:
                raise Fault()
        except (RedisError, OSError, TimeoutError):
            LOG.warning("redis_publish_unavailable")
            raise Fault() from None

    def already_seen(self, identifier):
        current = time.monotonic()
        while self.seen and next(iter(self.seen.values())) < current - 86400:
            self.seen.popitem(last=False)
        if identifier in self.seen:
            return True
        while len(self.seen) >= 4096:
            self.seen.popitem(last=False)
        self.seen[identifier] = current
        return False

    def apply_group_removals(self, value):
        if value["type"] != "conversation_events":
            return
        body = value["conversation_events"]
        if body["source"] != "A18":
            return
        # A split fragment need not target the removed user. Each trusted
        # envelope identifies the removed member independently of its recipient.
        # Apply the whole validated notice synchronously before any gate/queue
        # wait or delivery, so old pending authorization snapshots cannot win.
        removed_users = {delivery["envelope"]["payload"]["member_id"] for delivery in body["deliveries"]}
        for connection in tuple(self.connections):
            if connection.binding is not None and connection.binding["user_id"] in removed_users:
                connection.apply_group_removal(body["conversation_id"], body["membership_version"])

    async def consume(self):
        while True:
            value = await self.notice_queue.get()
            self.apply_group_removals(value)
            if self.already_seen(value["notice_id"]):
                continue
            if not await self.invalidations.gate(value["invalidation_position"]):
                continue
            for delivery in value["conversation_events"]["deliveries"]:
                frame = delivery["envelope"]
                recipient = delivery["recipient_user_id"]
                minimal_self_removal = frame["event"] == "conversation.member_removed" and frame["payload"]["member_id"] == recipient
                for connection in tuple(self.connections):
                    if connection.binding is not None and connection.binding["user_id"] == recipient:
                        connection.enqueue(frame, value["invalidation_position"], authorize=not minimal_self_removal, membership_version=value["conversation_events"]["membership_version"], self_removal=minimal_self_removal)

    async def authenticate(self, connection, frame):
        if connection.binding is not None:
            raise Fault("INVALID_ARGUMENT", False)
        p.keys(frame["payload"], ["access_token", "device_id"])
        token = p.string(frame["payload"]["access_token"], True)
        device = p.string(frame["payload"]["device_id"], True)
        if not self.settings.valid or self.invalidations is None or not self.invalidations.fresh():
            raise Fault()
        result = await self.client.call("validateAccess", {"access_token": token, "device_id": device})
        try:
            p.access_result(result)
        except (p.Invalid, TypeError, KeyError):
            raise Fault() from None
        remaining = p.timestamp(result["expires_at"]) - time.time()
        if not result["session_valid"] or remaining <= 0:
            raise Fault("UNAUTHENTICATED", False, user_session=True)
        binding = {key: result[key] for key in ["subject_id", "user_id", "session_id", "session_generation", "expires_at", "invalidation_position"]}
        binding["device_id"] = device
        binding["expires_monotonic"] = time.monotonic() + remaining
        binding["expires_unix"] = p.timestamp(result["expires_at"])
        try:
            await self.invalidations.register(connection, binding)
        except TimeoutError:
            raise Fault() from None
        connection.enqueue(p.event("auth.accepted", {"user_id": binding["user_id"], "device_id": device, "expires_at": binding["expires_at"], "session_generation": binding["session_generation"], "heartbeat_interval_seconds": self.settings.heartbeat_interval, "heartbeat_timeout_seconds": self.settings.heartbeat_timeout}, correlation=frame["event_id"]))

    async def send_message(self, connection, frame):
        p.check("conversation_id" in frame)
        conversation = p.string(frame["conversation_id"])
        content = p.message_payload(frame["payload"])
        body = {**connection.session_binding(), "conversation_id": conversation, "client_message_id": frame["payload"]["client_message_id"], "type": frame["payload"]["type"], "payload": {content: frame["payload"][content]}, "request_event_id": frame["event_id"]}
        result = await self.client.call("persistIfAbsent", body, write=True)
        try:
            p.persisted_result(result)
        except (p.Invalid, TypeError, KeyError):
            raise Fault("OUTCOME_UNCONFIRMED") from None
        position = result["invalidation_position"]
        if not await self.invalidations.gate(position):
            raise Fault()
        connection.enqueue(p.event("message.ack", {"client_message_id": body["client_message_id"], "message_id": result["message_id"], "status": "persisted"}, correlation=frame["event_id"], conversation=conversation), position=position, membership_version=result["membership_version"])
        deliveries = []
        for recipient in result["recipient_ids"]:
            payload = {"message_id": result["message_id"], "type": body["type"], content: body["payload"][content], "order_key": result["order_key"]}
            if recipient == connection.binding["user_id"]:
                payload["client_message_id"] = body["client_message_id"]
            deliveries.append({"recipient_user_id": recipient, "envelope": p.event("message.created", payload, conversation=conversation, event_id=result["event_id"], time=result["created_at"], sender=connection.binding["user_id"])})
        value = {"notice_id": result["event_id"], "type": "conversation_events", "committed_at": result["created_at"], "invalidation_position": position, "conversation_events": {"source": "W05", "conversation_id": conversation, "membership_version": result["membership_version"], "deliveries": deliveries}}
        try:
            await self.publish(p.notice(value))
        except Fault:
            # The BB commit is already confirmed. Redis is not persistence;
            # preserve W06 and rely on later feed/history recovery for fanout.
            LOG.warning("committed_message_fanout_unavailable")

    async def dispatch(self, connection, frame):
        name = frame["event"]
        if name == "auth.authenticate":
            await self.authenticate(connection, frame)
            return
        if not connection.valid():
            raise Fault("UNAUTHENTICATED", False, user_session=True)
        if name == "heartbeat.ping":
            p.keys(frame["payload"], ["nonce"])
            nonce = p.string(frame["payload"]["nonce"], True)
            digest = hashlib.sha256(p.dumps(nonce).encode("ascii")).digest()
            p.check(digest not in connection.nonces)
            # Keep only fixed-size replay fingerprints for the token-bounded
            # connection lifetime; never normalize or constrain nonce values.
            connection.nonces.add(digest)
            connection.last_heartbeat = time.monotonic()
            await connection.control(p.event("heartbeat.pong", {"nonce": nonce}, correlation=frame["event_id"]))
            return
        if not self.invalidations.fresh():
            raise Fault()
        if name == "message.send":
            await self.send_message(connection, frame)
        elif name in {"message.received", "message.read"}:
            await receipts.handle(self, connection, frame)
        elif name in {"sync.bootstrap.request", "sync.request"}:
            await synchronization.handle(self, connection, frame)
        else:
            raise Fault("INVALID_ARGUMENT", False)


async def websocket(request):
    runtime = request.app[RUNTIME]
    if len(runtime.connections) + runtime.pending_handshakes >= runtime.settings.max_connections:
        return rest_error(Fault("DEPENDENCY_UNAVAILABLE"))
    ws = web.WebSocketResponse(max_msg_size=runtime.settings.max_frame_bytes, compress=False, heartbeat=None, timeout=0.5, writer_limit=65536)
    runtime.pending_handshakes += 1
    try:
        await ws.prepare(request)
    finally:
        runtime.pending_handshakes -= 1
    connection = Connection(runtime, ws, request)
    runtime.connections.add(connection)
    try:
        async for message in ws:
            if connection.invalid:
                break
            correlation = None
            try:
                if not connection.frame_allowed():
                    raise Fault("RATE_LIMITED", True, 1000 // runtime.settings.frame_rate + 1)
                if message.type == aiohttp.WSMsgType.ERROR:
                    break
                if message.type != aiohttp.WSMsgType.TEXT:
                    raise Fault("UNSUPPORTED_MEDIA_TYPE", False)
                decoded = p.loads(message.data)
                if isinstance(decoded, dict):
                    with contextlib.suppress(p.Invalid):
                        correlation = p.uuid(decoded.get("event_id"))
                frame = p.envelope(decoded)
                correlation = frame["event_id"]
                if connection.binding is None and frame["event"] != "auth.authenticate":
                    raise Fault("UNAUTHENTICATED", False, user_session=True)
                await runtime.dispatch(connection, frame)
            except (p.Invalid, TypeError, KeyError, RecursionError):
                await connection.error(Fault("INVALID_ARGUMENT", False), correlation)
                if connection.binding is None:
                    await connection.close()
                    break
            except Fault as failure:
                await connection.error(failure, correlation)
                if connection.binding is None:
                    await connection.close()
                    break
    except (aiohttp.ClientError, ConnectionError, TimeoutError, RuntimeError):
        pass
    finally:
        runtime.connections.discard(connection)
        await connection.dispose()
    return ws


def rest_error(failure, service_identity=False):
    details = {"auth_layer": "service_identity"} if service_identity else {}
    return web.json_response({"error": {"code": failure.code, "message": p.MESSAGES[failure.code], "request_id": str(uuid4()), "retryable": failure.retryable, "details": details}}, status=p.ERROR_STATUS[failure.code])


async def provider(request):
    runtime = request.app[RUNTIME]
    header = request.headers.get("Authorization", "")
    expected = "Bearer " + runtime.settings.api_token
    # Authenticate allowed api before reading or structurally validating body.
    if not runtime.settings.valid or not runtime.settings.api_token or not hmac.compare_digest(header.encode("utf-8"), expected.encode("utf-8")):
        return rest_error(Fault("UNAUTHENTICATED", False), service_identity=True)
    try:
        if request.content_type != "application/json":
            raise p.Invalid("Invalid media type")
        body = p.obj(p.loads(await request.read()))
        operation = request.match_info["operation"]
        if operation == "publishCommitted":
            p.keys(body, ["notice"])
            value = p.notice(body["notice"], external=True)
            await runtime.publish(value)
            return web.json_response({"data": {"notice_id": value["notice_id"], "published": True}})
        if operation == "getDevicePresence":
            p.keys(body, ["subject_id", "device_id"])
            p.string(body["subject_id"])
            p.string(body["device_id"])
            online = await runtime.presence.device_presence(body["subject_id"], body["device_id"])
            return web.json_response({"data": {"online": online, "activity": "unknown", "valid_until": None}})
        raise p.Invalid("Unsupported operation")
    except (p.Invalid, TypeError, KeyError, web.HTTPRequestEntityTooLarge):
        return rest_error(Fault("INVALID_ARGUMENT", False))
    except Fault as failure:
        return rest_error(failure)


async def health(request):
    runtime = request.app[RUNTIME]
    dependencies = {"postgresql": "not_checked", "redis": "not_checked"}
    ready = True
    reason = None
    if request.path == "/health/ready":
        if not runtime.settings.valid:
            ready = False
            reason = "CONFIG_MISSING"
        else:
            try:
                await runtime.redis.ping()
                dependencies["redis"] = "ok"
            except (RedisError, OSError, TimeoutError):
                dependencies["redis"] = "fail"
                ready = False
            try:
                async with asyncio.timeout(runtime.settings.dependency_timeout):
                    await runtime.invalidations.catchup()
            except (Fault, TimeoutError):
                ready = False
            ready = ready and runtime.invalidations.fresh() and runtime.subscribed
    result = {"status": "ok" if ready else "unready", "service": "realtime", "timestamp": p.now(), "dependencies": dependencies}
    if reason is not None:
        result["reason"] = reason
    return web.json_response(result, status=200 if ready else 503)


def create_app(settings=None):
    settings = Settings.from_env() if settings is None else settings
    app = web.Application(client_max_size=1048576)
    runtime = Runtime(settings)
    app[RUNTIME] = runtime

    async def lifecycle(_):
        await runtime.start()
        yield
        await runtime.stop()

    async def shutdown(_):
        for connection in tuple(runtime.connections):
            await connection.close()

    app.cleanup_ctx.append(lifecycle)
    app.on_shutdown.append(shutdown)
    app.router.add_get("/ws/v1", websocket)
    app.router.add_get("/health/live", health)
    app.router.add_get("/health/ready", health)
    app.router.add_post("/internal/v1/{operation}", provider)
    return app
