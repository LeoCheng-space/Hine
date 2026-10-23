"""SEC-03 negative tests: cross-account, non-member, removed and rejoined access.

Three isolated accounts (A creator/admin, B member, C outsider) with group G={A,B}
and the direct conversation A-B. REST and internal checks run against the real native
API and PostgreSQL; WSS checks go through the real BA, Redis and the same API.
"""
import asyncio
import secrets
import uuid
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import datetime, timezone

from support import ProductCase
from test_attachments import PNG, PNG_SHA, signing_fixture
from test_domain import DomainConsumer

BINDING_FIELDS = ('subject_id', 'device_id', 'session_id', 'session_generation')


def frame(event, payload, conversation=None):
    result = {'event': event, 'event_id': str(uuid.uuid4()),
              'timestamp': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'), 'payload': payload}
    if conversation is not None:
        result['conversation_id'] = conversation
    return result


class Wire:
    """One authenticated BA socket; every received frame is retained for leak assertions."""
    def __init__(self, socket):
        self.socket = socket
        self.frames = []

    async def read_until(self, match, timeout=10):
        async with asyncio.timeout(timeout):
            while True:
                value = await self.socket.receive_json()
                self.frames.append(value)
                if match(value):
                    return value

    async def call(self, event, payload, conversation=None):
        request = frame(event, payload, conversation)
        await self.socket.send_json(request)
        return await self.read_until(lambda value: value.get('correlation_id') == request['event_id'])

    def of(self, event, **payload):
        return [value for value in self.frames if value['event'] == event
                and all(value['payload'].get(k) == v for k, v in payload.items())]


class AuthorizationCase(DomainConsumer, ProductCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        _, settings = signing_fixture(self.api.temp.name)
        self.api.settings_env.update(GCS_BUCKET=settings.gcs_bucket,
                                     GCS_CREDENTIALS_SECRET_REF=settings.gcs_credentials_file,
                                     UPLOAD_MAX_BYTES="10485760")
        await self.api.restart()
        self.alice, self.a = await self.account('alice')
        self.bob, self.b = await self.account('bob')
        self.carol, self.c = await self.account('carol')
        self.direct = await self.create_direct(self.a, self.bob)
        self.group = await self.create_group(self.a, [self.bob])
        self.binding = await self.api.binding(self.a)

    # ---- construction helpers -------------------------------------------------
    async def create_direct(self, access, peer):
        status, result = await self.request('POST', '/api/v1/conversations/direct', access,
                                            json={'peer_user_id': peer['id']})
        self.assertEqual(status, 201, result)
        return result['data']['id']

    async def create_group(self, access, members, title='Group G', key=None):
        status, result = await self.request('POST', '/api/v1/conversations/groups', access,
            json={'title': title, 'member_ids': [member['id'] for member in members]},
            headers={'Idempotency-Key': key or str(uuid.uuid4())})
        self.assertEqual(status, 201, result)
        return result['data']['id']

    async def add_member(self, access, cid, user):
        status, result = await self.request('POST', f'/api/v1/conversations/{cid}/members', access,
            json={'user_id': user['id']}, headers={'Idempotency-Key': str(uuid.uuid4())})
        self.assertEqual(status, 201, result)

    async def remove_member(self, access, cid, user):
        status, result = await self.request('DELETE', f'/api/v1/conversations/{cid}/members/{user["id"]}', access)
        self.assertEqual(status, 204, result)

    async def attachment(self, access, scope='conversation', conversation=None, ready=True):
        status, result = await self.request('POST', '/api/v1/uploads', access, json={
            'scope': scope, 'conversation_id': conversation if scope == 'conversation' else None,
            'filename': 'tiny.png', 'content_type': 'image/png', 'size_bytes': len(PNG), 'sha256': PNG_SHA},
            headers={'Idempotency-Key': secrets.token_urlsafe(20)})
        self.assertEqual(status, 201, result)
        aid = result['data']['attachment_id']
        if ready:
            async with self.runtime.pool.acquire() as conn:
                await conn.execute("UPDATE attachments SET state='ready',generation='1029',metageneration='4' WHERE attachment_id=$1", aid)
        return aid

    async def send_image(self, aid, conversation, access=None):
        binding = self.binding if access is None else await self.api.binding(access)
        status, result = await self.api.internal('persistIfAbsent', {
            **{k: binding[k] for k in BINDING_FIELDS}, 'conversation_id': conversation,
            'client_message_id': str(uuid.uuid4()), 'request_event_id': str(uuid.uuid4()),
            'type': 'image', 'payload': {'attachment_id': aid}})
        self.assertEqual(status, 200, result)
        return result['data']

    async def authorize(self, access, action, kind, resource_id):
        binding = await self.api.binding(access)
        return await self.api.internal('authorize', {**{k: binding[k] for k in BINDING_FIELDS},
            'action': action, 'resource_type': kind, 'resource_id': resource_id})

    # ---- assertion helpers ----------------------------------------------------
    async def snapshot(self):
        """Every table a rejected mutation could touch, as comparable plain values."""
        async with self.runtime.pool.acquire() as conn:
            return {
                'conversations': [tuple(r) for r in await conn.fetch(
                    'SELECT conversation_id,type,title,membership_version FROM conversations ORDER BY 1')],
                'memberships': [tuple(r) for r in await conn.fetch(
                    'SELECT conversation_id,user_id,role,active,joined_version FROM memberships ORDER BY 1,2')],
                'feed': await conn.fetchval('SELECT count(*) FROM user_feed'),
                'messages': await conn.fetchval('SELECT count(*) FROM messages'),
                'receipts': await conn.fetchval('SELECT count(*) FROM receipts'),
                'attachments': await conn.fetchval('SELECT count(*) FROM attachments'),
                'avatars': [tuple(r) for r in await conn.fetch('SELECT user_id,avatar_attachment_id FROM users ORDER BY 1')],
            }

    async def deny(self, method, path, access, status, code, json=None, headers=None):
        actual, result = await self.request(method, path, access, json=json, headers=headers)
        self.assertEqual((actual, result['error']['code']), (status, code), (method, path, result))

    async def read_ok(self, path, access):
        status, result = await self.request('GET', path, access)
        self.assertEqual(status, 200, result)
        return result


class AuthorizationRestTests(AuthorizationCase):
    async def test_a11_a12_conversation_list_and_detail_never_reveal_foreign_conversations(self):
        unknown = str(uuid.uuid4())
        for cid in (self.group, self.direct, unknown):
            with self.subTest(route='detail', conversation=cid):
                await self.deny('GET', f'/api/v1/conversations/{cid}', self.c, 404, 'NOT_FOUND')
        listing = await self.read_ok('/api/v1/conversations', self.c)
        self.assertEqual(listing['data']['items'], [])
        # A's own cursor cannot be replayed by C.
        page = await self.read_ok('/api/v1/conversations?limit=1', self.a)
        cursor = page['meta']['next_cursor']
        self.assertIsNotNone(cursor)
        await self.deny('GET', '/api/v1/conversations?cursor=' + cursor, self.c, 400, 'CURSOR_INVALID')
        # Control: B is listed in both until removed from G.
        before = await self.read_ok('/api/v1/conversations', self.b)
        self.assertEqual({item['id'] for item in before['data']['items']}, {self.group, self.direct})
        await self.remove_member(self.a, self.group, self.bob)
        await self.deny('GET', f'/api/v1/conversations/{self.group}', self.b, 404, 'NOT_FOUND')
        after = await self.read_ok('/api/v1/conversations', self.b)
        self.assertEqual([item['id'] for item in after['data']['items']], [self.direct])
        await self.read_ok(f'/api/v1/conversations/{self.direct}', self.b)

    async def test_a19_history_denies_outsider_removed_foreign_and_cross_conversation_cursors(self):
        for text in ('g1', 'g2'):
            await self.send(text, conversation=self.group)
        for text in ('d1', 'd2'):
            await self.send(text, conversation=self.direct)
        group_page = await self.read_ok(f'/api/v1/conversations/{self.group}/messages?limit=1', self.b)
        group_cursor = group_page['meta']['next_cursor']
        direct_page = await self.read_ok(f'/api/v1/conversations/{self.direct}/messages?limit=1', self.b)
        self.assertIsNotNone(direct_page['meta']['next_cursor'])
        base = f'/api/v1/conversations/{self.group}/messages'
        await self.deny('GET', base, self.c, 404, 'NOT_FOUND')
        # Membership is checked before the cursor, so B's valid cursor gives C nothing either.
        await self.deny('GET', f'{base}?before={group_cursor}', self.c, 404, 'NOT_FOUND')
        await self.deny('GET', f'/api/v1/conversations/{self.direct}/messages', self.c, 404, 'NOT_FOUND')
        await self.deny('GET', f'/api/v1/conversations/{uuid.uuid4()}/messages', self.c, 404, 'NOT_FOUND')
        # B is a member of both but a cursor minted for G is not valid on the direct conversation.
        await self.deny('GET', f'/api/v1/conversations/{self.direct}/messages?before={group_cursor}',
                        self.b, 400, 'CURSOR_INVALID')
        await self.remove_member(self.a, self.group, self.bob)
        await self.deny('GET', base, self.b, 404, 'NOT_FOUND')

    async def test_a15_rename_requires_current_group_admin_and_changes_nothing_when_denied(self):
        before = await self.snapshot()
        path = f'/api/v1/conversations/{self.group}'
        for access, label in ((self.c, 'outsider'), (self.b, 'plain member')):
            with self.subTest(actor=label):
                await self.deny('PATCH', path, access, 403, 'FORBIDDEN', json={'title': 'hijacked'})
        with self.subTest(actor='admin on direct'):
            await self.deny('PATCH', f'/api/v1/conversations/{self.direct}', self.a, 403, 'FORBIDDEN',
                            json={'title': 'hijacked'})
        with self.subTest(actor='unknown conversation'):
            await self.deny('PATCH', f'/api/v1/conversations/{uuid.uuid4()}', self.a, 404, 'NOT_FOUND',
                            json={'title': 'hijacked'})
        self.assertEqual(await self.snapshot(), before)
        # A removed ex-admin loses the right immediately.
        status, _ = await self.request('PATCH', f'/api/v1/conversations/{self.group}/members/{self.bob["id"]}',
                                       self.a, json={'role': 'admin'})
        self.assertEqual(status, 200)
        await self.remove_member(self.a, self.group, self.bob)
        removed = await self.snapshot()
        await self.deny('PATCH', path, self.b, 403, 'FORBIDDEN', json={'title': 'hijacked'})
        self.assertEqual(await self.snapshot(), removed)

    async def test_a16_a17_role_escalation_denied_including_rejoined_ex_admin(self):
        before = await self.snapshot()
        group = f'/api/v1/conversations/{self.group}'
        member_path = lambda user: f'{group}/members/{user["id"]}'
        headers = {'Idempotency-Key': str(uuid.uuid4())}
        checks = [
            ('member promotes self', 'PATCH', member_path(self.bob), self.b, {'role': 'admin'}, 403),
            ('outsider promotes member', 'PATCH', member_path(self.bob), self.c, {'role': 'admin'}, 403),
            ('outsider promotes self', 'PATCH', member_path(self.carol), self.c, {'role': 'admin'}, 403),
            ('outsider adds self', 'POST', group + '/members', self.c, {'user_id': self.carol['id']}, 403),
            ('member adds outsider', 'POST', group + '/members', self.b, {'user_id': self.carol['id']}, 403),
            ('admin changes role on direct', 'PATCH', f'/api/v1/conversations/{self.direct}/members/{self.bob["id"]}',
             self.a, {'role': 'admin'}, 403),
            ('admin adds to direct', 'POST', f'/api/v1/conversations/{self.direct}/members',
             self.a, {'user_id': self.carol['id']}, 403),
            ('unknown conversation', 'PATCH', f'/api/v1/conversations/{uuid.uuid4()}/members/{self.bob["id"]}',
             self.a, {'role': 'admin'}, 404),
        ]
        for label, method, path, access, body, status in checks:
            with self.subTest(case=label):
                code = 'NOT_FOUND' if status == 404 else 'FORBIDDEN'
                await self.deny(method, path, access, status, code, json=body,
                                headers=headers if method == 'POST' else None)
        self.assertEqual(await self.snapshot(), before)
        # Rejoin path: promoted, removed and re-added B returns as a plain member.
        await self.read_ok(group, self.b)
        status, _ = await self.request('PATCH', member_path(self.bob), self.a, json={'role': 'admin'})
        self.assertEqual(status, 200)
        await self.remove_member(self.a, self.group, self.bob)
        await self.add_member(self.a, self.group, self.bob)
        detail = await self.read_ok(group, self.a)
        self.assertEqual({m['user_id']: m['role'] for m in detail['data']['members']},
                         {self.alice['id']: 'admin', self.bob['id']: 'member'})
        rejoined = await self.snapshot()
        await self.deny('POST', group + '/members', self.b, 403, 'FORBIDDEN',
                        json={'user_id': self.carol['id']}, headers=headers)
        await self.deny('PATCH', member_path(self.bob), self.b, 403, 'FORBIDDEN', json={'role': 'admin'})
        await self.deny('PATCH', group, self.b, 403, 'FORBIDDEN', json={'title': 'hijacked'})
        self.assertEqual(await self.snapshot(), rejoined)

    async def test_a18_remove_member_denied_for_outsider_member_direct_unknown_and_removed(self):
        before = await self.snapshot()
        group = f'/api/v1/conversations/{self.group}'
        checks = [
            ('outsider removes member', f'{group}/members/{self.bob["id"]}', self.c, 403, 'FORBIDDEN'),
            ('member removes admin', f'{group}/members/{self.alice["id"]}', self.b, 403, 'FORBIDDEN'),
            ('admin removes from direct', f'/api/v1/conversations/{self.direct}/members/{self.bob["id"]}',
             self.a, 403, 'FORBIDDEN'),
            ('outsider on direct', f'/api/v1/conversations/{self.direct}/members/{self.bob["id"]}',
             self.c, 403, 'FORBIDDEN'),
            ('unknown conversation', f'/api/v1/conversations/{uuid.uuid4()}/members/{self.bob["id"]}',
             self.a, 404, 'NOT_FOUND'),
        ]
        for label, path, access, status, code in checks:
            with self.subTest(case=label):
                await self.deny('DELETE', path, access, status, code)
        self.assertEqual(await self.snapshot(), before)
        await self.remove_member(self.a, self.group, self.bob)
        removed = await self.snapshot()
        await self.deny('DELETE', f'{group}/members/{self.alice["id"]}', self.b, 403, 'FORBIDDEN')
        self.assertEqual(await self.snapshot(), removed)
        # A removed member leaving again is an idempotent no-op: no version or feed change.
        status, _ = await self.request('DELETE', f'{group}/members/{self.bob["id"]}', self.b)
        self.assertEqual(status, 204)
        self.assertEqual(await self.snapshot(), removed)

    async def test_a14_idempotent_replay_is_not_a_membership_credential_after_removal(self):
        key = str(uuid.uuid4())
        created = await self.create_group(self.b, [self.alice], title='B group', key=key)
        status, _ = await self.request('PATCH', f'/api/v1/conversations/{created}/members/{self.alice["id"]}',
                                       self.b, json={'role': 'admin'})
        self.assertEqual(status, 200)
        await self.remove_member(self.a, created, self.bob)
        before = await self.snapshot()
        await self.deny('POST', '/api/v1/conversations/groups', self.b, 403, 'FORBIDDEN',
                        json={'title': 'B group', 'member_ids': [self.alice['id']]},
                        headers={'Idempotency-Key': key})
        self.assertEqual(await self.snapshot(), before)

    async def test_a06_a07_avatar_visibility_and_cross_account_avatar_selection(self):
        avatar = await self.attachment(self.a, scope='avatar')
        status, result = await self.request('PATCH', '/api/v1/users/me', self.a, json={'avatar_attachment_id': avatar})
        self.assertEqual(status, 200, result)
        profile = f'/api/v1/users/{self.alice["id"]}'
        self.assertEqual((await self.read_ok(profile, self.b))['data']['avatar_attachment_id'], avatar)
        self.assertIsNone((await self.read_ok(profile, self.c))['data']['avatar_attachment_id'])
        await self.deny('GET', f'/api/v1/attachments/{avatar}/download', self.c, 403, 'FORBIDDEN')
        # Sharing a conversation makes the avatar visible; leaving it hides it again.
        shared = await self.create_group(self.a, [self.carol], title='H')
        self.assertEqual((await self.read_ok(profile, self.c))['data']['avatar_attachment_id'], avatar)
        carol_scoped = await self.attachment(self.c, conversation=shared)
        await self.remove_member(self.a, shared, self.carol)
        self.assertIsNone((await self.read_ok(profile, self.c))['data']['avatar_attachment_id'])
        # C cannot adopt A's avatar, a conversation-scoped upload, or an unknown attachment.
        before = await self.snapshot()
        for label, value in (('foreign avatar', avatar), ('own conversation attachment', carol_scoped),
                             ('unknown attachment', str(uuid.uuid4()))):
            with self.subTest(case=label):
                await self.deny('PATCH', '/api/v1/users/me', self.c, 403, 'FORBIDDEN',
                                json={'avatar_attachment_id': value})
        with self.subTest(case='A selects own conversation attachment'):
            group_scoped = await self.attachment(self.a, conversation=self.group)
            await self.deny('PATCH', '/api/v1/users/me', self.a, 403, 'FORBIDDEN',
                            json={'avatar_attachment_id': group_scoped})
        after = await self.snapshot()
        self.assertEqual(after['avatars'], before['avatars'])

    async def test_a20_upload_intent_for_foreign_conversation_is_rejected_without_a_row(self):
        for cid in (self.group, self.direct):
            with self.subTest(conversation=cid):
                await self.deny('POST', '/api/v1/uploads', self.c, 403, 'FORBIDDEN', json={
                    'scope': 'conversation', 'conversation_id': cid, 'filename': 'tiny.png',
                    'content_type': 'image/png', 'size_bytes': len(PNG), 'sha256': PNG_SHA},
                    headers={'Idempotency-Key': secrets.token_urlsafe(20)})
        async with self.runtime.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM attachments'), 0)

    async def test_a22_download_denied_for_never_member_removed_non_uploader_and_unreferenced(self):
        referenced = await self.attachment(self.a, conversation=self.group)
        await self.send_image(referenced, self.group)
        unreferenced = await self.attachment(self.a, conversation=self.group)
        path = '/api/v1/attachments/{}/download'
        # Control through the private authority: member B may read the sent image, never the unsent one.
        allowed = await self.authorize(self.b, 'attachment', 'attachment', referenced)
        self.assertTrue(allowed[1]['data']['allowed'])
        for access, label in ((self.c, 'never member'),):
            with self.subTest(case=label):
                await self.deny('GET', path.format(referenced), access, 403, 'FORBIDDEN')
                self.assertFalse((await self.authorize(access, 'attachment', 'attachment', referenced))[1]['data']['allowed'])
        with self.subTest(case='co-member, unreferenced attachment'):
            await self.deny('GET', path.format(unreferenced), self.b, 403, 'FORBIDDEN')
            self.assertFalse((await self.authorize(self.b, 'attachment', 'attachment', unreferenced))[1]['data']['allowed'])
            self.assertTrue((await self.authorize(self.a, 'attachment', 'attachment', unreferenced))[1]['data']['allowed'])
        await self.remove_member(self.a, self.group, self.bob)
        with self.subTest(case='removed non-uploader'):
            await self.deny('GET', path.format(referenced), self.b, 403, 'FORBIDDEN')
            self.assertFalse((await self.authorize(self.b, 'attachment', 'attachment', referenced))[1]['data']['allowed'])

    async def test_internal_authorize_denies_outsider_and_unknown_resources_are_not_found(self):
        message = (await self.send('secret', conversation=self.group))[1]['data']['message_id']
        for action in ('send', 'receive', 'read', 'history', 'manage_group'):
            with self.subTest(actor='outsider', kind='conversation', action=action):
                status, result = await self.authorize(self.c, action, 'conversation', self.group)
                self.assertEqual((status, result['data']['allowed']), (200, False))
        for action in ('receive', 'read', 'history'):
            with self.subTest(actor='outsider', kind='message', action=action):
                status, result = await self.authorize(self.c, action, 'message', message)
                self.assertEqual((status, result['data']['allowed']), (200, False))
        # Controls: the same questions answered for real members are not blanket-false.
        self.assertTrue((await self.authorize(self.b, 'receive', 'message', message))[1]['data']['allowed'])
        self.assertFalse((await self.authorize(self.b, 'manage_group', 'conversation', self.group))[1]['data']['allowed'])
        self.assertTrue((await self.authorize(self.a, 'manage_group', 'conversation', self.group))[1]['data']['allowed'])
        for kind in ('conversation', 'message', 'attachment'):
            with self.subTest(kind=kind, resource='unknown'):
                status, result = await self.authorize(self.c, 'read' if kind != 'attachment' else 'attachment',
                                                      kind, str(uuid.uuid4()))
                self.assertEqual((status, result['error']['code']), (404, 'NOT_FOUND'))


class AuthorizationRealtimeTests(AuthorizationCase):
    @asynccontextmanager
    async def connected(self, server, *accesses):
        async with AsyncExitStack() as stack:
            wires = []
            for access in accesses:
                socket = await self.client.ws_connect(server.make_url('/ws/v1'),
                    headers={'Origin': self.api.origin}, max_msg_size=1048576)
                stack.push_async_callback(socket.close)
                wire = Wire(socket)
                reply = await wire.call('auth.authenticate',
                    {'access_token': access['access_token'], 'device_id': access['device_id']})
                self.assertEqual(reply['event'], 'auth.accepted', reply)
                wires.append(wire)
            yield wires

    @staticmethod
    def text_message(text):
        return {'client_message_id': str(uuid.uuid4()), 'type': 'text', 'text': text}

    async def rejected(self, wire, event, payload, conversation, code):
        """Correlated non-retryable error frame, no ack/status/receipt, socket still serves requests."""
        reply = await wire.call(event, payload, conversation)
        self.assertEqual(reply['event'], 'error', reply)
        self.assertEqual((reply['payload']['code'], reply['payload']['retryable']), (code, False), reply)
        pong = await wire.call('heartbeat.ping', {'nonce': uuid.uuid4().hex})
        self.assertEqual(pong['event'], 'heartbeat.pong')

    async def sent(self, wire, conversation, text):
        reply = await wire.call('message.send', self.text_message(text), conversation)
        self.assertEqual(reply['event'], 'message.ack', reply)
        return reply

    async def stored_texts(self):
        async with self.runtime.pool.acquire() as conn:
            return sorted(row[0] for row in await conn.fetch("SELECT payload->>'text' FROM messages"))

    async def test_w05_outsider_removed_member_and_unknown_conversation_cannot_send(self):
        carol_direct = await self.create_direct(self.a, self.carol)
        async with self.real_realtime() as server, self.connected(server, self.a, self.b, self.c) as (A, B, C):
            await self.rejected(C, 'message.send', self.text_message('intrusion'), self.group, 'FORBIDDEN')
            await self.rejected(C, 'message.send', self.text_message('intrusion'), self.direct, 'FORBIDDEN')
            await self.rejected(C, 'message.send', self.text_message('intrusion'), str(uuid.uuid4()), 'NOT_FOUND')
            self.assertEqual(await self.stored_texts(), [])
            await self.remove_member(self.a, self.group, self.bob)
            await self.rejected(B, 'message.send', self.text_message('intrusion'), self.group, 'FORBIDDEN')
            # Positive controls on the same sockets prove the rejected frames were not merely queued.
            await self.sent(A, self.group, 'control-G')
            await self.sent(A, self.direct, 'control-B')
            await self.sent(A, carol_direct, 'control-C')
            await B.read_until(lambda f: f['event'] == 'message.created' and f['payload'].get('text') == 'control-B')
            await C.read_until(lambda f: f['event'] == 'message.created' and f['payload'].get('text') == 'control-C')
            self.assertEqual(await self.stored_texts(), ['control-B', 'control-C', 'control-G'])
            for label, wire in (('A', A), ('B', B), ('C', C)):
                with self.subTest(wire=label):
                    self.assertEqual(wire.of('message.created', text='intrusion'), [])
            for label, wire in (('B', B), ('C', C)):
                with self.subTest(wire=label, frame='message.ack'):
                    self.assertEqual(wire.of('message.ack'), [])
            for label, wire in (('B', B), ('C', C)):
                with self.subTest(wire=label, leak='group message after removal/never member'):
                    self.assertEqual(wire.of('message.created', text='control-G'), [])

    async def test_w05_attachment_misuse_is_forbidden_or_not_ready(self):
        b_other = await self.attachment(self.b, conversation=self.direct)
        b_ready = await self.attachment(self.b, conversation=self.group)
        b_pending = await self.attachment(self.b, conversation=self.group, ready=False)
        a_avatar = await self.attachment(self.a, scope='avatar')
        a_ready = await self.attachment(self.a, conversation=self.group)
        a_sent = await self.attachment(self.a, conversation=self.group)
        await self.send_image(a_sent, self.group)
        baseline = await self.snapshot()

        def image(aid, kind='image'):
            return {'client_message_id': str(uuid.uuid4()), 'type': kind, 'attachment_id': aid}

        async with self.real_realtime() as server, self.connected(server, self.a, self.b, self.c) as (A, B, C):
            cases = [
                (B, 'avatar scope', image(a_avatar), self.group, 'FORBIDDEN'),
                (B, 'other conversation', image(b_other), self.group, 'FORBIDDEN'),
                (B, 'wrong kind', image(b_ready, 'file'), self.group, 'FORBIDDEN'),
                (B, 'unknown attachment', image(str(uuid.uuid4())), self.group, 'FORBIDDEN'),
                (A, 'co-member unreferenced attachment', image(b_ready), self.group, 'FORBIDDEN'),
                (B, 'pending attachment', image(b_pending), self.group, 'UPLOAD_NOT_READY'),
                (C, 'outsider forwards valid attachment', image(a_sent), self.group, 'FORBIDDEN'),
                (C, 'outsider with unsent attachment', image(a_ready), self.group, 'FORBIDDEN'),
            ]
            for wire, label, payload, conversation, code in cases:
                with self.subTest(case=label):
                    await self.rejected(wire, 'message.send', payload, conversation, code)
            # Rejoined B cannot forward an attachment that was only visible before the join.
            await self.remove_member(self.a, self.group, self.bob)
            await self.add_member(self.a, self.group, self.bob)
            with self.subTest(case='rejoined member forwards pre-join attachment'):
                await self.rejected(B, 'message.send', image(a_sent), self.group, 'FORBIDDEN')
        after = await self.snapshot()
        self.assertEqual(after['messages'], baseline['messages'])
        self.assertEqual(after['attachments'], baseline['attachments'])

    async def test_w08_w09_receipts_denied_for_outsider_foreign_message_removed_and_sender(self):
        carol_direct = await self.create_direct(self.a, self.carol)
        async with self.real_realtime() as server, self.connected(server, self.a, self.b, self.c) as (A, B, C):
            direct_message = (await self.sent(A, self.direct, 'direct'))['payload']['message_id']
            group_message = (await self.sent(A, self.group, 'group'))['payload']['message_id']
            await self.remove_member(self.a, self.group, self.bob)
            for event in ('message.received', 'message.read'):
                cases = [
                    (C, 'outsider on foreign conversation', direct_message, self.direct, 'FORBIDDEN'),
                    (C, 'outsider on foreign group', group_message, self.group, 'FORBIDDEN'),
                    (C, 'own conversation, foreign message id', direct_message, carol_direct, 'NOT_FOUND'),
                    (A, 'sender reads own message', direct_message, self.direct, 'FORBIDDEN'),
                    (B, 'removed member', group_message, self.group, 'FORBIDDEN'),
                    (B, 'member, message from another conversation', group_message, self.direct, 'NOT_FOUND'),
                    (B, 'member, unknown message', str(uuid.uuid4()), self.direct, 'NOT_FOUND'),
                ]
                for wire, label, message_id, conversation, code in cases:
                    with self.subTest(event=event, case=label):
                        await self.rejected(wire, event, {'message_id': message_id}, conversation, code)
            snapshot = await self.snapshot()
            self.assertEqual(snapshot['receipts'], 0)
            async with self.runtime.pool.acquire() as conn:
                self.assertEqual(await conn.fetchval("SELECT count(*) FROM user_feed WHERE envelope->>'event'='message.status'"), 0)
            self.assertEqual(A.of('message.status'), [])
            for wire in (B, C):
                self.assertEqual(wire.of('receipt.ack'), [])
            # Control: B's legitimate read yields exactly one receipt and one W10 for A.
            reply = await B.call('message.read', {'message_id': direct_message}, self.direct)
            self.assertEqual((reply['event'], reply['payload']['status']), ('receipt.ack', 'read'), reply)
            await A.read_until(lambda f: f['event'] == 'message.status')
            self.assertEqual([f['payload']['recipient_id'] for f in A.of('message.status')], [self.bob['id']])
            self.assertEqual((await self.snapshot())['receipts'], 1)

    async def test_w13_foreign_or_mismatched_bootstrap_tokens_are_cursor_invalid(self):
        groups = [await self.create_group(self.a, [self.bob], title=f'bulk {i}') for i in range(11)]
        async with self.runtime.pool.acquire() as conn:
            await conn.execute('UPDATE conversations SET title=$1 WHERE conversation_id=ANY($2::text[])',
                               '😀' * 10000, groups)
        async with self.real_realtime() as server, self.connected(server, self.b, self.c) as (B, C):
            first = await B.call('sync.bootstrap.request', {'reason': 'first_login'})
            self.assertEqual(first['event'], 'sync.bootstrap.page', first)
            self.assertTrue(first['payload']['has_more'])
            second = await B.call('sync.bootstrap.request', {'reason': 'first_login'})
            self.assertTrue(second['payload']['has_more'])
            sid1, token1 = first['payload']['snapshot_id'], first['payload']['next_page_token']
            sid2, token2 = second['payload']['snapshot_id'], second['payload']['next_page_token']
            self.assertNotEqual(sid1, sid2)
            for wire, label, snapshot_id, token in ((C, "C replays B's snapshot and token", sid1, token1),
                                                    (C, "C replays B's second snapshot", sid2, token2),
                                                    (B, "B's snapshot with token from another snapshot", sid1, token2)):
                with self.subTest(case=label):
                    await self.rejected(wire, 'sync.bootstrap.request',
                        {'reason': 'first_login', 'snapshot_id': snapshot_id, 'page_token': token}, None, 'CURSOR_INVALID')
            # Control: B's own continuation still works and C never saw G or B's groups.
            page = await B.call('sync.bootstrap.request',
                {'reason': 'first_login', 'snapshot_id': sid1, 'page_token': token1})
            self.assertEqual(page['event'], 'sync.bootstrap.page', page)
            self.assertEqual(C.of('sync.bootstrap.page'), [])

    async def test_w13_w15_rejoin_exposes_only_content_after_the_new_join(self):
        async with self.real_realtime() as server, self.connected(server, self.b, self.c) as (B, C):
            boot = await B.call('sync.bootstrap.request', {'reason': 'first_login'})
            start = boot['payload']['start_cursor']
            await self.send('m1', conversation=self.group)
            await self.remove_member(self.a, self.group, self.bob)
            await self.send('m2', conversation=self.group)
            await self.add_member(self.a, self.group, self.bob)
            await self.send('m3', conversation=self.group)
            # C's own boundary token is not accepted for B's cursor.
            carol_boot = await C.call('sync.bootstrap.request', {'reason': 'first_login'})
            carol_batch = await C.call('sync.request', {'cursor': carol_boot['payload']['start_cursor']})
            self.assertEqual(carol_batch['event'], 'sync.batch', carol_batch)
            await self.rejected(B, 'sync.request',
                {'cursor': start, 'snapshot_boundary': carol_batch['payload']['snapshot_boundary']},
                None, 'CURSOR_INVALID')
            batch = await B.call('sync.request', {'cursor': start})
            self.assertEqual(batch['event'], 'sync.batch', batch)
            events = batch['payload']['events']
            self.assertFalse(batch['payload']['has_more'])
            self.assertEqual([e['event'] for e in events],
                             ['conversation.member_removed', 'conversation.member_added', 'message.created'])
            removed, added, created = events
            self.assertEqual(set(removed['payload']), {'member_id', 'change', 'membership_version'})
            self.assertEqual(removed['payload']['member_id'], self.bob['id'])
            self.assertEqual(added['payload']['membership_version'], 3)
            self.assertEqual(created['payload']['text'], 'm3')
            # Fresh bootstrap is bounded to the new join as well.
            fresh = await B.call('sync.bootstrap.request', {'reason': 'first_login'})
            entry = next(c for c in fresh['payload']['conversations'] if c['id'] == self.group)
            self.assertEqual([m['text'] for m in entry['recent_messages']], ['m3'])
            self.assertEqual(C.of('message.created', text='m3'), [])

    async def test_live_delivery_stops_at_removal_and_never_reaches_outsider(self):
        carol_direct = await self.create_direct(self.a, self.carol)
        async with self.real_realtime() as server, self.connected(server, self.a, self.b, self.c) as (A, B, C):
            await self.remove_member(self.a, self.group, self.bob)
            await self.sent(A, self.group, 'after removal')
            await self.sent(A, self.direct, 'direct-B')
            await self.sent(A, carol_direct, 'direct-C')
            await B.read_until(lambda f: f['event'] == 'message.created' and f['payload'].get('text') == 'direct-B')
            await C.read_until(lambda f: f['event'] == 'message.created' and f['payload'].get('text') == 'direct-C')
            for label, wire in (('removed B', B), ('outsider C', C)):
                with self.subTest(wire=label):
                    self.assertEqual(wire.of('message.created', text='after removal'), [])
                    self.assertEqual([f for f in wire.frames if f.get('conversation_id') == self.group
                                      and f['event'] == 'message.created'], [])
            # B is told it was removed, without the removing actor.
            removal = [f for f in B.frames if f['event'] == 'conversation.member_removed']
            self.assertEqual(len(removal), 1, B.frames)
            self.assertEqual(removal[0]['payload']['member_id'], self.bob['id'])
            self.assertNotIn('actor_id', removal[0]['payload'])
            self.assertEqual([f for f in C.frames if f.get('conversation_id') == self.group], [])
