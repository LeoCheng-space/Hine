"""Structural contract validation only; BB owns Unicode length/quota semantics."""
import json
import re
from datetime import datetime, timezone
from uuid import uuid4

ERROR_STATUS = {
    "INVALID_ARGUMENT": 400, "UNAUTHENTICATED": 401, "FORBIDDEN": 403,
    "NOT_FOUND": 404, "CONFLICT": 409, "IDEMPOTENCY_CONFLICT": 409,
    "CURSOR_INVALID": 400, "CURSOR_EXPIRED": 410, "SYNC_RESET_REQUIRED": 410,
    "PAYLOAD_TOO_LARGE": 413, "UNSUPPORTED_MEDIA_TYPE": 415,
    "UPLOAD_NOT_READY": 409, "RATE_LIMITED": 429,
    "DEPENDENCY_UNAVAILABLE": 503, "PERSISTENCE_FAILED": 503,
    "OUTCOME_UNCONFIRMED": 503,
}
MESSAGES = {code: code.replace("_", " ").capitalize() for code in ERROR_STATUS}
UUID_PATTERN = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z")


class Invalid(ValueError):
    """Never includes the rejected value in the exception."""


def check(condition):
    if not condition:
        raise Invalid("Invalid contract structure")


def obj(value):
    check(isinstance(value, dict))
    return value


def keys(value, required, optional=()):
    obj(value)
    check(set(required) <= value.keys())
    check(value.keys() <= set(required) | set(optional))
    return value


def string(value, nonempty=False):
    check(isinstance(value, str) and (not nonempty or bool(value)))
    return value


def integer(value, minimum=0):
    check(type(value) is int and minimum <= value <= 9007199254740991)
    return value


def boolean(value):
    check(type(value) is bool)
    return value


def uuid(value):
    check(isinstance(value, str) and UUID_PATTERN.fullmatch(value) is not None)
    return value


def timestamp(value):
    string(value, True)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        check("T" in value and parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0)
        return parsed.timestamp()
    except (ValueError, OverflowError):
        raise Invalid("Invalid timestamp") from None


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def loads(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            check(key not in result)
            result[key] = value
        return result

    def constant(_):
        raise Invalid("Invalid JSON number")

    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError):
        raise Invalid("Invalid JSON") from None


def dumps(value):
    return json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":"), sort_keys=True)


def envelope(value):
    obj(value)
    for key in ["event", "event_id", "timestamp", "payload"]:
        check(key in value)
    string(value["event"], True)
    uuid(value["event_id"])
    timestamp(value["timestamp"])
    obj(value["payload"])
    if "correlation_id" in value:
        uuid(value["correlation_id"])
    if "conversation_id" in value:
        string(value["conversation_id"])
    if "sender_id" in value:
        string(value["sender_id"])
    return value


def event(name, payload, correlation=None, conversation=None, event_id=None, time=None, sender=None):
    result = {"event": name, "event_id": event_id or str(uuid4()), "timestamp": time or now(), "payload": payload}
    if correlation is not None:
        result["correlation_id"] = correlation
    if conversation is not None:
        result["conversation_id"] = conversation
    if sender is not None:
        result["sender_id"] = sender
    return result


def message_payload(value, received=False):
    obj(value)
    check("type" in value and value["type"] in {"text", "image", "file"})
    content = "text" if value["type"] == "text" else "attachment_id"
    if received:
        keys(value, ["message_id", "type", content, "order_key"], ["client_message_id"])
        uuid(value["message_id"])
        order_key(value["order_key"])
        if "client_message_id" in value:
            uuid(value["client_message_id"])
    else:
        keys(value, ["client_message_id", "type", content])
        uuid(value["client_message_id"])
    # Empty/oversize text and EntityIDs intentionally reach BB canonical validation.
    string(value[content])
    return content


def order_key(value):
    check(isinstance(value, str) and re.fullmatch(r"[0-9]{20}", value) is not None)
    check(1 <= int(value) <= 9223372036854775807)


def access_result(value):
    obj(value)
    for key in ["subject_id", "user_id", "session_id", "session_generation", "expires_at", "session_valid", "invalidation_position"]:
        check(key in value)
    for key in ["subject_id", "user_id", "session_id"]:
        string(value[key], True)
    integer(value["session_generation"])
    boolean(value["session_valid"])
    timestamp(value["expires_at"])
    integer(value["invalidation_position"])
    return value


def presence_targets(value, limit=100):
    """Trusted BB IDs: validate structure, not BB's canonical length policy."""
    keys(value, ["targets", "next_cursor", "invalidation_position"])
    integer(value["invalidation_position"])
    check(isinstance(value["targets"], list) and len(value["targets"]) <= limit)
    users = set()
    for target in value["targets"]:
        keys(target, ["user_id", "subject_id"])
        string(target["user_id"], True)
        string(target["subject_id"], True)
        check(target["user_id"] not in users)
        users.add(target["user_id"])
    if value["next_cursor"] is not None:
        string(value["next_cursor"], True)
        check(bool(value["targets"]))
    return value


def persisted_result(value):
    obj(value)
    for key in ["message_id", "event_id", "order_key", "created_at", "recipient_ids", "status", "invalidation_position", "membership_version"]:
        check(key in value)
    uuid(value["message_id"])
    uuid(value["event_id"])
    order_key(value["order_key"])
    timestamp(value["created_at"])
    check(value["status"] == "persisted")
    integer(value["invalidation_position"])
    if value["membership_version"] is not None:
        integer(value["membership_version"], 1)
    recipients = value["recipient_ids"]
    check(isinstance(recipients, list) and bool(recipients))
    for recipient in recipients:
        string(recipient, True)
    check(len(set(recipients)) == len(recipients))
    return value


def invalidation(value):
    keys(value, ["position", "session_id", "reason", "min_valid_generation", "committed_at"])
    integer(value["position"], 1)
    string(value["session_id"], True)
    check(value["reason"] in {"refresh", "logout", "replaced"})
    if value["reason"] == "refresh":
        integer(value["min_valid_generation"], 1)
    else:
        check(value["min_valid_generation"] is None)
    timestamp(value["committed_at"])
    return value


def invalidation_page(value, after):
    keys(value, ["entries", "next_position", "head_position", "has_more"])
    integer(value["next_position"])
    integer(value["head_position"])
    boolean(value["has_more"])
    check(isinstance(value["entries"], list) and len(value["entries"]) <= 500)
    if after is None:
        check(value["entries"] == [] and value["next_position"] == value["head_position"] and value["has_more"] is False)
    else:
        position = after
        for entry in value["entries"]:
            invalidation(entry)
            check(entry["position"] == position + 1)
            position += 1
        check(value["next_position"] == position <= value["head_position"])
        check(value["has_more"] == (position < value["head_position"]))
        check(not value["has_more"] or bool(value["entries"]))
    return value


def notice(value, external=False):
    obj(value)
    check(value.get("type") in {"conversation_events", "session_invalidation"})
    content = value["type"]
    keys(value, ["notice_id", "type", "committed_at", "invalidation_position", content])
    uuid(value["notice_id"])
    timestamp(value["committed_at"])
    integer(value["invalidation_position"])
    if content == "session_invalidation":
        invalidation(value[content])
        check(value["invalidation_position"] == value[content]["position"])
        check(value["committed_at"] == value[content]["committed_at"])
        return value
    body = keys(value[content], ["source", "conversation_id", "membership_version", "deliveries"])
    source = body["source"]
    mapping = {"W05": "message.created", "W08": "message.status", "W09": "message.status", "A14": "conversation.member_added", "A16": "conversation.member_added", "A15": "conversation.updated", "A17": "conversation.updated", "A18": "conversation.member_removed"}
    check(source in mapping and (not external or source in {"A14", "A15", "A16", "A17", "A18"}))
    string(body["conversation_id"])
    if body["membership_version"] is not None:
        integer(body["membership_version"], 1)
    if source.startswith("A"):
        check(body["membership_version"] is not None)
    check(isinstance(body["deliveries"], list) and bool(body["deliveries"]))
    recipients = set()
    for delivery in body["deliveries"]:
        keys(delivery, ["recipient_user_id", "envelope"])
        recipient = string(delivery["recipient_user_id"])
        check(recipient not in recipients)
        recipients.add(recipient)
        frame = envelope(delivery["envelope"])
        check(frame["event"] == mapping[source] and frame.get("conversation_id") == body["conversation_id"])
        check("correlation_id" not in frame)
        allowed_top = {"event", "event_id", "timestamp", "payload", "conversation_id"}
        payload = frame["payload"]
        if source == "W05":
            allowed_top.add("sender_id")
            check("sender_id" in frame)
            message_payload(payload, received=True)
            check("client_message_id" not in payload or recipient == frame["sender_id"])
        elif source in {"W08", "W09"}:
            keys(payload, ["kind", "message_id", "recipient_id", "status", "updated_at"])
            check(payload["kind"] == "direct" and payload["status"] in {"delivered", "read"})
            uuid(payload["message_id"])
            string(payload["recipient_id"])
            timestamp(payload["updated_at"])
        elif source in {"A14", "A16"}:
            keys(payload, ["member_id", "role", "actor_id", "membership_version"])
            check(payload["role"] in {"admin", "member"})
            string(payload["member_id"])
            string(payload["actor_id"])
        elif source == "A18":
            keys(payload, ["member_id", "change", "membership_version"], ["actor_id"])
            string(payload["member_id"])
            check(payload["change"] == "removed")
            if recipient == payload["member_id"]:
                check("actor_id" not in payload)
            elif "actor_id" in payload:
                string(payload["actor_id"])
        else:
            keys(payload, ["changes", "actor_id", "membership_version"])
            string(payload["actor_id"])
            changes = obj(payload["changes"])
            if source == "A15":
                keys(changes, ["kind", "title"])
                check(changes["kind"] == "title")
                string(changes["title"])
            else:
                keys(changes, ["kind", "member_id", "role"])
                check(changes["kind"] == "role" and changes["role"] in {"admin", "member"})
                string(changes["member_id"])
        check(frame.keys() <= allowed_top)
        if source.startswith("A"):
            integer(payload["membership_version"], 1)
            check(payload["membership_version"] == body["membership_version"])
    return value
