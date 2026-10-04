"""Test-only stateful BB extension; no PostgreSQL/JWT/browser/product fallback."""
import asyncio
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

import aiohttp
from aiohttp import web
from test_realtime_boundaries import TestAuthority, error, frame, serve, timestamp


class AddonAuthority(TestAuthority):
    def __init__(self):
        super().__init__()
        self.receipts = {}
        self.feed = []
        self.snapshots = {}
        self.receipt_hold = self.read_hold = None
        self.receipt_entered = asyncio.Event()
        self.read_entered = asyncio.Event()
        self.requests = []

    def session(self, body):
        return next((s for s in self.sessions.values() if s['subject_id'] == body.get('subject_id')
                     and s['session_id'] == body.get('session_id')
                     and s['session_generation'] == body.get('session_generation')
                     and not self.invalid(s)), None)

    def locate(self, mid):
        return next(((key, value) for key, value in self.messages.items() if value['message_id'] == mid), None)

    def sender(self, subject):
        return next(s['user_id'] for s in self.sessions.values() if s['subject_id'] == subject)

    def view(self, key, saved, viewer):
        sender = self.sender(key[0])
        receipt = None
        if saved['membership_version'] is None:
            receipt = next((copy.deepcopy(value) for (mid, _), value in self.receipts.items()
                            if mid == saved['message_id']), None)
        result = {'id': saved['message_id'], 'event_id': saved['event_id'],
                  'conversation_id': saved['conversation_id'], 'sender_id': sender,
                  'created_at': saved['created_at'], 'order_key': saved['order_key'],
                  'type': 'text', 'text': saved['text'], 'receipt': receipt}
        if viewer == sender:
            result['client_message_id'] = key[1]
        return result

    def append_message(self, body, saved):
        if any(row['envelope']['event_id'] == saved['event_id'] for row in self.feed):
            return
        sender = self.sender(body['subject_id'])
        payload = {'message_id': saved['message_id'], 'client_message_id': body['client_message_id'],
                   'type': 'text', 'text': body['payload']['text'], 'order_key': saved['order_key']}
        self.feed.append({'recipients': saved['recipient_ids'], 'envelope': frame('message.created', payload,
                          conversation_id=body['conversation_id'], sender_id=sender,
                          event_id=saved['event_id'], timestamp=saved['created_at'])})

    async def handle(self, request):
        operation = request.match_info['operation']
        body = await request.json()
        if operation not in {'persistReceipt', 'readBootstrap', 'readFeed'}:
            response = await super().handle(request)
            if operation == 'persistIfAbsent' and response.status == 200:
                saved = json.loads(response.text)['data']
                self.append_message(body, saved)
            return response
        if request.headers.get('Authorization') != 'Bearer realtime-service-secret':
            return web.json_response(error('UNAUTHENTICATED', 'service_identity'), status=401)
        self.requests.append((operation, copy.deepcopy(body)))
        if operation in self.faults:
            status, data = self.faults[operation]
            return web.json_response(data, status=status)
        session = self.session(body)
        if session is None:
            return web.json_response(error('UNAUTHENTICATED', 'user_session'), status=401)
        viewer = session['user_id']
        if operation == 'persistReceipt':
            located = self.locate(body.get('message_id'))
            if located is None or located[1]['conversation_id'] != body.get('conversation_id'):
                return web.json_response(error('NOT_FOUND'), status=404)
            key, message = located
            if viewer == self.sender(key[0]) or not self.may_receive(viewer, 'message', message['message_id']):
                return web.json_response(error('FORBIDDEN'), status=403)
            self.receipt_entered.set()
            if self.receipt_hold is not None:
                await self.receipt_hold.wait()
            previous = self.receipts.get((message['message_id'], viewer))
            desired = body['kind']
            status = 'read' if desired == 'read' or (previous and previous['status'] == 'read') else 'delivered'
            changed = previous is None or previous['status'] != status
            updated = timestamp() if changed else previous['updated_at']
            projection = {'kind': 'direct', 'message_id': message['message_id'], 'recipient_id': viewer,
                          'status': status, 'updated_at': updated}
            self.receipts[(message['message_id'], viewer)] = projection
            direct = message['membership_version'] is None
            eid = str(uuid4()) if changed and direct else None
            observers = [self.sender(key[0])] if eid else []
            if eid:
                self.feed.append({'recipients': observers, 'envelope': frame('message.status', projection,
                    conversation_id=message['conversation_id'], event_id=eid, timestamp=updated)})
            result = {'message_id': message['message_id'], 'status': status, 'changed': changed,
                      'updated_at': updated, 'status_event_id': eid, 'invalidation_position': self.head,
                      'observer_ids': observers, 'membership_version': message['membership_version']}
        elif operation == 'readBootstrap':
            if ('snapshot_id' in body) != ('page_token' in body):
                return web.json_response(error('INVALID_ARGUMENT'), status=400)
            if 'snapshot_id' not in body:
                sid = 'snapshot-' + uuid4().hex
                rows = []
                for conversation in ['direct-1', *self.group_members]:
                    if not self.may_receive(viewer, 'conversation', conversation):
                        continue
                    messages = [self.view(key, saved, viewer) for key, saved in self.messages.items()
                                if saved['conversation_id'] == conversation and self.may_receive(viewer, 'message', saved['message_id'])]
                    rows.append({'id': conversation, 'type': 'direct' if conversation == 'direct-1' else 'group',
                                 'title': None if conversation == 'direct-1' else 'Fixture group',
                                 'unread_count': 0, 'my_role': None if conversation == 'direct-1' else 'member',
                                 'recent_messages': messages})
                self.snapshots[sid] = (viewer, copy.deepcopy(rows), 'cursor:' + str(len(self.feed)))
            else:
                sid = body['snapshot_id']
            if sid not in self.snapshots or self.snapshots[sid][0] != viewer:
                return web.json_response(error('SYNC_RESET_REQUIRED'), status=410)
            _, rows, cursor = self.snapshots[sid]
            result = {'snapshot_id': sid, 'start_cursor': cursor, 'conversations': copy.deepcopy(rows),
                      'next_page_token': None, 'has_more': False}
        else:
            try:
                cursor = int(body['cursor'].removeprefix('cursor:'))
                boundary = int(body.get('snapshot_boundary', 'cursor:' + str(len(self.feed))).removeprefix('cursor:'))
                if not 0 <= cursor <= boundary <= len(self.feed):
                    raise ValueError
            except (KeyError, ValueError, AttributeError):
                return web.json_response(error('SYNC_RESET_REQUIRED'), status=410)
            end = min(boundary, cursor + body['limit'])
            events = []
            for row in self.feed[cursor:end]:
                value = copy.deepcopy(row['envelope'])
                if viewer not in row['recipients']:
                    continue
                resource = value['payload'].get('message_id', value['conversation_id'])
                resource_type = 'message' if 'message_id' in value['payload'] else 'conversation'
                if not self.may_receive(viewer, resource_type, resource):
                    continue
                if value['event'] == 'message.created' and value['sender_id'] != viewer:
                    value['payload'].pop('client_message_id', None)
                events.append(value)
            result = {'snapshot_boundary': 'cursor:' + str(boundary), 'events': events,
                      'next_cursor': 'cursor:' + str(end), 'has_more': end < boundary}
        if self.mutate_result:
            result = self.mutate_result(operation, result)
        if operation in {'readBootstrap', 'readFeed'}:
            self.read_entered.set()
            if self.read_hold is not None:
                await self.read_hold.wait()
        return web.json_response({'data': result})


class AddonHarness(unittest.IsolatedAsyncioTestCase):
    authority_type = AddonAuthority

    async def asyncSetUp(self):
        from hine_realtime.config import Settings
        from hine_realtime.server import create_app
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        path = Path(self.temp.name)
        (path / 'outbound').write_text('realtime-service-secret')
        (path / 'inbound').write_text('api-service-secret')
        self.client = aiohttp.ClientSession()
        self.addAsyncCleanup(self.client.close)
        self.authority = self.authority_type()
        runner, self.bb_url = await serve(self.authority.app())
        self.addAsyncCleanup(runner.cleanup)
        self.env = {'HINE_ENV': 'test', 'API_INTERNAL_URL': self.bb_url,
                    'INTERNAL_CALLER_TOKEN_SECRET_REF': str(path / 'outbound'),
                    'INTERNAL_ALLOWED_CALLERS': json.dumps({'api': str(path / 'inbound')}),
                    'REDIS_URL': os.environ.get('HINE_TEST_REDIS_URL', 'redis://127.0.0.1:6397/0'),
                    'REALTIME_REDIS_PREFIX': 'addon-test:' + uuid4().hex, 'SYNC_PAGE_LIMIT': '100',
                    'INVALIDATION_POLL_SECONDS': '1', 'INVALIDATION_STALE_SECONDS': '3',
                    'NOTICE_CATCHUP_HOLD_MS': '1000', 'HEARTBEAT_INTERVAL_SECONDS': '30', 'HEARTBEAT_TIMEOUT_SECONDS': '90'}
        self.app = create_app(Settings.from_env(self.env))
        runner, self.url = await serve(self.app)
        self.addAsyncCleanup(runner.cleanup)
        async with asyncio.timeout(5):
            while True:
                async with self.client.get(self.url + '/health/ready') as response:
                    if response.status == 200:
                        break
                await asyncio.sleep(.02)

    async def auth(self, token):
        ws = await self.client.ws_connect(self.url + '/ws/v1')
        self.addAsyncCleanup(ws.close)
        await ws.send_json(frame('auth.authenticate', {'access_token': token, 'device_id': token.replace('access', 'device')}))
        accepted = await ws.receive_json(timeout=3)
        self.assertEqual(accepted['event'], 'auth.accepted')
        return ws

    async def correlated(self, ws, request):
        async with asyncio.timeout(5):
            while True:
                value = await ws.receive_json()
                if value.get('correlation_id') == request['event_id']:
                    return value

    async def send(self, ws, text='fixture text', conversation='direct-1'):
        request = frame('message.send', {'client_message_id': str(uuid4()), 'type': 'text', 'text': text}, conversation_id=conversation)
        await ws.send_json(request)
        ack = await self.correlated(ws, request)
        self.assertEqual(ack['event'], 'message.ack')
        return ack['payload']['message_id']
