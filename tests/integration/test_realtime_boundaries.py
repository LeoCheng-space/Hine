"""BA boundary tests: actual aiohttp/Redis plus a TEST-ONLY BB authority.

Not product E2E: the fixture is isolated from runtime, does not implement BB
PostgreSQL/JWT, and cannot establish A19/browser persistence acceptance.
Mutations caught: premature ACK, client identity/C1 leaks, skipped session gates,
service credential confusion, malformed success trust, duplicate notice fanout.
"""
import asyncio
import copy
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import aiohttp
from aiohttp import web
from redis.asyncio import Redis
from redis.exceptions import RedisError


def timestamp(seconds=0):
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def frame(event, payload, **extra):
    return {"event": event, "event_id": str(uuid4()), "timestamp": timestamp(), "payload": payload, **extra}


def error(code, layer=None, retryable=False, delay=None):
    details = {} if layer is None else {"auth_layer": layer}
    if delay is not None:
        details["retry_after_ms"] = delay
    return {"error": {"code": code, "message": "fixture private text must not be echoed", "request_id": "test-request", "retryable": retryable, "details": details}}


async def serve(app):
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = runner.addresses[0][1]
    return runner, f"http://127.0.0.1:{port}"


class TestAuthority:
    """Stateful test authority, never imported by production.

    Validates caller credential, session binding, canonical payload, C1 equality,
    authorization and commit barrier; records only a test-memory transaction.
    Network calls go to this real aiohttp endpoint, not patched client methods.
    """
    __test__ = False

    def __init__(self):
        self.entries = []
        self.sessions = {
            "access-a": {"subject_id": "private-a", "user_id": "user-a", "session_id": "session-a", "session_generation": 1},
            "access-b": {"subject_id": "private-b", "user_id": "user-b", "session_id": "session-b", "session_generation": 1},
            "access-a2": {"subject_id": "private-a", "user_id": "user-a", "session_id": "session-a2", "session_generation": 1},
        }
        self.messages = {}
        self.quota_exhausted = False
        self.block_commit = None
        self.commit_entered = asyncio.Event()
        self.validate_release = None
        self.validate_entered = asyncio.Event()
        self.faults = {}
        self.mutate_result = None
        self.fail_poll = False
        self.cursor_invalid = False
        self.denied_receivers = set()
        self.poll_entered = asyncio.Event()
        self.authorize_release = None
        self.authorize_entered = asyncio.Event()
        self.authorize_hold_user = None
        self.authorization_snapshots = []
        self.persist_response_release = None
        self.persist_response_entered = asyncio.Event()
        self.group_versions = {"group-1": 1}
        self.group_members = {"group-1": {"user-a": 0, "user-b": 0}}

    def remove_group_user(self, user, conversation="group-1"):
        self.group_versions[conversation] += 1
        self.group_members[conversation].pop(user, None)
        return self.group_versions[conversation]

    def rejoin_group_user(self, user, conversation="group-1"):
        self.group_versions[conversation] += 1
        boundary = max((int(message["order_key"]) for message in self.messages.values() if message["conversation_id"] == conversation), default=0)
        self.group_members[conversation][user] = boundary
        return self.group_versions[conversation]

    def may_receive(self, user, resource_type, resource_id):
        if user in self.denied_receivers:
            return False
        if resource_type == "message":
            message = next((message for message in self.messages.values() if message["message_id"] == resource_id), None)
            if message is None or user not in message["recipient_ids"]:
                return False
            conversation = message["conversation_id"]
        elif resource_type == "conversation":
            message = None
            conversation = resource_id
        else:
            return False
        if conversation not in self.group_members:
            return conversation == "direct-1"
        boundary = self.group_members[conversation].get(user)
        return boundary is not None and (message is None or int(message["order_key"]) > boundary)

    @property
    def head(self):
        return len(self.entries)

    def invalidate(self, session_id, generation=None, reason="logout"):
        entry = {"position": self.head + 1, "session_id": session_id, "reason": reason, "min_valid_generation": generation, "committed_at": timestamp()}
        self.entries.append(entry)
        return copy.deepcopy(entry)

    def invalid(self, session):
        return any(e["session_id"] == session["session_id"] and (e["min_valid_generation"] is None or session["session_generation"] < e["min_valid_generation"]) for e in self.entries)

    async def handle(self, request):
        operation = request.match_info["operation"]
        if request.headers.get("Authorization") != "Bearer realtime-service-secret":
            return web.json_response(error("UNAUTHENTICATED", "service_identity"), status=401)
        body = await request.json()
        if operation in self.faults:
            status, data = self.faults[operation]
            return web.json_response(data, status=status)
        if operation == "readSessionInvalidations":
            self.poll_entered.set()
            if self.fail_poll:
                return web.json_response(error("DEPENDENCY_UNAVAILABLE", retryable=True), status=503)
            after = body["after_position"]
            if after is not None and self.cursor_invalid:
                self.cursor_invalid = False
                return web.json_response(error("CURSOR_INVALID"), status=400)
            rows = [] if after is None else self.entries[after:after + body["limit"]]
            next_position = self.head if after is None else (rows[-1]["position"] if rows else after)
            return web.json_response({"data": {"entries": rows, "next_position": next_position, "head_position": self.head, "has_more": next_position < self.head}})
        if operation == "validateAccess":
            session = self.sessions.get(body.get("access_token"))
            if session is None or body.get("device_id") != body.get("access_token", "").replace("access", "device") or self.invalid(session):
                return web.json_response(error("UNAUTHENTICATED", "user_session"), status=401)
            result = {**session, "session_valid": True, "expires_at": timestamp(60), "invalidation_position": self.head}
            self.validate_entered.set()
            if self.validate_release is not None:
                await self.validate_release.wait()
            if self.mutate_result is not None:
                result = self.mutate_result(operation, result)
            return web.json_response({"data": result})
        if operation == "persistIfAbsent":
            # Contract order: canonical checks precede session/C1/quota checks.
            payload = body.get("payload", {})
            text = payload.get("text")
            if body.get("type") != "text" or not isinstance(text, str) or not 1 <= len(text) <= 4096 or len(body.get("conversation_id", "")) > 128:
                return web.json_response(error("INVALID_ARGUMENT"), status=400)
        session = next((s for s in self.sessions.values() if s["session_id"] == body.get("session_id") and s["subject_id"] == body.get("subject_id")), None)
        if session is None or body.get("session_generation") != session["session_generation"] or self.invalid(session):
            return web.json_response(error("UNAUTHENTICATED", "user_session"), status=401)
        if body.get("device_id") != "device-" + session["session_id"].removeprefix("session-"):
            return web.json_response(error("UNAUTHENTICATED", "user_session"), status=401)
        if operation == "authorize":
            # Capture the actual authorization snapshot BEFORE delaying its HTTP
            # response, so an allowed pre-removal response can arrive after A18.
            allowed = self.may_receive(session["user_id"], body["resource_type"], body["resource_id"])
            self.authorization_snapshots.append({"user": session["user_id"], "resource_type": body["resource_type"], "resource_id": body["resource_id"], "allowed": allowed})
            if self.authorize_hold_user is None or session["user_id"] == self.authorize_hold_user:
                self.authorize_entered.set()
                if self.authorize_release is not None:
                    await self.authorize_release.wait()
            return web.json_response({"data": {"allowed": allowed, "authorization_version": "auth-version"}})
        if operation != "persistIfAbsent":
            return web.json_response(error("INVALID_ARGUMENT"), status=400)
        conversation = body["conversation_id"]
        if conversation != "direct-1" and session["user_id"] not in self.group_members.get(conversation, {}):
            return web.json_response(error("FORBIDDEN"), status=403)
        key = (session["subject_id"], body["client_message_id"])
        saved = self.messages.get(key)
        if saved is not None and (saved["text"], saved["conversation_id"]) != (body["payload"]["text"], conversation):
            return web.json_response(error("IDEMPOTENCY_CONFLICT"), status=409)
        if saved is None:
            if self.quota_exhausted:
                return web.json_response(error("RATE_LIMITED", retryable=True, delay=250), status=429)
            self.commit_entered.set()
            if self.block_commit is not None:
                await self.block_commit.wait()
            recipients = ["user-a", "user-b"] if conversation == "direct-1" else list(self.group_members[conversation])
            saved = {"message_id": str(uuid4()), "event_id": str(uuid4()), "order_key": f"{len(self.messages) + 1:020d}", "created_at": timestamp(), "recipient_ids": recipients, "status": "persisted", "invalidation_position": self.head, "membership_version": self.group_versions.get(conversation), "text": body["payload"]["text"], "conversation_id": conversation}
            self.messages[key] = saved
        result = {k: v for k, v in saved.items() if k not in {"text", "conversation_id"}}
        self.persist_response_entered.set()
        if self.persist_response_release is not None:
            await self.persist_response_release.wait()
        if self.mutate_result is not None:
            result = self.mutate_result(operation, result)
        return web.json_response({"data": result})

    def app(self):
        app = web.Application()
        app.router.add_post("/internal/v1/{operation}", self.handle)
        return app


class RealtimeBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.secret_dir = Path(self.temp.name)
        (self.secret_dir / "outbound").write_text("realtime-service-secret\n")
        (self.secret_dir / "inbound").write_text("api-service-secret\n")
        self.client = aiohttp.ClientSession()
        self.addAsyncCleanup(self.client.close)
        self.authority = TestAuthority()
        runner, self.bb_url = await serve(self.authority.app())
        self.addAsyncCleanup(runner.cleanup)
        self.redis_url = os.environ.get("HINE_TEST_REDIS_URL", "redis://127.0.0.1:6379/0")
        self.prefix = "hine-test:" + str(uuid4())
        self.env = {
            "HINE_ENV": "test",
            "API_INTERNAL_URL": self.bb_url,
            "INTERNAL_CALLER_TOKEN_SECRET_REF": str(self.secret_dir / "outbound"),
            "INTERNAL_ALLOWED_CALLERS": json.dumps({"api": str(self.secret_dir / "inbound")}),
            "REDIS_URL": self.redis_url,
            "REALTIME_REDIS_PREFIX": self.prefix,
            "INVALIDATION_POLL_SECONDS": "1", "INVALIDATION_STALE_SECONDS": "3", "NOTICE_CATCHUP_HOLD_MS": "1000",
            "HEARTBEAT_INTERVAL_SECONDS": "30", "HEARTBEAT_TIMEOUT_SECONDS": "90",
        }

    async def start(self, env=None, redis_required=True):
        if redis_required:
            redis = Redis.from_url(self.redis_url, socket_connect_timeout=1, socket_timeout=1, protocol=2)
            try:
                await redis.ping()
            except (RedisError, OSError):
                if "HINE_TEST_REDIS_URL" in os.environ:
                    raise
                self.skipTest("Requires actual isolated Redis; set HINE_TEST_REDIS_URL")
            finally:
                await redis.aclose()
        from hine_realtime.config import Settings
        from hine_realtime.server import create_app
        app = create_app(Settings.from_env(self.env if env is None else env))
        runner, url = await serve(app)
        self.addAsyncCleanup(runner.cleanup)
        self.url = url
        self.app = app
        if redis_required:
            async with asyncio.timeout(5):
                while True:
                    async with self.client.get(url + "/health/ready") as response:
                        if response.status == 200:
                            break
                    await asyncio.sleep(0.03)
        return url

    async def auth(self, token="access-a"):
        ws = await self.client.ws_connect(self.url + "/ws/v1")
        self.addAsyncCleanup(ws.close)
        request = frame("auth.authenticate", {"access_token": token, "device_id": token.replace("access", "device")}, sender_id="client-forged-user", subject_id="client-forged-subject")
        await ws.send_json(request)
        return ws, request, await ws.receive_json(timeout=3)

    async def send(self, ws, text="  original 😀 e\u0301  ", c1=None, conversation="direct-1"):
        request = frame("message.send", {"client_message_id": c1 or str(uuid4()), "type": "text", "text": text}, conversation_id=conversation, sender_id="attacker")
        await ws.send_json(request)
        return request

    async def correlated(self, ws, request, event="message.ack"):
        async with asyncio.timeout(4):
            while True:
                message = await ws.receive_json()
                if message.get("correlation_id") == request["event_id"]:
                    self.assertEqual(message["event"], event)
                    return message

    async def no_frame(self, ws, timeout=0.15):
        with self.assertRaises(asyncio.TimeoutError):
            await ws.receive(timeout=timeout)

    async def publish(self, notice, token="api-service-secret"):
        async with self.client.post(self.url + "/internal/v1/publishCommitted", json={"notice": notice}, headers={"Authorization": "Bearer " + token}) as response:
            return response.status, await response.json()

    def invalidation_notice(self, entry):
        return {"notice_id": str(uuid4()), "type": "session_invalidation", "committed_at": entry["committed_at"], "invalidation_position": entry["position"], "session_invalidation": entry}

    def member_notice(self, user="user-b", source="A16", member="new-member", version=2):
        envelope = frame("conversation.member_added", {"member_id": member, "role": "member", "actor_id": "user-a", "membership_version": version}, conversation_id="group-1")
        return {"notice_id": str(uuid4()), "type": "conversation_events", "committed_at": timestamp(), "invalidation_position": self.authority.head, "conversation_events": {"source": source, "conversation_id": "group-1", "membership_version": version, "deliveries": [{"recipient_user_id": user, "envelope": envelope}]}}

    def removal_notice(self, recipient, version, conversation="group-1"):
        payload = {"member_id": "user-b", "change": "removed", "membership_version": version}
        if recipient != "user-b":
            payload["actor_id"] = "user-a"
        envelope = frame("conversation.member_removed", payload, conversation_id=conversation)
        return {"notice_id": str(uuid4()), "type": "conversation_events", "committed_at": timestamp(), "invalidation_position": self.authority.head, "conversation_events": {"source": "A18", "conversation_id": conversation, "membership_version": version, "deliveries": [{"recipient_user_id": recipient, "envelope": envelope}]}}

    async def receive_event(self, ws, event):
        async with asyncio.timeout(3):
            while True:
                message = await ws.receive_json()
                if message["event"] == event:
                    return message

    async def notice_consumed(self, notice):
        from hine_realtime.server import RUNTIME
        # Scheduling barrier only; assertions remain actual client-visible
        # deliveries/closure, not an assertion on private wiring or a fake echo.
        async with asyncio.timeout(2):
            while notice["notice_id"] not in self.app[RUNTIME].seen:
                await asyncio.sleep(0.01)

    async def test_missing_configuration_is_live_but_unready_and_auth_fails_closed(self):
        await self.start({}, redis_required=False)
        async with self.client.get(self.url + "/health/live") as response:
            self.assertEqual(response.status, 200)
            self.assertEqual((await response.json())["dependencies"], {"postgresql": "not_checked", "redis": "not_checked"})
        async with self.client.get(self.url + "/health/ready") as response:
            self.assertEqual(response.status, 503)
            self.assertEqual((await response.json())["reason"], "CONFIG_MISSING")
        ws, request, reply = await self.auth()
        self.assertEqual(reply["event"], "error")
        self.assertEqual(reply["payload"]["code"], "DEPENDENCY_UNAVAILABLE")
        self.assertEqual(reply["correlation_id"], request["event_id"])
        self.assertIn((await ws.receive(timeout=2)).type, {aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED})

    async def test_no_ack_or_fanout_before_commit_and_c1_is_sender_only(self):
        await self.start()
        sender, auth_request, accepted = await self.auth()
        receiver, _, receiver_accepted = await self.auth("access-b")
        self.assertEqual(accepted["payload"]["user_id"], "user-a")
        self.assertEqual(accepted["correlation_id"], auth_request["event_id"])
        self.assertEqual(receiver_accepted["payload"]["user_id"], "user-b")
        self.authority.block_commit = asyncio.Event()
        request = await self.send(sender)
        await asyncio.wait_for(self.authority.commit_entered.wait(), 2)
        await self.no_frame(sender)
        await self.no_frame(receiver)
        self.authority.block_commit.set()
        ack = await self.correlated(sender, request)
        received = await receiver.receive_json(timeout=3)
        self.assertEqual(received["event"], "message.created")
        self.assertEqual(received["sender_id"], "user-a")
        self.assertNotIn("client_message_id", received["payload"])
        self.assertEqual(received["payload"]["text"], "  original 😀 e\u0301  ")
        self.assertEqual(received["payload"]["message_id"], ack["payload"]["message_id"])
        self.assertNotIn("private-a", json.dumps(received))
        self.authority.quota_exhausted = True
        retry = await self.send(sender, c1=request["payload"]["client_message_id"])
        retry_ack = await self.correlated(sender, retry)
        self.assertEqual(retry_ack["payload"]["message_id"], ack["payload"]["message_id"])
        await self.no_frame(receiver)

    async def test_bb_canonical_conflict_and_quota_errors_preserve_original_request(self):
        await self.start()
        ws, _, _ = await self.auth()
        first = await self.send(ws, "Hello")
        await self.correlated(ws, first)
        self.authority.quota_exhausted = True
        for text, c1, code in [("", first["payload"]["client_message_id"], "INVALID_ARGUMENT"), ("A" * 4097, str(uuid4()), "INVALID_ARGUMENT"), ("World", first["payload"]["client_message_id"], "IDEMPOTENCY_CONFLICT"), ("Hello", str(uuid4()), "RATE_LIMITED")]:
            request = await self.send(ws, text, c1)
            reply = await self.correlated(ws, request, "error")
            self.assertEqual(reply["payload"]["code"], code)
            self.assertNotIn("private text", reply["payload"]["message"])
            if code == "RATE_LIMITED":
                self.assertEqual(reply["payload"]["retry_after_ms"], 250)
        ping = frame("heartbeat.ping", {"nonce": "  exact NONCE  "})
        await ws.send_json(ping)
        self.assertEqual((await self.correlated(ws, ping, "heartbeat.pong"))["payload"], {"nonce": "  exact NONCE  "})

    async def test_service_identity_failure_does_not_logout_authenticated_client(self):
        await self.start()
        ws, _, _ = await self.auth()
        for layer in ["service_identity", None]:
            self.authority.faults["persistIfAbsent"] = (401, error("UNAUTHENTICATED", layer))
            request = await self.send(ws)
            reply = await self.correlated(ws, request, "error")
            self.assertEqual(reply["payload"]["code"], "DEPENDENCY_UNAVAILABLE")
            self.assertNotIn("auth_layer", reply["payload"])
            ping = frame("heartbeat.ping", {"nonce": str(uuid4())})
            await ws.send_json(ping)
            await self.correlated(ws, ping, "heartbeat.pong")
        self.authority.faults["persistIfAbsent"] = (401, error("UNAUTHENTICATED", "user_session"))
        request = await self.send(ws)
        reply = await self.correlated(ws, request, "error")
        self.assertEqual(reply["payload"]["code"], "UNAUTHENTICATED")
        self.assertIn((await ws.receive(timeout=2)).type, {aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED})

    async def test_incomplete_persist_result_never_becomes_ack_or_fanout(self):
        await self.start()
        ws, _, _ = await self.auth()
        receiver, _, _ = await self.auth("access-b")
        for field in ["message_id", "event_id", "order_key", "created_at", "recipient_ids", "status", "invalidation_position", "membership_version"]:
            self.authority.mutate_result = lambda operation, result, field=field: {k: v for k, v in result.items() if k != field}
            request = await self.send(ws)
            reply = await self.correlated(ws, request, "error")
            self.assertEqual(reply["payload"]["code"], "OUTCOME_UNCONFIRMED")
            await self.no_frame(receiver)

    async def test_notice_auth_precedes_body_validation_source_mapping_and_idempotence(self):
        await self.start()
        ws, _, _ = await self.auth("access-b")
        status, body = await self.publish({}, "access-b")
        self.assertEqual(status, 401)
        self.assertEqual(body["error"]["details"], {"auth_layer": "service_identity"})
        for source in ["W05", "W08", "W09", "A15"]:
            status, _ = await self.publish(self.member_notice(source=source))
            self.assertEqual(status, 400)
        notice = self.member_notice(member="opaque" * 30)
        for _ in range(2):
            status, body = await self.publish(notice)
            self.assertEqual(status, 200)
            self.assertEqual(body["data"], {"notice_id": notice["notice_id"], "published": True})
        received = await ws.receive_json(timeout=3)
        self.assertEqual(received["event_id"], notice["conversation_events"]["deliveries"][0]["envelope"]["event_id"])
        await self.no_frame(ws)

    async def test_out_of_order_logout_blocks_racing_auth_and_preserves_other_device(self):
        await self.start()
        other, _, _ = await self.auth("access-a2")
        self.authority.validate_release = asyncio.Event()
        self.authority.validate_entered.clear()
        ws = await self.client.ws_connect(self.url + "/ws/v1")
        self.addAsyncCleanup(ws.close)
        request = frame("auth.authenticate", {"access_token": "access-a", "device_id": "device-a"})
        await ws.send_json(request)
        await asyncio.wait_for(self.authority.validate_entered.wait(), 2)
        self.authority.invalidate("irrelevant")
        entry = self.authority.invalidate("session-a")
        self.authority.fail_poll = True
        status, _ = await self.publish(self.invalidation_notice(entry))
        self.assertEqual(status, 200)
        await asyncio.sleep(0.1)
        self.authority.validate_release.set()
        reply = await ws.receive_json(timeout=3)
        self.assertEqual(reply["event"], "error")
        self.assertEqual(reply["payload"]["code"], "UNAUTHENTICATED")
        ping = frame("heartbeat.ping", {"nonce": "other device lives"})
        await other.send_json(ping)
        await self.correlated(other, ping, "heartbeat.pong")

    async def test_lost_logout_notice_is_caught_by_delivery_gate(self):
        await self.start()
        revoked, _, _ = await self.auth("access-b")
        sender, _, _ = await self.auth()
        self.authority.invalidate("session-b")
        request = await self.send(sender)
        await self.correlated(sender, request)
        message = await revoked.receive_json(timeout=3)
        self.assertEqual(message["event"], "error")
        self.assertEqual(message["payload"]["code"], "UNAUTHENTICATED")
        self.assertIn((await revoked.receive(timeout=2)).type, {aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED})

    async def test_stale_authority_keeps_heartbeat_but_suppresses_data_and_new_auth(self):
        await self.start()
        ws, _, _ = await self.auth("access-b")
        self.authority.fail_poll = True
        await asyncio.sleep(3.2)
        async with self.client.get(self.url + "/health/ready") as response:
            self.assertEqual(response.status, 503)
        _, _, reply = await self.auth()
        self.assertEqual(reply["payload"]["code"], "DEPENDENCY_UNAVAILABLE")
        status, _ = await self.publish(self.member_notice())
        self.assertEqual(status, 200)
        await self.no_frame(ws)
        ping = frame("heartbeat.ping", {"nonce": "alive while stale"})
        await ws.send_json(ping)
        await self.correlated(ws, ping, "heartbeat.pong")

    async def test_cursor_invalid_closes_every_local_session_before_reset(self):
        await self.start()
        a, _, _ = await self.auth()
        b, _, _ = await self.auth("access-b")
        self.authority.cursor_invalid = True
        for ws in [a, b]:
            async with asyncio.timeout(4):
                while (await ws.receive()).type not in {aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED}:
                    pass

    async def test_presence_requires_api_credential_and_reports_actual_device(self):
        await self.start()
        await self.auth()
        for subject, device, expected in [("private-a", "device-a", "online"), ("private-a", "device-a2", "offline")]:
            async with self.client.post(self.url + "/internal/v1/getDevicePresence", json={"subject_id": subject, "device_id": device}, headers={"Authorization": "Bearer api-service-secret"}) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual((await response.json())["data"], {"online": expected, "activity": "unknown", "valid_until": None})

    async def test_missing_public_mapping_and_invalid_access_never_emit_w02(self):
        await self.start()
        for token in ["unknown-access", "access-a"]:
            self.authority.mutate_result = lambda operation, result: {k: v for k, v in result.items() if k != "user_id"}
            ws, request, reply = await self.auth(token)
            self.assertEqual(reply["event"], "error")
            self.assertEqual(reply["correlation_id"], request["event_id"])
            self.assertEqual(reply["payload"]["code"], "UNAUTHENTICATED" if token == "unknown-access" else "DEPENDENCY_UNAVAILABLE")
            self.assertIn((await ws.receive(timeout=2)).type, {aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED})

    async def test_token_expiry_closes_even_when_authority_polling_is_down(self):
        await self.start()
        self.authority.mutate_result = lambda operation, result: {**result, "expires_at": timestamp(1)} if operation == "validateAccess" else result
        ws, _, accepted = await self.auth()
        self.assertEqual(accepted["event"], "auth.accepted")
        self.authority.fail_poll = True
        async with asyncio.timeout(2):
            while (await ws.receive()).type not in {aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED}:
                pass

    async def test_refresh_invalidates_only_old_generation_not_new_session(self):
        await self.start()
        old, _, _ = await self.auth()
        other, _, _ = await self.auth("access-a2")
        entry = self.authority.invalidate("session-a", 2, "refresh")
        self.authority.sessions["access-a"]["session_generation"] = 2
        status, _ = await self.publish(self.invalidation_notice(entry))
        self.assertEqual(status, 200)
        current, _, accepted = await self.auth()
        self.assertEqual(accepted["payload"]["session_generation"], 2)
        async with asyncio.timeout(2):
            while (await old.receive()).type not in {aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED}:
                pass
        for ws in [current, other]:
            ping = frame("heartbeat.ping", {"nonce": str(uuid4())})
            await ws.send_json(ping)
            await self.correlated(ws, ping, "heartbeat.pong")

    async def test_unsupported_event_and_structural_nulls_do_not_write_or_close_session(self):
        await self.start()
        ws, _, _ = await self.auth()
        for request in [
            frame("device.activity", {"state": "foreground"}),
            frame("message.send", {"client_message_id": str(uuid4()), "type": "text", "text": None}, conversation_id="direct-1"),
            frame("message.send", {"client_message_id": str(uuid4()), "type": "text", "text": "ok", "attachment_id": "forbidden-union"}, conversation_id="direct-1"),
            frame("heartbeat.ping", {"nonce": ""}),
        ]:
            await ws.send_json(request)
            reply = await self.correlated(ws, request, "error")
            self.assertEqual(reply["payload"]["code"], "INVALID_ARGUMENT")
        request = await self.send(ws, "valid after malformed")
        await self.correlated(ws, request)

    async def test_missing_bb_is_live_but_not_ready_despite_real_redis(self):
        await self.start({**self.env, "API_INTERNAL_URL": "http://127.0.0.1:9"}, redis_required=False)
        async with self.client.get(self.url + "/health/live") as response:
            self.assertEqual(response.status, 200)
        async with self.client.get(self.url + "/health/ready") as response:
            self.assertEqual(response.status, 503)
        _ws, _, reply = await self.auth()
        self.assertEqual(reply["event"], "error")
        self.assertEqual(reply["payload"]["code"], "DEPENDENCY_UNAVAILABLE")

    async def test_failed_redis_publish_does_not_mark_notice_complete(self):
        from urllib.parse import urlsplit, urlunsplit
        admin = Redis.from_url(self.redis_url, socket_connect_timeout=1, socket_timeout=1, protocol=2)
        try:
            await admin.ping()
        except (RedisError, OSError):
            await admin.aclose()
            if "HINE_TEST_REDIS_URL" in os.environ:
                raise
            self.skipTest("Requires actual isolated Redis")
        self.addAsyncCleanup(admin.aclose)
        username = "hine_test_" + uuid4().hex
        password = uuid4().hex
        try:
            await admin.execute_command("ACL", "SETUSER", username, "on", ">" + password, "~*", "&*", "+@all", "-publish")
        except RedisError:
            if "HINE_TEST_REDIS_URL" in os.environ:
                raise
            self.skipTest("Requires isolated Redis test authority with ACL administration")
        self.addAsyncCleanup(admin.execute_command, "ACL", "DELUSER", username)
        parsed = urlsplit(self.redis_url)
        host = parsed.hostname
        if ":" in host:
            host = "[" + host + "]"
        restricted_url = urlunsplit((parsed.scheme, f"{username}:{password}@{host}:{parsed.port or 6379}", parsed.path, "", ""))
        await self.start({**self.env, "REDIS_URL": restricted_url})
        ws, _, _ = await self.auth("access-b")
        notice = self.member_notice()
        status, body = await self.publish(notice)
        self.assertEqual(status, 503)
        self.assertEqual(body["error"]["code"], "DEPENDENCY_UNAVAILABLE")
        await self.no_frame(ws)
        await admin.execute_command("ACL", "SETUSER", username, "+publish")
        status, body = await self.publish(notice)
        self.assertEqual(status, 200)
        self.assertTrue(body["data"]["published"])
        received = await ws.receive_json(timeout=3)
        self.assertEqual(received["event"], "conversation.member_added")

    async def test_receiver_authorization_is_checked_after_commit_without_blocking_ack(self):
        await self.start()
        sender, _, _ = await self.auth()
        receiver, _, _ = await self.auth("access-b")
        self.authority.denied_receivers.add("user-b")
        request = await self.send(sender)
        ack = await self.correlated(sender, request)
        self.assertEqual(ack["payload"]["status"], "persisted")
        await self.no_frame(receiver)
        ping = frame("heartbeat.ping", {"nonce": "permission failure is not logout"})
        await receiver.send_json(ping)
        await self.correlated(receiver, ping, "heartbeat.pong")

    async def test_non_hine_and_invalid_retry_delay_do_not_leak_or_invent_success(self):
        await self.start()
        ws, _, _ = await self.auth()
        self.authority.faults["persistIfAbsent"] = (401, {"message": "private-a access-a SQL secret"})
        request = await self.send(ws)
        reply = await self.correlated(ws, request, "error")
        self.assertEqual(reply["payload"]["code"], "DEPENDENCY_UNAVAILABLE")
        self.assertNotIn("private-a", json.dumps(reply))
        for delay in [None, "0", -1, 1.5, True, 9007199254740992]:
            self.authority.faults["persistIfAbsent"] = (429, error("RATE_LIMITED", retryable=True, delay=delay))
            request = await self.send(ws)
            reply = await self.correlated(ws, request, "error")
            self.assertEqual(reply["payload"]["code"], "RATE_LIMITED")
            self.assertNotIn("retry_after_ms", reply["payload"])

    async def test_user_credential_cannot_authenticate_internal_provider(self):
        await self.start()
        async with self.client.post(self.url + "/internal/v1/getDevicePresence", data="not JSON", headers={"Authorization": "Bearer access-a"}) as response:
            self.assertEqual(response.status, 401)
            self.assertEqual((await response.json())["error"]["details"]["auth_layer"], "service_identity")

    async def test_both_sender_devices_get_sender_c1_and_stable_event_not_receiver_c1(self):
        await self.start()
        sender, _, _ = await self.auth()
        sender_device, _, _ = await self.auth("access-a2")
        receiver, _, _ = await self.auth("access-b")
        request = await self.send(sender, "C1 scope")
        await self.correlated(sender, request)
        own = await sender_device.receive_json(timeout=3)
        peer = await receiver.receive_json(timeout=3)
        self.assertEqual(own["payload"]["client_message_id"], request["payload"]["client_message_id"])
        self.assertNotIn("client_message_id", peer["payload"])
        self.assertEqual(own["event_id"], peer["event_id"])
        self.assertEqual(own["payload"]["order_key"], peer["payload"]["order_key"])

    async def test_ba_does_not_apply_bb_product_burst_quota_to_valid_sends(self):
        await self.start()
        ws, _, _ = await self.auth()
        # Fixture commits all intents; BA must not add the BB-owned burst10 gate.
        for index in range(12):
            request = await self.send(ws, f"intent-{index}")
            ack = await self.correlated(ws, request)
            self.assertEqual(ack["payload"]["status"], "persisted")

    async def test_duplicate_nonce_does_not_complete_a_second_heartbeat(self):
        await self.start()
        ws, _, _ = await self.auth()
        ping = frame("heartbeat.ping", {"nonce": "never reused on this connection"})
        await ws.send_json(ping)
        await self.correlated(ws, ping, "heartbeat.pong")
        duplicate = frame("heartbeat.ping", {"nonce": "never reused on this connection"})
        await ws.send_json(duplicate)
        reply = await self.correlated(ws, duplicate, "error")
        self.assertEqual(reply["payload"]["code"], "INVALID_ARGUMENT")

    async def test_invalidation_stream_jump_cannot_establish_freshness_or_auth(self):
        self.authority.faults["readSessionInvalidations"] = (200, {"data": {"entries": [], "next_position": 3, "head_position": 4, "has_more": False}})
        await self.start(redis_required=False)
        _, _, reply = await self.auth()
        self.assertEqual(reply["event"], "error")
        self.assertEqual(reply["payload"]["code"], "DEPENDENCY_UNAVAILABLE")

    async def test_bounded_output_closes_slow_recipient_without_blocking_other_session(self):
        await self.start({**self.env, "REALTIME_MAX_OUTGOING_FRAMES": "2"})
        slow, _, _ = await self.auth("access-b")
        other, _, _ = await self.auth()
        self.authority.authorize_release = asyncio.Event()
        status, _ = await self.publish(self.member_notice())
        self.assertEqual(status, 200)
        await asyncio.wait_for(self.authority.authorize_entered.wait(), 2)
        try:
            for _ in range(8):
                status, _ = await self.publish(self.member_notice())
                self.assertEqual(status, 200)
            async with asyncio.timeout(3):
                while (await slow.receive()).type not in {aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED}:
                    pass
            ping = frame("heartbeat.ping", {"nonce": "unrelated session still usable"})
            await other.send_json(ping)
            await self.correlated(other, ping, "heartbeat.pong")
        finally:
            self.authority.authorize_release.set()

    async def test_freshness_is_rechecked_after_delayed_receive_authorization(self):
        await self.start()
        receiver, _, _ = await self.auth("access-b")
        self.authority.fail_poll = True
        # Age the last complete catchup first, then delay authorization for less
        # than the 2s HTTP timeout so this catches missing final freshness checks,
        # not a dependency timeout that would independently discard the frame.
        await asyncio.sleep(1.8)
        self.authority.authorize_release = asyncio.Event()
        status, _ = await self.publish(self.member_notice())
        self.assertEqual(status, 200)
        await asyncio.wait_for(self.authority.authorize_entered.wait(), 2)
        try:
            await asyncio.sleep(1.4)
        finally:
            self.authority.authorize_release.set()
        await self.no_frame(receiver)
        ping = frame("heartbeat.ping", {"nonce": "still heartbeat only"})
        await receiver.send_json(ping)
        await self.correlated(receiver, ping, "heartbeat.pong")

    async def exercise_group_removal_race(self, hold_socket_lock=False):
        await self.start()
        sender, _, _ = await self.auth()
        receiver, _, _ = await self.auth("access-b")
        self.authority.authorize_hold_user = "user-b"
        self.authority.authorize_release = asyncio.Event()
        request = await self.send(sender, "old group secret", conversation="group-1")
        await self.correlated(sender, request)
        await asyncio.wait_for(self.authority.authorize_entered.wait(), 2)
        write_lock = None
        try:
            if hold_socket_lock:
                # Hold the REAL socket writer lock, not a patched send/client.
                from hine_realtime.server import RUNTIME
                connection = next(connection for connection in self.app[RUNTIME].connections if connection.binding is not None and connection.binding["user_id"] == "user-b")
                write_lock = connection.write_lock
                await write_lock.acquire()
                self.authority.authorize_release.set()
                await asyncio.sleep(0.05)
            version = self.authority.remove_group_user("user-b")
            # BB may split notices: this fragment targets only another member.
            # Its member_id still revokes user-b's pending content immediately.
            status, _ = await self.publish(self.removal_notice("user-a", version))
            self.assertEqual(status, 200)
            applied = await self.receive_event(sender, "conversation.member_removed")
            self.assertEqual(applied["payload"]["member_id"], "user-b")
            status, _ = await self.publish(self.removal_notice("user-b", version))
            self.assertEqual(status, 200)
            new_version = self.authority.rejoin_group_user("user-b")
            status, _ = await self.publish(self.member_notice(member="user-b", version=new_version))
            self.assertEqual(status, 200)
        finally:
            self.authority.authorize_release.set()
            if write_lock is not None and write_lock.locked():
                write_lock.release()
        # The first observable frame must be the minimal self-removal, never
        # the old W07 even though BB's allowed snapshot predates removal/rejoin.
        removed = await receiver.receive_json(timeout=3)
        self.assertEqual(removed["event"], "conversation.member_removed")
        self.assertEqual(removed["payload"], {"member_id": "user-b", "change": "removed", "membership_version": version})
        added = await receiver.receive_json(timeout=3)
        self.assertEqual(added["event"], "conversation.member_added")
        self.assertEqual(added["payload"]["membership_version"], new_version)
        await self.no_frame(receiver)
        request = await self.send(sender, "new readable group message", conversation="group-1")
        await self.correlated(sender, request)
        new_message = await receiver.receive_json(timeout=3)
        self.assertEqual(new_message["payload"]["text"], "new readable group message")
        request = await self.send(sender, "other conversation remains live")
        await self.correlated(sender, request)
        other_message = await receiver.receive_json(timeout=3)
        self.assertEqual(other_message["conversation_id"], "direct-1")
        self.assertEqual(other_message["payload"]["text"], "other conversation remains live")

    async def test_consumed_fragmented_removal_blocks_allowed_inflight_group_message(self):
        await self.exercise_group_removal_race()

    async def test_group_removal_is_rechecked_after_socket_write_lock_wait(self):
        await self.exercise_group_removal_race(hold_socket_lock=True)

    async def test_lost_removal_notice_and_rejoin_use_message_readability_not_current_conversation(self):
        await self.start()
        sender, _, _ = await self.auth()
        receiver, _, _ = await self.auth("access-b")
        self.authority.persist_response_release = asyncio.Event()
        request = await self.send(sender, "previous membership secret", conversation="group-1")
        await asyncio.wait_for(self.authority.persist_response_entered.wait(), 2)
        self.authority.remove_group_user("user-b")
        self.authority.rejoin_group_user("user-b")
        # Intentionally lose A18. Current conversation authorization permits b,
        # but BB's current join boundary denies the already-committed old M1.
        self.authority.persist_response_release.set()
        await self.correlated(sender, request)
        await self.no_frame(receiver)
        request = await self.send(sender, "after new join boundary", conversation="group-1")
        await self.correlated(sender, request)
        received = await receiver.receive_json(timeout=3)
        self.assertEqual(received["event"], "message.created")
        self.assertEqual(received["payload"]["text"], "after new join boundary")

    async def test_removal_applies_before_its_notice_catchup_gate_finishes(self):
        await self.start()
        sender, _, _ = await self.auth()
        receiver, _, _ = await self.auth("access-b")
        self.authority.authorize_hold_user = "user-b"
        self.authority.authorize_release = asyncio.Event()
        request = await self.send(sender, "pre-removal snapshot", conversation="group-1")
        await self.correlated(sender, request)
        await asyncio.wait_for(self.authority.authorize_entered.wait(), 2)
        try:
            version = self.authority.remove_group_user("user-b")
            for index in range(3):
                self.authority.invalidate(f"unrelated-session-{index}")
            self.authority.fail_poll = True
            notice = self.removal_notice("user-a", version)
            status, _ = await self.publish(notice)
            self.assertEqual(status, 200)
            await self.notice_consumed(notice)
        finally:
            self.authority.authorize_release.set()
        # The W=3 A18 delivery waits for failed catchup, but its observed removal
        # must already prevent the older W=0 allowed response from starting.
        await self.no_frame(receiver)
        ping = frame("heartbeat.ping", {"nonce": "group removal does not close session"})
        await receiver.send_json(ping)
        await self.correlated(receiver, ping, "heartbeat.pong")

    async def test_removal_metadata_exhaustion_never_evicts_an_active_exclusion(self):
        await self.start({**self.env, "REALTIME_MAX_GROUP_REMOVALS": "2"})
        sender, _, _ = await self.auth()
        receiver, _, _ = await self.auth("access-b")
        self.authority.authorize_hold_user = "user-b"
        self.authority.authorize_release = asyncio.Event()
        request = await self.send(sender, "protected pending content", conversation="group-1")
        await self.correlated(sender, request)
        await asyncio.wait_for(self.authority.authorize_entered.wait(), 2)
        try:
            for conversation in ["group-1", "group-other-2", "group-other-3"]:
                if conversation not in self.authority.group_members:
                    self.authority.group_members[conversation] = {"user-a": 0, "user-b": 0}
                    self.authority.group_versions[conversation] = 1
                version = self.authority.remove_group_user("user-b", conversation)
                notice = self.removal_notice("user-a", version, conversation)
                status, _ = await self.publish(notice)
                self.assertEqual(status, 200)
                await self.notice_consumed(notice)
            self.authority.authorize_release.set()
            async with asyncio.timeout(3):
                while True:
                    received = await receiver.receive()
                    if received.type in {aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED}:
                        break
                    if received.type == aiohttp.WSMsgType.TEXT:
                        self.assertNotEqual(json.loads(received.data)["event"], "message.created")
        finally:
            self.authority.authorize_release.set()
        request = await self.send(sender, "other session survives metadata pressure")
        await self.correlated(sender, request)


if __name__ == "__main__":
    unittest.main()
