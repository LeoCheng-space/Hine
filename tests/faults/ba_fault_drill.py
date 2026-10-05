#!/usr/bin/env python3
"""Actual local BA/Redis/socket drills with a TEST-ONLY in-memory BB authority.

No production runtime is imported into the runner: BA runs as its own native
``python -m hine_realtime`` process. The BB fixture is not a product fallback.
All response bodies, identities, cursors and child logs stay private/in memory.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import importlib.metadata
import json
import logging
import os
import platform
import re
import signal
import socket
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "backend/realtime/src"
FIXTURES = ROOT / "tests/integration"
POLL_SECONDS = 5
STALE_SECONDS = 15
OUTAGE_SECONDS = STALE_SECONDS + 1
COMMON_LIMITS = [
    "TEST_BB_IN_MEMORY_NOT_POSTGRESQL_DURABILITY",
    "TEST_ACCESS_TOKENS_NOT_PRODUCT_JWT",
    "LOOPBACK_COMPONENTS_NOT_REAL_BB_VM_BROWSER_OR_HA",
    "SINGLE_RUN_NOT_RTO_SLO_OR_OCCURRENCE_ESTIMATE",
]
SCENARIOS = [
    ("DR-01", "BA_SIGKILL_RECOVERY", "actualprocess"),
    ("DR-02", "REDIS_STOP_RESTART", "actualprocess"),
    ("DR-03", "BB_LINK_OUTAGE", "actualsocket"),
    ("DR-04", "LOST_LOGOUT_BB_OUTAGE", "actualsocket"),
    ("DR-05", "C13_SERVICE_CREDENTIAL_FAILURE", "HTTPfixturefault"),
    ("DR-06", "UNCERTAIN_WRITE_AND_ACK_RECOVERY", "actualsocket"),
]


class DrillFailure(Exception):
    """Only fixed, runner-authored categories may enter public evidence."""


class PrerequisiteFailure(Exception):
    pass


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def elapsed_ms(started):
    return round((time.monotonic() - started) * 1000, 3)


def record_for(sid, name, kind):
    return {"id": sid, "name": name, "status": "NOT_EXERCISED", "checks": {},
            "timings_ms": {}, "fault_kind": kind, "limits": list(COMMON_LIMITS)}


class Observation:
    def __init__(self, record):
        self.record = record

    def check(self, name, condition):
        self.record["checks"][name] = bool(condition)
        if not condition:
            raise DrillFailure("CHECK_" + name.upper())

    def count(self, name, value):
        self.record["checks"][name] = int(value)

    def timing(self, name, started):
        self.record["timings_ms"][name] = elapsed_ms(started)

    def error(self, name, response, code):
        self.check(name + "_error_frame", response.get("event") == "error")
        payload = response.get("payload", {})
        self.check(name + "_code", payload.get("code") == code)
        self.check(name + "_no_private_details", not any(
            key in payload for key in ("auth_layer", "details", "request_id")))
        self.check(name + "_no_private_fixture_text", "fixture private" not in json.dumps(response))
        self.check(name + "_no_cursor", not any(
            key in payload for key in ("next_cursor", "start_cursor", "snapshot_boundary")))


def reserve_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def private_file(path, contents):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as target:
        target.write(contents)


def child_environment():
    # Do not inherit operator Redis/BB references, .env files or product secrets.
    allowed = ("PATH", "LD_LIBRARY_PATH", "LANG", "LC_ALL", "SYSTEMROOT")
    result = {key: os.environ[key] for key in allowed if key in os.environ}
    result.update({"PYTHONPATH": str(SOURCE), "PYTHONDONTWRITEBYTECODE": "1",
                   "PYTHONUNBUFFERED": "1"})
    return result


async def command_output(*command, environment=None):
    process = await asyncio.create_subprocess_exec(
        *command, env=environment, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL)
    try:
        async with asyncio.timeout(8):
            output, _ = await process.communicate()
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
    if process.returncode != 0 or len(output) > 65536:
        raise PrerequisiteFailure("PREREQUISITE_COMMAND_FAILED")
    return output


async def prerequisites(args, evidence):
    if sys.version_info < (3, 12):
        raise PrerequisiteFailure("RUNNER_PYTHON_REQUIRES_3_12")
    if not args.redis_server:
        raise PrerequisiteFailure("REDIS_SERVER_ARGUMENT_REQUIRED")
    redis_path = Path(args.redis_server).resolve()
    if not redis_path.is_file() or not os.access(redis_path, os.X_OK):
        raise PrerequisiteFailure("REDIS_SERVER_NOT_EXECUTABLE")
    selected_python = Path(args.python).resolve()
    if not selected_python.is_file() or not os.access(selected_python, os.X_OK):
        raise PrerequisiteFailure("PYTHON_NOT_EXECUTABLE")
    # Preserve executable spelling: Python venvs and Redis multicall binaries
    # select behavior from argv[0], even when validation resolves a symlink.
    args.python = str(Path(args.python).absolute())
    args.redis_server = str(Path(args.redis_server).absolute())
    required = [SOURCE / "hine_realtime/__main__.py",
                FIXTURES / "receipt_sync_support.py", FIXTURES / "test_realtime_boundaries.py"]
    if not all(path.is_file() for path in required):
        raise PrerequisiteFailure("SOURCE_OR_TEST_FIXTURE_MISSING")
    try:
        global aiohttp, web, Redis, RedisError, Retry, NoBackoff
        global AddonAuthority, error, frame, timestamp
        import aiohttp
        from aiohttp import web
        from redis.asyncio import Redis
        from redis.asyncio.retry import Retry
        from redis.backoff import NoBackoff
        from redis.exceptions import RedisError
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(FIXTURES))
        from receipt_sync_support import AddonAuthority
        from test_realtime_boundaries import error, frame, timestamp
    except ImportError:
        raise PrerequisiteFailure("RUNNER_DEPENDENCY_MISSING") from None
    selected = await command_output(
        args.python, "-c", "import sys,json,importlib.metadata as m; "
        "print(json.dumps({'python':list(sys.version_info[:3]),"
        "'aiohttp':m.version('aiohttp'),'redis':m.version('redis')}))",
        environment=child_environment())
    try:
        versions = json.loads(selected)
        if tuple(versions["python"]) < (3, 12):
            raise PrerequisiteFailure("BA_PYTHON_REQUIRES_3_12")
        # Versions are metadata, never arbitrary executable output.
        if not all(re.fullmatch(r"[A-Za-z0-9.+_-]{1,64}", versions[key])
                   for key in ("aiohttp", "redis")):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise PrerequisiteFailure("DEPENDENCY_VERSION_UNAVAILABLE") from None
    native_version = await command_output(args.redis_server, "--version", environment=child_environment())
    match = re.search(rb"Redis server v=([0-9]+\.[0-9]+\.[0-9]+)", native_version)
    if match is None:
        raise PrerequisiteFailure("REDIS_VERSION_UNAVAILABLE")
    head = (await command_output("git", "-C", str(ROOT), "rev-parse", "HEAD")).decode("ascii").strip()
    if re.fullmatch(r"[0-9a-f]{40,64}", head) is None:
        raise PrerequisiteFailure("GIT_HEAD_UNAVAILABLE")
    source_paths = sorted((SOURCE / "hine_realtime").glob("*.py"))
    source_paths += [FIXTURES / "receipt_sync_support.py", FIXTURES / "test_realtime_boundaries.py",
                     Path(__file__).resolve(), ROOT / "tests/faults/README.md",
                     ROOT / "backend/realtime/requirements.txt"]
    hashes = {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in source_paths}
    evidence["provenance"] = {"analysis_baseline": "f3588c9690653b963d34303152be064be31c28ff",
                              "git_head": head, "source_sha256": hashes}
    evidence["environment"] = {
        "os": platform.system(), "os_release": platform.release(), "architecture": platform.machine(),
        "runner_python": platform.python_version(), "runner_aiohttp": importlib.metadata.version("aiohttp"),
        "runner_redis_py": importlib.metadata.version("redis"),
        "ba_python": ".".join(str(part) for part in versions["python"]),
        "ba_aiohttp": versions["aiohttp"], "ba_redis_py": versions["redis"],
        "redis_server": match.group(1).decode("ascii"),
    }


class Peer:
    """Read actual client frames; retain private contents only in memory."""
    def __init__(self, ws):
        self.ws = ws
        self.frames = []
        self.changed = asyncio.Event()
        self.closed = asyncio.Event()
        self.read_error = False
        self.reader = asyncio.create_task(self.read())

    async def read(self):
        try:
            async for message in self.ws:
                if message.type == aiohttp.WSMsgType.TEXT:
                    value = json.loads(message.data)
                    if not isinstance(value, dict):
                        self.read_error = True
                        break
                    self.frames.append(value)
                    self.changed.set()
                elif message.type == aiohttp.WSMsgType.ERROR:
                    break
        except (aiohttp.ClientError, ConnectionError, ValueError):
            self.read_error = True
        finally:
            self.closed.set()
            self.changed.set()

    async def send(self, request):
        await self.ws.send_json(request)

    async def response(self, request, timeout=8):
        async with asyncio.timeout(timeout):
            while True:
                self.changed.clear()
                if self.read_error:
                    raise DrillFailure("INVALID_CLIENT_FRAME")
                for value in self.frames:
                    if value.get("correlation_id") == request["event_id"]:
                        return value
                if self.closed.is_set():
                    raise DrillFailure("CORRELATED_RESPONSE_NOT_OBSERVED")
                await self.changed.wait()

    async def request(self, name, payload, **extra):
        request = frame(name, payload, **extra)
        await self.send(request)
        return request, await self.response(request)

    async def wait_closed(self):
        async with asyncio.timeout(8):
            await self.closed.wait()

    def count(self, name, correlation=None):
        return sum(value.get("event") == name and
                   (correlation is None or value.get("correlation_id") == correlation)
                   for value in self.frames)

    def abort(self):
        connection = self.ws._response.connection
        if connection is None or connection.transport is None:
            raise DrillFailure("OWNED_CLIENT_TRANSPORT_UNAVAILABLE")
        connection.transport.abort()

    async def close(self):
        await self.ws.close()
        await self.wait_closed()
        await self.reader


class Link:
    """Owned HTTP forwarding listener; BB stays alive when the listener closes.

    The uncertainty fault drops a REAL confirmed BB response before any response
    bytes reach BA. The ACK-loss barrier holds that same real response until the
    client socket has disconnected. Neither fault invents a write result.
    """
    def __init__(self, authority_url, client):
        self.authority_url = authority_url
        self.client = client
        self.runner = None
        self.site = None
        self.port = None
        self.transports = set()
        self.online = False
        self.drop_write = False
        self.hold_write = False
        self.confirmed = asyncio.Event()
        self.release = asyncio.Event()
        self.dropped = 0
        self.held = 0
        self.forwarded_held = asyncio.Event()
        self.forwarded_held_count = 0

    async def forward(self, request):
        transport = request.transport
        if transport is not None:
            self.transports.add(transport)
        operation = request.match_info["operation"]
        try:
            held_response = False
            async with self.client.post(
                self.authority_url + "/internal/v1/" + operation,
                data=await request.read(), headers={"Content-Type": "application/json",
                    "Authorization": request.headers.get("Authorization", "")}, allow_redirects=False,
            ) as response:
                contents = await response.read()
                status = response.status
            if operation == "persistIfAbsent" and status == 200:
                if self.drop_write:
                    self.drop_write = False
                    self.dropped += 1
                    self.confirmed.set()
                    if transport is not None:
                        transport.abort()
                    return web.Response(status=502)
                if self.hold_write:
                    self.hold_write = False
                    self.held += 1
                    held_response = True
                    self.confirmed.set()
                    await self.release.wait()
            reply = web.Response(body=contents, status=status, content_type="application/json")
            if held_response:
                await reply.prepare(request)
                await reply.write_eof()
                self.forwarded_held_count += 1
                self.forwarded_held.set()
            return reply
        except (aiohttp.ClientError, ConnectionError, TimeoutError):
            return web.Response(status=503)

    async def start(self):
        if self.runner is None:
            app = web.Application()
            app.router.add_post("/internal/v1/{operation}", self.forward)
            self.runner = web.AppRunner(app, access_log=None, shutdown_timeout=1)
            await self.runner.setup()
        self.site = web.TCPSite(self.runner, "127.0.0.1", self.port or 0)
        await self.site.start()
        if self.port is None:
            self.port = self.runner.addresses[0][1]
        self.online = True

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}"

    async def stop(self):
        self.online = False
        if self.site is not None:
            await self.site.stop()
            self.site = None
        # BA uses keepalive HTTP. Closing just the listening socket would not
        # exercise an outage for already-open forwarding connections.
        for transport in self.transports:
            transport.abort()
        self.transports.clear()

    async def close(self):
        self.release.set()
        await self.stop()
        if self.runner is not None:
            await self.runner.cleanup()


class Components:
    def __init__(self, args):
        self.args = args
        self.temp = None
        self.client = None
        self.authority_runner = None
        self.link = None
        self.redis = None
        self.redis_process = None
        self.ba_process = None
        self.children = []
        self.logs = []
        self.peers = []
        self.ba_starts = 0
        self.redis_starts = 0
        self.inbound_token = uuid4().hex
        self.prefix = "hine:ba-fault:" + uuid4().hex

    async def __aenter__(self):
        try:
            await self.start()
            return self
        except BaseException:
            await self.close()
            raise

    async def __aexit__(self, *unused):
        await self.close()

    async def spawn(self, label, *command, environment=None):
        log_path = self.directory / (label + "-" + uuid4().hex + ".log")
        fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        log = os.fdopen(fd, "wb")
        self.logs.append(log)
        child = await asyncio.create_subprocess_exec(
            *command, cwd=ROOT, env=environment or child_environment(),
            stdin=asyncio.subprocess.DEVNULL, stdout=log, stderr=log)
        self.children.append(child)
        return child

    async def stop_child(self, child, kill=False):
        if child is None or child.returncode is not None:
            return
        try:
            child.send_signal(signal.SIGKILL if kill else signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            async with asyncio.timeout(4):
                await child.wait()
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                child.kill()
            await child.wait()

    async def start(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hine-ba-drill-")
        self.directory = Path(self.temp.name)
        os.chmod(self.directory, 0o700)
        self.redis_port = reserve_port()
        self.ba_port = reserve_port()
        while self.ba_port == self.redis_port:
            self.ba_port = reserve_port()
        self.url = f"http://127.0.0.1:{self.ba_port}"
        self.client = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=8), trust_env=False, auto_decompress=False)
        # Only this test subclass changes fixture expiration/service responses.
        # No fixture or runtime file is edited by the drill.
        expiry = timestamp(600)

        class DrillAuthority(AddonAuthority):
            def __init__(self):
                super().__init__()
                self.reject_service = False
                self.reject_session = None
                self.service_failures = 0
                self.user_failures = 0
                self.mutate_result = lambda operation, result: (
                    {**result, "expires_at": expiry} if operation == "validateAccess" else result)

            async def handle(self, request):
                operation = request.match_info["operation"]
                if self.reject_service:
                    self.service_failures += 1
                    return web.json_response(error("UNAUTHENTICATED", "service_identity"), status=401)
                if operation == "persistIfAbsent" and self.reject_session is not None:
                    body = await request.json()
                    if body.get("session_id") == self.reject_session:
                        self.user_failures += 1
                        return web.json_response(error("UNAUTHENTICATED", "user_session"), status=401)
                return await super().handle(request)

        self.authority = DrillAuthority()
        authority_app = self.authority.app()

        async def fixture_health(request):
            return web.Response(status=204)

        authority_app.router.add_get("/drill/health", fixture_health)
        self.authority_runner = web.AppRunner(authority_app, access_log=None, shutdown_timeout=1)
        await self.authority_runner.setup()
        authority_site = web.TCPSite(self.authority_runner, "127.0.0.1", 0)
        await authority_site.start()
        self.authority_url = f"http://127.0.0.1:{self.authority_runner.addresses[0][1]}"
        self.link = Link(self.authority_url, self.client)
        await self.link.start()
        private_file(self.directory / "outbound", "realtime-service-secret")
        private_file(self.directory / "inbound", self.inbound_token)
        redis_password = uuid4().hex
        redis_socket = self.directory / "redis.sock"
        private_file(self.directory / "redis-url",
                     f"redis://:{redis_password}@127.0.0.1:{self.redis_port}/0")
        private_file(self.directory / "redis.conf",
                     f"bind 127.0.0.1\nport {self.redis_port}\nprotected-mode yes\n"
                     f"requirepass {redis_password}\nunixsocket {redis_socket}\nunixsocketperm 700\n"
                     f"dir {self.directory}\nsave \"\"\nappendonly no\ndaemonize no\nloglevel warning\n")
        self.env = child_environment()
        self.env.update({
            "HINE_ENV": "test", "REALTIME_HOST": "127.0.0.1", "REALTIME_PORT": str(self.ba_port),
            "API_INTERNAL_URL": self.link.url,
            "INTERNAL_CALLER_TOKEN_SECRET_REF": str(self.directory / "outbound"),
            "INTERNAL_ALLOWED_CALLERS": json.dumps({"api": str(self.directory / "inbound")}),
            "REDIS_URL_SECRET_REF": str(self.directory / "redis-url"), "REALTIME_REDIS_PREFIX": self.prefix,
            "INVALIDATION_POLL_SECONDS": str(POLL_SECONDS),
            "INVALIDATION_STALE_SECONDS": str(STALE_SECONDS), "NOTICE_CATCHUP_HOLD_MS": "1000",
            "HEARTBEAT_INTERVAL_SECONDS": "30", "HEARTBEAT_TIMEOUT_SECONDS": "90", "SYNC_PAGE_LIMIT": "100",
        })
        # A private Unix socket cannot attach to an operator Redis even if the
        # ephemeral TCP port was claimed between reservation and child startup.
        self.redis = Redis(unix_socket_path=str(redis_socket), password=redis_password,
                           decode_responses=True, socket_connect_timeout=1, socket_timeout=1,
                           retry=Retry(NoBackoff(), 0))
        await self.start_redis()
        await self.start_ba()

    async def start_redis(self):
        self.redis_process = await self.spawn(
            "redis", self.args.redis_server, str(self.directory / "redis.conf"))
        self.redis_starts += 1
        async with asyncio.timeout(15):
            while True:
                if self.redis_process.returncode is not None:
                    raise DrillFailure("OWNED_REDIS_EXITED_BEFORE_READY")
                try:
                    if await self.redis.ping():
                        info = await self.redis.info("server")
                        if int(info["process_id"]) != self.redis_process.pid:
                            raise DrillFailure("REDIS_OWNERSHIP_MISMATCH")
                        break
                except (RedisError, OSError, TimeoutError):
                    pass
                await asyncio.sleep(0.1)

    async def start_ba(self):
        self.ba_process = await self.spawn(
            "ba", self.args.python, "-m", "hine_realtime", environment=self.env)
        self.ba_starts += 1
        await self.wait_ready()

    def ba_owns_listener(self):
        process = Path("/proc") / str(self.ba_process.pid)
        try:
            sockets = set()
            for descriptor in (process / "fd").iterdir():
                with contextlib.suppress(OSError):
                    target = os.readlink(descriptor)
                    if target.startswith("socket:[") and target.endswith("]"):
                        sockets.add(target[8:-1])
            address = f"0100007F:{self.ba_port:04X}"
            for row in (process / "net/tcp").read_text().splitlines()[1:]:
                columns = row.split()
                if (len(columns) > 9 and columns[1] == address
                        and columns[3] == "0A" and columns[9] in sockets):
                    return True
        except OSError:
            return False
        return False

    async def readiness(self):
        if self.ba_process.returncode is not None or not self.ba_owns_listener():
            raise DrillFailure("OWNED_BA_LISTENER_NOT_PROVEN")
        async with self.client.get(self.url + "/health/ready") as response:
            return response.status

    async def wait_ready(self):
        async with asyncio.timeout(20):
            while True:
                if self.ba_process.returncode is not None:
                    raise DrillFailure("OWNED_BA_EXITED_BEFORE_READY")
                try:
                    if self.ba_owns_listener() and await self.readiness() == 200:
                        return
                except (aiohttp.ClientError, OSError, TimeoutError):
                    pass
                await asyncio.sleep(0.1)

    async def authority_alive(self):
        async with self.client.get(self.authority_url + "/drill/health") as response:
            return response.status

    async def listener_refuses_connection(self):
        try:
            async with asyncio.timeout(2):
                _, writer = await asyncio.open_connection("127.0.0.1", self.link.port)
        except ConnectionRefusedError:
            return True
        writer.close()
        await writer.wait_closed()
        return False

    async def auth(self, token="access-a"):
        ws = await self.client.ws_connect(self.url + "/ws/v1", timeout=aiohttp.ClientWSTimeout(ws_close=2))
        peer = Peer(ws)
        self.peers.append(peer)
        request, response = await peer.request("auth.authenticate", {
            "access_token": token, "device_id": token.replace("access", "device")})
        return peer, request, response

    async def authenticated(self, obs, label, token="access-a"):
        peer, _, response = await self.auth(token)
        obs.check(label + "_w02", response.get("event") == "auth.accepted")
        obs.count(label + "_w02_count", peer.count("auth.accepted"))
        return peer

    async def heartbeat(self, obs, peer, label):
        nonce = uuid4().hex
        _, reply = await peer.request("heartbeat.ping", {"nonce": nonce})
        obs.check(label + "_pong", reply.get("event") == "heartbeat.pong")
        obs.check(label + "_nonce", reply.get("payload", {}).get("nonce") == nonce)

    async def bootstrap(self, obs, peer, label):
        _, reply = await peer.request("sync.bootstrap.request", {"reason": "first_login"})
        obs.check(label + "_bootstrap_page", reply.get("event") == "sync.bootstrap.page")
        cursor = reply.get("payload", {}).get("start_cursor")
        obs.check(label + "_saved_cursor", isinstance(cursor, str) and bool(cursor))
        return cursor

    def intent(self):
        return frame("message.send", {"client_message_id": str(uuid4()), "type": "text",
                                      "text": "Synthetic local drill message"}, conversation_id="direct-1")

    async def ack(self, obs, peer, intent, label):
        # Retries keep the original C1/payload; only the envelope event ID changes.
        request = frame("message.send", dict(intent["payload"]), conversation_id=intent["conversation_id"])
        await peer.send(request)
        reply = await peer.response(request)
        obs.check(label + "_w06", reply.get("event") == "message.ack")
        payload = reply.get("payload", {})
        obs.check(label + "_original_c1", payload.get("client_message_id") == intent["payload"]["client_message_id"])
        obs.check(label + "_persisted", payload.get("status") == "persisted")
        obs.count(label + "_ack_count", peer.count("message.ack", request["event_id"]))
        return payload.get("message_id")

    async def recovery(self, obs, peer, cursor, mid, label, sender=False):
        _, reply = await peer.request("sync.request", {"cursor": cursor})
        obs.check(label + "_sync_batch", reply.get("event") == "sync.batch")
        payload = reply.get("payload", {})
        events = payload.get("events", [])
        matching = [event for event in events if event.get("event") == "message.created"
                    and event.get("payload", {}).get("message_id") == mid]
        obs.count(label + "_recovered_message_count", len(matching))
        obs.check(label + "_exactly_one_recovered_message", len(matching) == 1)
        key, saved = self.authority.locate(mid)
        event = matching[0]
        obs.check(label + "_stable_event_id", event.get("event_id") == saved["event_id"])
        if sender:
            obs.check(label + "_sender_original_c1", event["payload"].get("client_message_id") == key[1])
        else:
            obs.check(label + "_receiver_no_c1", "client_message_id" not in event["payload"])
        obs.check(label + "_cursor_progress", isinstance(payload.get("next_cursor"), str)
                  and payload["next_cursor"] != cursor)
        return payload["next_cursor"]

    async def presence(self, token=None):
        async with self.client.post(self.url + "/internal/v1/getDevicePresence",
            json={"subject_id": "private-a", "device_id": "device-a"},
            headers={"Authorization": "Bearer " + (self.inbound_token if token is None else token)}) as response:
            return response.status, await response.json()

    async def close(self):
        # A scenario timeout can arrive during __aexit__, not just its body.
        # Shield the entire cleanup and finish it before propagating cancellation.
        cleanup = asyncio.create_task(self.cleanup_owned())
        interrupted = False
        while not cleanup.done():
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                interrupted = True
        await cleanup
        if interrupted:
            raise asyncio.CancelledError

    async def cleanup_owned(self):
        failed = False
        if self.link is not None:
            self.link.release.set()
        for child in reversed(self.children):
            result, = await asyncio.gather(self.stop_child(child), return_exceptions=True)
            failed |= isinstance(result, BaseException)
        for peer in self.peers:
            result, = await asyncio.gather(peer.close(), return_exceptions=True)
            failed |= isinstance(result, BaseException)
        resources = [(self.redis, "aclose"), (self.link, "close"),
                     (self.authority_runner, "cleanup"), (self.client, "close")]
        for resource, method in resources:
            if resource is not None:
                result, = await asyncio.gather(getattr(resource, method)(), return_exceptions=True)
                failed |= isinstance(result, BaseException)
        for log in self.logs:
            log.close()
        if self.temp is not None:
            self.temp.cleanup()
        if failed:
            raise DrillFailure("OWNED_RESOURCE_CLEANUP_FAILED")


async def dr01(c, o):
    sender = await c.authenticated(o, "initial_sender")
    receiver = await c.authenticated(o, "initial_receiver", "access-b")
    sender_cursor = await c.bootstrap(o, sender, "sender")
    receiver_cursor = await c.bootstrap(o, receiver, "receiver")
    await receiver.close()
    intent = c.intent()
    mid = await c.ack(o, sender, intent, "prekill_commit")
    o.count("test_authority_writes_before_kill", len(c.authority.messages))
    o.check("one_test_memory_commit_before_kill", len(c.authority.messages) == 1)
    old = c.ba_process
    started = time.monotonic()
    await c.stop_child(old, kill=True)
    o.check("actual_sigkill_exit", old.returncode == -signal.SIGKILL)
    await sender.wait_closed()
    o.check("old_ws_closed", sender.closed.is_set())
    o.check("continuous_authority_http_alive", await c.authority_alive() == 204)
    restart_started = time.monotonic()
    await c.start_ba()
    o.timing("restart_to_ready", restart_started)
    o.timing("kill_to_ready", started)
    o.check("new_owned_ba_process", c.ba_process.pid != old.pid)
    o.count("actual_ba_starts", c.ba_starts)
    sync_started = time.monotonic()
    sender = await c.authenticated(o, "restarted_sender")
    receiver = await c.authenticated(o, "restarted_receiver", "access-b")
    await c.recovery(o, sender, sender_cursor, mid, "sender_recovery", sender=True)
    await c.recovery(o, receiver, receiver_cursor, mid, "receiver_recovery")
    o.timing("ready_to_authenticated_client_sync", sync_started)
    retried = await c.ack(o, sender, intent, "same_c1_retry")
    o.check("retry_original_m1", retried == mid)
    o.count("test_authority_writes_after_retry", len(c.authority.messages))
    o.check("retry_no_second_test_memory_write", len(c.authority.messages) == 1)


async def dr02(c, o):
    o.record["limits"].append("REDIS_RESTART_HAS_NO_RDB_AOF_MESSAGE_PERSISTENCE")
    sender = await c.authenticated(o, "sender")
    receiver = await c.authenticated(o, "receiver", "access-b")
    cursor = await c.bootstrap(o, receiver, "receiver")
    marker = c.prefix + ":drill-reset-marker"
    await c.redis.set(marker, "ephemeral")
    o.check("marker_observed_before_stop", await c.redis.get(marker) == "ephemeral")
    status, body = await c.presence()
    o.count("presence_before_http_status", status)
    o.check("presence_before_online", body.get("data", {}).get("online") == "online")
    old = c.redis_process
    stopped = time.monotonic()
    await c.stop_child(old)
    o.check("actual_owned_redis_stopped", old.returncode is not None)
    status = await c.readiness()
    o.count("outage_ready_http_status", status)
    o.check("outage_ready_503", status == 503)
    status, body = await c.presence()
    o.count("outage_presence_http_status", status)
    o.check("outage_presence_200", status == 200)
    o.check("outage_presence_unknown", body.get("data", {}).get("online") == "unknown")
    intent = c.intent()
    mid = await c.ack(o, sender, intent, "redis_down_confirmed_write")
    await asyncio.sleep(0.25)
    o.count("receiver_outage_live_message_count", receiver.count("message.created"))
    o.check("receiver_no_live_message_during_outage", receiver.count("message.created") == 0)
    o.check("continuous_authority_http_alive", await c.authority_alive() == 204)
    restart_started = time.monotonic()
    await c.start_redis()
    o.check("actual_new_redis_process", c.redis_process.pid != old.pid)
    o.check("ephemeral_marker_lost", await c.redis.get(marker) is None)
    await c.wait_ready()
    o.timing("redis_restart_to_ready", restart_started)
    o.timing("redis_stop_to_ready", stopped)
    status = await c.readiness()
    o.count("restored_ready_http_status", status)
    o.check("restored_ready_200", status == 200)
    subscriptions = await c.redis.pubsub_numsub(c.prefix + ":notices")
    subscription_count = sum(int(row[1]) for row in subscriptions)
    o.count("restored_native_subscription_count", subscription_count)
    o.check("restored_native_subscription", subscription_count >= 1)
    status, body = await c.presence()
    o.count("restored_presence_http_status", status)
    o.check("restored_presence_online", body.get("data", {}).get("online") == "online")
    sync_started = time.monotonic()
    await c.recovery(o, receiver, cursor, mid, "missed_message_recovery")
    o.timing("ready_to_client_sync", sync_started)
    retried = await c.ack(o, sender, intent, "same_c1_retry")
    o.check("retry_original_m1", retried == mid)
    o.count("test_authority_writes_after_retry", len(c.authority.messages))
    o.check("retry_no_second_test_memory_write", len(c.authority.messages) == 1)
    o.count("actual_redis_starts", c.redis_starts)


async def dr03(c, o):
    o.record["limits"].append("FRESHNESS_WINDOW_LOOPBACK_NOT_PRODUCTION_TRANSACTION_BOUND")
    sender = await c.authenticated(o, "sender")
    receiver = await c.authenticated(o, "receiver", "access-b")
    cursor = await c.bootstrap(o, receiver, "receiver")
    await c.link.stop()
    outage = time.monotonic()
    o.check("actual_forwarding_listener_refused", await c.listener_refuses_connection())
    o.check("continuous_authority_http_alive", await c.authority_alive() == 204)
    candidate, _, reply = await c.auth("access-a2")
    o.error("new_admission_outage", reply, "DEPENDENCY_UNAVAILABLE")
    await candidate.wait_closed()
    o.count("outage_new_w02_count", candidate.count("auth.accepted"))
    o.check("outage_no_new_w02", candidate.count("auth.accepted") == 0)
    intent = c.intent()
    await sender.send(intent)
    reply = await sender.response(intent)
    o.error("existing_write_outage", reply, "DEPENDENCY_UNAVAILABLE")
    o.count("outage_write_ack_count", sender.count("message.ack", intent["event_id"]))
    o.check("outage_no_fake_ack", sender.count("message.ack", intent["event_id"]) == 0)
    # No readiness polling during the outage. Wait a real standard stale window
    # measured from closure (any last successful catchup began before closure).
    await asyncio.sleep(max(0, OUTAGE_SECONDS - (time.monotonic() - outage)))
    o.timing("listener_closed_to_stale_probe", outage)
    await c.heartbeat(o, sender, "stale_session_heartbeat")
    _, reply = await receiver.request("sync.request", {"cursor": cursor})
    o.error("stale_sync", reply, "DEPENDENCY_UNAVAILABLE")
    stale_write = c.intent()
    await sender.send(stale_write)
    o.error("stale_write", await sender.response(stale_write), "DEPENDENCY_UNAVAILABLE")
    o.count("test_authority_writes_during_outage", len(c.authority.messages))
    o.check("outage_no_test_memory_commit", len(c.authority.messages) == 0)
    o.check("authority_still_alive_after_stale_window", await c.authority_alive() == 204)
    restored = time.monotonic()
    await c.link.start()
    await c.wait_ready()
    o.timing("link_restore_to_full_catchup_ready", restored)
    await c.heartbeat(o, sender, "same_sender_session_resumed")
    await c.heartbeat(o, receiver, "same_receiver_session_resumed")
    mid = await c.ack(o, sender, intent, "restored_original_intent")
    await c.recovery(o, receiver, cursor, mid, "saved_cursor_after_link_restore")
    o.check("same_valid_sessions_remained_open", not sender.closed.is_set() and not receiver.closed.is_set())


async def dr04(c, o):
    o.record["limits"].append("LOST_NOTIFICATION_GENERATED_BY_TEST_AUTHORITY_NOT_PRODUCT_LOGOUT")
    old = await c.authenticated(o, "revoked_binding")
    other = await c.authenticated(o, "other_device", "access-a2")
    receiver = await c.authenticated(o, "receiver", "access-b")
    cursor = await c.bootstrap(o, old, "old_binding")
    await c.link.stop()
    o.check("actual_forwarding_listener_refused", await c.listener_refuses_connection())
    committed = time.monotonic()
    entry = c.authority.invalidate("session-a")
    o.check("test_logout_entry_committed", c.authority.head == 1 and entry["position"] == 1)
    o.count("test_logout_invalidation_entries", c.authority.head)
    # Intentionally do not call publishCommitted: this is a lost notification.
    await asyncio.sleep(OUTAGE_SECONDS)
    o.timing("test_logout_commit_to_stale_probe", committed)
    await c.heartbeat(o, old, "stale_control_heartbeat")
    request = c.intent()
    await old.send(request)
    o.error("stale_old_binding_write", await old.response(request), "DEPENDENCY_UNAVAILABLE")
    _, reply = await old.request("sync.request", {"cursor": cursor})
    o.error("stale_old_binding_sync", reply, "DEPENDENCY_UNAVAILABLE")
    o.check("no_old_binding_test_memory_write", len(c.authority.messages) == 0)
    await c.heartbeat(o, other, "other_device_during_outage")
    o.check("continuous_authority_http_alive", await c.authority_alive() == 204)
    restored = time.monotonic()
    await c.link.start()
    await c.wait_ready()
    await old.wait_closed()
    o.timing("link_restore_to_revoked_binding_closed", restored)
    o.timing("test_logout_commit_to_revoked_binding_closed", committed)
    o.check("only_revoked_binding_closed", old.closed.is_set() and not other.closed.is_set() and not receiver.closed.is_set())
    o.check("revocation_error_observed", any(value.get("event") == "error" and
        value.get("payload", {}).get("code") == "UNAUTHENTICATED" for value in old.frames))
    o.count("old_binding_ack_count", old.count("message.ack"))
    o.check("old_binding_never_acked", old.count("message.ack") == 0)
    await c.heartbeat(o, other, "other_device_after_catchup")
    mid = await c.ack(o, other, c.intent(), "other_device_functional_write")
    o.check("other_device_real_message_committed", c.authority.locate(mid) is not None)


async def dr05(c, o):
    o.record["limits"].append("SERVICE_AND_USER_401_RESPONSES_ARE_TEST_HTTP_FAULT_INJECTION")
    sender = await c.authenticated(o, "sender")
    other = await c.authenticated(o, "other_device", "access-a2")
    # Actual incoming C13 service boundary, distinct from user authentication.
    for label, token in (("wrong_inbound_service", uuid4().hex),
                         ("outbound_token_as_inbound", "realtime-service-secret")):
        status, body = await c.presence(token)
        o.count(label + "_http_status", status)
        o.check(label + "_401", status == 401)
        o.check(label + "_service_identity", body.get("error", {}).get("details", {}).get("auth_layer") == "service_identity")
    status, _ = await c.presence()
    o.count("valid_inbound_service_http_status", status)
    o.check("valid_inbound_service_200", status == 200)
    c.authority.reject_service = True
    intent = c.intent()
    await sender.send(intent)
    o.error("outbound_service_failure", await sender.response(intent), "DEPENDENCY_UNAVAILABLE")
    o.check("service_failure_no_fake_ack", sender.count("message.ack", intent["event_id"]) == 0)
    await c.heartbeat(o, sender, "service_failure_session_kept")
    candidate, _, reply = await c.auth("access-b")
    o.error("service_failure_new_auth", reply, "DEPENDENCY_UNAVAILABLE")
    await candidate.wait_closed()
    o.count("service_failure_new_w02_count", candidate.count("auth.accepted"))
    o.check("service_failure_no_new_w02", candidate.count("auth.accepted") == 0)
    o.count("actual_service_401_response_count", c.authority.service_failures)
    o.check("actual_service_401_observed", c.authority.service_failures >= 2)
    o.check("service_failure_no_test_memory_commit", len(c.authority.messages) == 0)
    o.check("continuous_authority_http_alive", await c.authority_alive() == 204)
    c.authority.reject_service = False
    await c.wait_ready()
    await c.heartbeat(o, sender, "service_restored_same_session")
    c.authority.reject_session = "session-a"
    user_intent = c.intent()
    await sender.send(user_intent)
    o.error("explicit_user_session_failure", await sender.response(user_intent), "UNAUTHENTICATED")
    await sender.wait_closed()
    o.count("actual_user_session_401_response_count", c.authority.user_failures)
    o.check("explicit_user_session_401_observed", c.authority.user_failures == 1)
    o.check("explicit_user_failure_only_binding_closed", sender.closed.is_set() and not other.closed.is_set())
    c.authority.reject_session = None
    await c.heartbeat(o, other, "other_device_after_user_failure")
    mid = await c.ack(o, other, c.intent(), "other_device_still_functional")
    o.check("other_device_real_message_committed", c.authority.locate(mid) is not None)


async def dr06(c, o):
    o.record["limits"].extend([
        "UNCERTAIN_RESPONSE_DROPPED_AFTER_TEST_MEMORY_COMMIT_NOT_POSTGRESQL_COMMIT",
        "ACK_LOSS_CLIENT_DISCONNECT_AFTER_COMMIT_BEFORE_W06",
        "KNOWN_ROLLBACK_IS_STRUCTURED_TEST_HTTP_ERROR_INJECTION",
    ])
    sender = await c.authenticated(o, "sender")
    receiver = await c.authenticated(o, "receiver", "access-b")
    sender_cursor = await c.bootstrap(o, sender, "sender")
    receiver_cursor = await c.bootstrap(o, receiver, "receiver")
    uncertain = c.intent()
    c.link.drop_write = True
    c.link.confirmed.clear()
    await sender.send(uncertain)
    reply = await sender.response(uncertain)
    o.error("write_result_unknown", reply, "OUTCOME_UNCONFIRMED")
    o.check("actual_confirmed_response_dropped", c.link.confirmed.is_set() and c.link.dropped == 1)
    o.count("actual_dropped_confirmed_response_count", c.link.dropped)
    o.count("uncertain_original_ack_count", sender.count("message.ack", uncertain["event_id"]))
    o.check("uncertain_no_false_ack", sender.count("message.ack", uncertain["event_id"]) == 0)
    o.count("writes_after_uncertain_result", len(c.authority.messages))
    o.check("uncertain_one_actual_test_memory_commit", len(c.authority.messages) == 1)
    mid = c.authority.messages[("private-a", uncertain["payload"]["client_message_id"])]["message_id"]
    sender_cursor = await c.recovery(o, sender, sender_cursor, mid, "uncertain_sender_sync", sender=True)
    receiver_cursor = await c.recovery(o, receiver, receiver_cursor, mid, "uncertain_receiver_sync")
    retried = await c.ack(o, sender, uncertain, "uncertain_original_c1_retry")
    o.check("uncertain_retry_original_m1", retried == mid)
    o.check("uncertain_retry_no_second_test_memory_write", len(c.authority.messages) == 1)
    o.count("uncertain_stable_feed_event_count", sum(
        row["envelope"]["event_id"] == c.authority.locate(mid)[1]["event_id"] for row in c.authority.feed))
    o.check("uncertain_one_stable_feed_event", len(c.authority.feed) == 1)
    # A different committed intent loses its CLIENT acknowledgement. The proxy
    # confirms a real BB 200, then waits while the actual client WS disconnects.
    acklost = c.intent()
    c.link.confirmed.clear()
    c.link.release.clear()
    c.link.hold_write = True
    await sender.send(acklost)
    async with asyncio.timeout(5):
        await c.link.confirmed.wait()
    o.check("ackloss_real_confirmed_response_held", c.link.held == 1)
    o.count("actual_held_confirmed_response_count", c.link.held)
    o.check("ackloss_second_intent_committed", len(c.authority.messages) == 2)
    acklost_mid = c.authority.messages[("private-a", acklost["payload"]["client_message_id"])]["message_id"]
    sync_started = time.monotonic()
    sender.abort()
    await sender.wait_closed()
    c.link.release.set()
    async with asyncio.timeout(5):
        await c.link.forwarded_held.wait()
    o.count("ackloss_confirmed_response_forwarded_count", c.link.forwarded_held_count)
    o.check("ackloss_confirmed_response_successfully_forwarded", c.link.forwarded_held_count == 1)
    o.check("ackloss_actual_client_ws_closed", sender.closed.is_set())
    o.count("lost_client_w06_count", sender.count("message.ack", acklost["event_id"]))
    o.check("lost_client_never_received_w06", sender.count("message.ack", acklost["event_id"]) == 0)
    sender = await c.authenticated(o, "ackloss_reconnected_sender")
    await c.recovery(o, sender, sender_cursor, acklost_mid, "ackloss_sender_sync", sender=True)
    await c.recovery(o, receiver, receiver_cursor, acklost_mid, "ackloss_receiver_sync")
    retried = await c.ack(o, sender, acklost, "ackloss_original_c1_retry")
    o.check("ackloss_retry_original_m1", retried == acklost_mid)
    o.count("total_test_memory_writes_after_both_retries", len(c.authority.messages))
    o.check("both_retries_no_duplicate_test_memory_write", len(c.authority.messages) == 2)
    o.check("two_distinct_committed_intents", mid != acklost_mid)
    o.timing("ackloss_disconnect_to_sync_and_original_c1_recovery", sync_started)
    # A known rejection is not the same as an uncertain transport outcome.
    c.authority.faults["persistIfAbsent"] = (503, error("PERSISTENCE_FAILED", retryable=True))
    rollback = c.intent()
    await sender.send(rollback)
    o.error("known_rollback", await sender.response(rollback), "PERSISTENCE_FAILED")
    o.check("known_rollback_no_ack", sender.count("message.ack", rollback["event_id"]) == 0)
    o.check("known_rollback_no_test_memory_write", len(c.authority.messages) == 2)
    o.check("continuous_authority_http_alive", await c.authority_alive() == 204)
    del c.authority.faults["persistIfAbsent"]


async def execute(args, evidence):
    await prerequisites(args, evidence)
    functions = (dr01, dr02, dr03, dr04, dr05, dr06)
    for record, scenario in zip(evidence["scenarios"], functions):
        record["status"] = "RUNNING"
        started = time.monotonic()
        try:
            async with asyncio.timeout(75):
                async with Components(args) as components:
                    await scenario(components, Observation(record))
            record["status"] = "PASS"
        except asyncio.CancelledError:
            record["status"] = "FAIL"
            record["failure_code"] = "RUN_INTERRUPTED"
            raise
        except DrillFailure as failure:
            record["status"] = "FAIL"
            record["failure_code"] = str(failure)
            return 1
        except TimeoutError:
            record["status"] = "FAIL"
            record["failure_code"] = "OBSERVATION_OR_CLEANUP_TIMEOUT"
            return 1
        except Exception:
            record["status"] = "FAIL"
            record["failure_code"] = "COMPONENT_OR_RUNNER_ERROR"
            raise
        finally:
            record["timings_ms"]["scenario_including_setup_and_cleanup"] = elapsed_ms(started)
    return 0


async def interruptible_execute(args, evidence):
    loop = asyncio.get_running_loop()
    task = asyncio.current_task()
    interrupted = False

    def interrupt():
        nonlocal interrupted
        # Repeated SIGINT must not cancel the finally-cleanup a second time.
        if not interrupted:
            interrupted = True
            task.cancel()

    loop.add_signal_handler(signal.SIGINT, interrupt)
    try:
        # Capture unexpected failures without exposing private exception text.
        result, = await asyncio.gather(execute(args, evidence), return_exceptions=True)
        return result
    finally:
        loop.remove_signal_handler(signal.SIGINT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    # Validate semantically so a supplied --output also gets truthful NOT_EXERCISED
    # evidence when the required executable argument is missing.
    parser.add_argument("--redis-server", help="Required native Redis executable; never an existing service")
    parser.add_argument("--output", help="Required NEW evidence file; existing paths are never overwritten")
    parser.add_argument("--python", default=sys.executable, help="Python >=3.12 used for the native BA child")
    args = parser.parse_args()
    if not args.output:
        print("OUTPUT_ARGUMENT_REQUIRED", file=sys.stderr)
        return 2
    if os.path.lexists(args.output):
        print("OUTPUT_ALREADY_EXISTS", file=sys.stderr)
        return 2
    try:
        fd, temporary_path = tempfile.mkstemp(
            dir=Path(args.output).absolute().parent, prefix=".hine-ba-evidence-")
    except OSError:
        print("OUTPUT_CANNOT_BE_CREATED", file=sys.stderr)
        return 2
    evidence = {
        "schema_version": 1, "run_id": str(uuid4()), "started_utc": utc_now(), "completed_utc": None,
        "scope": "LOCAL_COMPONENT_WITH_TEST_BB", "status": "NOT_EXERCISED",
        "configuration": {"invalidation_poll_seconds": POLL_SECONDS,
                          "invalidation_stale_seconds": STALE_SECONDS, "notice_catchup_hold_ms": 1000,
                          "heartbeat_interval_seconds": 30, "heartbeat_timeout_seconds": 90,
                          "sync_page_limit": 100, "redis_persistence_enabled": False},
        "provenance": {}, "environment": {}, "limits": list(COMMON_LIMITS),
        "unmeasured": ["REAL_BB_POSTGRESQL_JWT", "VM_DISK_OR_HOST_FAILURE", "BROWSER_INDEXEDDB_C1",
                       "MULTI_INSTANCE_HA", "50_WSS_LOAD", "EMPIRICAL_OCCURRENCE_RPN_RTO_RPO_SLO"],
        "scenarios": [record_for(*scenario) for scenario in SCENARIOS],
    }
    # Prevent aiohttp/framework exception diagnostics from exposing private
    # request bodies. Child diagnostics are private files, removed at cleanup.
    logging.disable(logging.CRITICAL)
    code = 1
    try:
        result = asyncio.run(interruptible_execute(args, evidence))
        if isinstance(result, PrerequisiteFailure):
            evidence["failure_code"] = str(result)
            code = 2
        elif isinstance(result, BaseException):
            evidence["failure_code"] = "PREREQUISITE_OR_RUNNER_ERROR"
            code = 2 if all(row["status"] == "NOT_EXERCISED" for row in evidence["scenarios"]) else 1
        else:
            code = result
    except (KeyboardInterrupt, asyncio.CancelledError):
        evidence["failure_code"] = "RUN_INTERRUPTED"
        code = 1
    except (OSError, RuntimeError):
        evidence["failure_code"] = "PREREQUISITE_OR_RUNNER_ERROR"
        code = 2 if all(row["status"] == "NOT_EXERCISED" for row in evidence["scenarios"]) else 1
    finally:
        evidence["completed_utc"] = utc_now()
        evidence["status"] = "PASS" if code == 0 else ("NOT_EXERCISED" if code == 2 else "FAIL")
        evidence["exit_code"] = code
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as target:
                json.dump(evidence, target, ensure_ascii=True, indent=2, sort_keys=True)
                target.write("\n")
                target.flush()
                os.fsync(target.fileno())
            # Same-filesystem hard link publishes complete JSON atomically,
            # failing rather than replacing a destination created during the run.
            os.link(temporary_path, args.output)
        except FileExistsError:
            print("OUTPUT_ALREADY_EXISTS", file=sys.stderr)
            code = 2
        except OSError:
            print("OUTPUT_CANNOT_BE_PUBLISHED", file=sys.stderr)
            code = 2
        finally:
            os.unlink(temporary_path)
        if code == evidence["exit_code"]:
            print("BA_FAULT_DRILL_" + evidence["status"])
    return code


if __name__ == "__main__":
    raise SystemExit(main())
