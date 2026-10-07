"""PostgreSQL-only authority, migration integrity and commit-safe counters."""
import hashlib
import json
from pathlib import Path

import asyncpg

from .support import Fault, iso


async def create_pool(settings):
    async def initialize(conn):
        for name in ("json", "jsonb"):
            await conn.set_type_codec(name, schema="pg_catalog", encoder=lambda value: json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":")), decoder=json.loads)
    return await asyncpg.create_pool(
        settings.database_url, min_size=1, max_size=16, timeout=settings.dependency_timeout,
        command_timeout=10, init=initialize,
        server_settings={"search_path": '"' + settings.database_schema + '"', "application_name": "hine_api", "statement_timeout": "10000", "lock_timeout": "5000"},
    )


async def migrate(pool):
    directory = Path(__file__).resolve().parents[2] / "migrations"
    files = sorted(directory.glob("[0-9][0-9][0-9]_*.sql"))
    if not files:
        raise RuntimeError("Migration integrity failure")
    async with pool.acquire() as conn, conn.transaction():
        schema = await conn.fetchval("SELECT current_schema()")
        if schema is None:
            raise RuntimeError("Migration integrity failure")
        await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1,0))", "hine_api_migrate:" + schema)
        await conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations(name TEXT PRIMARY KEY,checksum TEXT NOT NULL,applied_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp())")
        applied = {row["name"]: row["checksum"] for row in await conn.fetch("SELECT name,checksum FROM schema_migrations")}
        if set(applied) - {path.name for path in files}:
            raise RuntimeError("Migration integrity failure")
        for path in files:
            raw = path.read_bytes()
            checksum = hashlib.sha256(raw).hexdigest()
            if path.name in applied:
                if applied[path.name] != checksum:
                    raise RuntimeError("Migration integrity failure")
                continue
            await conn.execute(raw.decode("utf-8"))
            await conn.execute("INSERT INTO schema_migrations(name,checksum) VALUES($1,$2)", path.name, checksum)


async def verify_migrations(pool):
    files = sorted((Path(__file__).resolve().parents[2] / "migrations").glob("[0-9][0-9][0-9]_*.sql"))
    expected = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    async with pool.acquire() as conn:
        applied = {row["name"]: row["checksum"] for row in await conn.fetch("SELECT name,checksum FROM schema_migrations")}
    if not expected or applied != expected:
        raise RuntimeError("Migration integrity failure")


async def frontier(conn, exclusive=False):
    return await conn.fetchval("SELECT position FROM authority_state WHERE id=1 FOR " + ("UPDATE" if exclusive else "SHARE"))


async def invalidate(conn, session_id, reason, min_valid_generation):
    position = await conn.fetchval("UPDATE authority_state SET position=position+1 WHERE id=1 RETURNING position")
    row = await conn.fetchrow("INSERT INTO session_invalidations(position,session_id,reason,min_valid_generation) VALUES($1,$2,$3,$4) RETURNING *", position, session_id, reason, min_valid_generation)
    return {"position": row["position"], "session_id": row["session_id"], "reason": row["reason"], "min_valid_generation": row["min_valid_generation"], "committed_at": iso(row["committed_at"])}


async def append_events(conn, deliveries):
    users = sorted({entry["recipient_user_id"] for entry in deliveries})
    positions = {}
    for user_id in users:
        position = await conn.fetchval("SELECT position FROM feed_heads WHERE user_id=$1 FOR UPDATE", user_id)
        if position is None:
            raise Fault("PERSISTENCE_FAILED", True)
        positions[user_id] = position
    for entry in deliveries:
        user_id = entry["recipient_user_id"]
        positions[user_id] += 1
        await conn.execute("INSERT INTO user_feed(user_id,position,envelope) VALUES($1,$2,$3)", user_id, positions[user_id], entry["envelope"])
    for user_id in users:
        await conn.execute("UPDATE feed_heads SET position=$2 WHERE user_id=$1", user_id, positions[user_id])
    return positions
