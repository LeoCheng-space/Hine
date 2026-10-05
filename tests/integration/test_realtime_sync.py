"""Real BA/WS/Redis snapshot and offline replay boundaries; not product DB/browser."""
import asyncio
import copy
from dataclasses import replace
from uuid import uuid4

from aiohttp import WSMsgType, web
from receipt_sync_support import AddonAuthority, AddonHarness
from test_realtime_boundaries import error, frame


class SyncAuthority(AddonAuthority):
    """Stateful BB boundary provider; never used by runtime or browser code."""

    def __init__(self):
        super().__init__()
        self.page_rows = 100
        self.scan_rows = 100
        self.calls = []
        self.sync_authorize_entered = asyncio.Event()
        self.sync_authorize_release = None
        self.sync_authorize_hold_user = None
        self.sync_authorize_hold_resource = None
        self.sync_authorizations_done = asyncio.Event()
        self.sync_expected_authorizations = None
        self.sync_authorization_snapshots = []
        self.sync_completed_authorizations = 0

    async def handle(self, request):
        operation = request.match_info['operation']
        body = await request.json()
        self.calls.append((operation, copy.deepcopy(body)))
        if operation == 'authorize' and body.get('action') in {'read', 'history'}:
            # Capture current BB permission before a sync-only response barrier.
            # Live W07 action=receive must never enter or complete this barrier.
            if request.headers.get('Authorization') != 'Bearer realtime-service-secret':
                return web.json_response(error('UNAUTHENTICATED', 'service_identity'), status=401)
            if operation in self.faults:
                status, data = self.faults[operation]
                return web.json_response(data, status=status)
            session = self.session(body)
            if session is None or body.get('device_id') != 'device-' + session['session_id'].removeprefix('session-'):
                return web.json_response(error('UNAUTHENTICATED', 'user_session'), status=401)
            allowed = self.may_receive(session['user_id'], body['resource_type'], body['resource_id'])
            self.sync_authorization_snapshots.append({
                **copy.deepcopy(body), 'user': session['user_id'], 'allowed': allowed})
            if (self.sync_authorize_hold_user is None or session['user_id'] == self.sync_authorize_hold_user) and (
                    self.sync_authorize_hold_resource is None or body['resource_id'] == self.sync_authorize_hold_resource):
                self.sync_authorize_entered.set()
                if self.sync_authorize_release is not None:
                    await self.sync_authorize_release.wait()
            self.sync_completed_authorizations += 1
            if (self.sync_expected_authorizations is not None and
                    self.sync_completed_authorizations >= self.sync_expected_authorizations):
                self.sync_authorizations_done.set()
            return web.json_response({'data': {'allowed': allowed, 'authorization_version': 'auth-version'}})
        if operation not in {'readBootstrap', 'readFeed'}:
            return await super().handle(request)
        if request.headers.get('Authorization') != 'Bearer realtime-service-secret':
            return web.json_response(error('UNAUTHENTICATED', 'service_identity'), status=401)
        allowed_keys = {'subject_id', 'session_id', 'session_generation'}
        allowed_keys |= ({'reason', 'snapshot_id', 'page_token'} if operation == 'readBootstrap'
                         else {'cursor', 'snapshot_boundary', 'limit'})
        if not body.keys() <= allowed_keys:
            return web.json_response(error('INVALID_ARGUMENT'), status=400)
        self.requests.append((operation, copy.deepcopy(body)))
        if operation in self.faults:
            status, value = self.faults[operation]
            return web.json_response(value, status=status)
        session = self.session(body)
        if session is None:
            return web.json_response(error('UNAUTHENTICATED', 'user_session'), status=401)
        viewer = session['user_id']
        if operation == 'readBootstrap':
            if 'snapshot_id' not in body:
                sid = 'opaque snapshot ' + uuid4().hex
                rows = []
                for cid in ['direct-1', *self.group_members]:
                    if not self.may_receive(viewer, 'conversation', cid):
                        continue
                    messages = [self.view(key, saved, viewer) for key, saved in self.messages.items()
                                if saved['conversation_id'] == cid and
                                self.may_receive(viewer, 'message', saved['message_id'])]
                    rows.append({'id': cid, 'type': 'direct' if cid == 'direct-1' else 'group',
                                 'title': None if cid == 'direct-1' else 'Fixture group',
                                 'unread_count': 0, 'my_role': None if cid == 'direct-1' else 'member',
                                 'recent_messages': messages})
                self.snapshots[sid] = (viewer, copy.deepcopy(rows), 'cursor:' + str(len(self.feed)))
                offset = 0
            else:
                sid = body['snapshot_id']
                if sid not in self.snapshots or self.snapshots[sid][0] != viewer:
                    return web.json_response(error('SYNC_RESET_REQUIRED'), status=410)
                try:
                    offset = int(body['page_token'].removeprefix('opaque page '))
                except (KeyError, ValueError):
                    return web.json_response(error('CURSOR_INVALID'), status=400)
            _, frozen, boundary = self.snapshots[sid]
            end = min(len(frozen), offset + self.page_rows)
            rows = []
            for row in frozen[offset:end]:
                if not self.may_receive(viewer, 'conversation', row['id']):
                    continue
                row = copy.deepcopy(row)
                row['recent_messages'] = [message for message in row['recent_messages']
                                          if self.may_receive(viewer, 'message', message['id'])]
                rows.append(row)
            result = {'snapshot_id': sid, 'start_cursor': boundary, 'conversations': rows,
                      'next_page_token': 'opaque page ' + str(end) if end < len(frozen) else None,
                      'has_more': end < len(frozen)}
        else:
            try:
                offset = int(body['cursor'].removeprefix('cursor:'))
                boundary = int(body.get('snapshot_boundary', 'cursor:' + str(len(self.feed))).removeprefix('cursor:'))
                if not 0 <= offset <= boundary <= len(self.feed):
                    raise ValueError
            except (KeyError, ValueError, AttributeError):
                return web.json_response(error('SYNC_RESET_REQUIRED'), status=410)
            end = min(boundary, offset + min(body['limit'], self.scan_rows))
            events = []
            for row in self.feed[offset:end]:
                event = copy.deepcopy(row['envelope'])
                if viewer not in row['recipients']:
                    continue
                own_removal = (event['event'] == 'conversation.member_removed' and
                               event['payload']['member_id'] == viewer)
                mid = event['payload'].get('message_id')
                if not own_removal and not self.may_receive(
                        viewer, 'message' if mid else 'conversation', mid or event['conversation_id']):
                    continue
                if event['event'] == 'message.created' and event['sender_id'] != viewer:
                    event['payload'].pop('client_message_id', None)
                events.append(event)
            result = {'snapshot_boundary': 'cursor:' + str(boundary), 'events': events,
                      'next_cursor': 'cursor:' + str(end), 'has_more': end < boundary}
        if self.mutate_result:
            result = self.mutate_result(operation, result)
        self.read_entered.set()
        if self.read_hold is not None:
            await self.read_hold.wait()
        return web.json_response({'data': result})


class SyncBoundaryTests(AddonHarness):
    authority_type = SyncAuthority

    async def request(self, ws, name='sync.request', **payload):
        request = frame(name, payload)
        await ws.send_json(request)
        return await self.correlated(ws, request)

    def connection(self, user='user-b'):
        from hine_realtime.server import RUNTIME
        return next(c for c in self.app[RUNTIME].connections
                    if c.binding and c.binding['user_id'] == user)

    async def assert_fault(self, ws, name='sync.request', code='DEPENDENCY_UNAVAILABLE', **payload):
        result = await self.request(ws, name, **payload)
        self.assertEqual(result['event'], 'error')
        self.assertEqual(result['payload']['code'], code)
        self.assertNotIn('fixture private', result['payload']['message'])
        self.assertNotIn('next_cursor', result['payload'])
        self.assertNotIn('start_cursor', result['payload'])
        return result

    async def publish_removal(self, version):
        notice = {'notice_id': str(uuid4()), 'type': 'conversation_events',
                  'committed_at': frame('unused', {})['timestamp'],
                  'invalidation_position': self.authority.head,
                  'conversation_events': {'source': 'A18', 'conversation_id': 'group-1',
                    'membership_version': version, 'deliveries': [
                      {'recipient_user_id': 'user-a', 'envelope': frame('conversation.member_removed',
                       {'member_id': 'user-b', 'change': 'removed', 'actor_id': 'user-a',
                        'membership_version': version}, conversation_id='group-1')}]}}
        async with self.client.post(self.url + '/internal/v1/publishCommitted',
                                    json={'notice': notice},
                                    headers={'Authorization': 'Bearer api-service-secret'}) as response:
            self.assertEqual(response.status, 200)
        async with asyncio.timeout(3):
            while self.connection().removed_versions.get('group-1') != version:
                await asyncio.sleep(.01)

    async def writer_waiting_on_lock(self, lock):
        # The sync-only permission barrier establishes this is the W14/W16
        # writer; wait for its actual socket-lock waiter, not an elapsed sleep.
        async with asyncio.timeout(2):
            while not lock._waiters or not any(not waiter.done() for waiter in lock._waiters):
                await asyncio.sleep(.01)

    async def test_saved_cursor_recovers_offline_message_without_receiver_c1(self):
        sender = await self.auth('access-a')
        receiver = await self.auth('access-b')
        bootstrap = frame('sync.bootstrap.request', {'reason': 'first_login'})
        await receiver.send_json(bootstrap)
        page = await self.correlated(receiver, bootstrap)
        self.assertEqual(page['event'], 'sync.bootstrap.page')
        saved = page['payload']['start_cursor']
        await receiver.close()
        mid = await self.send(sender, text='offline recovery message')
        reconnect = await self.auth('access-b')
        request = frame('sync.request', {'cursor': saved})
        await reconnect.send_json(request)
        batch = await self.correlated(reconnect, request)
        self.assertEqual(batch['event'], 'sync.batch')
        message = next(event for event in batch['payload']['events'] if event['payload'].get('message_id') == mid)
        self.assertEqual(message['payload']['text'], 'offline recovery message')
        self.assertNotIn('client_message_id', message['payload'])
        self.assertFalse(batch['payload']['has_more'])

    async def test_bootstrap_pages_keep_snapshot_and_complete_sender_private_snapshots(self):
        sender = await self.auth('access-a')
        receiver = await self.auth('access-b')
        direct = await self.send(sender, text='complete direct snapshot')
        group = await self.send(sender, text='complete group snapshot', conversation='group-1')
        command = frame('message.read', {'message_id': direct}, conversation_id='direct-1')
        await receiver.send_json(command)
        self.assertEqual((await self.correlated(receiver, command))['event'], 'receipt.ack')
        self.authority.page_rows = 1
        first = await self.request(sender, 'sync.bootstrap.request', reason='first_login')
        self.assertEqual(first['event'], 'sync.bootstrap.page')
        page = first['payload']
        self.assertTrue(page['has_more'])
        self.assertEqual(page['next_page_token'], 'opaque page 1')
        self.assertEqual(page['conversations'][0]['id'], 'direct-1')
        message = page['conversations'][0]['recent_messages'][0]
        self.assertEqual(message['id'], direct)
        self.assertEqual(message['text'], 'complete direct snapshot')
        self.assertEqual(message['sender_id'], 'user-a')
        self.assertEqual(message['order_key'], '00000000000000000001')
        self.assertEqual(message['receipt']['status'], 'read')
        self.assertEqual(message['receipt']['recipient_id'], 'user-b')
        self.assertIn('client_message_id', message)
        self.assertNotIn('subject_id', message)
        self.assertNotIn('download_url', message)
        second = await self.request(sender, 'sync.bootstrap.request', reason='first_login',
                                    snapshot_id=page['snapshot_id'], page_token=page['next_page_token'])
        self.assertEqual(second['event'], 'sync.bootstrap.page')
        self.assertEqual(second['payload']['snapshot_id'], page['snapshot_id'])
        self.assertEqual(second['payload']['start_cursor'], page['start_cursor'])
        self.assertIsNone(second['payload']['next_page_token'])
        self.assertFalse(second['payload']['has_more'])
        group_message = second['payload']['conversations'][0]['recent_messages'][0]
        self.assertEqual(group_message['id'], group)
        self.assertIsNone(group_message['receipt'])
        receiver_page = await self.request(receiver, 'sync.bootstrap.request', reason='first_login')
        self.assertNotIn('client_message_id', receiver_page['payload']['conversations'][0]['recent_messages'][0])
        reads = [body for operation, body in self.authority.calls if operation == 'readBootstrap']
        self.assertEqual(set(reads[0]), {'subject_id', 'session_id', 'session_generation', 'reason'})
        self.assertEqual(set(reads[1]), {'subject_id', 'session_id', 'session_generation', 'reason', 'snapshot_id', 'page_token'})

    async def test_bootstrap_request_tokens_are_paired_nonnull_and_opaque(self):
        ws = await self.auth('access-b')
        for extra in ({'snapshot_id': 's'}, {'page_token': 'p'},
                      {'snapshot_id': None, 'page_token': 'p'},
                      {'snapshot_id': 's', 'page_token': ''}, {'reason': 'unknown'}):
            with self.subTest(extra=extra):
                payload = {'reason': 'first_login', **extra}
                await self.assert_fault(ws, 'sync.bootstrap.request', code='INVALID_ARGUMENT', **payload)
        self.assertFalse(any(operation == 'readBootstrap' for operation, _ in self.authority.calls))
        await self.assert_fault(ws, 'sync.bootstrap.request', code='SYNC_RESET_REQUIRED',
                                reason='cursor_reset', snapshot_id='opaque missing snapshot',
                                page_token='opaque missing page')

    async def test_hidden_feed_positions_advance_and_boundary_replay_is_stateless(self):
        sender = await self.auth('access-a')
        receiver = await self.auth('access-b')
        self.authority.scan_rows = 1
        self.authority.feed.append({'recipients': ['user-a'], 'envelope':
            frame('conversation.updated', {'changes': {'kind': 'title', 'title': 'hidden title'},
                  'actor_id': 'user-a', 'membership_version': 1}, conversation_id='group-1')})
        mid = await self.send(sender, text='visible after hidden row')
        first = await self.request(receiver, cursor='cursor:0')
        self.assertEqual(first['event'], 'sync.batch')
        self.assertEqual(first['payload']['events'], [])
        self.assertEqual(first['payload']['next_cursor'], 'cursor:1')
        self.assertEqual(first['payload']['snapshot_boundary'], 'cursor:2')
        self.assertTrue(first['payload']['has_more'])
        await self.send(sender, text='after frozen boundary')
        second = await self.request(receiver, cursor='cursor:1', snapshot_boundary='cursor:2')
        self.assertEqual(second['payload']['next_cursor'], 'cursor:2')
        self.assertFalse(second['payload']['has_more'])
        self.assertEqual(second['payload']['events'][0]['payload']['message_id'], mid)
        replay = await self.request(receiver, cursor='cursor:1', snapshot_boundary='cursor:2')
        self.assertEqual(replay['payload']['events'][0]['event_id'], second['payload']['events'][0]['event_id'])
        tail = await self.request(receiver, cursor='cursor:2')
        self.assertEqual(tail['payload']['events'][0]['payload']['text'], 'after frozen boundary')
        reads = [body for operation, body in self.authority.calls if operation == 'readFeed']
        self.assertEqual(set(reads[0]), {'subject_id', 'session_id', 'session_generation', 'cursor', 'limit'})
        self.assertEqual(reads[0]['limit'], 100)

    async def test_expired_cursor_is_sync_reset_not_session_failure(self):
        ws = await self.auth('access-b')
        await self.assert_fault(ws, code='SYNC_RESET_REQUIRED', cursor='opaque expired cursor')
        page = await self.request(ws, 'sync.bootstrap.request', reason='cursor_reset')
        self.assertEqual(page['event'], 'sync.bootstrap.page')
        batch = await self.request(ws, cursor=page['payload']['start_cursor'])
        self.assertEqual(batch['event'], 'sync.batch')
        self.assertEqual(batch['payload']['events'], [])
        self.assertEqual(batch['payload']['next_cursor'], page['payload']['start_cursor'])
        self.assertFalse(batch['payload']['has_more'])

    async def test_malformed_bootstrap_rejects_whole_page_without_installable_cursor(self):
        sender = await self.auth('access-a')
        ws = await self.auth('access-b')
        await self.send(sender)
        def corrupt(field, value):
            def change(operation, result):
                if operation == 'readBootstrap':
                    target = result
                    for part in field[:-1]:
                        target = target[part]
                    target[field[-1]] = value
                return result
            return change
        cases = [
            (('has_more',), 1), (('next_page_token',), 'unexpected token'),
            (('snapshot_id',), None), (('start_cursor',), ''),
            (('conversations', 0, 'unread_count'), True),
            (('conversations', 0, 'title'), 'direct cannot have title'),
            (('conversations', 0, 'my_role'), 'admin'),
            (('conversations', 0, 'recent_messages', 0, 'receipt'), {}),
            (('conversations', 0, 'recent_messages', 0, 'client_message_id'), str(uuid4())),
            (('conversations', 0, 'recent_messages', 0, 'attachment_id'), 'private attachment'),
            (('conversations', 0, 'recent_messages', 0, 'order_key'), '1'),
            (('conversations', 0, 'recent_messages', 0, 'event_id'), None),
            (('conversations', 0, 'recent_messages', 0, 'conversation_id'), 'group-1'),
        ]
        for field, value in cases:
            with self.subTest(field=field):
                self.authority.mutate_result = corrupt(field, value)
                await self.assert_fault(ws, 'sync.bootstrap.request', reason='first_login')
        self.authority.mutate_result = None
        self.assertEqual((await self.request(ws, 'sync.bootstrap.request', reason='first_login'))['event'],
                         'sync.bootstrap.page')

    async def test_malformed_feed_and_c13_do_not_close_healthy_session(self):
        sender = await self.auth('access-a')
        ws = await self.auth('access-b')
        await self.send(sender)
        def corrupt(field, value):
            def change(operation, result):
                if operation == 'readFeed':
                    if field in {'has_more', 'events', 'snapshot_boundary', 'next_cursor'}:
                        result[field] = value
                    else:
                        result['events'][0][field] = value
                return result
            return change
        for field, value in [('has_more', 1), ('events', {}), ('snapshot_boundary', ''),
                             ('next_cursor', None), ('correlation_id', str(uuid4())),
                             ('event', 'presence.changed'), ('sender_id', None),
                             ('private_subject', 'private-a')]:
            with self.subTest(field=field):
                self.authority.mutate_result = corrupt(field, value)
                await self.assert_fault(ws, cursor='cursor:0')
        self.authority.mutate_result = None
        for layer in ('service_identity', None):
            self.authority.faults['readFeed'] = (401, error('UNAUTHENTICATED', layer))
            await self.assert_fault(ws, cursor='cursor:0')
        self.authority.faults.clear()
        self.assertEqual((await self.request(ws, cursor='cursor:0'))['event'], 'sync.batch')

    async def test_response_snapshot_and_boundary_must_match_requested_opaque_value(self):
        ws = await self.auth('access-b')
        first = await self.request(ws, 'sync.bootstrap.request', reason='first_login')
        self.authority.mutate_result = lambda op, data: {**data, 'snapshot_id': 'different opaque value'} if op == 'readBootstrap' else data
        await self.assert_fault(ws, 'sync.bootstrap.request', reason='first_login',
                                snapshot_id=first['payload']['snapshot_id'], page_token='opaque page 1')
        self.authority.mutate_result = lambda op, data: {**data, 'snapshot_boundary': 'cursor:other'} if op == 'readFeed' else data
        await self.assert_fault(ws, cursor='cursor:0', snapshot_boundary='cursor:0')

    async def test_page_logical_items_and_feed_events_obey_configured_limit(self):
        sender = await self.auth('access-a')
        ws = await self.auth('access-b')
        await self.send(sender)
        runtime = self.connection().runtime
        runtime.settings = replace(runtime.settings, sync_page_limit=1)
        await self.assert_fault(ws, 'sync.bootstrap.request', reason='first_login')
        def duplicate(operation, data):
            if operation == 'readFeed':
                data['events'].append(copy.deepcopy(data['events'][0]))
            return data
        self.authority.mutate_result = duplicate
        await self.assert_fault(ws, cursor='cursor:0')

    async def test_group_removal_during_authority_read_rejects_old_body_then_same_cursor_filters(self):
        sender = await self.auth('access-a')
        ws = await self.auth('access-b')
        await self.send(sender, text='old group body', conversation='group-1')
        await self.send(sender, text='other dialog remains available')
        self.authority.read_hold = asyncio.Event()
        self.authority.read_entered.clear()
        request = frame('sync.request', {'cursor': 'cursor:0'})
        await ws.send_json(request)
        await asyncio.wait_for(self.authority.read_entered.wait(), 2)
        version = self.authority.remove_group_user('user-b')
        await self.publish_removal(version)
        self.authority.read_hold.set()
        failed = await self.correlated(ws, request)
        self.assertEqual(failed['event'], 'error')
        self.assertEqual(failed['payload']['code'], 'DEPENDENCY_UNAVAILABLE')
        self.assertNotIn('next_cursor', failed['payload'])
        current = await self.request(ws, cursor='cursor:0')
        self.assertEqual(current['event'], 'sync.batch')
        self.assertEqual([event['payload']['text'] for event in current['payload']['events']],
                         ['other dialog remains available'])

    async def exercise_final_removal_race(self, hold_socket=False):
        sender = await self.auth('access-a')
        ws = await self.auth('access-b')
        group_mid = await self.send(sender, text='old snapshot under authorization', conversation='group-1')
        await self.send(sender, text='safe direct body')
        self.authority.sync_authorize_release = asyncio.Event()
        self.authority.sync_authorize_hold_user = 'user-b'
        self.authority.sync_authorize_hold_resource = group_mid
        self.authority.sync_authorize_entered.clear()
        self.authority.sync_expected_authorizations = 2
        request = frame('sync.request', {'cursor': 'cursor:0'})
        await ws.send_json(request)
        await asyncio.wait_for(self.authority.sync_authorize_entered.wait(), 2)
        held = next(snapshot for snapshot in self.authority.sync_authorization_snapshots
                    if snapshot['resource_id'] == group_mid)
        self.assertEqual((held['action'], held['resource_type'], held['allowed']), ('read', 'message', True))
        self.assertTrue(any(op == 'readFeed' for op, _ in self.authority.calls))
        lock = None
        try:
            if hold_socket:
                lock = self.connection().write_lock
                await lock.acquire()
                self.authority.sync_authorize_release.set()
                await asyncio.wait_for(self.authority.sync_authorizations_done.wait(), 2)
                await self.writer_waiting_on_lock(lock)
            version = self.authority.remove_group_user('user-b')
            await self.publish_removal(version)
        finally:
            self.authority.sync_authorize_release.set()
            if lock is not None and lock.locked():
                lock.release()
        failed = await self.correlated(ws, request)
        self.assertEqual(failed['event'], 'error')
        self.assertEqual(failed['payload']['code'], 'DEPENDENCY_UNAVAILABLE')
        self.assertNotIn('next_cursor', failed['payload'])
        next_batch = await self.request(ws, cursor='cursor:0')
        self.assertEqual(next_batch['event'], 'sync.batch')
        self.assertEqual(next_batch['payload']['events'][0]['payload']['text'], 'safe direct body')

    async def test_group_removal_during_allowed_authorization_discards_whole_batch(self):
        await self.exercise_final_removal_race()

    async def test_group_removal_after_authorization_while_waiting_write_lock_discards_cursor(self):
        await self.exercise_final_removal_race(hold_socket=True)

    async def test_current_message_authorization_blocks_lost_notice_and_rejoin_old_history(self):
        sender = await self.auth('access-a')
        ws = await self.auth('access-b')
        await self.send(sender, text='before new join boundary', conversation='group-1')
        self.authority.read_hold = asyncio.Event()
        self.authority.read_entered.clear()
        request = frame('sync.request', {'cursor': 'cursor:0'})
        await ws.send_json(request)
        await asyncio.wait_for(self.authority.read_entered.wait(), 2)
        self.authority.remove_group_user('user-b')
        self.authority.rejoin_group_user('user-b')
        self.authority.read_hold.set()
        denied = await self.correlated(ws, request)
        self.assertEqual(denied['event'], 'error')
        self.assertEqual(denied['payload']['code'], 'FORBIDDEN')
        await self.send(sender, text='after new join boundary', conversation='group-1')
        batch = await self.request(ws, cursor='cursor:0')
        self.assertEqual([event['payload']['text'] for event in batch['payload']['events']],
                         ['after new join boundary'])

    async def test_old_removal_marker_does_not_blackhole_rejoined_current_read(self):
        sender = await self.auth('access-a')
        ws = await self.auth('access-b')
        version = self.authority.remove_group_user('user-b')
        await self.publish_removal(version)
        self.authority.rejoin_group_user('user-b')
        await self.send(sender, text='readable rejoined body', conversation='group-1')
        batch = await self.request(ws, cursor='cursor:0')
        self.assertEqual(batch['event'], 'sync.batch')
        self.assertEqual(batch['payload']['events'][0]['payload']['text'], 'readable rejoined body')

    async def test_minimal_own_removal_survives_without_history_permission(self):
        ws = await self.auth('access-b')
        version = self.authority.remove_group_user('user-b')
        eid = str(uuid4())
        self.authority.feed.append({'recipients': ['user-b'], 'envelope':
            frame('conversation.member_removed', {'member_id': 'user-b', 'change': 'removed',
                  'membership_version': version}, conversation_id='group-1', event_id=eid)})
        batch = await self.request(ws, cursor='cursor:0')
        self.assertEqual(batch['event'], 'sync.batch')
        self.assertEqual(batch['payload']['events'][0]['event_id'], eid)
        self.assertEqual(batch['payload']['events'][0]['payload'],
                         {'member_id': 'user-b', 'change': 'removed', 'membership_version': 2})
        self.assertEqual(self.connection().removed_versions['group-1'], 2)
        self.assertFalse(any(op == 'authorize' for op, _ in self.authority.calls))

    async def test_own_removal_with_old_body_taints_entire_response_not_just_one_event(self):
        sender = await self.auth('access-a')
        ws = await self.auth('access-b')
        await self.send(sender, text='must not be partially delivered', conversation='group-1')
        self.authority.feed.append({'recipients': ['user-b'], 'envelope':
            frame('conversation.member_removed', {'member_id': 'user-b', 'change': 'removed',
                  'membership_version': 2}, conversation_id='group-1')})
        await self.assert_fault(ws, cursor='cursor:0')
        self.assertEqual(self.connection().removed_versions['group-1'], 2)

    async def test_session_revoke_during_read_never_delivers_old_cursor_or_body(self):
        ws = await self.auth('access-b')
        self.authority.read_hold = asyncio.Event()
        self.authority.read_entered.clear()
        request = frame('sync.bootstrap.request', {'reason': 'first_login'})
        await ws.send_json(request)
        await asyncio.wait_for(self.authority.read_entered.wait(), 2)
        self.authority.invalidate('session-b')
        self.authority.read_hold.set()
        observed = []
        async with asyncio.timeout(3):
            async for message in ws:
                if message.type == WSMsgType.TEXT:
                    observed.append(message.json())
        self.assertFalse(any(value['event'] in {'sync.bootstrap.page', 'sync.batch'} for value in observed))

    async def test_complete_catchup_after_empty_read_not_just_cached_freshness(self):
        ws = await self.auth('access-b')
        self.authority.calls.clear()
        batch = await self.request(ws, cursor='cursor:0')
        self.assertEqual(batch['event'], 'sync.batch')
        operations = [op for op, _ in self.authority.calls]
        self.assertIn('readSessionInvalidations', operations[operations.index('readFeed') + 1:])

    async def test_authorization_dependency_timeout_is_bounded_and_session_survives(self):
        sender = await self.auth('access-a')
        ws = await self.auth('access-b')
        await self.send(sender)
        self.authority.sync_authorize_release = asyncio.Event()
        self.authority.sync_authorize_hold_user = 'user-b'
        try:
            async with asyncio.timeout(3):
                await self.assert_fault(ws, cursor='cursor:0')
                self.assertTrue(self.authority.sync_authorize_entered.is_set())
                snapshots = self.authority.sync_authorization_snapshots
                self.assertEqual(len(snapshots), 1)
                self.assertEqual((snapshots[0]['action'], snapshots[0]['resource_type'],
                                  snapshots[0]['user'], snapshots[0]['allowed']),
                                 ('read', 'message', 'user-b', True))
        finally:
            self.authority.sync_authorize_release.set()
        self.assertEqual((await self.request(ws, cursor='cursor:0'))['event'], 'sync.batch')

    async def test_feed_supports_all_public_kinds_and_deduplicates_current_read_references(self):
        sender = await self.auth('access-a')
        ws = await self.auth('access-b')
        mid = await self.send(sender, text='message with receipt replay')
        ids = [str(uuid4()) for _ in range(4)]
        events = [
            frame('message.status', {'kind': 'direct', 'message_id': mid, 'recipient_id': 'user-b',
                  'status': 'read', 'updated_at': frame('unused', {})['timestamp']},
                  conversation_id='direct-1', event_id=ids[0]),
            frame('conversation.member_added', {'member_id': 'user-a', 'role': 'admin',
                  'actor_id': 'user-a', 'membership_version': 1},
                  conversation_id='group-1', event_id=ids[1]),
            frame('conversation.updated', {'changes': {'kind': 'title', 'title': 'updated title'},
                  'actor_id': 'user-a', 'membership_version': 1},
                  conversation_id='group-1', event_id=ids[2]),
            frame('conversation.updated', {'changes': {'kind': 'role', 'member_id': 'user-b', 'role': 'member'},
                  'actor_id': 'user-a', 'membership_version': 1},
                  conversation_id='group-1', event_id=ids[3]),
        ]
        self.authority.feed.extend({'recipients': ['user-b'], 'envelope': event} for event in events)
        self.authority.calls.clear()
        batch = await self.request(ws, cursor='cursor:0')
        self.assertEqual(batch['event'], 'sync.batch')
        self.assertEqual([event['event'] for event in batch['payload']['events']],
                         ['message.created', 'message.status', 'conversation.member_added',
                          'conversation.updated', 'conversation.updated'])
        self.assertEqual([event['event_id'] for event in batch['payload']['events'][1:]], ids)
        self.assertEqual(batch['payload']['events'][1]['payload']['status'], 'read')
        self.assertEqual(batch['payload']['events'][3]['payload']['changes']['title'], 'updated title')
        authorizations = [data for op, data in self.authority.calls
                          if op == 'authorize' and data['action'] in {'read', 'history'}]
        self.assertEqual(len(authorizations), 2)
        self.assertEqual({(data['action'], data['resource_type'], data['resource_id']) for data in authorizations},
                         {('read', 'message', mid), ('history', 'conversation', 'group-1')})
        self.assertTrue(all(data['subject_id'] == 'private-b' and data['device_id'] == 'device-b'
                            and data['session_id'] == 'session-b' and data['session_generation'] == 1
                            for data in authorizations))

    async def test_snapshot_image_file_union_is_complete_and_private_metadata_is_rejected(self):
        sender = await self.auth('access-a')
        ws = await self.auth('access-b')
        mid = await self.send(sender)
        def attachment(kind, extra=None):
            def change(operation, data):
                if operation == 'readBootstrap':
                    message = data['conversations'][0]['recent_messages'][0]
                    message.pop('text')
                    message.update(type=kind, attachment_id='opaque attachment id')
                    if extra:
                        message.update(extra)
                return data
            return change
        for kind in ('image', 'file'):
            with self.subTest(kind=kind):
                self.authority.mutate_result = attachment(kind)
                page = await self.request(ws, 'sync.bootstrap.request', reason='first_login')
                self.assertEqual(page['event'], 'sync.bootstrap.page')
                message = page['payload']['conversations'][0]['recent_messages'][0]
                self.assertEqual(message['id'], mid)
                self.assertEqual(message['type'], kind)
                self.assertEqual(message['attachment_id'], 'opaque attachment id')
                self.assertNotIn('text', message)
                self.assertIsNone(message['receipt'])
        for extra in ({'download_url': 'https://private.invalid/signed'},
                      {'subject_id': 'private-a'}, {'bucket': 'private-bucket'},
                      {'text': 'invalid second union branch'}):
            self.authority.mutate_result = attachment('image', extra)
            await self.assert_fault(ws, 'sync.bootstrap.request', reason='first_login')

    async def test_minimal_own_removal_does_not_block_other_dialog_and_rejects_actor_leak(self):
        sender = await self.auth('access-a')
        ws = await self.auth('access-b')
        await self.send(sender, text='other dialog alongside own removal')
        version = self.authority.remove_group_user('user-b')
        self.authority.feed.append({'recipients': ['user-b'], 'envelope':
            frame('conversation.member_removed', {'member_id': 'user-b', 'change': 'removed',
                  'membership_version': version}, conversation_id='group-1')})
        batch = await self.request(ws, cursor='cursor:0')
        self.assertEqual(batch['event'], 'sync.batch')
        self.assertEqual(batch['payload']['events'][0]['payload']['text'], 'other dialog alongside own removal')
        self.assertEqual(batch['payload']['events'][1]['event'], 'conversation.member_removed')
        def leak(operation, data):
            if operation == 'readFeed':
                data['events'][1]['payload']['actor_id'] = 'user-a'
            return data
        self.authority.mutate_result = leak
        await self.assert_fault(ws, cursor='cursor:0')

    async def test_malformed_group_event_payloads_and_receipt_union_fail_closed(self):
        sender = await self.auth('access-a')
        ws = await self.auth('access-b')
        mid = await self.send(sender)
        cases = [
            ('message.status', {'kind': 'group', 'message_id': mid, 'recipient_id': 'user-b',
                               'status': 'read', 'updated_at': frame('unused', {})['timestamp']}),
            ('message.status', {'kind': 'direct', 'message_id': mid, 'recipient_id': 'user-b',
                               'status': 'pending', 'updated_at': frame('unused', {})['timestamp']}),
            ('conversation.member_added', {'member_id': 'user-b', 'role': 'owner',
                                          'actor_id': 'user-a', 'membership_version': 1}),
            ('conversation.member_removed', {'member_id': 'user-b', 'change': 'removed',
                                             'membership_version': True}),
            ('conversation.updated', {'changes': {'kind': 'role', 'role': 'admin'},
                                      'actor_id': 'user-a', 'membership_version': 1}),
            ('conversation.updated', {'changes': {'kind': 'title', 'title': None},
                                      'actor_id': 'user-a', 'membership_version': 1}),
        ]
        for name, payload in cases:
            with self.subTest(name=name, payload=payload):
                event = frame(name, payload, conversation_id='group-1')
                self.authority.mutate_result = lambda op, data, event=event: {**data, 'events': [event]} if op == 'readFeed' else data
                await self.assert_fault(ws, cursor='cursor:0')

    async def test_failed_post_read_catchup_does_not_trust_previous_freshness(self):
        ws = await self.auth('access-b')
        self.authority.fail_poll = True
        try:
            await self.assert_fault(ws, cursor='cursor:0')
        finally:
            self.authority.fail_poll = False
        self.assertEqual((await self.request(ws, cursor='cursor:0'))['event'], 'sync.batch')

    async def test_current_read_c13_service_failure_is_not_logout(self):
        sender = await self.auth('access-a')
        ws = await self.auth('access-b')
        await self.send(sender)
        self.authority.faults['authorize'] = (401, error('UNAUTHENTICATED', 'service_identity'))
        await self.assert_fault(ws, cursor='cursor:0')
        self.authority.faults.clear()
        self.assertEqual((await self.request(ws, cursor='cursor:0'))['event'], 'sync.batch')

    async def test_trusted_user_session_read_error_is_correlated_and_closes_only_binding(self):
        ws = await self.auth('access-b')
        other = await self.auth('access-a')
        self.authority.faults['readFeed'] = (401, error('UNAUTHENTICATED', 'user_session'))
        await self.assert_fault(ws, code='UNAUTHENTICATED', cursor='cursor:0')
        async with asyncio.timeout(3):
            async for _ in ws:
                pass
        self.authority.faults.clear()
        self.assertEqual((await self.request(other, cursor='cursor:0'))['event'], 'sync.batch')

    async def exercise_session_final_race(self, hold_socket=False):
        sender = await self.auth('access-a')
        ws = await self.auth('access-b')
        mid = await self.send(sender)
        self.authority.sync_authorize_release = asyncio.Event()
        self.authority.sync_authorize_hold_user = 'user-b'
        self.authority.sync_authorize_hold_resource = mid
        self.authority.sync_authorize_entered.clear()
        self.authority.sync_expected_authorizations = 1
        request = frame('sync.request', {'cursor': 'cursor:0'})
        await ws.send_json(request)
        await asyncio.wait_for(self.authority.sync_authorize_entered.wait(), 2)
        held = next(snapshot for snapshot in self.authority.sync_authorization_snapshots
                    if snapshot['resource_id'] == mid)
        self.assertEqual((held['action'], held['resource_type'], held['allowed']), ('read', 'message', True))
        lock = None
        try:
            if hold_socket:
                lock = self.connection().write_lock
                await lock.acquire()
                self.authority.sync_authorize_release.set()
                await asyncio.wait_for(self.authority.sync_authorizations_done.wait(), 2)
                await self.writer_waiting_on_lock(lock)
            entry = self.authority.invalidate('session-b')
            notice = {'notice_id': str(uuid4()), 'type': 'session_invalidation',
                      'committed_at': entry['committed_at'], 'invalidation_position': entry['position'],
                      'session_invalidation': entry}
            async with self.client.post(self.url + '/internal/v1/publishCommitted',
                                        json={'notice': notice},
                                        headers={'Authorization': 'Bearer api-service-secret'}) as response:
                self.assertEqual(response.status, 200)
            from hine_realtime.server import RUNTIME
            async with asyncio.timeout(2):
                while not any(c.binding and c.binding['user_id'] == 'user-b' and c.invalid
                              for c in self.app[RUNTIME].connections) and not ws.closed:
                    if not any(c.binding and c.binding['user_id'] == 'user-b'
                               for c in self.app[RUNTIME].connections):
                        break
                    await asyncio.sleep(.01)
        finally:
            self.authority.sync_authorize_release.set()
            if lock is not None and lock.locked():
                lock.release()
        observed = []
        async with asyncio.timeout(3):
            async for message in ws:
                if message.type == WSMsgType.TEXT:
                    observed.append(message.json())
        self.assertFalse(any(value['event'] == 'sync.batch' for value in observed))

    async def test_session_revoke_during_allowed_read_authorization_prevents_old_cursor(self):
        await self.exercise_session_final_race()

    async def test_session_revoke_after_authorization_at_write_lock_prevents_old_cursor(self):
        await self.exercise_session_final_race(hold_socket=True)

    async def test_feed_request_cursor_and_optional_boundary_are_nonnull_strings(self):
        ws = await self.auth('access-b')
        for payload in ({}, {'cursor': None}, {'cursor': ''}, {'cursor': 1},
                        {'cursor': 'cursor:0', 'snapshot_boundary': None},
                        {'cursor': 'cursor:0', 'snapshot_boundary': ''},
                        {'cursor': 'cursor:0', 'limit': 100}):
            with self.subTest(payload=payload):
                await self.assert_fault(ws, code='INVALID_ARGUMENT', **payload)
        self.assertFalse(any(op == 'readFeed' for op, _ in self.authority.calls))

    async def test_receiver_feed_c1_and_attachment_union_leaks_reject_entire_cursor(self):
        sender = await self.auth('access-a')
        ws = await self.auth('access-b')
        await self.send(sender)
        def private_payload(extra):
            def change(operation, data):
                if operation == 'readFeed':
                    data['events'][0]['payload'].update(extra)
                return data
            return change
        for extra in ({'client_message_id': str(uuid4())}, {'attachment_id': 'wrong union'},
                      {'subject_id': 'private-a'}, {'text': None}, {'order_key': '00000000000000000000'}):
            with self.subTest(extra=extra):
                self.authority.mutate_result = private_payload(extra)
                await self.assert_fault(ws, cursor='cursor:0')
        self.authority.mutate_result = None
        batch = await self.request(ws, cursor='cursor:0')
        self.assertEqual(batch['event'], 'sync.batch')
        self.assertNotIn('client_message_id', batch['payload']['events'][0]['payload'])

    async def test_bootstrap_metadata_current_history_denial_does_not_logout_or_install_h(self):
        ws = await self.auth('access-b')
        self.authority.read_hold = asyncio.Event()
        self.authority.read_entered.clear()
        request = frame('sync.bootstrap.request', {'reason': 'first_login'})
        await ws.send_json(request)
        await asyncio.wait_for(self.authority.read_entered.wait(), 2)
        self.authority.remove_group_user('user-b')
        self.authority.read_hold.set()
        denied = await self.correlated(ws, request)
        self.assertEqual(denied['event'], 'error')
        self.assertEqual(denied['payload']['code'], 'FORBIDDEN')
        self.assertNotIn('start_cursor', denied['payload'])
        current = await self.request(ws, 'sync.bootstrap.request', reason='first_login')
        self.assertEqual(current['event'], 'sync.bootstrap.page')
        self.assertEqual([row['id'] for row in current['payload']['conversations']], ['direct-1'])

    async def test_bootstrap_continuation_reauthorizes_frozen_snapshot_after_removal(self):
        ws = await self.auth('access-b')
        self.authority.page_rows = 1
        first = await self.request(ws, 'sync.bootstrap.request', reason='first_login')
        self.authority.remove_group_user('user-b')
        next_page = await self.request(ws, 'sync.bootstrap.request', reason='first_login',
                                       snapshot_id=first['payload']['snapshot_id'],
                                       page_token=first['payload']['next_page_token'])
        self.assertEqual(next_page['event'], 'sync.bootstrap.page')
        self.assertEqual(next_page['payload']['conversations'], [])
        self.assertEqual(next_page['payload']['snapshot_id'], first['payload']['snapshot_id'])
        self.assertEqual(next_page['payload']['start_cursor'], first['payload']['start_cursor'])
        self.assertFalse(next_page['payload']['has_more'])
