#!/usr/bin/env python3
"""Real HINE HTTP/WSS exercise. Protocol receipt is NOT browser persistence/rendering."""
import argparse
import asyncio
import copy
import json
import math
import os
import sqlite3
import stat
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit
from uuid import UUID, uuid4

import aiohttp


class ProtocolFailure(Exception):
    """Only fixed, nonsecret diagnostic codes may leave this boundary."""


class InputFailure(Exception):
    pass


def require(condition, code):
    if not condition:
        raise ProtocolFailure(code)


def string(value):
    return isinstance(value, str) and bool(value)


def uuid(value):
    try:
        require(isinstance(value, str), "INVALID_UUID")
        return UUID(value).bytes
    except (ValueError, AttributeError):
        raise ProtocolFailure("INVALID_UUID") from None


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        require(parsed.utcoffset() is not None and parsed.utcoffset().total_seconds() == 0,
                "INVALID_TIMESTAMP")
        return parsed
    except (ValueError, AttributeError, TypeError):
        raise ProtocolFailure("INVALID_TIMESTAMP") from None


def envelope(event):
    require(isinstance(event, dict) and string(event.get("event")) and
            isinstance(event.get("payload"), dict), "INVALID_ENVELOPE")
    uuid(event.get("event_id"))
    timestamp(event.get("timestamp"))
    if "correlation_id" in event:
        uuid(event["correlation_id"])
    require("subject_id" not in event and "subject_id" not in event["payload"],
            "INTERNAL_ID_LEAK")
    return event["payload"]


def order(value):
    require(isinstance(value, str) and len(value) == 20 and value.isascii() and
            value.isdigit() and 1 <= int(value) <= 9223372036854775807, "INVALID_ORDER_KEY")
    return value


def message_view(value, viewer):
    require(isinstance(value, dict), "INVALID_MESSAGE_VIEW")
    uuid(value.get("id"))
    uuid(value.get("event_id"))
    timestamp(value.get("created_at"))
    order(value.get("order_key"))
    require(string(value.get("conversation_id")) and string(value.get("sender_id")) and
            "receipt" in value, "INVALID_MESSAGE_VIEW")
    require(value.get("type") in ("text", "image", "file"), "INVALID_MESSAGE_TYPE")
    if value["type"] == "text":
        require(string(value.get("text")) and "attachment_id" not in value, "INVALID_TEXT_VIEW")
    else:
        require(string(value.get("attachment_id")) and "text" not in value,
                "INVALID_ATTACHMENT_VIEW")
    if "client_message_id" in value:
        uuid(value["client_message_id"])
        require(viewer == value["sender_id"], "RECEIVER_C1_LEAK")
    receipt = value["receipt"]
    if receipt is not None:
        require(isinstance(receipt, dict) and receipt.get("kind") == "direct" and
                receipt.get("message_id") == value["id"] and
                string(receipt.get("recipient_id")) and
                receipt.get("status") in ("delivered", "read"), "INVALID_RECEIPT")
        timestamp(receipt.get("updated_at"))
    require("subject_id" not in value, "INTERNAL_ID_LEAK")
    return value


def message_event(event, viewer):
    payload = envelope(event)
    require(event["event"] == "message.created", "EXPECTED_W07")
    value = {"id": payload.get("message_id"), "event_id": event["event_id"],
             "conversation_id": event.get("conversation_id"), "sender_id": event.get("sender_id"),
             "created_at": event["timestamp"], "order_key": payload.get("order_key"),
             "type": payload.get("type"), "receipt": None}
    for name in ("text", "attachment_id", "client_message_id"):
        if name in payload:
            value[name] = payload[name]
    return message_view(value, viewer)


def same_message(actual, expected):
    for name in ("id", "event_id", "conversation_id", "sender_id", "created_at", "order_key",
                 "type", "text", "attachment_id"):
        require(actual.get(name) == expected.get(name), "MESSAGE_IDENTITY_CONTENT_CHANGED")


def check_history(items, expected, viewer, conversation):
    ids, previous = set(), None
    for item in items:
        message_view(item, viewer)
        require(item["conversation_id"] == conversation, "HISTORY_WRONG_ROOM")
        key = (item["order_key"], uuid(item["id"]))
        require(previous is None or key < previous, "HISTORY_ORDER_OR_DUPLICATE")
        require(item["id"] not in ids, "HISTORY_DUPLICATE_MESSAGE")
        ids.add(item["id"])
        previous = key
        if item["id"] in expected:
            same_message(item, expected[item["id"]])
    require(set(expected) <= ids, "HISTORY_MISSING_PERSISTED_MESSAGE")
    for target in expected.values():
        if target.get("type") == "text" and target.get("text", "").startswith("hine-qa-"):
            matching = [item for item in items if item.get("sender_id") == target["sender_id"]
                        and item.get("text") == target["text"]]
            require(len(matching) == 1, "RETRY_DUPLICATED_INTENT")


class Delivery:
    def __init__(self, conversation, sender, recipient, c1, text, started):
        self.conversation, self.sender, self.recipient = conversation, sender, recipient
        self.c1, self.text, self.started = c1, text, started
        self.ack_id = None
        self.received = None
        self.sender_event = None
        self.latency_ms = None
        self.signal = asyncio.Event()

    @property
    def complete(self):
        return self.ack_id is not None and self.received is not None

    def accept_ack(self, event):
        payload = envelope(event)
        require(event["event"] == "message.ack" and event.get("conversation_id") == self.conversation
                and payload.get("client_message_id") == self.c1 and
                payload.get("status") == "persisted", "INVALID_W06")
        uuid(payload.get("message_id"))
        require(self.ack_id in (None, payload["message_id"]), "RETRY_CHANGED_M1")
        if self.received is not None:
            require(self.received["id"] == payload["message_id"], "ACK_RECEIVER_M1_MISMATCH")
        self.ack_id = payload["message_id"]
        self.signal.set()

    def accept_created(self, event, viewer, received_at):
        value = message_event(event, viewer)
        require(value["conversation_id"] == self.conversation and value["sender_id"] == self.sender
                and value.get("text") == self.text, "W07_INTENT_MISMATCH")
        if viewer == self.sender:
            require(value.get("client_message_id") == self.c1, "SENDER_C1_MISMATCH")
            if self.sender_event:
                same_message(value, self.sender_event)
            self.sender_event = value
        else:
            require(viewer == self.recipient, "WRONG_RECIPIENT")
            if self.received:
                same_message(value, self.received)
            else:
                self.received = value
                self.latency_ms = (received_at - self.started) * 1000
            require(self.ack_id in (None, value["id"]), "ACK_RECEIVER_M1_MISMATCH")
        if self.received and self.sender_event:
            same_message(self.received, self.sender_event)
        self.signal.set()

    async def wait(self, timeout, sender_event=False):
        async with asyncio.timeout(timeout):
            while not self.complete or (sender_event and self.sender_event is None):
                self.signal.clear()
                await self.signal.wait()


class ProjectionStore:
    """QA-only durable projection/cursor, atomically committed; never a browser claim."""
    def __init__(self, path, viewer):
        self.viewer = viewer
        path = Path(path)
        if path.exists():
            protected(path)
        else:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS state (viewer TEXT PRIMARY KEY, value TEXT NOT NULL)")
        row = self.db.execute("SELECT value FROM state WHERE viewer=?", (viewer,)).fetchone()
        self.state = json.loads(row[0]) if row else {"cursor": None, "messages": {},
                                                    "conversations": {}, "events": {},
                                                    "pending_receipts": {}}
        # Extend saved projections without resetting their messages or cursor.
        self.state.setdefault("pending_receipts", {})

    @property
    def cursor(self):
        return self.state["cursor"]

    @property
    def messages(self):
        return self.state["messages"]

    @property
    def pending_receipts(self):
        return self.state["pending_receipts"]

    @staticmethod
    def merge_receipt(previous, incoming):
        if previous is None:
            return copy.deepcopy(incoming)
        if incoming is None:
            return copy.deepcopy(previous)
        require(previous["recipient_id"] == incoming["recipient_id"] and
                previous["message_id"] == incoming["message_id"], "SYNC_RECEIPT_IDENTITY_CHANGED")
        if previous["status"] != incoming["status"]:
            selected = previous if previous["status"] == "read" else incoming
        else:
            selected = previous if timestamp(previous["updated_at"]) >= timestamp(incoming["updated_at"]) else incoming
        return copy.deepcopy(selected)

    def stage_message(self, state, value):
        message_view(value, self.viewer)
        value = copy.deepcopy(value)
        previous = state["messages"].get(value["id"])
        if previous:
            same_message(value, previous)
            value["receipt"] = self.merge_receipt(previous["receipt"], value["receipt"])
        pending = state["pending_receipts"].pop(value["id"], None)
        if pending:
            require(pending["conversation_id"] == value["conversation_id"], "SYNC_RECEIPT_WRONG_ROOM")
            value["receipt"] = self.merge_receipt(value["receipt"], pending["receipt"])
        state["messages"][value["id"]] = value

    def load_messages(self, items):
        staged = copy.deepcopy(self.state)
        for value in items:
            self.stage_message(staged, value)
        self.commit(staged)

    def commit(self, state):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO state VALUES (?,?)",
                            (self.viewer, json.dumps(state, ensure_ascii=False)))
        self.state = state

    def install_bootstrap(self, conversations, cursor):
        require(string(cursor), "INVALID_BOOTSTRAP_CURSOR")
        state = {"cursor": cursor, "messages": {}, "conversations": {}, "events": {},
                 "pending_receipts": {}}
        for room in conversations:
            require(isinstance(room, dict) and string(room.get("id")) and
                    room.get("type") in ("direct", "group") and "title" in room and
                    type(room.get("unread_count")) is int and room["unread_count"] >= 0 and
                    "my_role" in room and isinstance(room.get("recent_messages"), list),
                    "INVALID_BOOTSTRAP_CONVERSATION")
            if room["type"] == "direct":
                require(room["title"] is None and room["my_role"] is None, "INVALID_DIRECT_SNAPSHOT")
            else:
                require(string(room["title"]) and room["my_role"] in ("admin", "member"),
                        "INVALID_GROUP_SNAPSHOT")
            require(room["id"] not in state["conversations"], "DUPLICATE_BOOTSTRAP_ROOM")
            state["conversations"][room["id"]] = copy.deepcopy(room)
            for value in room["recent_messages"]:
                message_view(value, self.viewer)
                require(value["conversation_id"] == room["id"] and value["id"] not in state["messages"],
                        "INVALID_BOOTSTRAP_MESSAGE")
                state["messages"][value["id"]] = copy.deepcopy(value)
        self.commit(state)

    def apply_batch(self, batch, boundary=None, requested_cursor=None):
        require(isinstance(batch, dict) and string(batch.get("snapshot_boundary")) and
                string(batch.get("next_cursor")) and type(batch.get("has_more")) is bool and
                isinstance(batch.get("events"), list) and len(batch["events"]) <= 100,
                "INVALID_SYNC_BATCH")
        require(boundary is None or boundary == batch["snapshot_boundary"], "SYNC_BOUNDARY_CHANGED")
        source_cursor = self.cursor if requested_cursor is None else requested_cursor
        require(not batch["has_more"] or batch["next_cursor"] != source_cursor,
                "SYNC_NONADVANCING_CONTINUATION")
        staged = copy.deepcopy(self.state)
        for event in batch["events"]:
            payload = envelope(event)
            require("correlation_id" not in event, "SYNC_EVENT_UNEXPECTED_CORRELATION")
            old = staged["events"].get(event["event_id"])
            if old is not None:
                require(old == event, "SYNC_STABLE_EVENT_CHANGED")
                continue
            kind, room = event["event"], event.get("conversation_id")
            require(string(room), "SYNC_MISSING_CONVERSATION")
            if kind == "message.created":
                self.stage_message(staged, message_event(event, self.viewer))
            elif kind == "message.status":
                require(payload.get("kind") == "direct" and string(payload.get("recipient_id")) and
                        payload.get("status") in ("delivered", "read"), "INVALID_SYNC_RECEIPT")
                uuid(payload.get("message_id"))
                timestamp(payload.get("updated_at"))
                previous = staged["messages"].get(payload["message_id"])
                if previous:
                    require(previous["conversation_id"] == room, "SYNC_RECEIPT_WRONG_ROOM")
                    previous["receipt"] = self.merge_receipt(previous["receipt"], payload)
                else:
                    pending = staged["pending_receipts"].get(payload["message_id"])
                    if pending:
                        require(pending["conversation_id"] == room, "SYNC_RECEIPT_WRONG_ROOM")
                    staged["pending_receipts"][payload["message_id"]] = {
                        "conversation_id": room,
                        "receipt": self.merge_receipt(pending["receipt"] if pending else None, payload)}
            elif kind in ("conversation.member_added", "conversation.member_removed", "conversation.updated"):
                require(type(payload.get("membership_version")) is int and
                        payload["membership_version"] >= 1, "INVALID_SYNC_MEMBERSHIP")
                projection = staged["conversations"].setdefault(room, {"id": room})
                projection["membership_version"] = payload["membership_version"]
                if kind == "conversation.member_removed":
                    require(string(payload.get("member_id")) and payload.get("change") == "removed",
                            "INVALID_SYNC_REMOVAL")
                    if payload["member_id"] == self.viewer:
                        projection["removed"] = True
                elif kind == "conversation.member_added":
                    require(string(payload.get("member_id")) and string(payload.get("actor_id")) and
                            payload.get("role") in ("admin", "member"), "INVALID_SYNC_ADDITION")
                    if payload["member_id"] == self.viewer:
                        projection["removed"] = False
                        projection["my_role"] = payload["role"]
                else:
                    changes = payload.get("changes")
                    require(isinstance(changes, dict) and string(payload.get("actor_id")),
                            "INVALID_SYNC_UPDATE")
                    if changes.get("kind") == "title":
                        require(string(changes.get("title")), "INVALID_SYNC_TITLE")
                        projection["title"] = changes["title"]
                    else:
                        require(changes.get("kind") == "role" and string(changes.get("member_id")) and
                                changes.get("role") in ("admin", "member"), "INVALID_SYNC_ROLE")
                        if changes["member_id"] == self.viewer:
                            projection["my_role"] = changes["role"]
            else:
                raise ProtocolFailure("UNSUPPORTED_SYNC_EVENT")
            staged["events"][event["event_id"]] = copy.deepcopy(event)
        staged["cursor"] = batch["next_cursor"]
        self.commit(staged)

    def close(self):
        self.db.close()


def protected(path):
    info = Path(path).stat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise InputFailure("INPUT_FILE_REQUIRES_OWNER_ONLY_PERMISSIONS")


def validate_target(value, scheme):
    if not isinstance(value, str):
        raise InputFailure("INVALID_TARGET_URL")
    parsed = urlsplit(value)
    if parsed.scheme not in (("http", "https") if scheme == "http" else ("ws", "wss")) or \
            not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise InputFailure("INVALID_TARGET_URL")
    if scheme == "http" and parsed.path not in ("", "/"):
        raise InputFailure("API_BASE_MUST_BE_ORIGIN")
    if scheme == "ws" and parsed.path != "/ws/v1":
        raise InputFailure("WS_PATH_MUST_BE_WS_V1")
    if parsed.scheme in ("http", "ws") and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise InputFailure("REMOTE_TARGET_REQUIRES_TLS")
    return value.rstrip("/") if scheme == "http" else value


def validate_count(mode, count, available):
    if count < 2 or count % 2 or count > available or (mode == "e2e" and count != 2):
        raise InputFailure("USER_COUNT_REQUIRES_DISTINCT_PAIRS")


def read_config(path, mode, count):
    protected(path)
    try:
        config = json.loads(Path(path).read_text())
        users = config["users"]
        if not isinstance(users, list):
            raise InputFailure("INVALID_USERS_INPUT")
        validate_count(mode, count, len(users))
        config["api_base_url"] = validate_target(config["api_base_url"], "http")
        config["ws_url"] = validate_target(config["ws_url"], "ws")
        selected = []
        for user in users[:count]:
            if not isinstance(user, dict) or (("session" in user) == ("login" in user)):
                raise InputFailure("USER_REQUIRES_SESSION_OR_LOGIN")
            if "session" in user:
                validate_session(user["session"])
            else:
                login = user["login"]
                if not isinstance(login, dict) or "device_id" not in login or \
                        (login["device_id"] is not None and not string(login["device_id"])):
                    raise InputFailure("LOGIN_REQUIRES_DEVICE_ID_OR_NULL")
                for name in ("email", "password"):
                    if (name in login) == (name + "_env" in login):
                        raise InputFailure("LOGIN_REQUIRES_ONE_CREDENTIAL_SOURCE")
                    value = login.get(name) if name in login else os.environ.get(login[name + "_env"])
                    if not string(value):
                        raise InputFailure("LOGIN_CREDENTIAL_UNAVAILABLE")
                    login[name] = value
                if user.get("register", False) and not string(user.get("display_name")):
                    raise InputFailure("REGISTRATION_REQUIRES_DISPLAY_NAME")
            selected.append(user)
        config["users"] = selected
        return config
    except (KeyError, ValueError, TypeError, ProtocolFailure):
        raise InputFailure("INVALID_CONFIG_SHAPE") from None


def validate_session(session):
    require(isinstance(session, dict) and all(string(session.get(key)) for key in
            ("access_token", "expires_at", "user_id", "device_id")) and
            type(session.get("session_generation")) is int and session["session_generation"] >= 1,
            "INVALID_ACCESS_SESSION")
    require(timestamp(session["expires_at"]) > datetime.now(timezone.utc), "ACCESS_SESSION_EXPIRED")


def frame(kind, payload, conversation=None):
    value = {"event": kind, "event_id": str(uuid4()),
             "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
             "payload": payload}
    if conversation is not None:
        value["conversation_id"] = conversation
    return value


def remote_error(payload):
    require(isinstance(payload, dict) and string(payload.get("code")) and
            isinstance(payload.get("message"), str) and type(payload.get("retryable")) is bool,
            "INVALID_ERROR_ENVELOPE")
    details = payload.get("details")
    require("auth_layer" not in payload and
            not (isinstance(details, dict) and "auth_layer" in details),
            "PUBLIC_INTERNAL_METADATA_LEAK")
    # Never trust server-provided code/message as a safe log string.
    codes = {"INVALID_ARGUMENT", "UNAUTHENTICATED", "FORBIDDEN", "NOT_FOUND", "CONFLICT",
             "IDEMPOTENCY_CONFLICT", "CURSOR_INVALID", "CURSOR_EXPIRED", "SYNC_RESET_REQUIRED",
             "PAYLOAD_TOO_LARGE", "UNSUPPORTED_MEDIA_TYPE", "UPLOAD_NOT_READY", "RATE_LIMITED",
             "DEPENDENCY_UNAVAILABLE", "PERSISTENCE_FAILED", "OUTCOME_UNCONFIRMED"}
    require(payload["code"] in codes, "UNKNOWN_ERROR_CODE")
    if "retry_after_ms" in payload:
        require(type(payload["retry_after_ms"]) is int and payload["retry_after_ms"] >= 0,
                "INVALID_RETRY_DELAY")
    return payload["code"]


class Client:
    def __init__(self, http, url, session, timeout, on_created, on_connection):
        self.http, self.url, self.session = http, url, session
        self.timeout, self.on_created = timeout, on_created
        self.pending = {}
        self.ws = None
        self.reader = self.heartbeat = None
        self.failure = None
        self.closing = False
        self.on_connection = on_connection
        self.authenticated = False

    def connection_state(self, authenticated):
        self.authenticated = authenticated
        self.on_connection(id(self), urlsplit(self.url).scheme, authenticated)

    def fail(self, code):
        self.failure = code
        self.connection_state(False)
        for future in self.pending.values():
            if not future.done():
                future.set_exception(ProtocolFailure(code))

    async def connect(self):
        self.ws = await self.http.ws_connect(self.url, autoping=True, max_msg_size=2 * 1024 * 1024)
        self.reader = asyncio.create_task(self.read())
        reply = await self.request("auth.authenticate", {"access_token": self.session["access_token"],
                                   "device_id": self.session["device_id"]}, "auth.accepted")
        payload = reply["payload"]
        for name in ("user_id", "device_id", "expires_at", "session_generation"):
            require(payload.get(name) == self.session[name], "W02_SESSION_MISMATCH")
        require(type(payload.get("heartbeat_interval_seconds")) is int and
                payload["heartbeat_interval_seconds"] == 30 and
                type(payload.get("heartbeat_timeout_seconds")) is int and
                payload["heartbeat_timeout_seconds"] == 90, "W02_HEARTBEAT_MISMATCH")
        self.connection_state(True)
        await self.ping()
        self.heartbeat = asyncio.create_task(self.keepalive())

    async def ping(self):
        nonce = str(uuid4())
        reply = await self.request("heartbeat.ping", {"nonce": nonce}, "heartbeat.pong")
        require(reply["payload"].get("nonce") == nonce, "W04_NONCE_MISMATCH")

    async def keepalive(self):
        try:
            while True:
                await asyncio.sleep(30)
                await self.ping()
        except (ProtocolFailure, TimeoutError, aiohttp.ClientError):
            self.fail("HEARTBEAT_FAILED")

    async def read(self):
        try:
            async for message in self.ws:
                require(message.type == aiohttp.WSMsgType.TEXT, "NON_TEXT_WS_FRAME")
                try:
                    value = json.loads(message.data)
                except (ValueError, TypeError):
                    raise ProtocolFailure("MALFORMED_WS_JSON") from None
                envelope(value)
                if value["event"] == "message.created":
                    require("correlation_id" not in value, "W07_UNEXPECTED_CORRELATION")
                    self.on_created(value, self.session["user_id"], time.monotonic())
                elif "correlation_id" in value:
                    future = self.pending.get(value["correlation_id"])
                    require(future is not None and not future.done(), "UNKNOWN_RESPONSE_CORRELATION")
                    future.set_result(value)
                elif value["event"] == "error":
                    raise ProtocolFailure("W17_" + remote_error(value["payload"]))
                elif value["event"] not in ("presence.changed", "message.status",
                        "conversation.member_added", "conversation.member_removed", "conversation.updated"):
                    raise ProtocolFailure("UNEXPECTED_WS_EVENT")
            if not self.closing:
                self.fail("WS_CLOSED")
        except ProtocolFailure as error:
            self.fail(str(error))
        except (aiohttp.ClientError, OSError):
            self.fail("WS_TRANSPORT_FAILED")

    async def request(self, kind, payload, expected, conversation=None, error_code=None):
        if self.failure:
            raise ProtocolFailure(self.failure)
        value = frame(kind, payload, conversation)
        future = asyncio.get_running_loop().create_future()
        self.pending[value["event_id"]] = future
        try:
            await self.ws.send_json(value)
            reply = await asyncio.wait_for(future, self.timeout)
            require(reply.get("correlation_id") == value["event_id"], "RESPONSE_CORRELATION_MISMATCH")
            if reply["event"] == "error":
                code = remote_error(reply["payload"])
                if error_code:
                    require(code == error_code, "UNEXPECTED_W17_CODE")
                    return reply
                raise ProtocolFailure("W17_" + code)
            require(error_code is None, "REJECTED_INPUT_RECEIVED_SUCCESS")
            require(reply["event"] == expected, "WRONG_RESPONSE_EVENT")
            return reply
        finally:
            self.pending.pop(value["event_id"], None)

    async def close(self):
        self.closing = True
        self.connection_state(False)
        if self.heartbeat:
            self.heartbeat.cancel()
            await asyncio.gather(self.heartbeat, return_exceptions=True)
        if self.ws:
            await self.ws.close()
        if self.reader:
            await asyncio.gather(self.reader, return_exceptions=True)


async def rest(http, base, method, path, statuses, session=None, body=None, params=None):
    headers = {"Authorization": "Bearer " + session["access_token"]} if session else {}
    async with http.request(method, base + path, headers=headers, json=body, params=params,
                            allow_redirects=False) as response:
        try:
            value = await response.json()
        except (ValueError, aiohttp.ContentTypeError):
            raise ProtocolFailure("NON_JSON_REST_RESPONSE") from None
        require(isinstance(value, dict), "INVALID_REST_ENVELOPE")
        if response.status not in statuses:
            error = value.get("error")
            code = remote_error(error)
            require(string(error.get("request_id")) and isinstance(error.get("details"), dict),
                    "INVALID_REST_ERROR")
            raise ProtocolFailure("REST_" + code)
        require("data" in value and "error" not in value, "INVALID_REST_SUCCESS")
        return value


async def bootstrap(client, store):
    request = {"reason": "first_login"}
    snapshot = cursor = None
    conversations, tokens = [], set()
    for _ in range(10000):
        reply = await client.request("sync.bootstrap.request", request, "sync.bootstrap.page")
        payload = reply["payload"]
        require(string(payload.get("snapshot_id")) and string(payload.get("start_cursor")) and
                isinstance(payload.get("conversations"), list) and
                type(payload.get("has_more")) is bool and "next_page_token" in payload,
                "INVALID_BOOTSTRAP_PAGE")
        if snapshot is None:
            snapshot, cursor = payload["snapshot_id"], payload["start_cursor"]
        require(snapshot == payload["snapshot_id"] and cursor == payload["start_cursor"],
                "BOOTSTRAP_SNAPSHOT_CHANGED")
        conversations.extend(payload["conversations"])
        token = payload["next_page_token"]
        if not payload["has_more"]:
            require(token is None, "BOOTSTRAP_TERMINAL_TOKEN")
            store.install_bootstrap(conversations, cursor)
            return
        require(string(token) and token not in tokens, "BOOTSTRAP_INVALID_CONTINUATION")
        tokens.add(token)
        request = {"reason": "first_login", "snapshot_id": snapshot, "page_token": token}
    raise ProtocolFailure("BOOTSTRAP_PAGE_LIMIT")


async def synchronize(client, store, cursor=None):
    current = store.cursor if cursor is None else cursor
    require(string(current), "SAVED_CURSOR_REQUIRED")
    boundary = None
    for _ in range(10000):
        request = {"cursor": current}
        if boundary is not None:
            request["snapshot_boundary"] = boundary
        reply = await client.request("sync.request", request, "sync.batch")
        payload = reply["payload"]
        store.apply_batch(payload, boundary, current)
        boundary = payload["snapshot_boundary"]
        current = store.cursor
        if not payload["has_more"]:
            return
    raise ProtocolFailure("SYNC_PAGE_LIMIT")


class ProcessSampler:
    def __init__(self, pid):
        self.pid, self.samples, self.failure = pid, [], None
        self.last = None

    def sample(self):
        if self.pid is None:
            return
        try:
            raw = Path(f"/proc/{self.pid}/stat").read_text()
            fields = raw[raw.rindex(")") + 2:].split()
            ticks, rss, birth = int(fields[11]) + int(fields[12]), int(fields[21]), fields[19]
            now = time.monotonic()
            if self.last:
                previous, when, identity = self.last
                if birth != identity:
                    self.failure = "MONITORED_PID_REUSED"
                    return
                cpu = (ticks - previous) / os.sysconf("SC_CLK_TCK") / (now - when) * 100
                self.samples.append((cpu, rss * os.sysconf("SC_PAGE_SIZE")))
            self.last = (ticks, now, birth)
        except (OSError, ValueError, IndexError):
            self.failure = "MONITORED_PROCESS_UNAVAILABLE"

    async def run(self):
        while True:
            self.sample()
            await asyncio.sleep(1)

    def report(self):
        if self.pid is None:
            return {"status": "not_supplied"}
        if self.failure:
            return {"status": "unavailable", "code": self.failure}
        if not self.samples:
            return {"status": "insufficient_samples"}
        return {"status": "sampled", "samples": len(self.samples),
                "cpu_percent_mean": sum(x[0] for x in self.samples) / len(self.samples),
                "cpu_percent_max": max(x[0] for x in self.samples),
                "rss_bytes_max": max(x[1] for x in self.samples)}


class LoadEvidence:
    """Count the requested time slots against actual dispatch timestamps, per user."""
    def __init__(self, users, duration, started):
        self.duration, self.started = duration, started
        self.timestamps = [[] for _ in range(users)]
        self.expected = [max(0, math.ceil((duration - (index % 2) * 2.5) / 5))
                         for index in range(users)]

    def record(self, index, dispatched):
        elapsed = dispatched - self.started
        require(0 <= elapsed < self.duration, "LOAD_DISPATCH_OUTSIDE_WINDOW")
        self.timestamps[index].append(elapsed)

    @property
    def met(self):
        return all(len(times) == expected for times, expected in zip(self.timestamps, self.expected))

    def require_met(self):
        require(self.met, "LOAD_REQUESTED_CADENCE_NOT_MET")

    def report(self):
        attempts = [len(times) for times in self.timestamps]
        return {"expected_attempts": self.expected, "attempts": attempts,
                "missed_slots": [max(0, expected - actual)
                                 for expected, actual in zip(self.expected, attempts)],
                "send_offsets_seconds": self.timestamps,
                "achieved_messages_per_second": [actual / self.duration for actual in attempts],
                "requested_cadence_met": self.met}


class ConnectionEvidence:
    """Observed successful W02 lifecycle counts; a socket object alone proves nothing."""
    def __init__(self):
        self.active = {}
        self.peak = {"ws": 0, "wss": 0}
        self.window = False
        self.initial = self.minimum = self.final = None

    def counts(self):
        return {scheme: sum(value == scheme for value in self.active.values())
                for scheme in ("ws", "wss")}

    def update(self, connection, scheme, authenticated):
        require(scheme in ("ws", "wss"), "INVALID_CONNECTION_SCHEME")
        if authenticated:
            self.active[connection] = scheme
        else:
            self.active.pop(connection, None)
        counts = self.counts()
        for kind in counts:
            self.peak[kind] = max(self.peak[kind], counts[kind])
            if self.window:
                self.minimum[kind] = min(self.minimum[kind], counts[kind])

    def begin_window(self):
        self.window = True
        self.initial = self.counts()
        self.minimum = self.initial.copy()
        self.final = None

    def end_window(self):
        if self.window:
            self.final = self.counts()
            self.window = False

    def window_met(self, users, scheme):
        return self.minimum is not None and self.initial[scheme] == users and self.minimum[scheme] == users

    def report(self):
        return {"current": self.counts(), "peak": self.peak, "window_initial": self.initial,
                "window_minimum": self.minimum, "window_final": self.final}


class RecoveryEvidence:
    def __init__(self, started):
        self.started = started
        self.recovery_ms = self.replay_start = self.replay_ms = None

    def recovered(self, now):
        self.recovery_ms = (now - self.started) * 1000

    def replay_started(self, now):
        self.replay_start = now

    def replayed(self, now):
        self.replay_ms = (now - self.replay_start) * 1000

    def report(self):
        return {"protocol_recovery_ms": self.recovery_ms, "saved_cursor_replay_ms": self.replay_ms}


class Exercise:
    def __init__(self, args, config):
        self.args, self.config = args, config
        self.clients, self.deliveries, self.sessions, self.rooms = [], {}, [], []
        self.errors, self.latencies = {}, []
        self.attempted = self.succeeded = 0
        self.reconnect_result = {"status": "not_requested"}
        self.monitor = ProcessSampler(args.monitor_pid)
        self.connections = ConnectionEvidence()
        self.load_evidence = None

    def created(self, event, viewer, received_at):
        value = message_event(event, viewer)
        evidence = self.deliveries.get((value["conversation_id"], value["sender_id"], value.get("text")))
        if evidence:
            evidence.accept_created(event, viewer, received_at)

    async def prepare(self, http):
        base = self.config["api_base_url"]
        for user in self.config["users"]:
            if "session" in user:
                session = user["session"]
            else:
                login = user["login"]
                if user.get("register", False):
                    await rest(http, base, "POST", "/api/v1/auth/register", {201}, body={
                        "email": login["email"], "password": login["password"],
                        "display_name": user["display_name"]})
                value = await rest(http, base, "POST", "/api/v1/auth/login", {200}, body={
                    name: login[name] for name in ("email", "password", "device_id")})
                session = value["data"]
            validate_session(session)
            require(session["user_id"] not in {x["user_id"] for x in self.sessions},
                    "DISTINCT_USERS_REQUIRED")
            self.sessions.append(session)
        for index in range(0, len(self.sessions), 2):
            left, right = self.sessions[index:index + 2]
            value = await rest(http, base, "POST", "/api/v1/conversations/direct", {200, 201},
                               left, {"peer_user_id": right["user_id"]})
            room = value["data"]
            require(isinstance(room, dict) and string(room.get("id")) and room.get("type") == "direct"
                    and "title" in room and room["title"] is None and "membership_version" in room
                    and room["membership_version"] is None and isinstance(room.get("member_ids"), list)
                    and len(room["member_ids"]) == 2 and set(room["member_ids"]) ==
                    {left["user_id"], right["user_id"]}, "INVALID_A13_DIRECT")
            self.rooms.append(room["id"])
        for session in self.sessions:
            client = Client(http, self.config["ws_url"], session, self.args.timeout, self.created,
                            self.connections.update)
            self.clients.append(client)
            await client.connect()

    def new_delivery(self, index):
        c1 = str(uuid4())
        # Generated QA text only; no user-provided message text appears in metrics.
        text = "hine-qa-" + c1
        require(len(text.encode("utf-8")) <= 1024, "BASELINE_TEXT_TOO_LARGE")
        delivery = Delivery(self.rooms[index // 2], self.sessions[index]["user_id"],
                            self.sessions[index ^ 1]["user_id"], c1, text, time.monotonic())
        self.deliveries[(delivery.conversation, delivery.sender, delivery.text)] = delivery
        return delivery

    async def ack(self, client, delivery, text=None, expected_error=None):
        reply = await client.request("message.send", {"client_message_id": delivery.c1,
                "type": "text", "text": delivery.text if text is None else text},
                "message.ack", delivery.conversation, expected_error)
        if expected_error is None:
            delivery.accept_ack(reply)

    async def send(self, index, sender_event=False):
        delivery = self.new_delivery(index)
        if self.load_evidence is not None and self.connections.window:
            self.load_evidence.record(index, delivery.started)
        self.attempted += 1
        await self.ack(self.clients[index], delivery)
        await delivery.wait(self.args.timeout, sender_event)
        self.succeeded += 1
        self.latencies.append(delivery.latency_ms)
        return delivery

    async def history_items(self, http, index):
        session, conversation = self.sessions[index], self.rooms[index // 2]
        items, cursor, seen = [], None, set()
        for _ in range(10000):
            params = {"limit": "50"}
            if cursor is not None:
                params["before"] = cursor
            value = await rest(http, self.config["api_base_url"], "GET",
                "/api/v1/conversations/" + quote(conversation, safe="") + "/messages",
                {200}, session, params=params)
            require(isinstance(value["data"], dict) and isinstance(value["data"].get("items"), list)
                    and len(value["data"]["items"]) <= 50 and isinstance(value.get("meta"), dict)
                    and "next_cursor" in value["meta"], "INVALID_A19_LIST_ENVELOPE")
            items.extend(value["data"]["items"])
            cursor = value["meta"]["next_cursor"]
            if cursor is None:
                return items
            require(string(cursor) and cursor not in seen, "HISTORY_INVALID_CONTINUATION")
            seen.add(cursor)
        raise ProtocolFailure("HISTORY_PAGE_LIMIT")

    async def history(self, http):
        for index, session in enumerate(self.sessions):
            conversation = self.rooms[index // 2]
            expected = {}
            for delivery in self.deliveries.values():
                if delivery.conversation == conversation and delivery.received is not None:
                    expected[delivery.received["id"]] = delivery.received
            if not expected:
                continue
            items = await self.history_items(http, index)
            check_history(items, expected, session["user_id"], conversation)
            for item in items:
                match = next((d for d in self.deliveries.values() if d.ack_id == item["id"]), None)
                if match and session["user_id"] == match.sender:
                    require(item.get("client_message_id") == match.c1, "A19_SENDER_C1_MISMATCH")
                intent = next((d for d in self.deliveries.values()
                               if d.c1 == item.get("client_message_id")), None)
                if intent:
                    require(item["id"] == intent.ack_id, "A19_C1_MULTIPLE_MESSAGES")

    async def reconnect(self, http):
        receiver = self.clients[1]
        store = ProjectionStore(self.args.state, self.sessions[1]["user_id"])
        try:
            if store.cursor is None:
                await bootstrap(receiver, store)
            else:
                await synchronize(receiver, store)
            saved = store.cursor
            await receiver.close()
            delivery = self.new_delivery(0)
            self.attempted += 1
            await self.ack(self.clients[0], delivery)
            started = time.monotonic()
            measurement = RecoveryEvidence(started)
            replacement = Client(http, self.config["ws_url"], self.sessions[1], self.args.timeout,
                                 self.created, self.connections.update)
            self.clients[1] = replacement
            await replacement.connect()
            await synchronize(replacement, store)
            value = store.messages.get(delivery.ack_id)
            require(value is not None, "SYNC_MISSING_OFFLINE_MESSAGE")
            require(value["conversation_id"] == delivery.conversation and value["sender_id"] == delivery.sender
                    and value.get("text") == delivery.text, "SYNC_OFFLINE_CONTENT_MISMATCH")
            if delivery.sender_event:
                same_message(value, delivery.sender_event)
            measurement.recovered(time.monotonic())
            self.reconnect_result = {"status": "recovered_replay_pending", **measurement.report()}
            # Older messages absent from W14 may have pending W16 receipt projections.
            items = await self.history_items(http, 1)
            check_history(items, {}, self.sessions[1]["user_id"], self.rooms[0])
            store.load_messages(items)
            # Sync recovery success is separate from live-W07 receive latency.
            delivery.received = value
            self.succeeded += 1
            before = len(store.messages)
            measurement.replay_started(time.monotonic())
            await synchronize(replacement, store, saved)
            require(len(store.messages) == before, "SYNC_REPLAY_DUPLICATE_PROJECTION")
            same_message(store.messages[delivery.ack_id], value)
            measurement.replayed(time.monotonic())
            self.reconnect_result = {"status": "verified", **measurement.report(),
                "saved_cursor_replay_deduplicated": True, "qa_projection_atomic_persistence": True,
                "browser_persistence": "not_measured"}
        finally:
            store.close()

    async def e2e(self, http):
        first = await self.send(0, sender_event=True)
        await self.ack(self.clients[0], first)  # same C1, same payload, NEW request event_id
        await self.ack(self.clients[0], first, "changed-valid-text", "IDEMPOTENCY_CONFLICT")
        await self.ack(self.clients[0], first, "", "INVALID_ARGUMENT")
        await self.send(1, sender_event=True)
        if self.args.reconnect:
            await self.reconnect(http)
        await self.history(http)

    async def load(self, http):
        start = time.monotonic()
        deadline = start + self.args.duration
        self.load_evidence = LoadEvidence(self.args.users, self.args.duration, start)
        if self.args.users == 50 and self.args.duration == 600:
            require(urlsplit(self.config["ws_url"]).scheme == "wss", "BASELINE_REQUIRES_WSS")
        async def user_loop(index):
            scheduled = start + (index % 2) * 2.5
            while scheduled < deadline:
                await asyncio.sleep(max(0, scheduled - time.monotonic()))
                if time.monotonic() >= deadline:
                    break
                try:
                    await self.send(index, sender_event=True)
                except ProtocolFailure as error:
                    self.errors[str(error)] = self.errors.get(str(error), 0) + 1
                    break
                except TimeoutError:
                    self.errors["DELIVERY_TIMEOUT"] = self.errors.get("DELIVERY_TIMEOUT", 0) + 1
                    break
                scheduled += 5
                # Do not turn delayed operations into catch-up bursts.
                scheduled = max(scheduled, time.monotonic())
        await asyncio.gather(*(user_loop(i) for i in range(len(self.clients))))
        if not self.errors:
            await asyncio.sleep(max(0, deadline - time.monotonic()))
        self.load_window = time.monotonic() - start
        self.connections.end_window()
        if self.errors:
            raise ProtocolFailure("LOAD_DELIVERY_FAILURES")
        self.load_evidence.require_met()
        require(self.connections.window_met(self.args.users, urlsplit(self.config["ws_url"]).scheme),
                "LOAD_AUTHENTICATED_CONNECTION_TARGET_NOT_MET")
        if self.args.reconnect:
            await self.reconnect(http)
        await self.history(http)

    async def run(self):
        monitoring = asyncio.create_task(self.monitor.run())
        try:
            timeout = aiohttp.ClientTimeout(total=self.args.timeout)
            async with aiohttp.ClientSession(timeout=timeout, cookie_jar=aiohttp.DummyCookieJar()) as http:
                try:
                    await self.prepare(http)
                    self.connections.begin_window()
                    if self.args.mode == "e2e":
                        await self.e2e(http)
                    else:
                        await self.load(http)
                    for client in self.clients:
                        require(client.failure is None, client.failure or "WS_FAILURE")
                finally:
                    self.connections.end_window()
                    await asyncio.gather(*(client.close() for client in self.clients), return_exceptions=True)
        finally:
            monitoring.cancel()
            await asyncio.gather(monitoring, return_exceptions=True)
            self.monitor.sample()

    def report(self, status, failure=None):
        p95 = None
        if self.latencies:
            p95 = sorted(self.latencies)[math.ceil(len(self.latencies) * .95) - 1]
        return {"status": status, "mode": self.args.mode, "failure_code": failure,
                "users": self.args.users, "rooms": self.args.users // 2,
                "baseline_requested": self.args.mode == "load" and self.args.users == 50
                                      and self.args.duration == 600,
                "baseline_measured": status == "passed" and self.args.mode == "load"
                                     and self.args.users == 50 and self.args.duration == 600
                                     and self.load_evidence is not None and self.load_evidence.met
                                     and self.connections.window_met(50, "wss"),
                "load_window_seconds": getattr(self, "load_window", None),
                "authenticated_connections": self.connections.report(),
                "load_dispatch_evidence": self.load_evidence.report() if self.load_evidence else None,
                "requested_duration_seconds": self.args.duration if self.args.mode == "load" else None,
                "send_interval_seconds": 5 if self.args.mode == "load" else None,
                "text_max_bytes": 1024, "attempted": self.attempted,
                "ack_and_receiver_or_sync_success": self.succeeded,
                "failed_or_unconfirmed": self.attempted - self.succeeded,
                "success_rate": self.succeeded / self.attempted if self.attempted else None,
                "errors": self.errors, "live_receiver_latency_samples": len(self.latencies),
                "live_receiver_protocol_p95_ms": p95, "reconnect": self.reconnect_result,
                "process": self.monitor.report(), "python_version": __import__("platform").python_version(),
                "aiohttp_version": aiohttp.__version__, "browser_persistence": "not_measured",
                "browser_presentation": "not_measured", "latency_boundary": "send_to_receiver_protocol_W07"}


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("mode", choices=("e2e", "load"))
    result.add_argument("--config", required=True, type=Path,
                        help="Owner-only JSON: api_base_url, ws_url, users[session OR login]")
    result.add_argument("--users", type=int, help="Even load user override; defaults 50 (e2e 2)")
    result.add_argument("--duration", type=float, default=600, help="Load seconds; baseline 600")
    result.add_argument("--timeout", type=float, default=15, help="Per request/delivery timeout seconds")
    result.add_argument("--reconnect", action="store_true", help="Verify first room offline recovery W13-W16")
    result.add_argument("--state", type=Path, help="Owner-only SQLite projection/cursor file; contains QA text/IDs")
    result.add_argument("--monitor-pid", type=int, help="Real local Linux product PID for CPU/RSS sampling")
    return result


def main():
    args = parser().parse_args()
    args.users = args.users if args.users is not None else (2 if args.mode == "e2e" else 50)
    exercise = None
    try:
        if not math.isfinite(args.duration) or args.duration <= 0 or not math.isfinite(args.timeout) or \
                args.timeout <= 0 or (args.reconnect and args.state is None) or \
                (args.monitor_pid is not None and args.monitor_pid <= 0):
            raise InputFailure("INVALID_CLI_INPUT")
        config = read_config(args.config, args.mode, args.users)
        exercise = Exercise(args, config)
        asyncio.run(exercise.run())
        print(json.dumps(exercise.report("passed"), sort_keys=True))
        return 0
    except InputFailure as error:
        code, exit_code = str(error), 2
    except ProtocolFailure as error:
        code, exit_code = str(error), 1
    except (aiohttp.ClientError, ConnectionError, TimeoutError):
        code, exit_code = "TARGET_UNAVAILABLE_OR_TIMEOUT", 1
    except OSError:
        code, exit_code = "LOCAL_FILE_OR_TARGET_UNAVAILABLE", 2
    except sqlite3.Error:
        code, exit_code = "QA_STATE_STORAGE_FAILED", 2
    except (ValueError, TypeError, KeyError, IndexError):
        code, exit_code = "MALFORMED_INPUT_OR_TARGET_RESPONSE", 1
    except KeyboardInterrupt:
        code, exit_code = "INTERRUPTED", 130
    if exercise:
        result = exercise.report("failed", code)
    else:
        result = {"status": "failed", "failure_code": code, "browser_persistence": "not_measured",
                  "browser_presentation": "not_measured"}
    print(json.dumps(result, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
