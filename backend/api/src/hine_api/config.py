"""Fail-closed deployment settings; secrets and references never enter diagnostics."""
import hmac
import json
import os
import re
from dataclasses import dataclass, field
from ipaddress import IPv4Network, IPv6Network, ip_network
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    valid: bool = False
    environment: str = ""
    host: str = "0.0.0.0"
    port: int = 8080
    public_origin: str = ""
    database_url: str = field(default="", repr=False)
    database_schema: str = "public"
    jwt_issuer: str = ""
    jwt_audience: str = ""
    jwt_signing_key: str = field(default="", repr=False)
    realtime_url: str = field(default="", repr=False)
    outbound_token: str = field(default="", repr=False)
    realtime_token: str = field(default="", repr=False)
    access_ttl_seconds: int = 900
    refresh_ttl_seconds: int = 1209600
    invalidation_retention_seconds: int = 900
    sync_page_limit: int = 100
    sync_scan_limit: int = 1000
    dependency_timeout: int = 2
    trusted_proxy_networks: tuple[IPv4Network | IPv6Network, ...] = ()
    gcs_bucket: str | None = None
    gcs_credentials_file: str | None = field(default=None, repr=False)
    gcs_project: str | None = None
    gcs_signing_service_account: str | None = field(default=None, repr=False)
    upload_max_bytes: int = 10485760

    @classmethod
    def from_env(cls, environment=None):
        values = os.environ if environment is None else environment
        fields = {}
        valid = True

        def text(name, default=None):
            nonlocal valid
            value = values.get(name, default)
            if not isinstance(value, str) or not value or "\x00" in value:
                valid = False
                return ""
            return value

        def integer(name, default=None, maximum=2147483647):
            nonlocal valid
            value = values.get(name, default)
            if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,10}", value) or not 1 <= int(value) <= maximum:
                valid = False
                return 1
            return int(value)

        def secret(path, token=False):
            nonlocal valid
            try:
                with Path(path).open("rb") as source:
                    raw = source.read(4097)
                if len(raw) > 4096:
                    raise ValueError
                result = raw.decode("utf-8").rstrip("\r\n")
                if not result or "\x00" in result or (token and not re.fullmatch(r"[A-Za-z0-9._~+/-]+=*", result)):
                    raise ValueError
                return result
            except (OSError, ValueError, UnicodeError):
                valid = False
                return ""

        def url(value, schemes, origin=False):
            nonlocal valid
            try:
                parsed = urlsplit(value)
                if parsed.scheme not in schemes or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
                    valid = False
                _ = parsed.port
                if origin and parsed.path:
                    valid = False
            except ValueError:
                valid = False
            return value.rstrip("/")

        fields["environment"] = text("HINE_ENV")
        if fields["environment"] not in {"development", "dev", "test", "staging", "production"}:
            valid = False
        fields["host"] = text("API_HOST", "0.0.0.0")
        fields["port"] = integer("API_PORT", "8080", 65535)
        fields["public_origin"] = url(text("PUBLIC_ORIGIN"), {"https"}, True)
        fields["realtime_url"] = url(text("REALTIME_INTERNAL_URL"), {"http", "https"}, True)
        ref = values.get("DATABASE_URL_SECRET_REF")
        fields["database_url"] = secret(ref) if ref else text("DATABASE_URL")
        try:
            parsed = urlsplit(fields["database_url"])
            if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname or not parsed.path or parsed.fragment:
                valid = False
            _ = parsed.port
        except ValueError:
            valid = False
        fields["database_schema"] = text("DATABASE_SCHEMA", "public")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", fields["database_schema"]):
            valid = False
            fields["database_schema"] = "public"
        fields["jwt_issuer"] = text("JWT_ISSUER")
        fields["jwt_audience"] = text("JWT_AUDIENCE")
        fields["jwt_signing_key"] = secret(text("JWT_SIGNING_KEY_SECRET_REF"))
        if len(fields["jwt_signing_key"].encode("utf-8")) < 32:
            valid = False
        fields["outbound_token"] = secret(text("INTERNAL_CALLER_TOKEN_SECRET_REF"), True)
        try:
            callers = json.loads(text("INTERNAL_ALLOWED_CALLERS"))
            if not isinstance(callers, dict) or "realtime" not in callers or any(not isinstance(k, str) or not isinstance(v, str) or not k or not v for k, v in callers.items()):
                raise ValueError
            fields["realtime_token"] = secret(callers["realtime"], True)
        except (ValueError, TypeError):
            fields["realtime_token"] = ""
            valid = False
        if fields["outbound_token"] and fields["realtime_token"] and hmac.compare_digest(fields["outbound_token"], fields["realtime_token"]):
            valid = False
        if len(fields["outbound_token"].encode("utf-8")) < 32 or len(fields["realtime_token"].encode("utf-8")) < 32:
            valid = False
        for name, key, default, maximum in (
            ("ACCESS_TTL_SECONDS", "access_ttl_seconds", "900", 86400),
            ("REFRESH_TTL_SECONDS", "refresh_ttl_seconds", "1209600", 31536000),
            ("INVALIDATION_RETENTION_SECONDS", "invalidation_retention_seconds", None, 2147483647),
            ("SYNC_PAGE_LIMIT", "sync_page_limit", None, 100),
            ("SYNC_SCAN_LIMIT", "sync_scan_limit", None, 1000),
        ):
            fields[key] = integer(name, default, maximum)
        if fields["invalidation_retention_seconds"] < fields["access_ttl_seconds"] or fields["refresh_ttl_seconds"] < fields["access_ttl_seconds"]:
            valid = False
        proxy_networks = values.get("TRUSTED_PROXY_NETWORKS", "")
        try:
            if not isinstance(proxy_networks, str):
                raise TypeError
            fields["trusted_proxy_networks"] = tuple(
                ip_network(value.strip(), strict=True)
                for value in proxy_networks.split(",")
                if proxy_networks
            )
            if proxy_networks and any("/" not in value or "%" in value for value in proxy_networks.split(",")):
                raise ValueError
        except (ValueError, TypeError):
            fields["trusted_proxy_networks"] = ()
            valid = False
        fields["gcs_credentials_file"] = values.get("GCS_CREDENTIALS_SECRET_REF") or values.get("GOOGLE_APPLICATION_CREDENTIALS") or None
        for key, name in (("gcs_bucket", "GCS_BUCKET"), ("gcs_project", "GCS_PROJECT"), ("gcs_signing_service_account", "GCS_SIGNING_SERVICE_ACCOUNT")):
            fields[key] = values.get(name) or None
        if fields["gcs_bucket"]:
            fields["upload_max_bytes"] = integer("UPLOAD_MAX_BYTES", None, 10485760)
        return cls(valid=valid, **fields)
