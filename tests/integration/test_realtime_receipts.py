"""Real BA/WS/Redis receipt boundaries with isolated stateful BB authority."""
import asyncio
import copy
import json
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import aiohttp
from aiohttp import web
from receipt_sync_support import AddonAuthority, AddonHarness
from redis.asyncio import Redis
from test_realtime_boundaries import error, frame


class ReceiptAuthority(AddonAuthority):
    """Test-only BB request validator; durable state remains in the fixture."""

    async def handle(self, request):
        if request.match_info['operation'] == 'persistReceipt':
            body = await request.json()
            required = {'subject_id', 'device_id', 'session_id', 'session_generation',
                        'conversation_id', 'message_id', 'kind', 'request_event_id'}
            if set(body) != required or body.get('kind') not in {'delivered', 'read'}:
                return web.json_response(error('INVALID_ARGUMENT'), status=400)
            if len(body['conversation_id']) > 128:
                return web.json_response(error('INVALID_ARGUMENT'), status=400)
            session = self.session(body)
            if session is not None and body['device_id'] != 'device-' + session['session_id'].removeprefix('session-'):
                return web.json_response(error('UNAUTHENTICATED', 'user_session'), status=401)
        return await super().handle(request)


class ReceiptBoundaryTests(AddonHarness):
    authority_type = ReceiptAuthority

    async def event(self, ws, name):
        async with asyncio.timeout(5):
            while True:
                value = await ws.receive_json()
                if value['event'] == name:
                    return value

    async def no_frame(self, ws):
        with self.assertRaises(TimeoutError):
            await ws.receive(timeout=.15)

    async def pair(self, conversation='direct-1'):
        sender = await self.auth('access-a')
        recipient = await self.auth('access-b')
        mid = await self.send(sender, conversation=conversation)
        await self.event(sender, 'message.created')
        await self.event(recipient, 'message.created')
        return sender, recipient, mid

    async def receipt(self, ws, mid, event='message.read', conversation='direct-1'):
        request = frame(event, {'message_id': mid}, conversation_id=conversation)
        await ws.send_json(request)
        return request, await self.correlated(ws, request)

    async def ping(self, ws):
        request = frame('heartbeat.ping', {'nonce': str(uuid4())})
        await ws.send_json(request)
        reply = await self.correlated(ws, request)
        self.assertEqual(reply['event'], 'heartbeat.pong')

    async def test_read_then_received_keeps_read_status_and_original_message(self):
        sender = await self.auth('access-a')
        recipient = await self.auth('access-b')
        mid = await self.send(sender)
        read = frame('message.read', {'message_id': mid}, conversation_id='direct-1')
        await recipient.send_json(read)
        ack = await self.correlated(recipient, read)
        self.assertEqual(ack['event'], 'receipt.ack')
        self.assertEqual(ack['payload'], {'message_id': mid, 'status': 'read', 'changed': True})
        received = frame('message.received', {'message_id': mid}, conversation_id='direct-1')
        await recipient.send_json(received)
        repeated = await self.correlated(recipient, received)
        self.assertEqual(repeated['event'], 'receipt.ack')
        self.assertEqual(repeated['payload'], {'message_id': mid, 'status': 'read', 'changed': False})

    async def test_receipt_ack_and_status_wait_for_commit_barrier(self):
        sender, recipient, mid = await self.pair()
        self.authority.receipt_hold = asyncio.Event()
        self.addCleanup(self.authority.receipt_hold.set)
        request = frame('message.received', {'message_id': mid}, conversation_id='direct-1')
        await recipient.send_json(request)
        await asyncio.wait_for(self.authority.receipt_entered.wait(), 2)
        await self.no_frame(recipient)
        await self.no_frame(sender)
        self.assertNotIn((mid, 'user-b'), self.authority.receipts)
        self.authority.receipt_hold.set()
        ack = await self.correlated(recipient, request)
        self.assertEqual(ack['event'], 'receipt.ack')
        self.assertEqual(ack['payload'], {'message_id': mid, 'status': 'delivered', 'changed': True})
        self.assertEqual((await self.event(sender, 'message.status'))['payload']['status'], 'delivered')

    async def test_direct_projection_uses_bb_time_id_public_actor_and_exact_observers(self):
        sender, recipient, mid = await self.pair()
        sender_other_device = await self.auth('access-a2')
        request, ack = await self.receipt(recipient, mid)
        self.assertEqual(ack['event'], 'receipt.ack')
        status = await self.event(sender, 'message.status')
        other_status = await self.event(sender_other_device, 'message.status')
        authoritative = self.authority.feed[-1]['envelope']
        self.assertEqual(status['event_id'], authoritative['event_id'])
        self.assertNotEqual(status['event_id'], request['event_id'])
        self.assertEqual(status['timestamp'], authoritative['timestamp'])
        self.assertEqual(other_status, status)
        self.assertEqual(status['payload'], {
            'kind': 'direct', 'message_id': mid, 'recipient_id': 'user-b',
            'status': 'read', 'updated_at': authoritative['timestamp']})
        self.assertEqual(set(status), {'event', 'event_id', 'timestamp', 'conversation_id', 'payload'})
        self.assertEqual(status['conversation_id'], 'direct-1')
        self.assertNotIn('private-', json.dumps(status))
        self.assertNotIn('device-', json.dumps(status))
        self.assertNotIn('client_message_id', json.dumps(status))
        await self.no_frame(recipient)
        operation, body = self.authority.requests[-1]
        self.assertEqual(operation, 'persistReceipt')
        self.assertEqual(body, {
            'subject_id': 'private-b', 'device_id': 'device-b', 'session_id': 'session-b',
            'session_generation': 1, 'conversation_id': 'direct-1',
            'message_id': mid, 'kind': 'read', 'request_event_id': request['event_id']})

    async def test_bb_observers_are_used_instead_of_guessed_sender_or_actor(self):
        sender, recipient, mid = await self.pair()
        self.authority.sessions['access-c'] = {
            'subject_id': 'private-c', 'user_id': 'user-c',
            'session_id': 'session-c', 'session_generation': 1}
        observer = await self.auth('access-c')
        # Grant the fixture's BB message permission to the explicitly selected
        # observer; W10 must reauthorize this M1, not only its conversation.
        self.authority.locate(mid)[1]['recipient_ids'].append('user-c')

        def choose_observer(operation, result):
            if operation == 'persistReceipt':
                result['observer_ids'] = ['user-c']
            return result

        self.authority.mutate_result = choose_observer
        _, ack = await self.receipt(recipient, mid)
        self.assertEqual(ack['event'], 'receipt.ack')
        status = await self.event(observer, 'message.status')
        self.assertEqual(status['payload']['recipient_id'], 'user-b')
        await self.no_frame(sender)
        await self.no_frame(recipient)

    async def test_retry_stable_status_event_does_not_duplicate_w10(self):
        sender, recipient, mid = await self.pair()
        request, ack = await self.receipt(recipient, mid, event='message.received')
        self.assertEqual(ack['event'], 'receipt.ack')
        status = await self.event(sender, 'message.status')

        def replay(operation, result):
            if operation == 'persistReceipt':
                result.update(status_event_id=status['event_id'], observer_ids=['user-a'])
            return result

        self.authority.mutate_result = replay
        await recipient.send_json(request)
        repeated = await self.correlated(recipient, request)
        self.assertEqual(repeated['event'], 'receipt.ack')
        self.assertEqual(repeated['payload'], {'message_id': mid, 'status': 'delivered', 'changed': False})
        await self.no_frame(sender)
        self.assertEqual(len([row for row in self.authority.feed if row['envelope']['event'] == 'message.status']), 1)

    async def test_no_change_with_null_event_still_acknowledges_authoritative_read(self):
        sender, recipient, mid = await self.pair()
        _, first = await self.receipt(recipient, mid)
        self.assertEqual(first['event'], 'receipt.ack')
        await self.event(sender, 'message.status')
        _, repeated = await self.receipt(recipient, mid, event='message.received')
        self.assertEqual(repeated['event'], 'receipt.ack')
        self.assertEqual(repeated['payload'], {'message_id': mid, 'status': 'read', 'changed': False})
        await self.no_frame(sender)

    async def test_group_receipts_ack_without_aggregate_status(self):
        sender, recipient, mid = await self.pair(conversation='group-1')
        for event, status, changed in [('message.read', 'read', True), ('message.received', 'read', False)]:
            _, ack = await self.receipt(recipient, mid, event=event, conversation='group-1')
            self.assertEqual(ack['event'], 'receipt.ack')
            self.assertEqual(ack['payload'], {'message_id': mid, 'status': status, 'changed': changed})
            await self.no_frame(sender)
            await self.no_frame(recipient)
        self.assertFalse(any(row['envelope']['event'] == 'message.status' for row in self.authority.feed))

    async def test_structurally_invalid_receipts_do_not_reach_write_authority(self):
        sender, recipient, mid = await self.pair()
        cases = [
            frame('message.read', {'message_id': mid}),
            frame('message.received', {'message_id': mid}, conversation_id=None),
            frame('message.read', {}, conversation_id='direct-1'),
            frame('message.read', {'message_id': 'not-a-uuid'}, conversation_id='direct-1'),
            frame('message.read', {'message_id': None}, conversation_id='direct-1'),
            frame('message.read', {'message_id': mid, 'recipient_id': 'user-a'}, conversation_id='direct-1'),
            frame('message.read', {'message_id': mid, 'client_message_id': str(uuid4())}, conversation_id='direct-1'),
            frame('message.read', {'message_id': mid}, conversation_id='direct-1', sender_id='user-a'),
            frame('message.read', {'message_id': mid}, conversation_id='direct-1', correlation_id=str(uuid4())),
            frame('message.read', {'message_id': mid}, conversation_id='direct-1', device_id='device-a'),
        ]
        for request in cases:
            with self.subTest(request=request):
                await recipient.send_json(request)
                reply = await self.correlated(recipient, request)
                self.assertEqual(reply['event'], 'error')
                self.assertEqual(reply['payload']['code'], 'INVALID_ARGUMENT')
        self.assertFalse(any(op == 'persistReceipt' for op, _ in self.authority.requests))
        self.assertEqual(self.authority.receipts, {})
        await self.no_frame(sender)
        await self.ping(recipient)

    async def test_bb_canonical_id_failure_does_not_become_a_receipt(self):
        sender, recipient, mid = await self.pair()
        _, reply = await self.receipt(recipient, mid, conversation='a' * 129)
        self.assertEqual(reply['event'], 'error')
        self.assertEqual(reply['payload']['code'], 'INVALID_ARGUMENT')
        self.assertEqual(self.authority.receipts, {})
        await self.no_frame(sender)

    async def test_incomplete_and_malformed_write_results_never_ack_or_publish(self):
        sender, recipient, mid = await self.pair()
        fields = ['message_id', 'status', 'changed', 'updated_at', 'status_event_id',
                  'invalidation_position', 'observer_ids', 'membership_version']
        mutations = [('missing-' + field, lambda value, field=field: value.pop(field)) for field in fields]
        bad_values = {
            'message_id': str(uuid4()), 'status': 'persisted', 'changed': 1,
            'updated_at': '2026-10-01T00:00:00', 'status_event_id': 'unstable',
            'invalidation_position': True, 'observer_ids': ['user-a', 'user-a'],
            'membership_version': 0}
        mutations += [('bad-' + key, lambda value, key=key, bad=bad: value.update({key: bad}))
                      for key, bad in bad_values.items()]
        mutations += [
            ('null-event-with-observer', lambda value: value.update(status_event_id=None, observer_ids=['user-a'])),
            ('empty-observer', lambda value: value.update(observer_ids=[''])),
            ('wrong-observer-type', lambda value: value.update(observer_ids='user-a')),
            ('group-status-event', lambda value: value.update(
                membership_version=1, status_event_id=str(uuid4()), observer_ids=['user-a'])),
            ('read-cannot-return-delivered', lambda value: value.update(status='delivered')),
        ]
        for name, mutation in mutations:
            def corrupt(operation, result, mutation=mutation):
                if operation == 'persistReceipt':
                    mutation(result)
                return result

            self.authority.mutate_result = corrupt
            with self.subTest(name=name):
                _, reply = await self.receipt(recipient, mid)
                self.assertEqual(reply['event'], 'error')
                self.assertEqual(reply['payload']['code'], 'OUTCOME_UNCONFIRMED')
                await self.no_frame(sender)
        self.authority.mutate_result = None
        await self.ping(recipient)

    async def test_refused_writes_produce_sanitized_c13_faults_without_ack(self):
        sender, recipient, mid = await self.pair()
        for code, http in [('INVALID_ARGUMENT', 400), ('FORBIDDEN', 403), ('NOT_FOUND', 404),
                           ('PERSISTENCE_FAILED', 503), ('OUTCOME_UNCONFIRMED', 503),
                           ('DEPENDENCY_UNAVAILABLE', 503)]:
            self.authority.faults['persistReceipt'] = (http, error(code, retryable=code.endswith('UNCONFIRMED')))
            _, reply = await self.receipt(recipient, mid)
            self.assertEqual(reply['event'], 'error')
            self.assertEqual(reply['payload']['code'], code)
            self.assertNotIn('private text', reply['payload']['message'])
            self.assertNotIn('details', reply['payload'])
            await self.no_frame(sender)
        self.assertEqual(self.authority.receipts, {})
        await self.ping(recipient)

    async def test_c13_service_identity_keeps_socket_user_session_fault_closes_it(self):
        sender, recipient, mid = await self.pair()
        for layer in ['service_identity', None]:
            self.authority.faults['persistReceipt'] = (401, error('UNAUTHENTICATED', layer))
            _, reply = await self.receipt(recipient, mid)
            self.assertEqual(reply['event'], 'error')
            self.assertEqual(reply['payload']['code'], 'DEPENDENCY_UNAVAILABLE')
            self.assertNotIn('auth_layer', reply['payload'])
            await self.ping(recipient)
        self.authority.faults['persistReceipt'] = (401, error('UNAUTHENTICATED', 'user_session'))
        _, reply = await self.receipt(recipient, mid)
        self.assertEqual(reply['event'], 'error')
        self.assertEqual(reply['payload']['code'], 'UNAUTHENTICATED')
        self.assertIn((await recipient.receive(timeout=2)).type,
                      {aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED})
        self.assertEqual(self.authority.receipts, {})
        await self.no_frame(sender)

    async def test_confirmed_ack_survives_actual_redis_publish_denial(self):
        from hine_realtime.server import RUNTIME

        sender, recipient, mid = await self.pair()
        runtime = self.app[RUNTIME]
        admin = Redis.from_url(self.env['REDIS_URL'], protocol=2)
        self.addAsyncCleanup(admin.aclose)
        username, password = 'receipt_' + uuid4().hex, uuid4().hex
        await admin.execute_command('ACL', 'SETUSER', username, 'on', '>' + password,
                                    '~*', '&*', '+@all', '-publish')
        self.addAsyncCleanup(admin.execute_command, 'ACL', 'DELUSER', username)
        parsed = urlsplit(self.env['REDIS_URL'])
        host = '[' + parsed.hostname + ']' if ':' in parsed.hostname else parsed.hostname
        url = urlunsplit((parsed.scheme, f'{username}:{password}@{host}:{parsed.port or 6379}',
                          parsed.path, parsed.query, parsed.fragment))
        restricted = Redis.from_url(url, protocol=2)
        self.addAsyncCleanup(restricted.aclose)
        original = runtime.redis
        runtime.redis = restricted
        try:
            _, ack = await self.receipt(recipient, mid)
            self.assertEqual(ack['event'], 'receipt.ack')
            self.assertEqual(ack['payload'], {'message_id': mid, 'status': 'read', 'changed': True})
            await self.no_frame(sender)
            self.assertEqual(self.authority.receipts[(mid, 'user-b')]['status'], 'read')
            authoritative = copy.deepcopy(self.authority.feed[-1]['envelope'])
            await admin.execute_command('ACL', 'SETUSER', username, '+publish')

            def committed_retry(operation, result):
                if operation == 'persistReceipt':
                    result.update(status_event_id=authoritative['event_id'], observer_ids=['user-a'])
                return result

            self.authority.mutate_result = committed_retry
            _, repeated = await self.receipt(recipient, mid)
            self.assertEqual(repeated['event'], 'receipt.ack')
            self.assertFalse(repeated['payload']['changed'])
            recovered = await self.event(sender, 'message.status')
            self.assertEqual(recovered['event_id'], authoritative['event_id'])
            await self.no_frame(sender)
        finally:
            runtime.redis = original
