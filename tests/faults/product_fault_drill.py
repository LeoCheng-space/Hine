#!/usr/bin/env python3
"""Owned native PostgreSQL/API/BA/Redis/Caddy fault and archive acceptance.

No existing service or database can be selected. This is local real-product
protocol evidence, not browser, cloud, HA, host-disk or zero-RPO certification.
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
import secrets
import signal
import socket
import ssl
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
API_SOURCE = ROOT / "backend/api/src"
BA_SOURCE = ROOT / "backend/realtime/src"
SCENARIOS = (
    ("PF01", "API SIGKILL and durable JWT/C1 recovery"),
    ("PF02", "BA SIGKILL and saved-cursor offline recovery"),
    ("PF03", "PostgreSQL outage, fail-closed freshness and restart"),
    ("PF04", "Redis reset, unknown presence and durable feed recovery"),
    ("PF05", "Lost real logout notification and independent device"),
    ("PF06", "Real committed write response loss and original C1 retry"),
    ("PF07", "Real transaction rollback without a message mapping"),
    ("PF08", "Private pg_dump and atomic owned-clone restore"),
)
LIMITS = [
    "LOCAL_REAL_PRODUCT_POSTGRESQL_NOT_FORMAL_VM_ACCEPTANCE",
    "PRIVATE_LOCAL_CA_NOT_PUBLIC_CERTIFICATE_OR_VM_PROOF",
    "PROTOCOL_RECEIPT_NOT_BROWSER_INDEXEDDB_OR_RENDERING",
    "OWNED_DEVELOPMENT_CLUSTER_SUPERUSER_NOT_PRODUCTION_CONFIGURATION",
    "NO_GCS_CLOUD_WRITES_OR_ATTACHMENT_PHYSICAL_ACCEPTANCE",
    "NO_MULTI_INSTANCE_HA_HOST_DISK_FAILURE_OR_ZERO_RPO_CLAIM",
    "ARCHIVED_SET_VALIDATION_NO_POST_BACKUP_ACKED_WRITES_OR_RPO_MEASUREMENT",
]
TABLES = ("users", "devices", "sessions", "authority_state", "session_invalidations",
          "contacts", "conversations", "memberships", "messages", "receipts",
          "feed_heads", "user_feed", "sync_cursors", "snapshots", "rest_cursors",
          "mutation_keys", "message_quota", "attachments", "schema_migrations", "auth_rate_limits")


class DrillFailure(Exception):
    """Only fixed runner-authored diagnostic codes cross the evidence boundary."""


class PrerequisiteFailure(Exception):
    pass


class Observation:
    def __init__(self, record):
        self.record = record

    def check(self, name, condition):
        self.record["checks"][name] = bool(condition)
        if not condition:
            raise DrillFailure(name.upper())

    def count(self, name, value):
        self.record["counts"][name] = int(value)

    def timing(self, name, started):
        self.record["timings_ms"][name] = milliseconds(started)


async def api_crash(c, o):
    a, b = await c.setup_accounts(o)
    cursor = await c.bootstrap(b, o)
    intent = c.intent()
    mid = await c.ack(a, intent, o)
    before = await c.persisted_state()
    started = time.monotonic()
    await c.stop(c.api_process, kill=True)
    await c.start_api()
    o.timing("api_sigkill_to_ready", started)
    o.check("postgresql_records_unchanged_after_api_sigkill", before == await c.persisted_state())
    await c.current_user(c.a, o)
    a = await c.connect(c.a, o)
    o.check("original_c1_same_m1_after_api_restart", await c.ack(a, intent, o) == mid)
    await c.recover(b, cursor, mid, o)
    await c.one_mapping(intent, mid, o)


async def ba_crash(c, o):
    a, b = await c.setup_accounts(o)
    cursor = await c.bootstrap(b, o)
    intent = c.intent()
    mid = await c.ack(a, intent, o)
    started = time.monotonic()
    await c.stop(c.ba_process, kill=True)
    await c.start_ba()
    o.timing("ba_sigkill_to_ready", started)
    a, b = await c.connect(c.a, o), await c.connect(c.b, o)
    offline = c.intent()
    await c.close_peer(b)
    offline_mid = await c.ack(a, offline, o)
    b = await c.connect(c.b, o)
    events = await c.recover(b, cursor, mid, o)
    o.check("offline_message_in_saved_cursor_feed", any(e.get("payload", {}).get("message_id") == offline_mid for e in events))
    o.check("ba_restart_original_c1_same_m1", await c.ack(a, intent, o) == mid)
    await c.one_mapping(intent, mid, o)


async def pg_outage(c, o):
    a, b = await c.setup_accounts(o)
    cursor = await c.bootstrap(b, o)
    baseline = c.intent()
    mid = await c.ack(a, baseline, o)
    intent = c.intent()
    outage_receiver_start = len(b.frames)
    started = time.monotonic()
    await c.stop(c.pg_process)
    stopped = time.monotonic()
    o.check("api_live_200_during_pg_outage", await c.health("api", "live") == 200)
    await c.wait_health("api", 503)
    o.check("api_ready_503_during_pg_outage", await c.health("api", "ready") == 503)
    await c.wait_health("ba", 503)
    fresh, request, response = await c.authenticate(c.a)
    o.check("new_w01_has_no_w02_when_pg_unavailable",
            response.get("event") == "error" and response.get("payload", {}).get("code") == "DEPENDENCY_UNAVAILABLE" and
            fresh.count("auth.accepted") == 0)
    request, reply = await a.request("message.send", intent["payload"], c.conversation)
    o.check("pg_outage_has_no_fake_ack", reply.get("event") == "error" and a.count("message.ack", request["event_id"]) == 0)
    o.check("pg_outage_write_dependency_error", reply.get("payload", {}).get("code") in {"DEPENDENCY_UNAVAILABLE", "OUTCOME_UNCONFIRMED"})
    await asyncio.sleep(max(0, 17 - (time.monotonic() - stopped)))
    stale_started = time.monotonic()
    stale_starts = [(peer, len(peer.frames)) for peer in (a, b)]
    o.check("authority_stale_retains_existing_valid_sockets", not a.closed.is_set() and not b.closed.is_set())
    for index, peer in enumerate((a, b)):
        nonce = str(uuid4())
        heartbeat, pong = await peer.request("heartbeat.ping", {"nonce": nonce})
        o.check("stale_w04_exact_nonce_and_correlation_" + str(index),
                pong.get("event") == "heartbeat.pong" and pong["payload"].get("nonce") == nonce and
                pong.get("correlation_id") == heartbeat["event_id"])
    blocked = (
        (a, "message.send", intent["payload"], c.conversation, "message.ack"),
        (b, "sync.bootstrap.request", {"reason": "first_login"}, None, "sync.bootstrap.page"),
        (b, "sync.request", {"cursor": cursor}, None, "sync.batch"),
    )
    for peer, event, payload, conversation, forbidden in blocked:
        request, reply = await peer.request(event, payload, conversation)
        o.check("authority_stale_rejects_" + event.replace(".", "_"),
                reply.get("event") == "error" and reply.get("payload", {}).get("code") == "DEPENDENCY_UNAVAILABLE")
        o.check("authority_stale_no_" + forbidden.replace(".", "_"),
                peer.count(forbidden, request["event_id"]) == 0)
    await asyncio.sleep(2)
    for index, (peer, offset) in enumerate(stale_starts):
        observed = peer.frames[offset:]
        o.count("stale_window_frames_" + str(index), len(observed))
        o.check("stale_window_only_w04_w17_" + str(index),
                all(frame["event"] in {"heartbeat.pong", "error"} for frame in observed))
    o.timing("actual_stale_no_data_control_only_window", stale_started)
    o.timing("postgres_stop_to_completed_stale_window", started)
    o.check("stale_api_live_200_ready_503", await c.health("api", "live") == 200 and
            await c.health("api", "ready") == 503)
    o.check("stale_ba_ready_503", await c.health("ba", "ready") == 503)
    o.check("pg_outage_no_receiver_w07_for_failed_private_intent",
            not any(frame.get("event") == "message.created" and
                    frame.get("conversation_id") == c.conversation and
                    frame.get("sender_id") == c.a["user_id"] and
                    frame.get("payload", {}).get("text") == intent["payload"]["text"]
                    for frame in b.frames[outage_receiver_start:]))
    restarted = time.monotonic()
    await c.start_pg()
    await c.wait_health("api", 200)
    await c.wait_health("ba", 200)
    o.timing("pg_restart_to_api_ba_ready", restarted)
    async with c.sql() as conn:
        failed_count = await conn.fetchval("SELECT count(*) FROM messages WHERE client_message_id=$1",
                                          __import__("uuid").UUID(intent["payload"]["client_message_id"]))
    o.check("outage_write_has_no_pg_mapping_before_retry", failed_count == 0)
    await c.current_user(c.a, o)
    o.check("same_existing_sockets_recover_without_reauthentication",
            not a.closed.is_set() and not b.closed.is_set() and
            a.count("auth.accepted") == 1 and b.count("auth.accepted") == 1)
    await c.recover(b, cursor, mid, o)
    new_mid = await c.ack(a, intent, o)
    o.check("new_intent_commits_only_after_pg_recovery", new_mid != mid)
    await c.one_mapping(intent, new_mid, o)
    o.check("baseline_c1_same_m1_after_pg_restart", await c.ack(a, baseline, o) == mid)
    # An independent short real API-issued TTL exercises actual expiry without
    # altering clocks, forging JWTs, modifying DB expiry or changing product code.
    async with Components(c.args, access_ttl_seconds=30) as expiry:
        expiring_a, expiring_b = await expiry.setup_accounts(o)
        async with expiry.sql() as conn:
            rows = await conn.fetch("SELECT device_id,access_expires_at FROM sessions WHERE device_id=ANY($1::text[])",
                                    [expiry.a["device_id"], expiry.b["device_id"]])
        stored = {row["device_id"]: row["access_expires_at"].timestamp() for row in rows}
        sessions = ((expiring_a, expiry.a), (expiring_b, expiry.b))
        o.check("short_real_jwt_expiry_matches_persisted_sessions",
                len(stored) == 2 and all(stored[session["device_id"]] == qa.timestamp(session["expires_at"]).timestamp()
                                         for _, session in sessions))
        await expiry.stop(expiry.pg_process)
        expired_started = time.monotonic()
        await asyncio.sleep(17)
        o.check("short_ttl_stale_sockets_retained_before_actual_expiry",
                all(time.time() < stored[session["device_id"]] and not peer.closed.is_set()
                    for peer, session in sessions))
        for peer, session in sessions:
            remaining = max(0, stored[session["device_id"]] - time.time())
            await peer.wait_closed(timeout=remaining + 2)
            o.check("actual_db_token_expiry_closes_socket",
                    time.time() >= stored[session["device_id"]])
        o.timing("short_real_ttl_pg_outage_to_expiry_closure", expired_started)
        o.count("actual_short_access_ttl_seconds", 30)


async def redis_outage(c, o):
    a, b = await c.setup_accounts(o)
    await c.contact(c.a, c.b["user_id"])
    cursor = await c.bootstrap(b, o)
    intent = c.intent()
    await c.stop(c.redis_process)
    await c.wait_health("ba", 503)
    o.check("api_stays_ready_without_redis", await c.health("api", "ready") == 200)
    status, result, _ = await c.http_request("GET", "/api/v1/contacts", c.a)
    o.check("redis_outage_presence_unknown", status == 200 and result["data"]["items"][0]["presence"] == "unknown")
    started = time.monotonic()
    mid = await c.ack(a, intent, o)
    o.timing("confirmed_bb_commit_ack_during_redis_outage", started)
    await c.one_mapping(intent, mid, o)
    await asyncio.sleep(1)
    o.check("redis_outage_no_live_fanout", not any(e.get("event") == "message.created" and e.get("payload", {}).get("message_id") == mid for e in b.frames))
    await c.start_redis()
    await c.wait_health("ba", 200)
    o.check("owned_redis_reset_has_no_old_presence_keys", await c.redis.dbsize() == 0)
    # Old sockets may re-register after the reset; close and reconnect explicitly.
    await c.close_peer(a)
    await c.close_peer(b)
    a, b = await c.connect(c.a, o), await c.connect(c.b, o)
    await c.recover(b, cursor, mid, o)
    o.check("redis_reset_original_c1_same_m1", await c.ack(a, intent, o) == mid)


async def lost_logout(c, o):
    a, _ = await c.setup_accounts(o)
    other, _ = await c.login(c.email_a, c.password)
    other_peer = await c.connect(other, o)
    c.notice_link.block.add("publishCommitted")
    started = time.monotonic()
    status, _, _ = await c.http_request("POST", "/api/v1/auth/logout", cookie=c.cookie_a)
    o.check("actual_a04_committed", status == 204)
    o.check("real_logout_publish_listener_cut", c.notice_link.blocked > 0)
    async with c.sql() as conn:
        row = await conn.fetchrow("SELECT s.revoked,i.reason FROM sessions s JOIN session_invalidations i USING(session_id) WHERE s.device_id=$1", c.a["device_id"])
        o.check("real_pg_logout_and_invalidation_committed", row is not None and row["revoked"] and row["reason"] == "logout")
    status, _, _ = await c.http_request("GET", "/api/v1/users/me", c.a)
    o.check("revoked_jwt_current_user_rejected", status == 401)
    await a.wait_closed(timeout=16)
    duration = milliseconds(started)
    o.record["timings_ms"]["lost_notify_to_actual_wss_revocation"] = duration
    o.check("lost_notify_revocation_within_15_seconds", duration <= 15000)
    o.check("lost_notify_w17_unauthenticated_observed", any(e.get("event") == "error" and e.get("payload", {}).get("code") == "UNAUTHENTICATED" for e in a.frames))
    await c.current_user(other, o)
    o.check("other_device_preserved", not other_peer.closed.is_set())
    await c.ack(other_peer, c.intent(), o)


async def committed_response_loss(c, o):
    a, b = await c.setup_accounts(o)
    cursor = await c.bootstrap(b, o)
    intent = c.intent()
    c.api_link.drop_write = True
    started = time.monotonic()
    request, reply = await a.request("message.send", intent["payload"], c.conversation)
    o.check("real_confirmed_200_dropped_after_commit", c.api_link.dropped == 1)
    o.check("unconfirmed_outcome_no_ack", reply.get("event") == "error" and reply.get("payload", {}).get("code") == "OUTCOME_UNCONFIRMED" and a.count("message.ack", request["event_id"]) == 0)
    async with c.sql() as conn:
        mid = str(await conn.fetchval("SELECT message_id FROM messages WHERE client_message_id=$1", __import__("uuid").UUID(intent["payload"]["client_message_id"])))
    o.check("original_c1_retry_confirms_original_m1", await c.ack(a, intent, o) == mid)
    o.timing("confirmed_response_loss_to_retry_ack", started)
    await c.one_mapping(intent, mid, o)
    await c.recover(b, cursor, mid, o)


async def transaction_rollback(c, o):
    a, _ = await c.setup_accounts(o)
    before = await c.persisted_state()
    async with c.sql() as conn:
        await conn.execute("""CREATE FUNCTION drill_reject_message() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'owned rollback barrier' USING ERRCODE='23514'; END $$;
            CREATE TRIGGER drill_reject_message BEFORE INSERT ON messages
            FOR EACH ROW EXECUTE FUNCTION drill_reject_message()""")
    intent = c.intent()
    request, reply = await a.request("message.send", intent["payload"], c.conversation)
    o.check("known_real_rollback_persistence_failed", reply.get("event") == "error" and reply.get("payload", {}).get("code") == "PERSISTENCE_FAILED")
    o.check("known_rollback_no_ack", a.count("message.ack", request["event_id"]) == 0)
    o.check("rollback_keeps_all_persisted_product_rows", before == await c.persisted_state())
    async with c.sql() as conn:
        await conn.execute("DROP TRIGGER drill_reject_message ON messages; DROP FUNCTION drill_reject_message()")
    await c.one_mapping(intent, await c.ack(a, intent, o), o)


async def archive_restore(c, o):
    a, b = await c.setup_accounts(o)
    cursor = await c.bootstrap(b, o)
    intent = c.intent()
    mid = await c.ack(a, intent, o)
    _, reply = await b.request("message.read", {"message_id": mid}, c.conversation)
    o.check("archived_read_receipt_acked", reply.get("event") == "receipt.ack" and reply["payload"].get("status") == "read")
    revoked, revoked_cookie = await c.login(c.email_a, c.password)
    status, _, _ = await c.http_request("POST", "/api/v1/auth/logout", cookie=revoked_cookie)
    o.check("archived_invalidation_committed", status == 204)
    original_history = await c.history(c.a)
    await c.close_all_peers()
    await c.stop(c.ba_process)
    await c.stop(c.api_process)
    async with c.sql(admin=True, database="postgres") as conn:
        connections = await conn.fetchval("SELECT count(*) FROM pg_stat_activity WHERE datname=$1", c.database)
    o.count("active_source_connections_before_dump", connections)
    o.check("actual_zero_connections_before_archive", connections == 0)
    expected = await c.persisted_state()
    for table in TABLES:
        o.count("archived_" + table, expected[table][0])
    started = time.monotonic()
    archive = c.directory / "private-product.dump"
    # pg_dump must create the file; private parent plus umask makes it private.
    await c.command("pg_dump", *c.pg_arguments(), "--format=custom", "--no-password", "--file", str(archive), c.database, timeout=45)
    archive.chmod(0o600)
    o.count("private_archive_bytes", archive.stat().st_size)
    o.check("archive_is_private", archive.stat().st_mode & 0o077 == 0)
    o.timing("actual_pg_dump", started)
    clone = "clone_" + secrets.token_hex(8)
    identifier(clone)
    await c.command("createdb", *c.pg_arguments(), "--no-password", "--owner", "drill_app", clone)
    async with c.sql(admin=True, database="postgres") as conn:
        active = await conn.fetchval("SELECT count(*) FROM pg_stat_activity WHERE datname=$1", clone)
    o.count("active_clone_connections_before_restore", active)
    o.check("actual_zero_connections_before_atomic_restore", active == 0)
    started = time.monotonic()
    await c.command("pg_restore", *c.pg_arguments(), "--no-password", "--exit-on-error", "--single-transaction", "--dbname", clone, str(archive), timeout=45)
    o.timing("actual_atomic_pg_restore", started)
    c.database = clone
    c.write_database_reference()
    o.check("every_archived_table_record_restored_exactly", expected == await c.persisted_state())
    await c.start_api()
    await c.start_ba()
    await c.current_user(c.a, o)
    await c.current_user(c.b, o)
    status, _, _ = await c.http_request("GET", "/api/v1/users/me", revoked)
    o.check("restored_revoked_session_stays_rejected", status == 401)
    o.check("a19_restored_message_public_ids_and_receipts_stable", original_history == await c.history(c.a))
    a, b = await c.connect(c.a, o), await c.connect(c.b, o)
    await c.bootstrap(a, o)
    restored_messages = [message for conversation in c.last_bootstrap_conversations
                         if conversation["id"] == c.conversation
                         for message in conversation["recent_messages"]]
    o.check("restored_w15_public_message_and_receipt_stable",
            len(restored_messages) == 1 and restored_messages[0] == original_history["data"]["items"][0])
    await c.recover(b, cursor, mid, o)
    o.check("restored_original_c1_same_m1", await c.ack(a, intent, o) == mid)
    await c.one_mapping(intent, mid, o)
    o.check("restored_receipt_remains_read", (await c.history(c.a))["data"]["items"][0]["receipt"]["status"] == "read")


def milliseconds(started):
    return round((time.monotonic() - started) * 1000, 3)


def identifier(value):
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", value):
        raise DrillFailure("OWNED_SQL_IDENTIFIER_INVALID")
    return '"' + value + '"'


def environment():
    allowed = ("PATH", "LD_LIBRARY_PATH", "LANG", "LC_ALL")
    result = {key: os.environ[key] for key in allowed if key in os.environ}
    result.update(PYTHONPATH=os.pathsep.join((str(API_SOURCE), str(BA_SOURCE))),
                  PYTHONDONTWRITEBYTECODE="1", PYTHONUNBUFFERED="1")
    return result


def private_file(path, content):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as target:
        target.write(content)


def owned_listener(child, port):
    """Inspect ONLY a recorded child's descriptors, never discover arbitrary PIDs."""
    if child is None or child.returncode is not None:
        return False
    process = Path("/proc") / str(child.pid)
    try:
        sockets = set()
        for descriptor in (process / "fd").iterdir():
            with contextlib.suppress(OSError):
                target = os.readlink(descriptor)
                if target.startswith("socket:[") and target.endswith("]"):
                    sockets.add(target[8:-1])
        for row in (process / "net/tcp").read_text().splitlines()[1:]:
            columns = row.split()
            if (len(columns) > 9 and columns[1] == f"0100007F:{port:04X}" and
                    columns[3] == "0A" and columns[9] in sockets):
                return True
    except OSError:
        pass
    return False


async def finish_shielded(task):
    interrupted = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            interrupted = True
    result = await task
    if interrupted:
        raise asyncio.CancelledError
    return result


class Peer:
    """Actual WSS frames retained only in private process memory."""
    def __init__(self, ws):
        self.ws = ws
        self.frames = []
        self.changed = asyncio.Event()
        self.closed = asyncio.Event()
        self.invalid = False
        self.reader = asyncio.create_task(self.read())
        self.heartbeat = None

    async def read(self):
        try:
            async for message in self.ws:
                if message.type != aiohttp.WSMsgType.TEXT:
                    break
                value = json.loads(message.data)
                qa.envelope(value)
                self.frames.append(value)
                self.changed.set()
        except (aiohttp.ClientError, OSError, ValueError, qa.ProtocolFailure):
            self.invalid = True
        finally:
            self.closed.set()
            self.changed.set()

    async def response(self, request, timeout=10):
        async with asyncio.timeout(timeout):
            while True:
                self.changed.clear()
                if self.invalid:
                    raise DrillFailure("ACTUAL_WSS_FRAME_INVALID")
                for value in self.frames:
                    if value.get("correlation_id") == request["event_id"]:
                        return value
                if self.closed.is_set():
                    raise DrillFailure("ACTUAL_WSS_RESPONSE_NOT_OBSERVED")
                await self.changed.wait()

    async def request(self, event, payload, conversation=None):
        request = qa.frame(event, payload, conversation)
        await self.ws.send_json(request)
        return request, await self.response(request)

    def count(self, event, correlation=None):
        return sum(value.get("event") == event and
                   (correlation is None or value.get("correlation_id") == correlation)
                   for value in self.frames)

    async def keepalive(self):
        try:
            while True:
                await asyncio.sleep(30)
                nonce = str(uuid4())
                _, reply = await self.request("heartbeat.ping", {"nonce": nonce})
                if reply.get("event") != "heartbeat.pong" or reply["payload"].get("nonce") != nonce:
                    raise DrillFailure("ACTUAL_HEARTBEAT_INVALID")
        except (DrillFailure, aiohttp.ClientError, TimeoutError):
            await self.ws.close()

    async def wait_closed(self, timeout=10):
        async with asyncio.timeout(timeout):
            await self.closed.wait()

    async def close(self):
        if self.heartbeat is not None:
            self.heartbeat.cancel()
            await asyncio.gather(self.heartbeat, return_exceptions=True)
        await self.ws.close()
        if not self.reader.done():
            self.reader.cancel()
        await asyncio.gather(self.reader, return_exceptions=True)


class Link:
    """Owned real-service forwarding fault, never a fabricated product response."""
    def __init__(self, client, target):
        self.client, self.target = client, target
        self.runner = None
        self.block = set()
        self.blocked = self.dropped = 0
        self.drop_write = False
        self.transports = set()

    async def forward(self, request):
        operation = request.match_info["operation"]
        transport = request.transport
        if transport is not None:
            self.transports.add(transport)
        if operation in self.block:
            self.blocked += 1
            if transport is not None:
                transport.abort()
            return web.Response(status=503)
        try:
            async with self.client.post(self.target + "/internal/v1/" + operation,
                    data=await request.read(),
                    headers={"Content-Type": "application/json",
                             "Authorization": request.headers.get("Authorization", "")},
                    allow_redirects=False) as response:
                content, status = await response.read(), response.status
            if operation == "persistIfAbsent" and status == 200 and self.drop_write:
                self.drop_write = False
                self.dropped += 1
                if transport is not None:
                    transport.abort()
                return web.Response(status=502)
            return web.Response(body=content, status=status, content_type="application/json")
        except (aiohttp.ClientError, OSError, TimeoutError):
            return web.Response(status=503)

    async def start(self):
        app = web.Application(client_max_size=1048576)
        app.router.add_post("/internal/v1/{operation}", self.forward)
        self.runner = web.AppRunner(app, access_log=None, shutdown_timeout=1)
        await self.runner.setup()
        await web.TCPSite(self.runner, "127.0.0.1", 0).start()
        self.url = f"http://127.0.0.1:{self.runner.addresses[0][1]}"

    async def close(self):
        for transport in self.transports:
            transport.abort()
        if self.runner is not None:
            await self.runner.cleanup()


class Components:
    def __init__(self, args, access_ttl_seconds=900):
        self.args = args
        self.access_ttl_seconds = access_ttl_seconds
        self.children, self.logs, self.peers = [], [], []
        self.temp = self.http = self.local_http = self.redis = None
        self.api_link = self.notice_link = None
        self.pg_process = self.api_process = self.ba_process = self.redis_process = None
        self.sockets = []
        self.database = "product_" + secrets.token_hex(8)
        self.password = secrets.token_urlsafe(36)
        self.admin_password = secrets.token_hex(32)
        self.app_password = secrets.token_hex(32)
        self.redis_password = secrets.token_hex(32)

    async def __aenter__(self):
        try:
            await self.start()
            return self
        except BaseException:
            await self.close()
            raise

    async def __aexit__(self, *unused):
        await self.close()

    def port(self):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        self.sockets.append(listener)
        return listener.getsockname()[1]

    def release_port(self, port):
        for listener in tuple(self.sockets):
            if listener.getsockname()[1] == port:
                listener.close()
                self.sockets.remove(listener)

    async def spawn(self, label, *command, env=None, capture=False):
        log_path = self.directory / (label + "-" + secrets.token_hex(8) + ".log")
        log = os.fdopen(os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb")
        self.logs.append(log)

        async def launch():
            child = await asyncio.create_subprocess_exec(
                *command, cwd=ROOT, env=env or environment(),
                stdin=asyncio.subprocess.DEVNULL, start_new_session=True,
                stdout=asyncio.subprocess.PIPE if capture else log, stderr=log)
            self.children.append(child)
            return child

        return await finish_shielded(asyncio.create_task(launch()))

    async def stop(self, child, kill=False):
        if child is None or child.returncode is not None:
            return
        with contextlib.suppress(ProcessLookupError):
            if child is self.pg_process:
                child.send_signal(signal.SIGINT)
            else:
                os.killpg(child.pid, signal.SIGKILL if kill else signal.SIGTERM)
        try:
            async with asyncio.timeout(8):
                await child.wait()
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                if child is self.pg_process:
                    child.send_signal(signal.SIGQUIT)
                else:
                    os.killpg(child.pid, signal.SIGKILL)
            async with asyncio.timeout(8):
                await child.wait()

    async def run_command(self, label, command, env=None, timeout=20, capture=False):
        child = await self.spawn(label, *command, env=env, capture=capture)
        try:
            async with asyncio.timeout(timeout):
                output, _ = await child.communicate()
        finally:
            await self.stop(child)
        if child.returncode != 0:
            raise DrillFailure("OWNED_NATIVE_COMMAND_FAILED")
        if output is not None and len(output) > 65536:
            raise DrillFailure("NATIVE_METADATA_TOO_LARGE")
        return output

    async def command(self, name, *arguments, timeout=20):
        return await self.run_command(name, [str(Path(self.args.postgres_bin) / name), *arguments],
                                      env=self.pg_env, timeout=timeout)

    def pg_arguments(self):
        return ("--host", str(self.pg_socket), "--port", str(self.pg_port), "--username", "drill_admin")

    @contextlib.asynccontextmanager
    async def sql(self, admin=False, database=None):
        conn = await asyncpg.connect(host=str(self.pg_socket), port=self.pg_port,
            user="drill_admin" if admin else "drill_app",
            password=self.admin_password if admin else self.app_password,
            database=database or self.database, timeout=3, command_timeout=10)
        try:
            yield conn
        finally:
            await finish_shielded(asyncio.create_task(conn.close(timeout=3)))

    def write_database_reference(self):
        content = (f"postgresql://drill_app:{quote(self.app_password, safe='')}@"
                   f"127.0.0.1:{self.pg_port}/{self.database}")
        path = self.directory / ("database-" + secrets.token_hex(8))
        private_file(path, content)
        self.api_env["DATABASE_URL_SECRET_REF"] = str(path)

    async def start(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hine-product-fault-")
        self.directory = Path(self.temp.name)
        self.directory.chmod(0o700)
        self.pg_data, self.pg_socket = self.directory / "pgdata", self.directory / "pgsocket"
        self.pg_socket.mkdir(mode=0o700)
        self.pg_port, self.redis_port, self.api_port, self.ba_port, self.tls_port = [self.port() for _ in range(5)]
        self.api_url = f"http://127.0.0.1:{self.api_port}"
        self.ba_url = f"http://127.0.0.1:{self.ba_port}"
        self.origin = f"https://localhost:{self.tls_port}"
        self.local_http = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=8), trust_env=False,
            cookie_jar=aiohttp.DummyCookieJar())
        self.api_link, self.notice_link = Link(self.local_http, self.api_url), Link(self.local_http, self.ba_url)
        await self.api_link.start()
        await self.notice_link.start()
        for name, value in (("admin-password", self.admin_password), ("jwt", secrets.token_urlsafe(48)),
                            ("api-token", secrets.token_urlsafe(48)), ("ba-token", secrets.token_urlsafe(48))):
            private_file(self.directory / name, value)
        self.pg_env = environment()
        private_file(self.directory / "pgpass",
                     f"*:{self.pg_port}:*:drill_admin:{self.admin_password}\n")
        self.pg_env["PGPASSFILE"] = str(self.directory / "pgpass")
        await self.command("initdb", "--pgdata", str(self.pg_data), "--username", "drill_admin",
                           "--pwfile", str(self.directory / "admin-password"),
                           "--auth-local=scram-sha-256", "--auth-host=scram-sha-256",
                           "--encoding=UTF8", "--no-locale", timeout=45)
        await self.start_pg()
        async with self.sql(admin=True, database="postgres") as conn:
            # Generated hex credentials never enter argv, diagnostics or reports.
            await conn.execute("CREATE ROLE drill_app LOGIN PASSWORD '" + self.app_password + "'")
            if not await conn.fetchval("SELECT rolpassword LIKE 'SCRAM-SHA-256$%' FROM pg_authid WHERE rolname='drill_app'"):
                raise DrillFailure("OWNED_APP_ROLE_SCRAM_NOT_PROVEN")
        await self.command("createdb", *self.pg_arguments(), "--no-password", "--owner", "drill_app", self.database)
        self.api_env = environment()
        self.api_env.update({
            "HINE_ENV": "test", "API_HOST": "127.0.0.1", "API_PORT": str(self.api_port),
            "PUBLIC_ORIGIN": self.origin, "JWT_ISSUER": "hine-owned-product-drill",
            "JWT_AUDIENCE": "hine-owned-product-clients",
            "JWT_SIGNING_KEY_SECRET_REF": str(self.directory / "jwt"),
            "REALTIME_INTERNAL_URL": self.notice_link.url,
            "INTERNAL_CALLER_TOKEN_SECRET_REF": str(self.directory / "api-token"),
            "INTERNAL_ALLOWED_CALLERS": json.dumps({"realtime": str(self.directory / "ba-token")}),
            "SYNC_PAGE_LIMIT": "100", "SYNC_SCAN_LIMIT": "1000",
            "INVALIDATION_RETENTION_SECONDS": "900",
            "ACCESS_TTL_SECONDS": str(self.access_ttl_seconds),
        })
        self.write_database_reference()
        private_file(self.directory / "redis-url",
                     f"redis://:{self.redis_password}@127.0.0.1:{self.redis_port}/0")
        self.redis_socket = self.directory / "redis.sock"
        private_file(self.directory / "redis.conf",
            f"bind 127.0.0.1\nport {self.redis_port}\nprotected-mode yes\n"
            f"requirepass {self.redis_password}\nunixsocket {self.redis_socket}\nunixsocketperm 700\n"
            f'dir {self.directory}\nsave ""\nappendonly no\ndaemonize no\nloglevel warning\n')
        self.ba_env = environment()
        self.ba_env.update({
            "HINE_ENV": "test", "REALTIME_HOST": "127.0.0.1", "REALTIME_PORT": str(self.ba_port),
            "API_INTERNAL_URL": self.api_link.url,
            "INTERNAL_CALLER_TOKEN_SECRET_REF": str(self.directory / "ba-token"),
            "INTERNAL_ALLOWED_CALLERS": json.dumps({"api": str(self.directory / "api-token")}),
            "REDIS_URL_SECRET_REF": str(self.directory / "redis-url"),
            "REALTIME_REDIS_PREFIX": "hine:owned-product-drill:" + secrets.token_hex(16),
            "INVALIDATION_POLL_SECONDS": "5", "INVALIDATION_STALE_SECONDS": "15",
            "NOTICE_CATCHUP_HOLD_MS": "1000", "HEARTBEAT_INTERVAL_SECONDS": "30",
            "HEARTBEAT_TIMEOUT_SECONDS": "90", "SYNC_PAGE_LIMIT": "100",
        })
        self.redis = Redis(unix_socket_path=str(self.redis_socket), password=self.redis_password,
                           decode_responses=True, socket_connect_timeout=1, socket_timeout=1,
                           retry=Retry(NoBackoff(), 0))
        await self.start_redis()
        await self.run_command("actual-api-migrate", [self.args.python, "-m", "hine_api", "migrate"],
                               env=self.api_env, timeout=30)
        await self.start_api()
        await self.start_ba()
        await self.start_tls()

    async def start_pg(self):
        self.release_port(self.pg_port)
        self.pg_process = await self.spawn("postgres", str(Path(self.args.postgres_bin) / "postgres"),
            "-D", str(self.pg_data), "-p", str(self.pg_port), "-h", "127.0.0.1",
            "-k", str(self.pg_socket), "-c", "password_encryption=scram-sha-256",
            "-c", "fsync=on", "-c", "synchronous_commit=on", env=self.pg_env)
        async with asyncio.timeout(20):
            while True:
                if self.pg_process.returncode is not None:
                    raise DrillFailure("OWNED_POSTGRES_EXITED")
                try:
                    async with self.sql(admin=True, database="postgres") as conn:
                        version = await conn.fetchval("SHOW server_version_num")
                        pid = (self.pg_data / "postmaster.pid").read_text().splitlines()[0]
                        data_directory = await conn.fetchval("SHOW data_directory")
                        if (int(pid) != self.pg_process.pid or Path(data_directory) != self.pg_data or
                                int(version) // 10000 != 17 or not owned_listener(self.pg_process, self.pg_port)):
                            raise DrillFailure("OWNED_POSTGRES_ATTESTATION_FAILED")
                        return
                except (OSError, asyncpg.PostgresError, TimeoutError):
                    await asyncio.sleep(0.1)

    async def start_redis(self):
        self.release_port(self.redis_port)
        self.redis_process = await self.spawn("redis", self.args.redis_server, str(self.directory / "redis.conf"))
        async with asyncio.timeout(15):
            while True:
                if self.redis_process.returncode is not None:
                    raise DrillFailure("OWNED_REDIS_EXITED")
                try:
                    if await self.redis.ping():
                        info = await self.redis.info("server")
                        if (int(info["process_id"]) != self.redis_process.pid or
                                not owned_listener(self.redis_process, self.redis_port)):
                            raise DrillFailure("OWNED_REDIS_ATTESTATION_FAILED")
                        return
                except (RedisError, OSError, TimeoutError):
                    await asyncio.sleep(0.1)

    async def start_api(self):
        self.release_port(self.api_port)
        self.api_process = await self.spawn("api", self.args.python, "-m", "hine_api", env=self.api_env)
        await self.wait_health("api", 200)

    async def start_ba(self):
        self.release_port(self.ba_port)
        self.ba_process = await self.spawn("ba", self.args.python, "-m", "hine_realtime", env=self.ba_env)
        await self.wait_health("ba", 200)

    async def health(self, service, kind):
        child = self.api_process if service == "api" else self.ba_process
        port = self.api_port if service == "api" else self.ba_port
        if not owned_listener(child, port):
            raise DrillFailure("OWNED_PRODUCT_LISTENER_NOT_ATTESTED")
        url = self.api_url if service == "api" else self.ba_url
        async with self.local_http.get(url + "/health/" + kind) as reply:
            return reply.status

    async def wait_health(self, service, status):
        async with asyncio.timeout(25):
            while True:
                child = self.api_process if service == "api" else self.ba_process
                port = self.api_port if service == "api" else self.ba_port
                if child.returncode is not None:
                    raise DrillFailure("OWNED_PRODUCT_CHILD_EXITED")
                try:
                    if owned_listener(child, port) and await self.health(service, "ready") == status:
                        return
                except (aiohttp.ClientError, OSError, TimeoutError):
                    pass
                await asyncio.sleep(0.1)

    async def start_tls(self):
        config = ("{\n admin off\n skip_install_trust\n auto_https disable_redirects\n}\n"
                  f"https://localhost:{self.tls_port} {{\n bind 127.0.0.1\n tls internal\n"
                  f" handle /api/v1/* {{\n  reverse_proxy 127.0.0.1:{self.api_port}\n }}\n"
                  f" handle /ws/v1 {{\n  reverse_proxy 127.0.0.1:{self.ba_port}\n }}\n")
        if self.args.web_root:
            config += f" handle {{\n  root * {json.dumps(self.args.web_root)}\n  try_files {{path}} /index.html\n  file_server\n }}\n"
        else:
            config += ' handle {\n  respond \"Owned product protocol drill\" 200\n }\n'
        config += "}\n"
        private_file(self.directory / "Caddyfile", config)
        caddy_env = environment()
        for name in ("HOME", "XDG_DATA_HOME", "XDG_CONFIG_HOME"):
            caddy_env[name] = str(self.directory / name.lower())
            Path(caddy_env[name]).mkdir(mode=0o700)
        self.release_port(self.tls_port)
        self.caddy_process = await self.spawn("caddy", self.args.caddy, "run", "--config",
                                            str(self.directory / "Caddyfile"), "--adapter", "caddyfile", env=caddy_env)
        root = Path(caddy_env["XDG_DATA_HOME"]) / "caddy/pki/authorities/local/root.crt"
        async with asyncio.timeout(25):
            while not root.is_file() or not owned_listener(self.caddy_process, self.tls_port):
                if self.caddy_process.returncode is not None:
                    raise DrillFailure("OWNED_CADDY_EXITED")
                await asyncio.sleep(0.1)
        tls = ssl.create_default_context(cafile=str(root))
        self.http = aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=tls),
            timeout=aiohttp.ClientTimeout(total=12), trust_env=False,
            cookie_jar=aiohttp.DummyCookieJar())
        async with self.http.get(self.origin + "/") as reply:
            if reply.status != 200:
                raise DrillFailure("OWNED_TLS_VERIFIED_REQUEST_FAILED")

    async def http_request(self, method, path, session=None, body=None, cookie=None):
        headers = {"Origin": self.origin}
        if session is not None:
            headers["Authorization"] = "Bearer " + session["access_token"]
        if cookie is not None:
            headers["Cookie"] = cookie
        async with self.http.request(method, self.origin + path, headers=headers,
                                     json=body, allow_redirects=False) as reply:
            result = None if reply.status == 204 else await reply.json()
            cookie = reply.headers.get("Set-Cookie", "").split(";", 1)[0]
            return reply.status, result, cookie

    async def login(self, email, password):
        status, result, cookie = await self.http_request("POST", "/api/v1/auth/login",
            body={"email": email, "password": password, "device_id": None})
        if status != 200:
            raise DrillFailure("REAL_LOGIN_FAILED")
        qa.validate_session(result["data"])
        return result["data"], cookie

    async def setup_accounts(self, o):
        for label in ("a", "b"):
            email = secrets.token_hex(12) + "@owned.product.test"
            status, profile, _ = await self.http_request("POST", "/api/v1/auth/register",
                body={"email": email, "password": self.password, "display_name": "Owned drill " + label})
            o.check("real_registration_" + label, status == 201)
            session, cookie = await self.login(email, self.password)
            o.check("public_user_id_matches_real_session_" + label, profile["data"]["id"] == session["user_id"])
            setattr(self, "email_" + label, email)
            setattr(self, "cookie_" + label, cookie)
            setattr(self, label, session)
        status, result, _ = await self.http_request("POST", "/api/v1/conversations/direct", self.a,
                                                   body={"peer_user_id": self.b["user_id"]})
        o.check("real_direct_conversation", status == 201)
        self.conversation = result["data"]["id"]
        o.check("private_ca_verified_https_and_wss", self.http.connector._ssl.verify_mode == ssl.CERT_REQUIRED)
        return await self.connect(self.a, o), await self.connect(self.b, o)

    async def authenticate(self, session):
        ws = await self.http.ws_connect(self.origin.replace("https:", "wss:") + "/ws/v1",
            headers={"Origin": self.origin}, timeout=aiohttp.ClientWSTimeout(ws_close=2))
        peer = Peer(ws)
        self.peers.append(peer)
        request, reply = await peer.request("auth.authenticate", {
            "access_token": session["access_token"], "device_id": session["device_id"]})
        return peer, request, reply

    async def connect(self, session, o):
        peer, _, reply = await self.authenticate(session)
        o.check("actual_w02_binding", reply.get("event") == "auth.accepted" and
                all(reply.get("payload", {}).get(k) == session[k] for k in
                    ("user_id", "device_id", "expires_at", "session_generation")))
        peer.heartbeat = asyncio.create_task(peer.keepalive())
        return peer

    async def current_user(self, session, o):
        status, result, _ = await self.http_request("GET", "/api/v1/users/me", session)
        o.check("actual_jwt_session_and_public_id_preserved", status == 200 and result["data"]["id"] == session["user_id"])

    async def contact(self, session, user_id):
        status, _, _ = await self.http_request("POST", "/api/v1/contacts", session, body={"user_id": user_id})
        if status != 201:
            raise DrillFailure("REAL_CONTACT_CREATE_FAILED")

    def intent(self):
        return {"payload": {"client_message_id": str(uuid4()), "type": "text",
                            "text": "Private owned native product drill " + secrets.token_hex(8)}}

    async def ack(self, peer, intent, o):
        request, reply = await peer.request("message.send", intent["payload"], self.conversation)
        payload = reply.get("payload", {})
        o.check("actual_w06_confirmed_persistence", reply.get("event") == "message.ack" and
                payload.get("status") == "persisted" and
                payload.get("client_message_id") == intent["payload"]["client_message_id"] and
                peer.count("message.ack", request["event_id"]) == 1)
        qa.uuid(payload.get("message_id"))
        return payload["message_id"]

    async def bootstrap(self, peer, o):
        request, snapshot, cursor = {"reason": "first_login"}, None, None
        tokens = set()
        self.last_bootstrap_conversations = []
        for _ in range(100):
            _, reply = await peer.request("sync.bootstrap.request", request)
            payload = reply.get("payload", {})
            o.check("actual_w15_bootstrap", reply.get("event") == "sync.bootstrap.page")
            if snapshot is None:
                snapshot, cursor = payload["snapshot_id"], payload["start_cursor"]
            o.check("frozen_bootstrap_cursor_stable", payload["snapshot_id"] == snapshot and payload["start_cursor"] == cursor)
            self.last_bootstrap_conversations.extend(payload["conversations"])
            if not payload["has_more"]:
                o.check("terminal_bootstrap_no_continuation", payload["next_page_token"] is None)
                return cursor
            token = payload["next_page_token"]
            o.check("bootstrap_continuation_advances", isinstance(token, str) and token not in tokens)
            tokens.add(token)
            request = {"reason": "first_login", "snapshot_id": snapshot, "page_token": token}
        raise DrillFailure("BOOTSTRAP_BOUND_EXCEEDED")

    async def recover(self, peer, cursor, mid, o):
        events, boundary = [], None
        for _ in range(100):
            request = {"cursor": cursor}
            if boundary is not None:
                request["snapshot_boundary"] = boundary
            _, reply = await peer.request("sync.request", request)
            o.check("actual_saved_cursor_w16", reply.get("event") == "sync.batch")
            payload = reply["payload"]
            events.extend(payload["events"])
            cursor, boundary = payload["next_cursor"], payload["snapshot_boundary"]
            if not payload["has_more"]:
                matching = [e for e in events if e.get("event") == "message.created" and e.get("payload", {}).get("message_id") == mid]
                o.count("saved_cursor_matching_messages", len(matching))
                o.check("saved_cursor_recovers_exactly_one_original_m1", len(matching) == 1)
                async with self.sql() as conn:
                    row = await conn.fetchrow("SELECT event_id,payload FROM messages WHERE message_id=$1", __import__("uuid").UUID(mid))
                o.check("feed_stable_original_event_and_private_body", matching[0]["event_id"] == str(row["event_id"]) and matching[0]["payload"]["text"] == json.loads(row["payload"])["text"])
                o.check("receiver_feed_has_no_sender_c1", "client_message_id" not in matching[0]["payload"])
                return events
        raise DrillFailure("SYNC_BOUND_EXCEEDED")

    async def one_mapping(self, intent, mid, o):
        async with self.sql() as conn:
            count = await conn.fetchval("SELECT count(*) FROM messages WHERE client_message_id=$1", __import__("uuid").UUID(intent["payload"]["client_message_id"]))
            feed = await conn.fetchval("SELECT count(*) FROM user_feed WHERE envelope->>'event'='message.created' AND envelope->'payload'->>'message_id'=$1", mid)
        o.count("pg_original_c1_message_count", count)
        o.count("pg_original_m1_feed_count", feed)
        o.check("one_actual_pg_c1_mapping", count == 1)
        o.check("one_pg_message_created_per_recipient", feed == 2)

    async def history(self, session):
        status, result, _ = await self.http_request("GET", "/api/v1/conversations/" + quote(self.conversation, safe="") + "/messages", session)
        if status != 200:
            raise DrillFailure("ACTUAL_A19_HISTORY_FAILED")
        return result

    async def persisted_state(self):
        state = {}
        async with self.sql() as conn:
            for table in TABLES:
                rows = await conn.fetch(f'SELECT to_jsonb(t)::text AS row FROM {identifier(table)} t ORDER BY to_jsonb(t)::text COLLATE "C"')
                digest = hashlib.sha256()
                for row in rows:
                    digest.update(row["row"].encode())
                    digest.update(b"\n")
                state[table] = (len(rows), digest.digest())
        return state

    async def close_peer(self, peer):
        await peer.close()

    async def close_all_peers(self):
        for peer in self.peers:
            await peer.close()

    async def cleanup_owned(self):
        failed = False
        actions = [peer.close for peer in self.peers]
        actions += [lambda child=child: self.stop(child) for child in reversed(self.children)]
        actions += [resource.close for resource in (self.api_link, self.notice_link, self.http, self.local_http) if resource is not None]
        if self.redis is not None:
            actions.append(self.redis.aclose)
        for action in actions:
            result, = await asyncio.gather(action(), return_exceptions=True)
            failed |= isinstance(result, BaseException)
        for listener in self.sockets:
            listener.close()
        for log in self.logs:
            log.close()
        if self.temp is not None:
            self.temp.cleanup()
        if failed:
            raise DrillFailure("OWNED_RESOURCE_CLEANUP_FAILED")

    async def close(self):
        await finish_shielded(asyncio.create_task(self.cleanup_owned()))


async def prerequisites(args, evidence):
    if sys.version_info < (3, 12) or os.geteuid() == 0 or platform.system() != "Linux":
        raise PrerequisiteFailure("NONROOT_LINUX_PYTHON_3_12_REQUIRED")
    tools = {}
    for name in ("postgres_bin", "redis_server", "caddy", "python"):
        value = getattr(args, name)
        if not value:
            raise PrerequisiteFailure("REQUIRED_NATIVE_TOOL_ARGUMENT_MISSING")
        path = Path(value)
        if name == "postgres_bin":
            for executable in ("initdb", "postgres", "pg_ctl", "createdb", "pg_dump", "pg_restore"):
                if not (path / executable).is_file() or not os.access(path / executable, os.X_OK):
                    raise PrerequisiteFailure("REQUIRED_POSTGRES_EXECUTABLE_UNAVAILABLE")
        elif not path.is_file() or not os.access(path, os.X_OK):
            raise PrerequisiteFailure("REQUIRED_NATIVE_EXECUTABLE_UNAVAILABLE")
        # Preserve supplied executable spelling, including venv and Redis argv[0].
        setattr(args, name, str(path.absolute()))
    if args.web_root:
        root = Path(args.web_root)
        if not root.is_dir() or not (root / "index.html").is_file():
            raise PrerequisiteFailure("EXISTING_REAL_WEB_BUILD_REQUIRED")
        args.web_root = str(root.absolute())
    if not all(path.is_file() for path in (API_SOURCE / "hine_api/__main__.py",
            BA_SOURCE / "hine_realtime/__main__.py", ROOT / "tests/load/protocol.py")):
        raise PrerequisiteFailure("ACTUAL_PRODUCT_OR_QA_SOURCE_UNAVAILABLE")
    try:
        global aiohttp, asyncpg, web, Redis, RedisError, Retry, NoBackoff, qa
        import aiohttp
        import asyncpg
        from aiohttp import web
        from redis.asyncio import Redis
        from redis.asyncio.retry import Retry
        from redis.backoff import NoBackoff
        from redis.exceptions import RedisError
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(ROOT / "tests/load"))
        import protocol as qa
    except ImportError:
        raise PrerequisiteFailure("RUNNER_REAL_PRODUCT_DEPENDENCIES_UNAVAILABLE") from None
    c = Components(args)
    c.temp = tempfile.TemporaryDirectory(prefix="hine-product-prerequisite-")
    c.directory = Path(c.temp.name)
    c.directory.chmod(0o700)
    try:
        for name in ("initdb", "postgres", "pg_ctl", "createdb", "pg_dump", "pg_restore"):
            raw = await c.run_command("version", [str(Path(args.postgres_bin) / name), "--version"], capture=True)
            match = re.search(rb"\(PostgreSQL\) (17\.[0-9]+(?:\.[0-9]+)?)", raw)
            if match is None:
                raise PrerequisiteFailure("POSTGRES_17_TOOL_VERSION_REQUIRED")
            tools[name] = match.group(1).decode("ascii")
        if len(set(tools.values())) != 1:
            raise PrerequisiteFailure("POSTGRES_TOOL_VERSION_MISMATCH")
        raw = await c.run_command("version", [args.redis_server, "--version"], capture=True)
        match = re.search(rb"Redis server v=([0-9]+\.[0-9]+\.[0-9]+)", raw)
        if match is None:
            raise PrerequisiteFailure("REDIS_VERSION_UNAVAILABLE")
        tools["redis_server"] = match.group(1).decode("ascii")
        raw = await c.run_command("version", [args.caddy, "version"], capture=True)
        match = re.match(rb"v?([0-9]+\.[0-9]+\.[0-9]+)", raw)
        if match is None:
            raise PrerequisiteFailure("CADDY_VERSION_UNAVAILABLE")
        tools["caddy"] = match.group(1).decode("ascii")
        raw = await c.run_command("python-versions", [args.python, "-c",
            ("import sys,json,importlib.metadata as m; print(json.dumps({'python':list(sys.version_info[:3]),"
             "'aiohttp':m.version('aiohttp'),'asyncpg':m.version('asyncpg'),'PyJWT':m.version('PyJWT'),"
             "'redis':m.version('redis'),'google-cloud-storage':m.version('google-cloud-storage')}))")],
            capture=True)
        versions = json.loads(raw)
        if tuple(versions["python"]) < (3, 12):
            raise PrerequisiteFailure("PRODUCT_CHILD_PYTHON_3_12_REQUIRED")
        for name in ("aiohttp", "asyncpg", "PyJWT", "redis", "google-cloud-storage"):
            if not re.fullmatch(r"[A-Za-z0-9.+_-]{1,64}", versions[name]):
                raise PrerequisiteFailure("DEPENDENCY_VERSION_INVALID")
        tools["product_python"] = ".".join(str(part) for part in versions.pop("python"))
        tools.update(versions)
    except (DrillFailure, OSError, TimeoutError, KeyError, TypeError, ValueError):
        raise PrerequisiteFailure("NATIVE_PREREQUISITE_METADATA_FAILED") from None
    finally:
        await c.close()
    paths = sorted((API_SOURCE / "hine_api").glob("*.py"))
    paths += sorted((BA_SOURCE / "hine_realtime").glob("*.py"))
    paths += sorted((ROOT / "backend/api/migrations").glob("*.sql"))
    paths += [ROOT / "backend/api/requirements.txt", ROOT / "backend/realtime/requirements.txt",
              ROOT / "tests/load/protocol.py", Path(__file__).resolve()]
    evidence["provenance"] = {
        "analysis_baseline": "fc9eb08ca484ef9495d98afb830e1f10ee5973d7",
        "source_sha256": {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in paths},
        "native_executable_sha256": {
            **{name: hashlib.sha256((Path(args.postgres_bin) / name).read_bytes()).hexdigest()
               for name in ("initdb", "postgres", "pg_ctl", "createdb", "pg_dump", "pg_restore")},
            **{name: hashlib.sha256(Path(getattr(args, name)).read_bytes()).hexdigest()
               for name in ("redis_server", "caddy", "python")},
        },
        "authority": "UNMODIFIED_REAL_PRODUCT_MODULES_WITH_REAL_SQL_MIGRATIONS",
        "network_faults": "OWNED_PRIVATE_HTTP_FORWARDERS_REAL_RESPONSES_ONLY",
    }
    evidence["environment"] = {"os": platform.system(), "release": platform.release(),
        "architecture": platform.machine(), "runner_python": platform.python_version(),
        "runner_aiohttp": importlib.metadata.version("aiohttp"),
        "runner_asyncpg": importlib.metadata.version("asyncpg"), "tools": tools}


async def execute(args, evidence):
    await prerequisites(args, evidence)
    functions = (api_crash, ba_crash, pg_outage, redis_outage, lost_logout,
                 committed_response_loss, transaction_rollback, archive_restore)
    failed = False
    for record, scenario in zip(evidence["scenarios"], functions):
        if record["id"] not in args.case:
            continue
        record["status"] = "RUNNING"
        started = time.monotonic()
        try:
            async with asyncio.timeout(180):
                async with Components(args) as c:
                    await scenario(c, Observation(record))
            record["status"] = "PASS"
        except asyncio.CancelledError:
            record["status"] = "FAIL"
            record["failure_code"] = "RUN_INTERRUPTED"
            raise
        except DrillFailure as failure:
            record["status"] = "FAIL"
            record["failure_code"] = str(failure)
            failed = True
        except TimeoutError:
            record["status"] = "FAIL"
            record["failure_code"] = "BOUNDED_OBSERVATION_OR_CLEANUP_TIMEOUT"
            failed = True
        except Exception:  # noqa: BLE001 - Quarantine private service/SQL exception details at evidence boundary.
            record["status"] = "FAIL"
            record["failure_code"] = "REAL_PRODUCT_OR_RUNNER_ERROR"
            failed = True
        finally:
            record["timings_ms"]["scenario_setup_fault_verification_cleanup"] = milliseconds(started)
    return 1 if failed else 0


async def interruptible_execute(args, evidence):
    loop = asyncio.get_running_loop()
    task = asyncio.current_task()
    interrupted = False

    def interrupt():
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            task.cancel()

    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, interrupt)
    try:
        result, = await asyncio.gather(execute(args, evidence), return_exceptions=True)
        return result
    finally:
        for signum in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(signum)


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--postgres-bin", help="Required native PostgreSQL 17 tool directory")
    parser.add_argument("--redis-server", help="Required native Redis executable, not a service")
    parser.add_argument("--caddy", help="Required native Caddy executable")
    parser.add_argument("--python", help="Required Python >=3.12 with actual product dependencies")
    parser.add_argument("--output", help="Required NEW safe JSON path; never overwritten")
    parser.add_argument("--web-root", help="Optional existing real frontend build directory")
    parser.add_argument("--case", action="append", choices=[item[0] for item in SCENARIOS],
                        help="Select a case; repeatable; omitted means all eight cases")
    args = parser.parse_args()
    args.case = args.case or [item[0] for item in SCENARIOS]
    if not args.output:
        print("OUTPUT_ARGUMENT_REQUIRED", file=sys.stderr)
        return 2
    if os.path.lexists(args.output):
        print("OUTPUT_ALREADY_EXISTS", file=sys.stderr)
        return 2
    try:
        fd, temporary = tempfile.mkstemp(dir=Path(args.output).absolute().parent,
                                        prefix=".hine-product-evidence-")
    except OSError:
        print("OUTPUT_CANNOT_BE_CREATED", file=sys.stderr)
        return 2
    evidence = {
        "schema_version": 1, "started_utc": utc_now(), "completed_utc": None,
        "scope": "LOCAL_REAL_PRODUCT_POSTGRESQL", "status": "NOT_EXERCISED",
        "configuration": {"selected_cases": args.case, "owned_fresh_cluster_per_case": True,
            "postgres_host_authentication": "scram-sha-256",
            "postgres_fsync": True, "postgres_synchronous_commit": True,
            "redis_persistence": False, "invalidation_poll_seconds": 5,
            "invalidation_stale_seconds": 15, "tls_hostname_verification": True,
            "tls_ca": "OWNED_PRIVATE_CADDY_CA", "existing_real_web_build": bool(args.web_root)},
        "provenance": {}, "environment": {}, "limits": list(LIMITS),
        "scenarios": [{"id": sid, "name": name, "status": "NOT_EXERCISED",
            "checks": {}, "counts": {}, "timings_ms": {}} for sid, name in SCENARIOS],
    }
    logging.disable(logging.CRITICAL)
    previous_umask = os.umask(0o077)
    code = 1
    try:
        result = asyncio.run(interruptible_execute(args, evidence))
        if isinstance(result, PrerequisiteFailure):
            evidence["failure_code"] = str(result)
            code = 2
        elif isinstance(result, asyncio.CancelledError):
            evidence["failure_code"] = "RUN_INTERRUPTED"
            code = 1
        elif isinstance(result, BaseException):
            evidence["failure_code"] = "PREREQUISITE_OR_RUNNER_ERROR"
            code = 2 if all(row["status"] == "NOT_EXERCISED" for row in evidence["scenarios"]) else 1
        else:
            code = result
    except (KeyboardInterrupt, asyncio.CancelledError):
        evidence["failure_code"] = "RUN_INTERRUPTED"
        code = 1
    except Exception:  # noqa: BLE001 - CLI boundary must publish safe evidence without private traceback text.
        evidence["failure_code"] = "PREREQUISITE_OR_RUNNER_ERROR"
        code = 2 if all(row["status"] == "NOT_EXERCISED" for row in evidence["scenarios"]) else 1
    finally:
        os.umask(previous_umask)
        evidence["completed_utc"] = utc_now()
        evidence["status"] = "PASS" if code == 0 else ("NOT_EXERCISED" if code == 2 else "FAIL")
        evidence["exit_code"] = code
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as target:
                json.dump(evidence, target, ensure_ascii=True, indent=2, sort_keys=True)
                target.write("\n")
                target.flush()
                os.fsync(target.fileno())
            os.link(temporary, args.output)
            directory = os.open(Path(args.output).absolute().parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except FileExistsError:
            print("OUTPUT_ALREADY_EXISTS", file=sys.stderr)
            code = 2
        except OSError:
            print("OUTPUT_CANNOT_BE_PUBLISHED", file=sys.stderr)
            code = 2
        finally:
            os.unlink(temporary)
        if code == evidence["exit_code"]:
            print("PRODUCT_FAULT_DRILL_" + evidence["status"])
    return code


if __name__ == "__main__":
    raise SystemExit(main())
