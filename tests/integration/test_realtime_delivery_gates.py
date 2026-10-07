"""Request/reply sync must fail explicitly at stale delivery, unlike live fanout."""
import asyncio

from receipt_sync_support import AddonHarness
from test_realtime_boundaries import frame


class SyncDeliveryGateTests(AddonHarness):
    async def test_stale_final_and_dequeue_gates_return_both_correlated_errors(self):
        from hine_realtime.server import RUNTIME
        ws = await self.auth('access-b')
        runtime = self.app[RUNTIME]
        connection = next(c for c in runtime.connections if c.binding and c.binding['user_id'] == 'user-b')
        first = frame('sync.request', {'cursor': 'cursor:0'})
        second = frame('sync.request', {'cursor': 'cursor:0'})
        await connection.write_lock.acquire()
        try:
            await ws.send_json(first)
            async with asyncio.timeout(2):
                while not connection.write_lock._waiters:
                    await asyncio.sleep(.01)
            await ws.send_json(second)
            async with asyncio.timeout(2):
                while connection.queue.empty():
                    await asyncio.sleep(.01)
            self.authority.fail_poll = True
            async with asyncio.timeout(5):
                while runtime.invalidations.fresh():
                    await asyncio.sleep(.02)
        finally:
            connection.write_lock.release()
        replies = []
        async with asyncio.timeout(3):
            while len(replies) < 2:
                replies.append(await ws.receive_json())
        self.assertEqual({r['correlation_id'] for r in replies}, {first['event_id'], second['event_id']})
        for reply in replies:
            self.assertEqual(reply['event'], 'error')
            self.assertEqual(reply['payload']['code'], 'DEPENDENCY_UNAVAILABLE')
            self.assertNotIn('next_cursor', reply['payload'])
        self.assertFalse(ws.closed)
        self.authority.fail_poll = False
        request = frame('sync.request', {'cursor': 'cursor:0'})
        async with asyncio.timeout(3):
            while not runtime.invalidations.fresh():
                await asyncio.sleep(.02)
        await ws.send_json(request)
        self.assertEqual((await self.correlated(ws, request))['event'], 'sync.batch')
