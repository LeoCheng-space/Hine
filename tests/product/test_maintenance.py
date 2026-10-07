"""Bounded retention against real PostgreSQL and the native API consumer paths."""
import asyncio

from hine_api import db, synchronization
from hine_api.config import Settings
from support import ProductCase
from test_domain import DomainConsumer


class RetentionTests(DomainConsumer, ProductCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.runtime.settings = Settings.from_env(self.api.settings_env)
        self.assertTrue(self.runtime.settings.valid)
        self.profile, self.access = await self.account("Retention")
        self.binding = await self.api.binding(self.access)

    async def prune(self, **options):
        # Import only when exercising the private maintenance consumer, so the
        # independent native lifecycle regression runs on the pre-fix app too.
        from hine_api.maintenance import prune_expired
        return await prune_expired(self.runtime, **options)

    async def bootstrap(self):
        return await self.internal("readBootstrap", {
            **{key: self.binding[key] for key in
               ("subject_id", "session_id", "session_generation")},
            "reason": "first_login",
        })

    async def feed(self, cursor, **continuation):
        return await self.api.internal("readFeed", {
            **{key: self.binding[key] for key in
               ("subject_id", "session_id", "session_generation")},
            "cursor": cursor, "limit": 100, **continuation,
        })

    async def seed_invalidations(self, ages):
        """Use the real gapless writer; adjust only fixture commit timestamps."""
        positions = []
        async with self.api.pool.acquire() as conn, conn.transaction():
            await db.frontier(conn, True)
            generation = await conn.fetchval(
                "UPDATE sessions SET generation=generation+$2 "
                "WHERE session_id=$1 RETURNING generation",
                self.binding["session_id"], len(ages),
            )
            for offset, age in enumerate(ages, start=1):
                entry = await db.invalidate(
                    conn, self.binding["session_id"], "refresh",
                    generation - len(ages) + offset,
                )
                positions.append(entry["position"])
                await conn.execute(
                    "UPDATE session_invalidations "
                    "SET committed_at=clock_timestamp()-($2::int*interval '1 second') "
                    "WHERE position=$1", entry["position"], age,
                )
        return positions

    async def seed_expired_boundaries(self, count):
        tokens = [synchronization.cursor_issue(
            self.runtime, self.profile["id"], "sync:boundary",
        ) for _ in range(count)]
        async with self.api.pool.acquire() as conn:
            await conn.executemany(
                "INSERT INTO sync_cursors(token,user_id,position,boundary,kind,expires_at) "
                "VALUES($1,$2,0,NULL,'boundary',clock_timestamp()-interval '1 hour')",
                [(token, self.profile["id"]) for token in tokens],
            )
        return tokens

    async def wait_for_frontier_block(self, task, blocker_pid):
        # Observe PostgreSQL's actual lock wait, not a sleep or a mock call.
        async with asyncio.timeout(3):
            async with self.api.pool.acquire() as conn:
                while True:
                    if task.done():
                        await task
                        self.fail("Retention crossed a held authority frontier")
                    blocked = await conn.fetchval(
                        "SELECT EXISTS(SELECT 1 FROM pg_stat_activity "
                        "WHERE $1::int=ANY(pg_blocking_pids(pid)))", blocker_pid,
                    )
                    if blocked:
                        return
                    await asyncio.sleep(0.01)

    async def test_sync_sweep_deletes_at_most_1000_expired_rows_and_preserves_live_feed(self):
        snapshot = await self.bootstrap()
        start = snapshot["start_cursor"]
        status, batch = await self.feed(start)
        self.assertEqual(status, 200)
        boundary = batch["data"]["snapshot_boundary"]
        async with self.api.pool.acquire() as conn:
            expiry = await conn.fetchval(
                "SELECT expires_at FROM sync_cursors WHERE token=$1", start,
            )
            remaining_lifetime = await conn.fetchval(
                "SELECT extract(epoch FROM expires_at-clock_timestamp()) "
                "FROM sync_cursors WHERE token=$1", start,
            )
        self.assertGreater(remaining_lifetime, 13 * 24 * 60 * 60)
        expired = await self.seed_expired_boundaries(1001)

        self.assertEqual(await self.prune(), {
            "sync_cursors": 1000, "session_invalidations": 0,
        })
        async with self.api.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval(
                "SELECT count(*) FROM sync_cursors WHERE expires_at<=clock_timestamp()",
            ), 1)
            self.assertEqual(await conn.fetchval(
                "SELECT expires_at FROM sync_cursors WHERE token=$1", start,
            ), expiry)
            self.assertEqual(await conn.fetchval(
                "SELECT count(*) FROM sync_cursors WHERE token=ANY($1::text[])",
                [start, boundary],
            ), 2)
            self.assertEqual(await conn.fetchval(
                "SELECT count(*) FROM snapshots WHERE snapshot_id=$1",
                snapshot["snapshot_id"],
            ), 1)
        status, continuation = await self.feed(start, snapshot_boundary=boundary)
        self.assertEqual(status, 200)
        self.assertEqual(continuation["data"]["next_cursor"], start)
        self.assertEqual(continuation["data"]["events"], [])
        self.assertFalse(continuation["data"]["has_more"])

        self.assertEqual(await self.prune(), {
            "sync_cursors": 1, "session_invalidations": 0,
        })
        status, rejected = await self.feed(start, snapshot_boundary=expired[0])
        self.assertEqual(status, 410)
        self.assertEqual(rejected["error"]["code"], "SYNC_RESET_REQUIRED")
        self.assertEqual(await self.prune(), {
            "sync_cursors": 0, "session_invalidations": 0,
        })

    async def test_invalidation_sweep_keeps_expired_interior_rows_after_live_prefix_boundary(self):
        self.assertEqual(await self.seed_invalidations([1800, 60, 1800, 60]), [1, 2, 3, 4])
        self.assertEqual(await self.prune(), {
            "sync_cursors": 0, "session_invalidations": 1,
        })
        async with self.api.pool.acquire() as conn:
            self.assertEqual([row["position"] for row in await conn.fetch(
                "SELECT position FROM session_invalidations ORDER BY position",
            )], [2, 3, 4])
        status, stale = await self.api.internal("readSessionInvalidations", {
            "after_position": 0, "limit": 500,
        })
        self.assertEqual(status, 400)
        self.assertEqual(stale["error"]["code"], "CURSOR_INVALID")
        page = await self.internal("readSessionInvalidations", {
            "after_position": 1, "limit": 1,
        })
        self.assertEqual([entry["position"] for entry in page["entries"]], [2])
        self.assertEqual((page["next_position"], page["head_position"], page["has_more"]),
                         (2, 4, True))
        page = await self.internal("readSessionInvalidations", {
            "after_position": 2, "limit": 500,
        })
        self.assertEqual([entry["position"] for entry in page["entries"]], [3, 4])
        self.assertEqual((page["next_position"], page["head_position"], page["has_more"]),
                         (4, 4, False))

    async def test_invalidation_sweep_is_bounded_and_floor_tracks_the_remaining_prefix(self):
        await self.seed_invalidations([1800] * 1001 + [60])
        self.assertEqual(await self.prune(), {
            "sync_cursors": 0, "session_invalidations": 1000,
        })
        async with self.api.pool.acquire() as conn:
            self.assertEqual([row["position"] for row in await conn.fetch(
                "SELECT position FROM session_invalidations ORDER BY position",
            )], [1001, 1002])
        status, stale = await self.api.internal("readSessionInvalidations", {
            "after_position": 999, "limit": 500,
        })
        self.assertEqual(status, 400)
        self.assertEqual(stale["error"]["code"], "CURSOR_INVALID")
        page = await self.internal("readSessionInvalidations", {
            "after_position": 1000, "limit": 500,
        })
        self.assertEqual([entry["position"] for entry in page["entries"]], [1001, 1002])
        self.assertEqual((page["next_position"], page["head_position"], page["has_more"]),
                         (1002, 1002, False))
        self.assertEqual(await self.prune(limit=1), {
            "sync_cursors": 0, "session_invalidations": 1,
        })
        page = await self.internal("readSessionInvalidations", {
            "after_position": 1001, "limit": 500,
        })
        self.assertEqual([entry["position"] for entry in page["entries"]], [1002])
        self.assertFalse(page["has_more"])

    async def test_configured_retention_longer_than_access_ttl_keeps_its_full_window(self):
        self.runtime.settings = Settings.from_env({
            **self.api.settings_env, "ACCESS_TTL_SECONDS": "900",
            "INVALIDATION_RETENTION_SECONDS": "1800",
        })
        self.assertTrue(self.runtime.settings.valid)
        await self.seed_invalidations([2400, 1200, 60])
        self.assertEqual(await self.prune(), {
            "sync_cursors": 0, "session_invalidations": 1,
        })
        page = await self.internal("readSessionInvalidations", {
            "after_position": 1, "limit": 500,
        })
        self.assertEqual([entry["position"] for entry in page["entries"]], [2, 3])
        self.assertEqual((page["next_position"], page["head_position"], page["has_more"]),
                         (3, 3, False))

    async def test_all_pruned_log_keeps_authority_head_and_accepts_only_current_position(self):
        await self.seed_invalidations([1800, 1800])
        self.assertEqual(await self.prune(), {
            "sync_cursors": 0, "session_invalidations": 2,
        })
        async with self.api.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval("SELECT count(*) FROM session_invalidations"), 0)
            self.assertEqual(await conn.fetchval("SELECT position FROM authority_state WHERE id=1"), 2)
        for after in (0, 1, 3):
            with self.subTest(after=after):
                status, stale = await self.api.internal("readSessionInvalidations", {
                    "after_position": after, "limit": 500,
                })
                self.assertEqual(status, 400)
                self.assertEqual(stale["error"]["code"], "CURSOR_INVALID")
        for after in (None, 2):
            page = await self.internal("readSessionInvalidations", {
                "after_position": after, "limit": 500,
            })
            self.assertEqual(page, {
                "entries": [], "next_position": 2,
                "head_position": 2, "has_more": False,
            })
        status, _ = await self.api.request("POST", "/api/v1/auth/refresh")
        self.assertEqual(status, 200)
        page = await self.internal("readSessionInvalidations", {
            "after_position": 2, "limit": 500,
        })
        self.assertEqual([entry["position"] for entry in page["entries"]], [3])
        self.assertEqual((page["next_position"], page["head_position"], page["has_more"]),
                         (3, 3, False))

    async def test_retention_waits_for_existing_consumer_frontier_snapshot(self):
        await self.seed_invalidations([1800])
        task = None
        try:
            async with self.api.pool.acquire() as conn, conn.transaction():
                self.assertEqual(await db.frontier(conn), 1)
                blocker_pid = await conn.fetchval("SELECT pg_backend_pid()")
                page = await self.internal("readSessionInvalidations", {
                    "after_position": 0, "limit": 500,
                })
                self.assertEqual([entry["position"] for entry in page["entries"]], [1])
                task = asyncio.create_task(self.prune())
                await self.wait_for_frontier_block(task, blocker_pid)
                self.assertEqual(await conn.fetchval("SELECT count(*) FROM session_invalidations"), 1)
            self.assertEqual(await asyncio.wait_for(task, 5), {
                "sync_cursors": 0, "session_invalidations": 1,
            })
        finally:
            if task is not None:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        status, stale = await self.api.internal("readSessionInvalidations", {
            "after_position": 0, "limit": 500,
        })
        self.assertEqual(status, 400)
        self.assertEqual(stale["error"]["code"], "CURSOR_INVALID")

    async def test_retention_serializes_with_uncommitted_invalidation_writer(self):
        await self.seed_invalidations([1800])
        task = None
        try:
            async with self.api.pool.acquire() as conn, conn.transaction():
                self.assertEqual(await db.frontier(conn, True), 1)
                blocker_pid = await conn.fetchval("SELECT pg_backend_pid()")
                entry = await db.invalidate(conn, self.binding["session_id"], "refresh", 3)
                self.assertEqual(entry["position"], 2)
                task = asyncio.create_task(self.prune())
                await self.wait_for_frontier_block(task, blocker_pid)
                self.assertEqual(await conn.fetchval("SELECT count(*) FROM session_invalidations"), 2)
            self.assertEqual(await asyncio.wait_for(task, 5), {
                "sync_cursors": 0, "session_invalidations": 1,
            })
        finally:
            if task is not None:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        page = await self.internal("readSessionInvalidations", {
            "after_position": 1, "limit": 500,
        })
        self.assertEqual([entry["position"] for entry in page["entries"]], [2])
        self.assertEqual((page["next_position"], page["head_position"], page["has_more"]),
                         (2, 2, False))

    async def test_native_api_sixty_second_tick_prunes_expired_rows_without_private_helper(self):
        snapshot = await self.bootstrap()
        start = snapshot["start_cursor"]
        status, batch = await self.feed(start)
        self.assertEqual(status, 200)
        expired_boundary = batch["data"]["snapshot_boundary"]
        async with self.api.pool.acquire() as conn:
            await conn.execute(
                "UPDATE sync_cursors SET expires_at=clock_timestamp()-interval '1 hour' "
                "WHERE token=$1", expired_boundary,
            )
        await self.seed_invalidations([1800, 60])
        # The log fixtures represent refreshes; obtain the current authentic
        # session binding before testing the unchanged live feed cursor.
        status, refreshed = await self.api.request("POST", "/api/v1/auth/refresh")
        self.assertEqual(status, 200)
        self.binding = await self.api.binding(refreshed["data"])
        await asyncio.sleep(61)
        with self.subTest(consumer="expired synchronization boundary"):
            status, rejected = await self.feed(start, snapshot_boundary=expired_boundary)
            self.assertEqual(rejected["error"]["code"], "SYNC_RESET_REQUIRED")
            self.assertEqual(status, 410)
        with self.subTest(consumer="invalidation cursor below retained floor"):
            status, stale = await self.api.internal("readSessionInvalidations", {
                "after_position": 0, "limit": 500,
            })
            self.assertEqual(status, 400)
            self.assertEqual(stale["error"]["code"], "CURSOR_INVALID")
        async with self.api.pool.acquire() as conn:
            with self.subTest(storage="expired synchronization rows"):
                self.assertEqual(await conn.fetchval(
                    "SELECT count(*) FROM sync_cursors WHERE token=$1", expired_boundary,
                ), 0)
            self.assertEqual(await conn.fetchval(
                "SELECT count(*) FROM sync_cursors WHERE token=$1", start,
            ), 1)
            with self.subTest(storage="expired invalidation prefix"):
                self.assertEqual([row["position"] for row in await conn.fetch(
                    "SELECT position FROM session_invalidations ORDER BY position",
                )], [2, 3])
        status, live = await self.feed(start)
        self.assertEqual(status, 200)
        self.assertEqual(live["data"]["next_cursor"], start)
        self.assertEqual(live["data"]["events"], [])
        page = await self.internal("readSessionInvalidations", {
            "after_position": 1, "limit": 500,
        })
        self.assertEqual([entry["position"] for entry in page["entries"]], [2, 3])
        self.assertEqual((page["next_position"], page["head_position"], page["has_more"]),
                         (3, 3, False))

    async def test_pruned_progress_resets_but_invalid_mac_user_scope_and_rest_cursor_do_not(self):
        snapshot = await self.bootstrap()
        start = snapshot["start_cursor"]
        async with self.api.pool.acquire() as conn:
            await conn.execute(
                "UPDATE sync_cursors SET expires_at=clock_timestamp()-interval '1 hour' "
                "WHERE token=$1", start,
            )
        self.assertEqual(await self.prune(), {
            "sync_cursors": 1, "session_invalidations": 0,
        })
        signed_missing = synchronization.cursor_issue(
            self.runtime, self.profile["id"], "sync:progress",
        )
        for cursor in (start, signed_missing):
            with self.subTest(cursor_state="pruned" if cursor == start else "signed missing"):
                status, rejected = await self.feed(cursor)
                self.assertEqual(rejected["error"]["code"], "SYNC_RESET_REQUIRED")
                self.assertEqual(status, 410)
        foreign = await self.api.signup()
        invalid = {
            "invalid MAC": start[:-1] + ("A" if start[-1] != "A" else "B"),
            "foreign user": synchronization.cursor_issue(
                self.runtime, foreign["id"], "sync:progress",
            ),
            "boundary scope": synchronization.cursor_issue(
                self.runtime, self.profile["id"], "sync:boundary",
            ),
        }
        for label, cursor in invalid.items():
            with self.subTest(cursor_state=label):
                status, rejected = await self.feed(cursor)
                self.assertEqual(rejected["error"]["code"], "CURSOR_INVALID")
                self.assertEqual(status, 400)
        missing_rest = synchronization.cursor_issue(
            self.runtime, self.profile["id"], "rest:conversations",
        )
        status, rejected = await self.request(
            "GET", "/api/v1/conversations?cursor=" + missing_rest, self.access,
        )
        self.assertEqual(rejected["error"]["code"], "CURSOR_INVALID")
        self.assertEqual(status, 400)

    async def socket_reply(self, socket, event, payload):
        from hine_realtime import protocol as p
        request = p.event(event, payload)
        await socket.send_str(p.dumps(request))
        async with asyncio.timeout(10):
            while True:
                reply = await socket.receive_json()
                if reply.get("correlation_id") == request["event_id"]:
                    return reply

    async def test_pruned_progress_actual_wss_reset_bootstrap_recovers_stable_feed(self):
        peer, _ = await self.account("Retention peer")
        status, direct = await self.request(
            "POST", "/api/v1/conversations/direct", self.access,
            json={"peer_user_id": peer["id"]},
        )
        self.assertEqual(status, 201)
        self.conversation = direct["data"]["id"]
        status, before = await self.send("before retention")
        self.assertEqual(status, 200)
        async with self.real_realtime() as server:
            socket = await self.client.ws_connect(
                server.make_url("/ws/v1"), headers={"Origin": self.api.origin},
                max_msg_size=1048576,
            )
            try:
                authenticated = await self.socket_reply(socket, "auth.authenticate", {
                    "access_token": self.access["access_token"],
                    "device_id": self.access["device_id"],
                })
                self.assertEqual(authenticated["event"], "auth.accepted")
                initial = await self.socket_reply(
                    socket, "sync.bootstrap.request", {"reason": "first_login"},
                )
                self.assertEqual(initial["event"], "sync.bootstrap.page")
                start = initial["payload"]["start_cursor"]
                async with self.api.pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE sync_cursors SET expires_at=clock_timestamp()-interval '1 hour' "
                        "WHERE token=$1", start,
                    )
                self.assertEqual(await self.prune(), {
                    "sync_cursors": 1, "session_invalidations": 0,
                })
                rejected = await self.socket_reply(socket, "sync.request", {"cursor": start})
                self.assertEqual(rejected["event"], "error")
                self.assertEqual(rejected["payload"]["code"], "SYNC_RESET_REQUIRED")

                recovered = await self.socket_reply(
                    socket, "sync.bootstrap.request", {"reason": "cursor_reset"},
                )
                self.assertEqual(recovered["event"], "sync.bootstrap.page")
                self.assertFalse(recovered["payload"]["has_more"])
                current = recovered["payload"]["start_cursor"]
                self.assertNotEqual(current, start)
                conversations = recovered["payload"]["conversations"]
                self.assertEqual([entry["id"] for entry in conversations], [self.conversation])
                self.assertEqual([message["id"] for message in conversations[0]["recent_messages"]],
                                 [before["data"]["message_id"]])
                self.assertEqual(conversations[0]["recent_messages"][0]["text"], "before retention")
                status, after = await self.send("after reset")
                self.assertEqual(status, 200)
                batch = await self.socket_reply(socket, "sync.request", {"cursor": current})
                self.assertEqual(batch["event"], "sync.batch")
                self.assertFalse(batch["payload"]["has_more"])
                self.assertEqual([entry["payload"]["message_id"] for entry in batch["payload"]["events"]],
                                 [after["data"]["message_id"]])
                self.assertEqual(batch["payload"]["events"][0]["payload"]["text"], "after reset")
                replay = await self.socket_reply(socket, "sync.request", {
                    "cursor": current, "snapshot_boundary": batch["payload"]["snapshot_boundary"],
                })
                self.assertEqual(replay["event"], "sync.batch")
                self.assertEqual(replay["payload"]["events"], batch["payload"]["events"])
                empty = await self.socket_reply(socket, "sync.request", {
                    "cursor": batch["payload"]["next_cursor"],
                    "snapshot_boundary": batch["payload"]["snapshot_boundary"],
                })
                self.assertEqual(empty["event"], "sync.batch")
                self.assertEqual(empty["payload"]["events"], [])
                self.assertFalse(empty["payload"]["has_more"])
            finally:
                await socket.close()
