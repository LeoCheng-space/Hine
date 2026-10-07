"""Shared canonical validation and privacy-preserving REST envelopes."""
from datetime import timezone
from uuid import uuid4

from aiohttp import web
from hine_realtime import protocol as p

keys = p.keys
string = p.string
integer = p.integer
uuid = p.uuid


class Fault(Exception):
    def __init__(self, code, retryable=False, auth_layer=None, retry_after_ms=None):
        super().__init__(code)
        self.code = code
        self.retryable = retryable
        self.auth_layer = auth_layer
        self.retry_after_ms = retry_after_ms


def iso(value):
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def entity(value):
    p.string(value, True)
    p.check(len(value) <= 128)
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError:
        raise p.Invalid("Invalid contract structure") from None
    return value


def lookup_entity(value):
    # PostgreSQL TEXT cannot hold NUL, so no server-issued ID can equal it.
    # SQL NULL yields a nonexistent lookup without changing canonical input,
    # C1 payload equality, or the resource's ordinary authorization result.
    entity(value)
    return None if "\x00" in value else value


async def body(request):
    if request.content_type != "application/json":
        raise Fault("UNSUPPORTED_MEDIA_TYPE")
    try:
        raw = await request.read()
    except web.HTTPRequestEntityTooLarge:
        raise Fault("PAYLOAD_TOO_LARGE") from None
    return p.obj(p.loads(raw))


def response(data, status=200):
    if status == 204:
        return web.Response(status=204)
    return web.json_response({"data": data}, status=status, dumps=p.dumps)


def list_response(items, next_cursor):
    return web.json_response({"data": {"items": items}, "meta": {"next_cursor": next_cursor}}, dumps=p.dumps)


def error(failure):
    details = {}
    if failure.auth_layer is not None:
        details["auth_layer"] = failure.auth_layer
    if failure.retry_after_ms is not None:
        details["retry_after_ms"] = failure.retry_after_ms
    return web.json_response({"error": {"code": failure.code, "message": p.MESSAGES[failure.code], "request_id": str(uuid4()), "retryable": failure.retryable, "details": details}}, status=p.ERROR_STATUS[failure.code], dumps=p.dumps)
