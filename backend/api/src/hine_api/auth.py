"""JWT/access and refresh authority, always rechecked in PostgreSQL."""
import asyncio
import base64
import hashlib
import hmac
import re
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from ipaddress import IPv6Address, ip_address
from uuid import uuid4

import asyncpg
import jwt
from hine_realtime import protocol as p

from . import db
from .support import Fault, body, entity, iso, lookup_entity, response

COOKIE = "hine_refresh"
COOKIE_PATH = "/api/v1/auth"


@asynccontextmanager
async def committed(conn):
    tx = conn.transaction()
    await tx.start()
    try:
        yield
    except BaseException:
        if conn.is_in_transaction():
            await tx.rollback()
        raise
    else:
        try:
            await tx.commit()
        except (asyncpg.PostgresError, OSError, TimeoutError):
            raise Fault("OUTCOME_UNCONFIRMED", True) from None


def opaque():
    return secrets.token_urlsafe(24)


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def source_ip(request, settings):
    """Trust only a configured TCP peer and its single overwritten IP header."""
    try:
        peer = ip_address(request.remote)
    except (ValueError, TypeError):
        return "unknown"
    address = peer
    if any(peer in network for network in settings.trusted_proxy_networks):
        forwarded = request.headers.getall("X-Hine-Client-IP", [])
        if len(forwarded) == 1 and "%" not in forwarded[0]:
            try:
                address = ip_address(forwarded[0])
            except ValueError:
                pass
    # Equivalent IPv4-mapped spellings must not create extra quota buckets.
    if isinstance(address, IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return str(address)


def password_hash(password, salt=None):
    salt = secrets.token_bytes(16) if salt is None else salt
    value = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1, maxmem=67108864, dklen=32)
    return "scrypt$16384$8$1$" + base64.b64encode(salt).decode("ascii") + "$" + base64.b64encode(value).decode("ascii")


def password_valid(password, stored):
    try:
        method, n, r, parallel, salt, _expected = stored.split("$")
        if (method, n, r, parallel) != ("scrypt", "16384", "8", "1"):
            return False
        return hmac.compare_digest(password_hash(password, base64.b64decode(salt, validate=True)), stored)
    except (ValueError, TypeError):
        return False


def credentials(value, register=False):
    p.keys(value, ["email", "password", "display_name"] if register else ["email", "password", "device_id"])
    email = p.string(value["email"], True)
    password = p.string(value["password"], True)
    p.check(len(email) <= 320 and re.fullmatch(r"[^\s@\x00-\x1f\x7f]+@[^\s@\x00-\x1f\x7f]+\.[^\s@\x00-\x1f\x7f]+", email) is not None)
    p.check(len(password) <= 1024)
    for item in (email, password):
        try:
            item.encode("utf-8", errors="strict")
        except UnicodeError:
            raise p.Invalid("Invalid contract structure") from None
    if register:
        p.string(value["display_name"], True)
        value["display_name"].encode("utf-8", errors="strict")
    elif value["device_id"] is not None:
        p.string(value["device_id"], True)
        value["device_id"].encode("utf-8", errors="strict")
    return email.casefold(), password


class AuthService:
    def __init__(self, runtime):
        self.runtime = runtime
        self.hash_slots = asyncio.Semaphore(4)

    async def hashed(self, password, stored=None):
        async with self.hash_slots:
            if stored is None:
                return await asyncio.to_thread(password_hash, password)
            return await asyncio.to_thread(password_valid, password, stored)

    def claims(self, token):
        try:
            claims = jwt.decode(token, self.runtime.settings.jwt_signing_key, algorithms=["HS256"], issuer=self.runtime.settings.jwt_issuer, audience=self.runtime.settings.jwt_audience, options={"require": ["exp", "iat", "sub", "sid", "gen", "did", "iss", "aud", "jti"], "strict_aud": True})
            for field in ("sub", "sid"):
                entity(claims[field])
            p.string(claims["did"], True)
            p.integer(claims["gen"], 1)
            p.integer(claims["exp"], 1)
            p.integer(claims["iat"], 1)
            p.uuid(claims["jti"])
            return claims
        except (jwt.InvalidTokenError, p.Invalid, TypeError, ValueError, KeyError, UnicodeError):
            raise Fault("UNAUTHENTICATED", auth_layer="user_session") from None

    async def binding(self, conn, value, lock=False):
        for field in ("subject_id", "session_id"):
            entity(value[field])
        p.integer(value["session_generation"], 1)
        if "device_id" in value:
            p.string(value["device_id"], True)
        sql = "SELECT s.*,u.user_id FROM sessions s JOIN users u ON u.subject_id=s.subject_id WHERE s.session_id=$1"
        if lock:
            sql += " FOR SHARE OF s"
        row = await conn.fetchrow(sql, lookup_entity(value["session_id"]))
        if row is None or row["revoked"] or row["subject_id"] != value["subject_id"] or row["generation"] != value["session_generation"] or row["access_expires_at"] <= datetime.now(timezone.utc) or ("device_id" in value and row["device_id"] != value["device_id"]):
            raise Fault("UNAUTHENTICATED", auth_layer="user_session")
        return {"subject_id": row["subject_id"], "user_id": row["user_id"], "session_id": row["session_id"], "device_id": row["device_id"], "session_generation": row["generation"], "expires_at": row["access_expires_at"]}

    async def access(self, request, conn, lock=False):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            raise Fault("UNAUTHENTICATED")
        claims = self.claims(header[7:])
        binding = await self.binding(conn, {"subject_id": claims["sub"], "session_id": claims["sid"], "session_generation": claims["gen"], "device_id": claims["did"]}, lock)
        if claims["exp"] != int(binding["expires_at"].timestamp()):
            raise Fault("UNAUTHENTICATED", auth_layer="user_session")
        return binding

    async def validate_access(self, value):
        p.keys(value, ["access_token", "device_id"])
        p.string(value["access_token"], True)
        p.string(value["device_id"], True)
        claims = self.claims(value["access_token"])
        if claims["did"] != value["device_id"]:
            raise Fault("UNAUTHENTICATED", auth_layer="user_session")
        async with self.runtime.pool.acquire() as conn, conn.transaction():
            position = await db.frontier(conn)
            binding = await self.binding(conn, {"subject_id": claims["sub"], "session_id": claims["sid"], "session_generation": claims["gen"], "device_id": claims["did"]}, True)
            if claims["exp"] != int(binding["expires_at"].timestamp()):
                raise Fault("UNAUTHENTICATED", auth_layer="user_session")
        return {key: binding[key] for key in ("subject_id", "user_id", "session_id", "session_generation")} | {"expires_at": iso(binding["expires_at"]), "session_valid": True, "invalidation_position": position}

    async def read_invalidations(self, value):
        p.keys(value, ["after_position", "limit"])
        after = value["after_position"]
        if after is not None:
            p.integer(after)
        limit = p.integer(value["limit"], 1)
        p.check(limit <= 500)
        async with self.runtime.pool.acquire() as conn, conn.transaction():
            head = await db.frontier(conn)
            if after is None:
                return {"entries": [], "next_position": head, "head_position": head, "has_more": False}
            floor = await conn.fetchval("SELECT min(position) FROM session_invalidations")
            if after > head or (floor is not None and after < floor - 1) or (floor is None and after < head):
                raise Fault("CURSOR_INVALID")
            rows = await conn.fetch("SELECT * FROM session_invalidations WHERE position>$1 ORDER BY position LIMIT $2", after, limit)
            entries = [{**dict(row), "committed_at": iso(row["committed_at"])} for row in rows]
            next_position = entries[-1]["position"] if entries else after
            return {"entries": entries, "next_position": next_position, "head_position": head, "has_more": next_position < head}

    async def quota(self, request, account, operation="login"):
        # Rolling 60-second window, persisted across processes. Denied requests
        # do no credential work and cannot grow the bounded per-key history.
        scopes = ((operation + ":account", digest(account), 10), (operation + ":ip", digest(source_ip(request, self.runtime.settings)), 60))
        delay = 0
        async with self.runtime.pool.acquire() as conn, committed(conn):
            for scope, key, maximum in scopes:
                await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1,0))", scope + ":" + key)
            now = await conn.fetchval("SELECT clock_timestamp()")
            cutoff = now - timedelta(seconds=60)
            for scope, key, maximum in scopes:
                row = await conn.fetchrow("SELECT COALESCE(sum(count),0) AS count,min(window_start) AS oldest FROM auth_rate_limits WHERE scope=$1 AND key=$2 AND window_start>$3", scope, key, cutoff)
                if row["count"] >= maximum:
                    # Counts normally equal one; an existing aggregated row
                    # expires as a unit, so its oldest timestamp is safe too.
                    seconds = ((row["oldest"] + timedelta(seconds=60)) - now).total_seconds()
                    delay = max(delay, max(1, int(seconds * 1000) + 1))
            if delay == 0:
                for scope, key, maximum in scopes:
                    await conn.execute("INSERT INTO auth_rate_limits(scope,key,window_start,count) VALUES($1,$2,$3,1) ON CONFLICT(scope,key,window_start) DO UPDATE SET count=auth_rate_limits.count+1", scope, key, now)
            await conn.execute("DELETE FROM auth_rate_limits WHERE window_start<=$1", cutoff)
        if delay:
            raise Fault("RATE_LIMITED", True, retry_after_ms=delay)


    def access_session(self, row, user_id):
        settings = self.runtime.settings
        claims = {"sub": row["subject_id"], "sid": row["session_id"], "did": row["device_id"], "gen": row["generation"], "exp": int(row["access_expires_at"].timestamp()), "iat": int(datetime.now(timezone.utc).timestamp()), "jti": str(uuid4()), "iss": settings.jwt_issuer, "aud": settings.jwt_audience}
        return {"access_token": jwt.encode(claims, settings.jwt_signing_key, algorithm="HS256"), "expires_at": iso(row["access_expires_at"]), "user_id": user_id, "device_id": row["device_id"], "session_generation": row["generation"]}

    async def notices(self, entries):
        for entry in entries:
            await self.runtime.notify({"notice_id": str(uuid4()), "type": "session_invalidation", "committed_at": entry["committed_at"], "invalidation_position": entry["position"], "session_invalidation": entry})


def runtime(request):
    from .server import RUNTIME
    return request.app[RUNTIME]


def set_cookie(reply, token, settings):
    reply.set_cookie(COOKIE, token, max_age=settings.refresh_ttl_seconds, path=COOKIE_PATH, secure=True, httponly=True, samesite="Strict")


async def cookie_request(request):
    if request.headers.get("Origin") != runtime(request).settings.public_origin or request.headers.get("Sec-Fetch-Site") not in {None, "same-origin", "none"}:
        raise Fault("FORBIDDEN")
    if await request.read():
        raise Fault("INVALID_ARGUMENT")


async def register_user(request):
    rt = runtime(request)
    value = await body(request)
    email, password = credentials(value, True)
    await rt.auth.quota(request, email, "register")
    encoded = await rt.auth.hashed(password)
    user_id, subject_id = opaque(), opaque()
    try:
        async with rt.pool.acquire() as conn, committed(conn):
            await conn.execute("INSERT INTO users(user_id,subject_id,email,password_hash,display_name) VALUES($1,$2,$3,$4,$5)", user_id, subject_id, email, encoded, value["display_name"])
            await conn.execute("INSERT INTO feed_heads(user_id,position) VALUES($1,0)", user_id)
    except asyncpg.UniqueViolationError:
        raise Fault("CONFLICT") from None
    return response({"id": user_id, "email": email, "display_name": value["display_name"], "avatar_attachment_id": None}, 201)


async def login(request):
    rt = runtime(request)
    value = await body(request)
    email, password = credentials(value)
    if request.headers.get("Origin") is not None and request.headers["Origin"] != rt.settings.public_origin:
        raise Fault("FORBIDDEN")
    await rt.auth.quota(request, email)
    async with rt.pool.acquire() as conn:
        user = await conn.fetchrow("SELECT * FROM users WHERE email=$1", email)
    # Missing accounts pay the same password KDF cost; never reveal the reason.
    if user is None:
        await rt.auth.hashed(password)
        raise Fault("UNAUTHENTICATED")
    if not await rt.auth.hashed(password, user["password_hash"]):
        raise Fault("UNAUTHENTICATED")
    token = secrets.token_urlsafe(48)
    entries = []
    async with rt.pool.acquire() as conn, committed(conn):
        await db.frontier(conn, True)
        device_id = value["device_id"]
        if device_id is None:
            device_id = opaque()
            await conn.execute("INSERT INTO devices(device_id,subject_id) VALUES($1,$2)", device_id, user["subject_id"])
        else:
            owner = await conn.fetchval("SELECT subject_id FROM devices WHERE device_id=$1", None if "\x00" in device_id else device_id)
            if owner != user["subject_id"]:
                raise Fault("UNAUTHENTICATED")
        old = await conn.fetch("SELECT session_id FROM sessions WHERE subject_id=$1 AND device_id=$2 AND NOT revoked ORDER BY session_id FOR UPDATE", user["subject_id"], device_id)
        for row in old:
            await conn.execute("UPDATE sessions SET revoked=TRUE WHERE session_id=$1", row["session_id"])
            entries.append(await db.invalidate(conn, row["session_id"], "replaced", None))
        now = datetime.now(timezone.utc).replace(microsecond=0)
        row = await conn.fetchrow("INSERT INTO sessions(session_id,subject_id,device_id,generation,access_expires_at,refresh_hash,refresh_expires_at) VALUES($1,$2,$3,1,$4,$5,$6) RETURNING *", opaque(), user["subject_id"], device_id, now + timedelta(seconds=rt.settings.access_ttl_seconds), digest(token), now + timedelta(seconds=rt.settings.refresh_ttl_seconds))
    reply = response(rt.auth.access_session(row, user["user_id"]))
    set_cookie(reply, token, rt.settings)
    await rt.auth.notices(entries)
    return reply


async def refresh(request):
    rt = runtime(request)
    await cookie_request(request)
    token = request.cookies.get(COOKIE)
    if not token:
        raise Fault("UNAUTHENTICATED")
    await rt.auth.quota(request, token, "refresh")
    fresh = secrets.token_urlsafe(48)
    async with rt.pool.acquire() as conn, committed(conn):
        await db.frontier(conn, True)
        row = await conn.fetchrow("SELECT s.*,u.user_id FROM sessions s JOIN users u ON u.subject_id=s.subject_id WHERE refresh_hash=$1 FOR UPDATE OF s", digest(token))
        now = datetime.now(timezone.utc).replace(microsecond=0)
        if row is None or row["revoked"] or row["refresh_expires_at"] <= now:
            raise Fault("UNAUTHENTICATED")
        updated = await conn.fetchrow("UPDATE sessions SET generation=generation+1,refresh_hash=$2,access_expires_at=$3,refresh_expires_at=$4 WHERE session_id=$1 RETURNING *", row["session_id"], digest(fresh), now + timedelta(seconds=rt.settings.access_ttl_seconds), now + timedelta(seconds=rt.settings.refresh_ttl_seconds))
        entry = await db.invalidate(conn, row["session_id"], "refresh", updated["generation"])
    reply = response(rt.auth.access_session(updated, row["user_id"]))
    set_cookie(reply, fresh, rt.settings)
    await rt.auth.notices([entry])
    return reply


async def logout(request):
    rt = runtime(request)
    await cookie_request(request)
    token = request.cookies.get(COOKIE)
    entries = []
    if token:
        async with rt.pool.acquire() as conn, committed(conn):
            await db.frontier(conn, True)
            row = await conn.fetchrow("SELECT * FROM sessions WHERE refresh_hash=$1 FOR UPDATE", digest(token))
            if row is None or row["refresh_expires_at"] <= datetime.now(timezone.utc):
                raise Fault("UNAUTHENTICATED")
            if not row["revoked"]:
                await conn.execute("UPDATE sessions SET revoked=TRUE WHERE session_id=$1", row["session_id"])
                entries.append(await db.invalidate(conn, row["session_id"], "logout", None))
    reply = response(None, 204)
    reply.set_cookie(COOKIE, "", max_age=0, expires="Thu, 01 Jan 1970 00:00:00 GMT", path=COOKIE_PATH, secure=True, httponly=True, samesite="Strict")
    await rt.auth.notices(entries)
    return reply


def register(app):
    for name, handler in (("register", register_user), ("login", login), ("refresh", refresh), ("logout", logout)):
        app.router.add_post("/api/v1/auth/" + name, handler)
