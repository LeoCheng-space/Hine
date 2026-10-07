"""Bounded database-only retention; authority history remains a contiguous suffix."""
from . import db


async def prune_expired(runtime, limit=1000):
    limit = min(limit, 1000)
    counts = {"sync_cursors": 0, "session_invalidations": 0}
    async with runtime.pool.acquire() as conn:
        async with conn.transaction():
            cutoff = await conn.fetchval("SELECT clock_timestamp()")
            counts["sync_cursors"] = await conn.fetchval("""
                WITH expired AS (
                    SELECT token FROM sync_cursors
                    WHERE expires_at <= $1
                    ORDER BY expires_at LIMIT $2
                    FOR UPDATE SKIP LOCKED
                ), deleted AS (
                    DELETE FROM sync_cursors USING expired
                    WHERE sync_cursors.token = expired.token
                    RETURNING sync_cursors.token
                )
                SELECT count(*) FROM deleted
            """, cutoff, limit)
        async with conn.transaction():
            # Readers hold SHARE on this frontier while they observe the floor
            # and head; T1 writers hold UPDATE while assigning new positions.
            await db.frontier(conn, True)
            cutoff = await conn.fetchval(
                "SELECT clock_timestamp()-($1::int*interval '1 second')",
                runtime.settings.invalidation_retention_seconds,
            )
            counts["session_invalidations"] = await conn.fetchval("""
                WITH candidates AS MATERIALIZED (
                    SELECT position, committed_at FROM session_invalidations
                    ORDER BY position LIMIT $2
                ), boundary AS (
                    SELECT min(position) AS position FROM candidates
                    WHERE committed_at >= $1
                ), deleted AS (
                    DELETE FROM session_invalidations USING candidates, boundary
                    WHERE session_invalidations.position = candidates.position
                      AND (boundary.position IS NULL
                           OR candidates.position < boundary.position)
                    RETURNING session_invalidations.position
                )
                SELECT count(*) FROM deleted
            """, cutoff, limit)
    return counts
