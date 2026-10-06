"""W18 boundaries over actual HTTP/WS/Redis and a TEST-ONLY BB extension.

This fixture is not PostgreSQL/JWT product evidence. Mutations caught: routing to
noncontacts, device-close false offline, stale/queued authorization reuse, C13
misclassification, incomplete-page pruning, and unknown becoming false offline.
"""
import asyncio
import copy
import json
import time
from datetime import datetime
from uuid import UUID, uuid4

import aiohttp
from aiohttp import web
from receipt_sync_support import AddonAuthority, AddonHarness
from redis.asyncio import Redis
from test_realtime_boundaries import error, frame


class PresenceAuthority(AddonAuthority):
    """Only the existing test provider is extended; runtime never imports it."""

    def __init__(self):
        super().__init__()
        self.sessions['access-c'] = {'subject_id': 'private-c', 'user_id': 'user-c',
                                     'session_id': 'session-c', 'session_generation': 1}
        self.contacts = {'user-b': {'user-a': 'private-a'}}
        self.presence_requests = []
        self.presence_cursors = {}
        self.page_size = 100
        self.filtered_entered = asyncio.Event()
        self.filtered_release = None
        self.hold_filtered_once = False
        self.page_entered = asyncio.Event()
        self.page_release = None
        self.mutate_presence = None
        self.fault_subject = None
        self.device_entered = asyncio.Event()
        self.device_release = None
        self.remove_page_after_read = False

    async def handle(self, request):
        if request.match_info['operation'] != 'readPresenceTargets':
            return await super().handle(request)
        if request.headers.get('Authorization') != 'Bearer realtime-service-secret':
            return web.json_response(error('UNAUTHENTICATED', 'service_identity'), status=401)
        body = await request.json()
        self.presence_requests.append(copy.deepcopy(body))
        fault = self.faults.get('readPresenceTargets')
        if fault and (self.fault_subject is None or body.get('subject_id') == self.fault_subject):
            return web.json_response(fault[1], status=fault[0])
        required = {'subject_id', 'session_id', 'session_generation', 'limit'}
        if (not required <= body.keys() or not body.keys() <= required | {'cursor', 'contact_user_id'}
                or type(body['limit']) is not int or not 1 <= body['limit'] <= 100):
            return web.json_response(error('INVALID_ARGUMENT'), status=400)
        session = self.session(body)
        if session is None:
            return web.json_response(error('UNAUTHENTICATED', 'user_session'), status=401)
        owner = session['user_id']
        contact = body.get('contact_user_id')
        rows = sorted(self.contacts.get(owner, {}).items())
        if contact is not None:
            rows = [(user, subject) for user, subject in rows if user == contact]
        start = 0
        if 'cursor' in body:
            scope = self.presence_cursors.get(body['cursor'])
            if scope is None or scope[:2] != (owner, contact):
                return web.json_response(error('CURSOR_INVALID'), status=400)
            start = next((index for index, (user, _) in enumerate(rows) if user > scope[2]), len(rows))
        page = rows[start:start + min(body['limit'], self.page_size)]
        cursor = None
        if start + len(page) < len(rows):
            cursor = 'fixture-presence:' + uuid4().hex
            self.presence_cursors[cursor] = (owner, contact, page[-1][0])
        result = {'targets': [{'user_id': user, 'subject_id': subject} for user, subject in page],
                  'next_cursor': cursor, 'invalidation_position': self.head}
        if contact is None and self.remove_page_after_read:
            for user, _ in page:
                self.contacts[owner].pop(user, None)
        if self.mutate_presence is not None:
            result = self.mutate_presence(result, body)
        if contact is not None:
            self.filtered_entered.set()
            if self.hold_filtered_once:
                self.hold_filtered_once = False
                await self.filtered_release.wait()
        else:
            if body['subject_id'] == 'private-a' and body['limit'] == 1:
                self.device_entered.set()
                if self.device_release is not None:
                    await self.device_release.wait()
            self.page_entered.set()
            if self.page_release is not None:
                await self.page_release.wait()
        return web.json_response({'data': result})


class PresenceTests(AddonHarness):
    authority_type = PresenceAuthority

    def runtime(self):
        from hine_realtime.server import RUNTIME
        return self.app[RUNTIME]

    def connection(self, user):
        return next(connection for connection in self.runtime().connections
                    if connection.binding and connection.binding['user_id'] == user)

    async def presence(self, ws, user='user-a', state='online'):
        async with asyncio.timeout(8):
            while True:
                value = await ws.receive_json()
                if value['event'] != 'presence.changed':
                    continue
                self.assertEqual(value['payload'], {'user_id': user, 'presence': state})
                self.assertEqual(set(value), {'event', 'event_id', 'timestamp', 'payload'})
                UUID(value['event_id'])
                self.assertEqual(datetime.fromisoformat(value['timestamp'].replace('Z', '+00:00')).utcoffset().total_seconds(), 0)
                self.assertNotIn('private-', json.dumps(value))
                return value

    async def no_presence(self, ws, seconds=1.3):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                value = await ws.receive(timeout=deadline - time.monotonic())
            except asyncio.TimeoutError:
                return
            self.assertEqual(value.type, aiohttp.WSMsgType.TEXT)
            self.assertNotEqual(json.loads(value.data)['event'], 'presence.changed')

    async def heartbeat(self, ws):
        request = frame('heartbeat.ping', {'nonce': 'presence-control:' + uuid4().hex})
        await ws.send_json(request)
        reply = await self.correlated(ws, request)
        self.assertEqual(reply['event'], 'heartbeat.pong')
        self.assertEqual(reply['payload'], request['payload'])

    async def device_presence(self, subject, device):
        async with self.client.post(self.url + '/internal/v1/getDevicePresence',
                                    json={'subject_id': subject, 'device_id': device},
                                    headers={'Authorization': 'Bearer api-service-secret'}) as response:
            self.assertEqual(response.status, 200)
            return (await response.json())['data']

    async def unavailable_redis(self):
        runtime = self.runtime()
        previous = runtime.redis
        failed = Redis.from_url('redis://127.0.0.1:1/0', socket_connect_timeout=.1,
                                socket_timeout=.1, protocol=2)
        runtime.redis = failed

        async def restore():
            runtime.redis = previous
            await failed.aclose()

        self.addAsyncCleanup(restore)

    async def test_allowed_contact_initial_transition_and_noncontact_silence(self):
        target = await self.auth('access-a')
        observer = await self.auth('access-b')
        outsider = await self.auth('access-c')
        await self.presence(observer)
        await self.no_presence(outsider)
        await target.close()
        await self.presence(observer, state='offline')
        await self.no_presence(outsider)
        await self.no_presence(observer)

    async def test_one_closed_device_keeps_full_user_online(self):
        first = await self.auth('access-a')
        second = await self.auth('access-a2')
        observer = await self.auth('access-b')
        await self.presence(observer)
        await first.close()
        self.assertEqual((await self.device_presence('private-a', 'device-a'))['online'], 'offline')
        self.assertEqual((await self.device_presence('private-a', 'device-a2'))['online'], 'online')
        await self.no_presence(observer)
        await second.close()
        await self.presence(observer, state='offline')

    async def test_new_contact_gets_initial_state_even_without_presence_transition(self):
        await self.auth('access-a')
        observer = await self.auth('access-c')
        await self.no_presence(observer)
        self.authority.contacts['user-c'] = {'user-a': 'private-a'}
        await self.presence(observer)
        del self.authority.contacts['user-c']['user-a']
        await self.no_presence(observer)
        self.authority.contacts['user-c']['user-a'] = 'private-a'
        await self.presence(observer)

    async def test_redis_failure_is_unknown_not_false_offline(self):
        await self.auth('access-a')
        observer = await self.auth('access-b')
        await self.presence(observer)
        await self.unavailable_redis()
        await self.presence(observer, state='unknown')
        self.assertEqual(await self.device_presence('private-a', 'device-a'),
                         {'online': 'unknown', 'activity': 'unknown', 'valid_until': None})
        await self.heartbeat(observer)

    async def test_stale_node_suppresses_w18_but_keeps_control_frames(self):
        await self.auth('access-a')
        observer = await self.auth('access-b')
        await self.presence(observer)
        self.authority.fail_poll = True
        async with asyncio.timeout(5):
            while self.runtime().invalidations.fresh():
                await asyncio.sleep(.02)
        await self.unavailable_redis()
        await self.no_presence(observer)
        await self.heartbeat(observer)
        self.assertEqual((await self.device_presence('private-a', 'device-a'))['online'], 'unknown')

    async def test_current_session_revocation_suppresses_queued_w18(self):
        await self.auth('access-a')
        observer = await self.auth('access-b')
        await self.presence(observer)
        connection = self.connection('user-b')
        await connection.write_lock.acquire()
        try:
            await self.unavailable_redis()
            async with asyncio.timeout(4):
                while not connection.queue.empty() or not self.authority.presence_requests:
                    await asyncio.sleep(.02)
                await asyncio.sleep(1.2)
            self.authority.invalidate('session-b')
            async with asyncio.timeout(5):
                while not connection.invalid:
                    await asyncio.sleep(.02)
        finally:
            connection.write_lock.release()
        while True:
            message = await observer.receive(timeout=3)
            if message.type != aiohttp.WSMsgType.TEXT:
                self.assertIn(message.type, {aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED})
                break
            self.assertNotEqual(json.loads(message.data)['event'], 'presence.changed')

    async def test_contact_removal_during_socket_lock_wait_denies_old_allowed_read(self):
        await self.auth('access-a')
        observer = await self.auth('access-b')
        await self.presence(observer)
        connection = self.connection('user-b')
        await connection.write_lock.acquire()
        try:
            await self.unavailable_redis()
            await asyncio.sleep(1.2)
            self.authority.contacts['user-b'].clear()
        finally:
            connection.write_lock.release()
        await self.no_presence(observer)
        await self.heartbeat(observer)

    async def test_contact_removal_after_page_allowed_before_delivery_is_rechecked(self):
        await self.auth('access-a')
        observer = await self.auth('access-b')
        await self.presence(observer)
        self.authority.page_entered.clear()
        self.authority.page_release = asyncio.Event()
        await self.unavailable_redis()
        await asyncio.wait_for(self.authority.page_entered.wait(), 4)
        self.authority.contacts['user-b'].clear()
        self.authority.page_release.set()
        await self.no_presence(observer)

    async def test_final_authorization_expiring_during_http_wait_cannot_start_w18(self):
        await self.auth('access-a')
        observer = await self.auth('access-b')
        await self.presence(observer)
        self.authority.filtered_entered.clear()
        self.authority.filtered_release = asyncio.Event()
        self.authority.hold_filtered_once = True
        await self.unavailable_redis()
        await asyncio.wait_for(self.authority.filtered_entered.wait(), 4)
        connection = self.connection('user-b')
        connection.binding['expires_monotonic'] = time.monotonic() - 1
        connection.binding['expires_unix'] = time.time() - 1
        self.authority.filtered_release.set()
        while True:
            message = await observer.receive(timeout=3)
            if message.type != aiohttp.WSMsgType.TEXT:
                break
            self.assertNotEqual(json.loads(message.data)['event'], 'presence.changed')

    async def test_service_auth_failure_is_dependency_not_user_logout(self):
        await self.auth('access-a')
        observer = await self.auth('access-b')
        await self.presence(observer)
        self.authority.faults['readPresenceTargets'] = (401, error('UNAUTHENTICATED', 'service_identity'))
        await self.unavailable_redis()
        await self.no_presence(observer)
        await self.heartbeat(observer)
        self.assertFalse(observer.closed)
        self.assertEqual((await self.device_presence('private-a', 'device-a'))['online'], 'unknown')

    async def test_trusted_user_session_failure_closes_only_matching_binding(self):
        await self.auth('access-a')
        observer = await self.auth('access-b')
        await self.presence(observer)
        self.authority.invalidate('session-b')
        while True:
            message = await observer.receive(timeout=5)
            if message.type != aiohttp.WSMsgType.TEXT:
                break
            self.assertNotEqual(json.loads(message.data)['event'], 'presence.changed')
        self.assertTrue(self.connection('user-a').valid())

    async def test_paginated_contacts_complete_without_pruning_other_pages(self):
        self.authority.page_size = 1
        self.authority.contacts['user-b']['user-c'] = 'private-c'
        await self.auth('access-a')
        await self.auth('access-c')
        observer = await self.auth('access-b')
        seen = set()
        async with asyncio.timeout(8):
            while len(seen) < 2:
                value = await observer.receive_json()
                if value['event'] == 'presence.changed':
                    self.assertEqual(value['payload']['presence'], 'online')
                    seen.add(value['payload']['user_id'])
        self.assertEqual(seen, {'user-a', 'user-c'})
        await self.no_presence(observer, 2.3)
        self.assertTrue(any('cursor' in body for body in self.authority.presence_requests))

    async def test_malformed_or_wrong_filtered_target_never_leaks_presence(self):
        self.authority.mutate_presence = lambda result, body: (
            {**result, 'targets': [{'user_id': 'user-c', 'subject_id': 'private-c'}]}
            if 'contact_user_id' in body else result)
        await self.auth('access-a')
        observer = await self.auth('access-b')
        await self.no_presence(observer)
        await self.heartbeat(observer)

    async def test_device_provider_checks_service_before_body_and_not_canonical_length(self):
        async with self.client.post(self.url + '/internal/v1/getDevicePresence', data='not-json',
                                    headers={'Authorization': 'Bearer wrong'}) as response:
            self.assertEqual(response.status, 401)
            self.assertEqual((await response.json())['error']['details'], {'auth_layer': 'service_identity'})
        self.assertEqual((await self.device_presence('x' * 129, 'missing'))['online'], 'offline')

    async def test_missing_catchup_authority_never_reports_offline(self):
        self.authority.fail_poll = True
        self.assertEqual((await self.device_presence('private-a', 'device-a'))['online'], 'unknown')

    async def test_single_frame_output_limit_still_delivers_authorized_presence(self):
        from dataclasses import replace
        self.runtime().settings = replace(self.runtime().settings, max_outgoing_frames=1)
        await self.auth('access-a')
        observer = await self.auth('access-b')
        await self.presence(observer)
        await self.heartbeat(observer)

    async def test_private_presence_c13_user_failure_closes_only_its_observer(self):
        target = await self.auth('access-a')
        observer = await self.auth('access-b')
        await self.presence(observer)
        self.authority.fault_subject = 'private-b'
        self.authority.faults['readPresenceTargets'] = (401, error('UNAUTHENTICATED', 'user_session'))
        saw_error = False
        async with asyncio.timeout(5):
            while True:
                message = await observer.receive()
                if message.type != aiohttp.WSMsgType.TEXT:
                    break
                value = json.loads(message.data)
                self.assertNotEqual(value['event'], 'presence.changed')
                if value['event'] == 'error':
                    self.assertEqual(value['payload']['code'], 'UNAUTHENTICATED')
                    saw_error = True
        self.assertTrue(saw_error)
        await self.heartbeat(target)

    async def test_partial_contact_page_failure_does_not_repeat_prior_initial_state(self):
        self.authority.page_size = 1
        self.authority.contacts['user-b']['user-c'] = 'private-c'
        await self.auth('access-a')
        await self.auth('access-c')
        observer = await self.auth('access-b')
        await self.presence(observer)
        self.authority.fault_subject = 'private-b'
        self.authority.faults['readPresenceTargets'] = (503, error('DEPENDENCY_UNAVAILABLE', retryable=True))
        await self.no_presence(observer)
        self.authority.faults.pop('readPresenceTargets')
        await self.presence(observer, user='user-c')
        await self.no_presence(observer, 2.3)

    async def test_redis_failure_during_initial_filtered_authority_wait_is_unknown(self):
        await self.auth('access-a')
        self.authority.filtered_release = asyncio.Event()
        self.authority.hold_filtered_once = True
        observer = await self.auth('access-b')
        await asyncio.wait_for(self.authority.filtered_entered.wait(), 4)
        try:
            await self.unavailable_redis()
        finally:
            self.authority.filtered_release.set()
        await self.presence(observer, state='unknown')
        await self.heartbeat(observer)

    async def test_device_redis_failure_during_initial_c2_wait_is_unknown(self):
        await self.auth('access-a')
        self.authority.device_release = asyncio.Event()
        request = asyncio.create_task(self.device_presence('private-a', 'device-a'))
        try:
            await asyncio.wait_for(self.authority.device_entered.wait(), 3)
            await self.unavailable_redis()
        finally:
            self.authority.device_release.set()
        self.assertEqual((await request)['online'], 'unknown')

    async def test_byte_limited_multi_contact_snapshot_is_paced_not_disconnected(self):
        from dataclasses import replace
        self.runtime().settings = replace(self.runtime().settings, max_outgoing_bytes=600)
        self.authority.contacts['user-b'].update({'user-c': 'private-c',
                                                 'user-d': 'private-d', 'user-e': 'private-e'})
        observer = await self.auth('access-b')
        received = set()
        async with asyncio.timeout(8):
            while len(received) < 4:
                value = await observer.receive_json()
                if value['event'] == 'presence.changed':
                    self.assertEqual(value['payload']['presence'], 'offline')
                    received.add(value['payload']['user_id'])
        self.assertEqual(received, {'user-a', 'user-c', 'user-d', 'user-e'})
        await self.heartbeat(observer)
        self.assertFalse(observer.closed)

    async def test_paginated_contact_removal_bounds_all_retained_scan_ids(self):
        import contextlib
        runtime = self.runtime()
        task = runtime.tasks[-1]
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        self.authority.contacts['user-b'] = {
            f'user-churn-{index:05d}': f'private-churn-{index:05d}' for index in range(4097)}
        self.authority.remove_page_after_read = True
        observer = await self.auth('access-b')
        connection = self.connection('user-b')
        async with asyncio.timeout(25):
            for _ in range(42):
                await runtime.presence.poll_observer(connection, bool(await runtime.redis.ping()))
                state = runtime.presence.observers[connection]
                async with asyncio.timeout(3):
                    while state.pending and not connection.invalid:
                        await asyncio.sleep(.001)
                retained = set(state.contacts) | state.seen | set(state.pending) | set(state.delivered)
                self.assertLessEqual(len(retained), 4096)
                if connection.invalid:
                    break
        self.assertTrue(connection.invalid)
        async with asyncio.timeout(3):
            while True:
                message = await observer.receive()
                if message.type != aiohttp.WSMsgType.TEXT:
                    self.assertIn(message.type, {aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED})
                    break
                self.assertNotEqual(json.loads(message.data)['event'], 'presence.changed')

    async def test_individually_oversized_presence_uses_resource_cleanup_not_permanent_deferral(self):
        from dataclasses import replace
        self.runtime().settings = replace(self.runtime().settings, max_outgoing_bytes=600)
        self.authority.contacts['user-b'] = {'\U00010000' * 128: 'private-d'}
        unaffected = await self.auth('access-a')
        observer = await self.auth('access-b')
        saw_dependency = False
        async with asyncio.timeout(5):
            while True:
                message = await observer.receive()
                if message.type != aiohttp.WSMsgType.TEXT:
                    self.assertIn(message.type, {aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED})
                    break
                value = json.loads(message.data)
                self.assertNotEqual(value['event'], 'presence.changed')
                if value['event'] == 'error':
                    self.assertEqual(value['payload']['code'], 'DEPENDENCY_UNAVAILABLE')
                    saw_dependency = True
        self.assertTrue(saw_dependency)
        await self.heartbeat(unaffected)
