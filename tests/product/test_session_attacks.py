"""SEC-04: stolen, tampered, expired and replayed credentials against the real API, PostgreSQL, Redis and BA.

Every rejection is asserted as a consumer sees it (HTTP status and public error shape, W17 frames and close
codes, absence of `auth.accepted`/`message.ack`) and the genuine credential is shown to keep working, so a
broken forgery helper cannot make a test pass. Tests named `test_policy_pin_*` record current behavior that is
a product decision rather than an obvious defect; see docs/security/risk-assessment.md (SEC-04).
"""
import asyncio
import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from unittest import mock
from urllib.parse import urlsplit, urlunsplit

import aiohttp
import jwt
from redis.asyncio import Redis
from support import ProductCase
from test_domain import DomainConsumer

REQUIRED = ("exp", "iat", "sub", "sid", "gen", "did", "iss", "aud", "jti")
PUBLIC_REJECTION = {"code": "UNAUTHENTICATED", "retryable": False, "details": {}}


def b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def segment(value):
    return b64(json.dumps(value, separators=(",", ":")).encode())


def forge(claims, key, header=None):
    """A genuine-format HS256 token signed with `key`; `header` adds or overrides header fields."""
    signing_input = segment({"alg": "HS256", "typ": "JWT", **(header or {})}) + "." + segment(claims)
    return signing_input + "." + b64(hmac.new(key.encode(), signing_input.encode(), hashlib.sha256).digest())


def claims_of(access):
    return jwt.decode(access["access_token"], options={"verify_signature": False})


def forged_tokens(key, claims, foreign, sibling_device):
    """(name, token, device_id or None) for every forgery; None means the token owner's real device."""
    now = int(time.time())
    genuine = forge(claims, key)
    head, body, signature = genuine.split(".")

    def altered(**changes):
        return forge({**claims, **changes}, key)

    cases = [
        ("signed with another key", forge(claims, "x" * 48), None),
        ("gen+1 payload under the original signature", f"{head}.{segment({**claims, 'gen': claims['gen'] + 1})}.{signature}", None),
        ("another session's payload under the original signature", f"{head}.{segment(foreign)}.{signature}", None),
        ("alg none with empty signature", segment({"alg": "none", "typ": "JWT"}) + "." + body + ".", None),
        ("alg none keeping the HS256 signature", segment({"alg": "none", "typ": "JWT"}) + f".{body}.{signature}", None),
        ("HS384", jwt.encode(claims, key, algorithm="HS384"), None),
        ("HS512", jwt.encode(claims, key, algorithm="HS512"), None),
        ("two segments", f"{head}.{body}", None),
        ("empty signature", f"{head}.{body}.", None),
        ("truncated", genuine[:len(genuine) // 2], None),
        ("not base64", "!!!.@@@.###", None),
        ("wrong issuer", altered(iss="wrong"), None),
        ("wrong audience", altered(aud="wrong"), None),
        ("unknown session", altered(sid="not-issued"), None),
        ("unknown subject", altered(sub="not-issued"), None),
        ("generation ahead of the session", altered(gen=claims["gen"] + 1), None),
        ("generation as string", altered(gen=str(claims["gen"])), None),
        ("generation as boolean", altered(gen=True), None),
        ("generation zero", altered(gen=0), None),
        ("float exp", altered(exp=claims["exp"] + 0.5), None),
        ("iat zero", altered(iat=0), None),
        ("jti not a uuid", altered(jti="not-a-uuid"), None),
        ("integer sub", altered(sub=12345), None),
        ("129 character sub", altered(sub="s" * 129), None),
        ("integer sid", altered(sid=12345), None),
        ("129 character sid", altered(sid="s" * 129), None),
        ("empty did", altered(did=""), None),
        ("integer did", altered(did=7), None),
        ("audience as list", altered(aud=[claims["aud"]]), None),
        ("iat in the future", altered(iat=now + 60), None),
        ("nbf in the future", altered(nbf=now + 60), None),
        ("exp later than the stored session expiry", altered(exp=claims["exp"] + 60), None),
        ("did of the user's other device, supplied device unchanged", altered(did=sibling_device), None),
        ("did of the user's other device, matching supplied device", altered(did=sibling_device), sibling_device),
        ("integer kid header", forge(claims, key, {"kid": 1}), None),
        ("unsupported crit header", forge(claims, key, {"crit": ["x"]}), None),
    ]
    for name in REQUIRED:
        cases.append((f"missing {name}", forge({k: v for k, v in claims.items() if k != name}, key), None))
        cases.append((f"null {name}", altered(**{name: None}), None))
    return cases


class SessionAttackCase(ProductCase):
    async def public(self, header):
        return await self.api.request("GET", "/api/v1/users/me", headers={"Authorization": header}, cookie=False)

    async def assert_public_rejected(self, header):
        status, result = await self.public(header)
        self.assertEqual(status, 401, result)
        error = result["error"]
        self.assertEqual({key: error[key] for key in PUBLIC_REJECTION}, PUBLIC_REJECTION, result)

    async def assert_internal_rejected(self, token, device_id):
        status, result = await self.api.internal("validateAccess", {"access_token": token, "device_id": device_id})
        self.assertEqual(status, 401, result)
        self.assertEqual(result["error"]["code"], "UNAUTHENTICATED")
        self.assertEqual(result["error"]["details"], {"auth_layer": "user_session"})

    async def assert_rejected(self, access, device_id=None):
        await self.assert_public_rejected("Bearer " + access["access_token"])
        await self.assert_internal_rejected(access["access_token"], device_id or access["device_id"])

    async def assert_accepted(self, access):
        status, result = await self.request("GET", "/api/v1/users/me", access)
        self.assertEqual(status, 200, result)
        self.assertEqual(result["data"]["id"], access["user_id"])
        status, result = await self.api.internal("validateAccess", {"access_token": access["access_token"], "device_id": access["device_id"]})
        self.assertEqual(status, 200, result)

    async def post_cookie(self, path, cookie):
        """POST with an explicit refresh cookie; returns (status, data or None, cookie pair set by the reply)."""
        async with self.client.post(self.api.base_url + path, headers={"Origin": self.api.origin, "Cookie": cookie}) as reply:
            data = (await reply.json())["data"] if reply.status == 200 else None
            pair = reply.headers["Set-Cookie"].split(";", 1)[0] if "Set-Cookie" in reply.headers else None
            return reply.status, data, pair

    async def refresh(self, cookie):
        return await self.post_cookie("/api/v1/auth/refresh", cookie)

    async def logout(self, cookie):
        return (await self.post_cookie("/api/v1/auth/logout", cookie))[0]

    async def device(self, profile, device_id=None):
        """Log in and return (access, refresh cookie)."""
        access = await self.api.login(profile["email"], device_id=device_id)
        return access, self.api.last_cookie

    async def invalidations(self):
        status, result = await self.api.internal("readSessionInvalidations", {"after_position": 0, "limit": 500})
        self.assertEqual(status, 200, result)
        return result["data"]["entries"]


class SessionTokenTests(SessionAttackCase):
    async def test_tampered_tokens_are_rejected_on_public_rest_and_internal_validation(self):
        profile, access = await self.account("Tamper")
        sibling = await self.api.login(profile["email"])
        _, foreign = await self.account("Foreign")
        claims = claims_of(access)
        cases = forged_tokens(self.api.signing_key, claims, claims_of(foreign), sibling["device_id"])
        self.assertGreater(len(cases), 50)
        # Control: the forgery helper itself produces tokens the API accepts, so each rejection below is
        # caused by the tampering and not by a malformed helper.
        control = {**access, "access_token": forge(claims, self.api.signing_key)}
        await self.assert_accepted(control)
        for name, token, device_id in cases:
            with self.subTest(name):
                await self.assert_public_rejected("Bearer " + token)
                await self.assert_internal_rejected(token, device_id or access["device_id"])
        await self.assert_accepted(access)
        await self.assert_accepted(sibling)
        await self.assert_accepted(foreign)

    async def test_only_the_exact_bearer_scheme_authenticates_public_rest(self):
        _, access = await self.account("Scheme")
        token = access["access_token"]
        for name, header in (("lowercase scheme", "bearer " + token), ("token scheme", "Token " + token), ("no separator", "Bearer" + token),
                             ("bare token", token), ("basic scheme", "Basic " + token), ("empty bearer", "Bearer "), ("double space", "Bearer  " + token)):
            with self.subTest(name):
                await self.assert_public_rejected(header)
        status, result = await self.api.request("GET", "/api/v1/users/me", cookie=False)
        self.assertEqual((status, result["error"]["code"]), (401, "UNAUTHENTICATED"))
        await self.assert_accepted(access)

    async def test_expired_tokens_are_rejected_and_refresh_still_recovers_the_session(self):
        profile, access = await self.account("Expired")
        cookie = self.api.last_cookie
        claims = claims_of(access)
        past = int(time.time()) - 1
        expired = {**access, "access_token": forge({**claims, "iat": past - 60, "exp": past}, self.api.signing_key)}
        await self.assert_rejected(expired)
        await self.assert_accepted(access)
        # Genuine expiry: a short access lifetime elapses and the stored session expiry rejects the real token.
        self.api.settings_env["ACCESS_TTL_SECONDS"] = "3"
        await self.api.restart()
        short, short_cookie = await self.device(profile)
        await self.assert_accepted(short)
        async with asyncio.timeout(15):
            while (await self.request("GET", "/api/v1/users/me", short))[0] == 200:
                await asyncio.sleep(0.2)
        await self.assert_rejected(short)
        status, refreshed, _ = await self.refresh(short_cookie)
        self.assertEqual(status, 200)
        self.assertEqual(refreshed["session_generation"], short["session_generation"] + 1)
        await self.assert_accepted(refreshed)
        await self.assert_rejected(short)
        # The first session (default lifetime) is unaffected by the other device's expiry and recovery.
        self.assertEqual((await self.refresh(cookie))[0], 200)

    async def test_token_from_before_a_refresh_is_rejected_on_public_rest(self):
        _, old = await self.account("Generation")
        cookie = self.api.last_cookie
        status, fresh, _ = await self.refresh(cookie)
        self.assertEqual(status, 200)
        self.assertEqual(fresh["session_generation"], old["session_generation"] + 1)
        await self.assert_rejected(old)
        await self.assert_accepted(fresh)

    async def test_replaced_session_loses_token_and_cookie_and_logout_replay_is_a_noop(self):
        profile, first = await self.account("Replaced")
        old_cookie = self.api.last_cookie
        old_session = (await self.api.binding(first))["session_id"]
        other, other_cookie = await self.device(profile)
        replacement, new_cookie = await self.device(profile, first["device_id"])
        self.assertEqual(replacement["device_id"], first["device_id"])
        self.assertEqual((await self.refresh(old_cookie))[0], 401)
        await self.assert_rejected(first)
        entries = await self.invalidations()
        self.assertEqual([(entry["session_id"], entry["reason"], entry["min_valid_generation"]) for entry in entries],
                         [(old_session, "replaced", None)])
        # Replaying the dead session's cookie at logout answers 204 but must neither add an entry nor touch the new session.
        self.assertEqual(await self.logout(old_cookie), 204)
        self.assertEqual(await self.invalidations(), entries)
        await self.assert_accepted(replacement)
        await self.assert_accepted(other)
        self.assertEqual((await self.refresh(new_cookie))[0], 200)
        self.assertEqual((await self.refresh(other_cookie))[0], 200)

    async def test_expired_refresh_cookie_cannot_refresh_or_log_out(self):
        _, access = await self.account("Dead cookie")
        cookie = self.api.last_cookie
        session_id = (await self.api.binding(access))["session_id"]
        async with self.api.pool.acquire() as conn:
            await conn.execute("UPDATE sessions SET refresh_expires_at=clock_timestamp()-interval '1 second' WHERE session_id=$1", session_id)
        self.assertEqual((await self.refresh(cookie))[0], 401)
        self.assertEqual(await self.logout(cookie), 401)
        self.assertEqual(await self.invalidations(), [])
        # The short-lived access token is independent of the refresh cookie's lifetime.
        await self.assert_accepted(access)

    async def test_policy_pin_rotated_cookie_has_no_reuse_detection_and_only_relogin_evicts_the_thief(self):
        # POLICY DECISION (SEC-04): replaying a rotated refresh cookie yields 401 but does not revoke the
        # session, and the stale cookie cannot log out. If an attacker rotates first, the victim is locked
        # out while the attacker's session stays alive until the victim logs in again on the same device.
        profile, victim = await self.account("Victim")
        victim_cookie = self.api.last_cookie
        status, stolen, attacker_cookie = await self.refresh(victim_cookie)
        self.assertEqual(status, 200)
        self.assertEqual((await self.refresh(victim_cookie))[0], 401)
        self.assertEqual(await self.logout(victim_cookie), 401)
        await self.assert_rejected(victim)
        await self.assert_accepted(stolen)
        status, rotated, attacker_cookie = await self.refresh(attacker_cookie)
        self.assertEqual(status, 200)
        self.assertEqual([entry["reason"] for entry in await self.invalidations()], ["refresh", "refresh"])
        recovery, recovery_cookie = await self.device(profile, victim["device_id"])
        await self.assert_rejected(rotated)
        self.assertEqual((await self.refresh(attacker_cookie))[0], 401)
        entries = await self.invalidations()
        # The evicted session's cookie is now a revoked one: logout is an idempotent 204 that adds nothing.
        self.assertEqual(await self.logout(attacker_cookie), 204)
        self.assertEqual(await self.invalidations(), entries)
        self.assertEqual(entries[-1]["reason"], "replaced")
        self.assertIsNone(entries[-1]["min_valid_generation"])
        await self.assert_accepted(recovery)
        self.assertEqual((await self.refresh(recovery_cookie))[0], 200)

    async def test_policy_pin_logout_without_cookie_returns_204_and_revokes_nothing(self):
        # POLICY DECISION (SEC-04): A04 is idempotent, so a cookie-less logout reports success while the
        # session, its access token and its refresh cookie all stay valid and no invalidation is recorded.
        _, access = await self.account("No cookie")
        cookie = self.api.last_cookie
        status, _ = await self.api.request("POST", "/api/v1/auth/logout", cookie=False)
        self.assertEqual(status, 204)
        self.assertEqual(await self.invalidations(), [])
        await self.assert_accepted(access)
        self.assertEqual((await self.refresh(cookie))[0], 200)

    async def test_refresh_racing_logout_on_one_cookie_has_exactly_one_winner(self):
        for round_number in range(3):
            with self.subTest(round=round_number):
                _, access = await self.account("Race")
                cookie = self.api.last_cookie
                before = len(await self.invalidations())
                (refresh_status, fresh, fresh_cookie), logout_status = await asyncio.gather(self.refresh(cookie), self.logout(cookie))
                self.assertIn((refresh_status, logout_status), {(200, 401), (401, 204)})
                entries = (await self.invalidations())[before:]
                self.assertEqual(len(entries), 1, entries)
                await self.assert_rejected(access)
                if refresh_status == 200:
                    self.assertEqual(entries[0]["reason"], "refresh")
                    await self.assert_accepted(fresh)
                    self.assertEqual((await self.refresh(fresh_cookie))[0], 200)
                else:
                    self.assertEqual(entries[0]["reason"], "logout")
                    self.assertEqual((await self.refresh(cookie))[0], 401)

    async def test_parallel_refresh_leaves_only_the_winner_usable(self):
        _, before = await self.account("Winner")
        cookie = self.api.last_cookie
        results = await asyncio.gather(*(self.refresh(cookie) for _ in range(4)))
        self.assertEqual(sorted(status for status, _, _ in results), [200, 401, 401, 401])
        winner = next(result for result in results if result[0] == 200)
        await self.assert_rejected(before)
        await self.assert_accepted(winner[1])
        entries = await self.invalidations()
        self.assertEqual([(entry["reason"], entry["min_valid_generation"]) for entry in entries], [("refresh", before["session_generation"] + 1)])
        status, next_session, _ = await self.refresh(winner[2])
        self.assertEqual(status, 200)
        await self.assert_rejected(winner[1])
        await self.assert_accepted(next_session)


class SessionSocketTests(DomainConsumer, SessionAttackCase):
    @asynccontextmanager
    async def realtime(self, **overrides):
        """The real BA/Redis stack; `overrides` adjust only the BA's environment (e.g. poll interval, Redis user)."""
        if not overrides:
            async with self.real_realtime() as server:
                yield server
            return
        from hine_realtime.config import Settings
        original = Settings.from_env
        with mock.patch.object(Settings, "from_env", lambda environment=None: original({**environment, **overrides})):
            async with self.real_realtime() as server:
                yield server

    async def connect(self, server, access=None, token=None, device_id=None):
        from hine_realtime import protocol as p
        socket = await self.client.ws_connect(server.make_url("/ws/v1"), headers={"Origin": self.api.origin}, max_msg_size=1048576)
        self.addAsyncCleanup(socket.close)
        request = p.event("auth.authenticate", {"access_token": token or access["access_token"], "device_id": device_id or access["device_id"]})
        await socket.send_str(p.dumps(request))
        async with asyncio.timeout(10):
            return socket, request, await socket.receive_json()

    async def accepted(self, server, access):
        socket, request, reply = await self.connect(server, access)
        self.assertEqual(reply["event"], "auth.accepted", reply)
        self.assertEqual(reply["correlation_id"], request["event_id"])
        self.assertEqual(reply["payload"]["session_generation"], access["session_generation"])
        return socket

    async def drain(self, socket, timeout=10):
        frames = []
        async with asyncio.timeout(timeout):
            while True:
                message = await socket.receive()
                if message.type == aiohttp.WSMsgType.TEXT:
                    frames.append(json.loads(message.data))
                elif message.type == aiohttp.WSMsgType.CLOSE:
                    return frames, message.data
                elif message.type in {aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR}:
                    return frames, socket.close_code

    async def assert_revoked(self, socket, timeout=10):
        """W17 UNAUTHENTICATED (uncorrelated) then close 1008; nothing else is delivered."""
        frames, code = await self.drain(socket, timeout)
        self.assertEqual([(frame["event"], frame["payload"]["code"]) for frame in frames], [("error", "UNAUTHENTICATED")], frames)
        self.assertNotIn("correlation_id", frames[0])
        self.assertEqual(code, 1008)

    async def heartbeat(self, socket):
        from hine_realtime import protocol as p
        ping = p.event("heartbeat.ping", {"nonce": str(uuid.uuid4())})
        await socket.send_str(p.dumps(ping))
        async with asyncio.timeout(5):
            while True:
                reply = await socket.receive_json()
                if reply.get("correlation_id") == ping["event_id"]:
                    self.assertEqual(reply["event"], "heartbeat.pong", reply)
                    return

    def message_request(self, client_message_id=None, text="attack test"):
        from hine_realtime import protocol as p
        return p.event("message.send", {"client_message_id": client_message_id or str(uuid.uuid4()), "type": "text", "text": text}, conversation=self.conversation)

    async def send_message(self, socket, request):
        from hine_realtime import protocol as p
        await socket.send_str(p.dumps(request))
        async with asyncio.timeout(10):
            while True:
                reply = await socket.receive_json()
                if reply.get("correlation_id") == request["event_id"]:
                    self.assertEqual(reply["event"], "message.ack", reply)
                    return reply

    async def message_count(self):
        return await self.api.pool.fetchval("SELECT count(*) FROM messages")

    async def test_w01_rejects_forged_foreign_and_revoked_credentials_without_accepting(self):
        profile, access = await self.account("Handshake")
        sibling = await self.api.login(profile["email"])
        _, foreign = await self.account("Stranger")
        claims = claims_of(access)
        rejected = [(name, token, device_id or access["device_id"])
                    for name, token, device_id in forged_tokens(self.api.signing_key, claims, claims_of(foreign), sibling["device_id"])]
        rejected += [("valid token, user's other device", access["access_token"], sibling["device_id"]),
                     ("valid token, another user's device", access["access_token"], foreign["device_id"])]
        async with self.realtime() as server:
            stale, stale_cookie = await self.device(profile)
            refreshed = await self.refresh(stale_cookie)
            self.assertEqual(refreshed[0], 200)
            gone, gone_cookie = await self.device(profile)
            self.assertEqual(await self.logout(gone_cookie), 204)
            replaced, _ = await self.device(profile)
            await self.device(profile, replaced["device_id"])
            rejected += [("token from before a refresh", stale["access_token"], stale["device_id"]),
                         ("token after logout", gone["access_token"], gone["device_id"]),
                         ("token of a replaced session", replaced["access_token"], replaced["device_id"])]
            for name, token, device_id in rejected:
                with self.subTest(name):
                    socket, request, reply = await self.connect(server, token=token, device_id=device_id)
                    self.assertEqual(reply["event"], "error", reply)
                    self.assertEqual(reply["correlation_id"], request["event_id"])
                    self.assertEqual({key: reply["payload"][key] for key in ("code", "retryable")}, {"code": "UNAUTHENTICATED", "retryable": False})
                    frames, code = await self.drain(socket, 5)
                    self.assertNotIn("auth.accepted", [frame["event"] for frame in frames])
                    self.assertEqual(code, 1001)
            # The same server still authenticates the genuine credential and the rejected attempts left no trace.
            socket = await self.accepted(server, access)
            await self.heartbeat(socket)
            await self.heartbeat(await self.accepted(server, sibling))

    async def test_logout_with_delivered_notice_closes_every_socket_of_the_session_through_redis(self):
        await self.setup_direct()
        # A 14 s poll makes a close inside the 5 s bound attributable to the Redis notice, not the poll.
        async with self.realtime(INVALIDATION_POLL_SECONDS="14") as server:
            first, first_cookie = await self.device(self.alice)
            second, _ = await self.device(self.alice)
            socket_a, socket_b = await self.accepted(server, first), await self.accepted(server, first)
            survivor = await self.accepted(server, second)
            started = time.monotonic()
            self.assertEqual(await self.logout(first_cookie), 204)
            await asyncio.gather(self.assert_revoked(socket_a, 5), self.assert_revoked(socket_b, 5))
            self.assertLess(time.monotonic() - started, 5)
            await self.assert_rejected(first)
            await self.assert_accepted(second)
            await self.heartbeat(survivor)
            self.assertEqual((await self.send_message(survivor, self.message_request()))["payload"]["status"], "persisted")
            self.assertEqual(await self.message_count(), 1)
            _, _, reply = await self.connect(server, first)
            self.assertEqual((reply["event"], reply["payload"]["code"]), ("error", "UNAUTHENTICATED"))

    async def test_refresh_closes_the_old_generation_socket_and_its_in_flight_send_is_never_acknowledged(self):
        await self.setup_direct()
        async with self.realtime() as server:
            old_access, cookie = await self.device(self.alice)
            other_access, _ = await self.device(self.alice)
            old, other = await self.accepted(server, old_access), await self.accepted(server, other_access)
            status, fresh, _ = await self.refresh(cookie)
            self.assertEqual((status, fresh["session_generation"]), (200, old_access["session_generation"] + 1))
            request = self.message_request()
            try:
                await old.send_str(json.dumps(request))
            except (ConnectionError, aiohttp.ClientError):
                pass  # already closed by the revocation; the send must not have reached the backend either way
            frames, code = await self.drain(old)
            self.assertNotIn("message.ack", [frame["event"] for frame in frames])
            self.assertEqual(code, 1008)
            errors = [frame for frame in frames if frame["event"] == "error"]
            self.assertTrue(errors)
            self.assertEqual({frame["payload"]["code"] for frame in errors}, {"UNAUTHENTICATED"})
            self.assertEqual(await self.message_count(), 0)
            current = await self.accepted(server, fresh)
            self.assertEqual((await self.send_message(current, request))["payload"]["status"], "persisted")
            await self.send_message(current, request)
            self.assertEqual(await self.message_count(), 1)
            await self.heartbeat(other)

    async def test_same_device_login_replacement_closes_the_old_socket_and_new_session_logout_closes_the_new_one(self):
        profile, first = await self.account("Replacement")
        async with self.realtime() as server:
            old = await self.accepted(server, first)
            other_access, _ = await self.device(profile)
            other = await self.accepted(server, other_access)
            replacement, replacement_cookie = await self.device(profile, first["device_id"])
            await self.assert_revoked(old)
            new = await self.accepted(server, replacement)
            await self.heartbeat(new)
            self.assertEqual(await self.logout(replacement_cookie), 204)
            await self.assert_revoked(new)
            await self.heartbeat(other)
            _, _, reply = await self.connect(server, replacement)
            self.assertEqual((reply["event"], reply["payload"]["code"]), ("error", "UNAUTHENTICATED"))

    async def test_concurrent_refresh_closes_old_socket_and_losing_replays_never_close_the_winner(self):
        profile, first = await self.account("Concurrent")
        cookie = self.api.last_cookie
        async with self.realtime() as server:
            old = await self.accepted(server, first)
            other_access, _ = await self.device(profile)
            other = await self.accepted(server, other_access)
            results = await asyncio.gather(*(self.refresh(cookie) for _ in range(4)))
            self.assertEqual(sorted(status for status, _, _ in results), [200, 401, 401, 401])
            _, winner, winner_cookie = next(result for result in results if result[0] == 200)
            await self.assert_revoked(old)
            current = await self.accepted(server, winner)
            self.assertEqual(winner["session_generation"], first["session_generation"] + 1)
            for _ in range(2):
                self.assertEqual((await self.refresh(cookie))[0], 401)
            await self.heartbeat(current)
            await self.heartbeat(other)
            self.assertEqual((await self.refresh(winner_cookie))[0], 200)
            await self.assert_revoked(current)

    async def test_logout_closes_socket_by_poll_when_redis_publish_is_denied(self):
        admin = Redis.from_url(os.environ["HINE_TEST_REDIS_URL"], decode_responses=True)
        self.addAsyncCleanup(admin.aclose)
        username, password = "hine_sec04_" + uuid.uuid4().hex, uuid.uuid4().hex
        await admin.execute_command("ACL", "SETUSER", username, "on", ">" + password, "~*", "&*", "+@all", "-publish")
        self.addAsyncCleanup(admin.execute_command, "ACL", "DELUSER", username)
        parsed = urlsplit(os.environ["HINE_TEST_REDIS_URL"])
        host = "[" + parsed.hostname + "]" if ":" in parsed.hostname else parsed.hostname
        restricted = urlunsplit((parsed.scheme, f"{username}:{password}@{host}:{parsed.port or 6379}", parsed.path, "", ""))
        profile, _ = await self.account("Denied publish")
        async with self.realtime(REDIS_URL=restricted) as server:
            revoked_access, revoked_cookie = await self.device(profile)
            survivor_access, _ = await self.device(profile)
            revoked, survivor = await self.accepted(server, revoked_access), await self.accepted(server, survivor_access)
            # The API still reports the committed logout and REST revokes immediately, whatever Redis does.
            self.assertEqual(await self.logout(revoked_cookie), 204)
            await self.assert_rejected(revoked_access)
            entry = (await self.invalidations())[-1]
            self.assertEqual(entry["reason"], "logout")
            notice = {"notice_id": str(uuid.uuid4()), "type": "session_invalidation", "committed_at": entry["committed_at"],
                      "invalidation_position": entry["position"], "session_invalidation": entry}
            token = Path(self.api.settings_env["INTERNAL_CALLER_TOKEN_SECRET_REF"]).read_text()
            async with self.client.post(str(server.make_url("/internal/v1/publishCommitted")), json={"notice": notice}, headers={"Authorization": "Bearer " + token}) as reply:
                body = await reply.json()
                self.assertEqual((reply.status, body["error"]["code"]), (503, "DEPENDENCY_UNAVAILABLE"))
                self.assertNotIn("data", body)
            # No notice reached Redis, so the committed-stream poll (5 s + 1 s hold; contract bound 15 s) closes it.
            await self.assert_revoked(revoked, 15)
            await self.heartbeat(survivor)
            await self.assert_accepted(survivor_access)
