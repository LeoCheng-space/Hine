"""Real private synchronization consumer tests; no in-memory authority."""
import asyncio
import json
import uuid

from support import ProductCase
from test_domain import DomainConsumer


class SynchronizationTests(DomainConsumer, ProductCase):
    async def bootstrap(self, access=None, **continuation):
        binding = await self.api.binding(access or self.b)
        return await self.api.internal('readBootstrap', {
            **{k: binding[k] for k in ('subject_id', 'session_id', 'session_generation')},
            'reason': 'first_login', **continuation,
        })

    async def feed(self, cursor, access=None, **fields):
        binding = await self.api.binding(access or self.b)
        return await self.api.internal('readFeed', {
            **{k: binding[k] for k in ('subject_id', 'session_id', 'session_generation')},
            'cursor': cursor, 'limit': 100, **fields,
        })

    async def websocket_reply(self, socket, event, payload):
        from hine_realtime import protocol as p
        request = p.event(event, payload)
        await socket.send_str(p.dumps(request))
        async with asyncio.timeout(10):
            while True:
                reply = await socket.receive_json()
                self.assertNotEqual(reply['event'], 'error', reply)
                if reply.get('correlation_id') == request['event_id']:
                    self.assertLessEqual(len(p.dumps(reply).encode('utf-8')), 1048576)
                    return reply

    async def sync_socket(self, server):
        socket = await self.client.ws_connect(server.make_url('/ws/v1'),
            headers={'Origin': self.api.origin}, max_msg_size=1048576)
        reply = await self.websocket_reply(socket, 'auth.authenticate',
            {'access_token': self.b['access_token'], 'device_id': self.b['device_id']})
        self.assertEqual(reply['event'], 'auth.accepted')
        return socket

    async def test_frozen_bootstrap_then_feed_fixed_boundary_and_empty_stability(self):
        await self.setup_direct()
        _, snapshot = await self.bootstrap()
        start = snapshot['data']['start_cursor']
        _, first = await self.send('after H')
        _, batch = await self.feed(start, limit=1)
        self.assertEqual(batch['data']['events'][0]['payload']['message_id'], first['data']['message_id'])
        boundary = batch['data']['snapshot_boundary']
        cursor = batch['data']['next_cursor']
        await self.send('next round')
        _, empty = await self.feed(cursor, snapshot_boundary=boundary)
        self.assertEqual(empty['data']['events'], [])
        self.assertEqual(empty['data']['next_cursor'], cursor)
        self.assertFalse(empty['data']['has_more'])
        _, following = await self.feed(cursor)
        self.assertEqual([e['payload']['text'] for e in following['data']['events']], ['next round'])
        _, invalid = await self.feed(start, access=self.a)
        self.assertEqual(invalid['error']['code'], 'CURSOR_INVALID')

    async def test_revoked_group_hidden_progress_minimal_self_w12_other_dialog_survives(self):
        await self.setup_direct()
        _, snapshot = await self.bootstrap()
        start = snapshot['data']['start_cursor']
        _, group = await self.request('POST', '/api/v1/conversations/groups', self.a,
                                     json={'title': 'Secret', 'member_ids': [self.bob['id']]},
                                     headers={'Idempotency-Key': str(uuid.uuid4())})
        gid = group['data']['id']
        await self.send('hidden secret', conversation=gid)
        await self.request('DELETE', f'/api/v1/conversations/{gid}/members/{self.bob["id"]}', self.a)
        await self.send('visible direct')
        _, batch = await self.feed(start)
        events = batch['data']['events']
        self.assertEqual([e['payload']['text'] for e in events if e['event'] == 'message.created'], ['visible direct'])
        removed = [e for e in events if e['event'] == 'conversation.member_removed']
        self.assertEqual(len(removed), 1)
        self.assertEqual(set(removed[0]['payload']), {'member_id', 'change', 'membership_version'})
        self.assertNotEqual(batch['data']['next_cursor'], start)
        self.assertFalse(batch['data']['has_more'])

    async def test_rest_scope_expiry_and_snapshot_pair_rejection(self):
        await self.setup_direct()
        for i in range(3):
            await self.send(str(i))
        _, history = await self.request('GET', f'/api/v1/conversations/{self.conversation}/messages?limit=1', self.b)
        before = history['meta']['next_cursor']
        self.assertIsNotNone(before)
        _, invalid = await self.request('GET', '/api/v1/contacts?cursor=' + before, self.b)
        self.assertEqual(invalid['error']['code'], 'CURSOR_INVALID')
        async with self.runtime.pool.acquire() as conn:
            await conn.execute("UPDATE rest_cursors SET expires_at=clock_timestamp()-interval '1 second' WHERE token=$1", before)
        _, expired = await self.request('GET', f'/api/v1/conversations/{self.conversation}/messages?before={before}', self.b)
        self.assertEqual(expired['error']['code'], 'CURSOR_EXPIRED')
        _, first = await self.bootstrap()
        _, mismatch = await self.bootstrap(snapshot_id='not-the-snapshot', page_token=first['data']['start_cursor'])
        self.assertEqual(mismatch['error']['code'], 'CURSOR_INVALID')
        async with self.runtime.pool.acquire() as conn:
            await conn.execute("UPDATE sync_cursors SET expires_at=clock_timestamp()-interval '1 second' WHERE token=$1", first['data']['start_cursor'])
        _, expired = await self.feed(first['data']['start_cursor'])
        self.assertEqual(expired['error']['code'], 'SYNC_RESET_REQUIRED')

    async def test_feed_frontier_does_not_cross_uncommitted_head(self):
        await self.setup_direct()
        _, snapshot = await self.bootstrap()
        async with self.runtime.pool.acquire() as conn:
            tx = conn.transaction()
            await tx.start()
            await conn.fetchrow('SELECT position FROM feed_heads WHERE user_id=$1 FOR UPDATE', self.bob['id'])
            writer = asyncio.create_task(self.send('blocked pending commit'))
            await asyncio.sleep(0.05)
            _, batch = await self.feed(snapshot['data']['start_cursor'])
            self.assertEqual(batch['data']['events'], [])
            self.assertEqual(batch['data']['next_cursor'], snapshot['data']['start_cursor'])
            await tx.commit()
        await writer
        _, batch = await self.feed(snapshot['data']['start_cursor'])
        self.assertEqual([e['payload']['text'] for e in batch['data']['events']], ['blocked pending commit'])
        self.assertLess(len(json.dumps({'data': batch['data']}, ensure_ascii=True).encode()), 1048576)

    async def test_rejoin_empty_history_does_not_reuse_old_bootstrap_membership(self):
        await self.setup_direct()
        groups = []
        for i in range(11):
            _, result = await self.request('POST', '/api/v1/conversations/groups', self.a,
                json={'title': 'old title ' + str(i), 'member_ids': [self.bob['id']]},
                headers={'Idempotency-Key': str(uuid.uuid4())})
            groups.append(result['data']['id'])
        async with self.runtime.pool.acquire() as conn:
            await conn.execute("UPDATE conversations SET title=$1 WHERE conversation_id=ANY($2::text[])", '😀'*10000, groups)
        _, initial = await self.bootstrap()
        self.assertTrue(initial['data']['has_more'])
        visible_ids = {c['id'] for c in initial['data']['conversations']}
        hidden_group = next(gid for gid in groups if gid not in visible_ids)
        await self.request('DELETE', f'/api/v1/conversations/{hidden_group}/members/{self.bob["id"]}', self.a)
        await self.request('POST', f'/api/v1/conversations/{hidden_group}/members', self.a, json={'user_id': self.bob['id']})
        continuation = initial['data']
        all_ids = set()
        while continuation['has_more']:
            _, result = await self.bootstrap(snapshot_id=continuation['snapshot_id'], page_token=continuation['next_page_token'])
            continuation = result['data']
            all_ids.update(c['id'] for c in continuation['conversations'])
        self.assertNotIn(hidden_group, all_ids)

    async def test_hidden_only_scan_is_bounded_and_continues_to_other_dialog(self):
        await self.setup_direct()
        _, snapshot = await self.bootstrap()
        _, group = await self.request('POST', '/api/v1/conversations/groups', self.a,
            json={'title': 'Initial', 'member_ids': [self.bob['id']]},
            headers={'Idempotency-Key': str(uuid.uuid4())})
        gid = group['data']['id']
        for number in range(1001):
            status, _ = await self.request('PATCH', f'/api/v1/conversations/{gid}', self.a,
                json={'title': str(number)})
            self.assertEqual(status, 200)
        await self.request('DELETE', f'/api/v1/conversations/{gid}/members/{self.bob["id"]}', self.a)
        await self.send('other dialog still readable')
        _, first = await self.feed(snapshot['data']['start_cursor'])
        self.assertEqual(first['data']['events'], [])
        self.assertTrue(first['data']['has_more'])
        async with self.runtime.pool.acquire() as conn:
            inspected = await conn.fetchval('SELECT position FROM sync_cursors WHERE token=$1', first['data']['next_cursor'])
        self.assertEqual(inspected, 1000)
        _, second = await self.feed(first['data']['next_cursor'],
            snapshot_boundary=first['data']['snapshot_boundary'])
        self.assertFalse(second['data']['has_more'])
        self.assertEqual([event['payload']['text'] for event in second['data']['events']
                          if event['event']=='message.created'], ['other dialog still readable'])

    async def test_byte_packing_preserves_large_unicode_events_and_recent_snapshot(self):
        await self.setup_direct()
        _, initial = await self.bootstrap()
        text = '😀'*4096
        for number in range(30):
            async with self.runtime.pool.acquire() as conn:
                await conn.execute('DELETE FROM message_quota WHERE subject_id=$1', self.binding['subject_id'])
            status, _ = await self.send(text)
            self.assertEqual(status, 200)
        cursor, boundary, received = initial['data']['start_cursor'], None, []
        while True:
            _, batch = await self.feed(cursor, **({'snapshot_boundary': boundary} if boundary else {}))
            data = batch['data']
            self.assertLessEqual(len(json.dumps({'data': data}, ensure_ascii=True, separators=(',', ':')).encode()), 1048576)
            received.extend(event['payload']['text'] for event in data['events'])
            cursor, boundary = data['next_cursor'], data['snapshot_boundary']
            if not data['has_more']:
                break
        self.assertEqual(received, [text]*30)
        _, snapshot = await self.bootstrap()
        self.assertLessEqual(len(json.dumps(snapshot, ensure_ascii=True, separators=(',', ':')).encode()), 1048576)
        count = sum(1+len(c['recent_messages']) for c in snapshot['data']['conversations'])
        self.assertLessEqual(count, 100)
        self.assertTrue(all(message['text']==text for c in snapshot['data']['conversations'] for message in c['recent_messages']))

    async def test_revoked_session_cannot_use_previously_valid_cursor(self):
        await self.setup_direct()
        _, snapshot = await self.bootstrap()
        original_binding = await self.api.binding(self.b)
        await self.api.login(self.bob['email'], device_id=self.b['device_id'])
        status, rejected = await self.api.internal('readFeed', {
            **{k: original_binding[k] for k in ('subject_id','session_id','session_generation')},
            'cursor': snapshot['data']['start_cursor'], 'limit': 100})
        self.assertEqual(status, 401)
        self.assertEqual(rejected['error']['details']['auth_layer'], 'user_session')

    async def test_rest_cursor_signature_cannot_be_retargeted_by_cursor_row_corruption(self):
        await self.setup_direct()
        await self.send('first')
        await self.send('second')
        _, history = await self.request('GET',f'/api/v1/conversations/{self.conversation}/messages?limit=1',self.a)
        token = history['meta']['next_cursor']
        async with self.runtime.pool.acquire() as conn:
            await conn.execute('UPDATE rest_cursors SET user_id=$1 WHERE token=$2',self.bob['id'],token)
        _, rejected = await self.request('GET',f'/api/v1/conversations/{self.conversation}/messages?before={token}',self.b)
        self.assertEqual(rejected['error']['code'],'CURSOR_INVALID')

    async def test_large_legal_titles_bootstrap_fit_actual_ba_frame_and_continue(self):
        from hine_realtime import protocol as p
        from hine_realtime.server import RUNTIME
        await self.setup_direct()
        groups = []
        for title in ('A' * 520000, ''):
            status, result = await self.request('POST', '/api/v1/conversations/groups', self.a,
                json={'title': title, 'member_ids': [self.bob['id']]},
                headers={'Idempotency-Key': str(uuid.uuid4())})
            self.assertEqual(status, 201)
            groups.append(result['data']['id'])
        _, preliminary = await self.bootstrap()
        probe = preliminary['data']
        # Legal content within the private HTTP limit, but close enough that the
        # additional real W14 UUID/timestamp/correlation envelope must split it.
        padding = 1048576 - 150 - len(p.dumps({'data': probe}).encode('utf-8'))
        self.assertGreater(padding, 0)
        title = 'B' * padding
        status, _ = await self.request('PATCH', f'/api/v1/conversations/{groups[1]}', self.a,
            json={'title': title})
        self.assertEqual(status, 200)
        seen, page_count = {}, 0
        async with self.real_realtime() as server:
            socket = await self.sync_socket(server)
            try:
                request = {'reason': 'first_login'}
                snapshot_id = start_cursor = None
                while True:
                    reply = await self.websocket_reply(socket, 'sync.bootstrap.request', request)
                    self.assertEqual(reply['event'], 'sync.bootstrap.page')
                    page = reply['payload']
                    page_count += 1
                    if snapshot_id is None:
                        snapshot_id, start_cursor = page['snapshot_id'], page['start_cursor']
                    self.assertEqual(page['snapshot_id'], snapshot_id)
                    self.assertEqual(page['start_cursor'], start_cursor)
                    for conversation in page['conversations']:
                        self.assertNotIn(conversation['id'], seen)
                        seen[conversation['id']] = conversation
                    connection = next(c for c in server.app[RUNTIME].connections if c.binding['user_id'] == self.bob['id'])
                    self.assertFalse(connection.invalid)
                    self.assertFalse(connection.closed)
                    if not page['has_more']:
                        break
                    request.update(snapshot_id=snapshot_id, page_token=page['next_page_token'])
            finally:
                await socket.close()
        self.assertGreaterEqual(page_count, 2)
        self.assertEqual(set(seen), {self.conversation, *groups})
        self.assertEqual(seen[groups[0]]['title'], 'A' * 520000)
        self.assertEqual(seen[groups[1]]['title'], title)

    async def test_large_legal_title_feed_events_fit_actual_ba_queue_and_replay_all(self):
        from hine_realtime import protocol as p
        from hine_realtime.server import RUNTIME
        await self.setup_direct()
        groups = []
        for title in ('First', 'Second'):
            _, result = await self.request('POST', '/api/v1/conversations/groups', self.a,
                json={'title': title, 'member_ids': [self.bob['id']]},
                headers={'Idempotency-Key': str(uuid.uuid4())})
            groups.append(result['data']['id'])
        _, initial = await self.bootstrap()
        start_cursor = initial['data']['start_cursor']
        async with self.runtime.pool.acquire() as conn:
            head = await conn.fetchval('SELECT position FROM sync_cursors WHERE token=$1', start_cursor)
        await self.request('PATCH', f'/api/v1/conversations/{groups[0]}', self.a, json={'title': 'A' * 520000})
        await self.request('PATCH', f'/api/v1/conversations/{groups[1]}', self.a, json={'title': ''})
        async with self.runtime.pool.acquire() as conn:
            rows = await conn.fetch('SELECT envelope FROM user_feed WHERE user_id=$1 AND position>$2 ORDER BY position',
                                    self.bob['id'], head)
        events = [row['envelope'] for row in rows]
        last = {**events[-1], 'timestamp': '9999-12-31T23:59:59.999999Z',
                'payload': {**events[-1]['payload'], 'membership_version': 3}}
        probe = {'snapshot_boundary': start_cursor, 'events': [*events, last],
                 'next_cursor': start_cursor, 'has_more': False}
        padding = 1048576 - 64 - len(p.dumps({'data': probe}).encode('utf-8'))
        self.assertGreater(padding, 0)
        title = 'B' * padding
        status, _ = await self.request('PATCH', f'/api/v1/conversations/{groups[1]}', self.a, json={'title': title})
        self.assertEqual(status, 200)
        async with self.runtime.pool.acquire() as conn:
            rows = await conn.fetch('SELECT envelope FROM user_feed WHERE user_id=$1 AND position>$2 ORDER BY position',
                                    self.bob['id'], head)
        expected = [row['envelope'] for row in rows]
        received, batch_count = [], 0
        async with self.real_realtime() as server:
            socket = await self.sync_socket(server)
            try:
                request = {'cursor': start_cursor}
                boundary = None
                while True:
                    reply = await self.websocket_reply(socket, 'sync.request', request)
                    self.assertEqual(reply['event'], 'sync.batch')
                    batch = reply['payload']
                    batch_count += 1
                    if boundary is None:
                        boundary = batch['snapshot_boundary']
                    self.assertEqual(batch['snapshot_boundary'], boundary)
                    received.extend(batch['events'])
                    connection = next(c for c in server.app[RUNTIME].connections if c.binding['user_id'] == self.bob['id'])
                    self.assertFalse(connection.invalid)
                    self.assertFalse(connection.closed)
                    if not batch['has_more']:
                        break
                    self.assertNotEqual(batch['next_cursor'], request['cursor'])
                    request.update(cursor=batch['next_cursor'], snapshot_boundary=boundary)
            finally:
                await socket.close()
        self.assertGreaterEqual(batch_count, 2)
        self.assertEqual(received, expected)
        self.assertEqual(received[-1]['payload']['changes']['title'], title)
