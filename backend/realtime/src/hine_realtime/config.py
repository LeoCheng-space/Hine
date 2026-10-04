"""Deployment configuration, with secrets kept out of repr and diagnostics."""
import hmac
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    valid: bool = False
    environment: str = ""
    host: str = "0.0.0.0"
    port: int = 8081
    api_url: str = field(default="", repr=False)
    redis_url: str = field(default="", repr=False)
    outbound_token: str = field(default="", repr=False)
    api_token: str = field(default="", repr=False)
    prefix: str = "hine:realtime"
    poll_seconds: int = 5
    stale_seconds: int = 15
    catchup_ms: int = 1000
    heartbeat_interval: int = 30
    heartbeat_timeout: int = 90
    max_frame_bytes: int = 65536
    max_outgoing_frames: int = 128
    max_outgoing_bytes: int = 1048576
    max_connections: int = 1000
    max_group_removals: int = 4096
    frame_rate: int = 120
    frame_burst: int = 240
    auth_timeout: int = 10
    dependency_timeout: int = 2
    send_timeout: int = 2

    @classmethod
    def from_env(cls, environment=None):
        values = os.environ if environment is None else environment
        fields = {}
        valid = True

        def text(name, default=None):
            nonlocal valid
            value = values.get(name, default)
            if not isinstance(value, str) or not value:
                valid = False
                return ""
            return value

        def integer(name, default=None):
            nonlocal valid
            value = values.get(name, default)
            if not isinstance(value, str) or re.fullmatch(r"[0-9]+", value) is None:
                valid = False
                return 1
            parsed = int(value) if len(value) < 10 else 0
            if not 0 < parsed <= 2147483647:
                valid = False
                return 1
            return parsed

        def secret(path):
            nonlocal valid
            try:
                with Path(path).open("rb") as source:
                    raw = source.read(4097)
                if len(raw) > 4096:
                    raise ValueError
                result = raw.decode("ascii").rstrip("\r\n")
                if not result or re.fullmatch(r"[A-Za-z0-9._~+/-]+=*", result) is None:
                    raise ValueError
                return result
            except (OSError, ValueError, UnicodeError):
                valid = False
                return ""

        fields["environment"] = text("HINE_ENV")
        fields["host"] = text("REALTIME_HOST", "0.0.0.0")
        fields["port"] = integer("REALTIME_PORT", "8081")
        if fields["port"] > 65535:
            valid = False
            fields["port"] = 8081
        fields["api_url"] = text("API_INTERNAL_URL").rstrip("/")
        try:
            url = urlsplit(fields["api_url"])
            if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password or url.query or url.fragment or url.path:
                valid = False
            _ = url.port
        except ValueError:
            valid = False
        fields["outbound_token"] = secret(text("INTERNAL_CALLER_TOKEN_SECRET_REF"))
        try:
            callers = json.loads(text("INTERNAL_ALLOWED_CALLERS"))
            if not isinstance(callers, dict) or "api" not in callers or any(not isinstance(k, str) or not isinstance(v, str) or not v for k, v in callers.items()):
                raise ValueError
            fields["api_token"] = secret(callers["api"])
        except (ValueError, TypeError):
            valid = False
            fields["api_token"] = ""
        if fields["outbound_token"] and hmac.compare_digest(fields["outbound_token"], fields["api_token"]):
            valid = False
        ref = values.get("REDIS_URL_SECRET_REF")
        try:
            if ref:
                with Path(ref).open("rb") as source:
                    raw = source.read(4097)
                if len(raw) > 4096:
                    raise ValueError
                fields["redis_url"] = raw.decode("utf-8").rstrip("\r\n")
            else:
                fields["redis_url"] = text("REDIS_URL")
            url = urlsplit(fields["redis_url"])
            if url.scheme not in {"redis", "rediss"} or not url.hostname or url.query or url.fragment or re.fullmatch(r"/[0-9]+|", url.path) is None:
                raise ValueError
            _ = url.port
        except (OSError, ValueError, UnicodeError):
            valid = False
            fields["redis_url"] = ""
        fields["prefix"] = text("REALTIME_REDIS_PREFIX", "hine:realtime")
        for name, key in [
            ("INVALIDATION_POLL_SECONDS", "poll_seconds"),
            ("INVALIDATION_STALE_SECONDS", "stale_seconds"),
            ("NOTICE_CATCHUP_HOLD_MS", "catchup_ms"),
            ("HEARTBEAT_INTERVAL_SECONDS", "heartbeat_interval"),
            ("HEARTBEAT_TIMEOUT_SECONDS", "heartbeat_timeout"),
        ]:
            fields[key] = integer(name)
        if not fields["poll_seconds"] < fields["stale_seconds"] <= 15 or fields["catchup_ms"] > 1000 or fields["heartbeat_interval"] >= fields["heartbeat_timeout"]:
            valid = False
        for name, key, default in [
            ("REALTIME_MAX_FRAME_BYTES", "max_frame_bytes", "65536"),
            ("REALTIME_MAX_OUTGOING_FRAMES", "max_outgoing_frames", "128"),
            ("REALTIME_MAX_OUTGOING_BYTES", "max_outgoing_bytes", "1048576"),
            ("REALTIME_MAX_CONNECTIONS", "max_connections", "1000"),
            ("REALTIME_MAX_GROUP_REMOVALS", "max_group_removals", "4096"),
            ("REALTIME_FRAME_RATE", "frame_rate", "120"),
            ("REALTIME_FRAME_BURST", "frame_burst", "240"),
        ]:
            fields[key] = integer(name, default)
        return cls(valid=valid, **fields)
