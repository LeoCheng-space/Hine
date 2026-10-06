"""Product authority tests: real PostgreSQL, HTTP and private BA consumer boundary."""
import asyncio
import uuid
from contextlib import asynccontextmanager

from support import ProductCase


class DomainConsumer:
    async def setup_direct(self):
        self.alice, self.a = await self.account('alice')
        self.bob, self.b = await self.account('bob')
        status, result = await self.request('POST', '/api/v1/conversations/direct', self.a,
                                           json={'peer_user_id': self.bob['id']})
        self.assertEqual(status, 201)
        self.conversation = result['data']['id']
        self.binding = await self.api.binding(self.a)

    async def send(self, text='Hello', c1=None, access=None, conversation=None):
        binding = self.binding if access is None else await self.api.binding(access)
        fields = {key: binding[key] for key in ('subject_id', 'device_id', 'session_id', 'session_generation')}
        return await self.api.internal('persistIfAbsent', {
            **fields, 'conversation_id': conversation or self.conversation,
            'client_message_id': c1 or str(uuid.uuid4()), 'type': 'text',
            'payload': {'text': text}, 'request_event_id': str(uuid.uuid4()),
        })

    async def receipt(self, message_id, kind, access=None, conversation=None):
        binding = await self.api.binding(access or self.b)
        return await self.api.internal('persistReceipt', {
            **{key: binding[key] for key in ('subject_id', 'device_id', 'session_id', 'session_generation')},
            'conversation_id': conversation or self.conversation, 'message_id': message_id,
            'kind': kind, 'request_event_id': str(uuid.uuid4()),
        })

    @asynccontextmanager
    async def real_realtime(self):
        """Actual BA/Redis/private HTTP provider, with a test-owned Redis namespace."""
        import json
        import os

        from aiohttp.test_utils import TestServer
        from hine_realtime.config import Settings
        from hine_realtime.server import create_app
        from redis.asyncio import Redis

        configuration = dict(self.api.settings_env)
        redis_url = os.environ.get('HINE_TEST_REDIS_URL')
        if redis_url:
            configuration.pop('REDIS_URL_SECRET_REF', None)
            configuration['REDIS_URL'] = redis_url
        if not configuration.get('REDIS_URL') and not configuration.get('REDIS_URL_SECRET_REF'):
            raise RuntimeError('Real Redis required for BA product path: HINE_TEST_REDIS_URL')
        caller_refs = json.loads(configuration['INTERNAL_ALLOWED_CALLERS'])
        prefix = 'product-sync-' + uuid.uuid4().hex
        configuration.update(API_INTERNAL_URL=self.api.base_url,
            INTERNAL_CALLER_TOKEN_SECRET_REF=caller_refs['realtime'],
            INTERNAL_ALLOWED_CALLERS=json.dumps({'api': self.api.settings_env['INTERNAL_CALLER_TOKEN_SECRET_REF']}),
            REALTIME_REDIS_PREFIX=prefix, INVALIDATION_POLL_SECONDS='5',
            INVALIDATION_STALE_SECONDS='15', NOTICE_CATCHUP_HOLD_MS='1000',
            HEARTBEAT_INTERVAL_SECONDS='30', HEARTBEAT_TIMEOUT_SECONDS='90')
        settings = Settings.from_env(configuration)
        self.assertTrue(settings.valid)
        server = TestServer(create_app(settings))
        try:
            await server.start_server()
            async with asyncio.timeout(10):
                while True:
                    async with self.client.get(server.make_url('/health/ready')) as reply:
                        if reply.status == 200:
                            break
                    await asyncio.sleep(0.05)
            self.api.settings_env['REALTIME_INTERNAL_URL'] = str(server.make_url('/')).rstrip('/')
            await self.api.restart()
            yield server
        finally:
            await server.close()
            redis = Redis.from_url(settings.redis_url, decode_responses=True)
            try:
                async for key in redis.scan_iter(match=prefix + ':*', count=100):
                    await redis.delete(key)
            finally:
                await redis.aclose()


class DomainTests(DomainConsumer, ProductCase):
    async def test_concurrent_c1_commits_one_message_and_one_feed_per_user(self):
        await self.setup_direct()
        c1 = str(uuid.uuid4())
        results = await asyncio.gather(*(self.send('😀e\u0301 ', c1) for _ in range(8)))
        self.assertTrue(all(status == 200 for status, _ in results))
        identities = {(r['data']['message_id'], r['data']['event_id'], r['data']['order_key']) for _, r in results}
        self.assertEqual(len(identities), 1)
        async with self.runtime.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM messages WHERE client_message_id=$1', uuid.UUID(c1)), 1)
            self.assertEqual(await conn.fetchval("SELECT count(*) FROM user_feed WHERE envelope->>'event'='message.created'"), 2)
        _, history = await self.request('GET', f'/api/v1/conversations/{self.conversation}/messages', self.b)
        message = history['data']['items'][0]
        self.assertEqual(message['text'], '😀e\u0301 ')
        self.assertNotIn('client_message_id', message)
        self.assertRegex(message['order_key'], r'^[0-9]{20}$')

    async def test_exhausted_quota_five_precedence_cases_and_no_failed_mapping(self):
        await self.setup_direct()
        c1 = str(uuid.uuid4())
        _, original = await self.send(c1=c1)
        async with self.runtime.pool.acquire() as conn:
            await conn.execute("UPDATE message_quota SET tokens=-1000,updated_at=clock_timestamp() WHERE subject_id=$1", self.binding['subject_id'])
        cases = [('X' * 5000, None, 'INVALID_ARGUMENT'), ('Hello', None, 'RATE_LIMITED'),
                 ('Hello', c1, None), ('World', c1, 'IDEMPOTENCY_CONFLICT'),
                 ('X' * 5000, c1, 'INVALID_ARGUMENT')]
        for text, key, code in cases:
            status, result = await self.send(text, key)
            if code is None:
                self.assertEqual(status, 200)
                self.assertEqual(result['data']['message_id'], original['data']['message_id'])
            else:
                self.assertEqual(result['error']['code'], code)
        async with self.runtime.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM messages'), 1)

    async def test_direct_receipt_monotone_noop_and_server_unread(self):
        await self.setup_direct()
        _, sent = await self.send()
        mid = sent['data']['message_id']
        _, detail = await self.request('GET', f'/api/v1/conversations/{self.conversation}', self.b)
        self.assertEqual(detail['data']['unread_count'], 1)
        _, delivered = await self.receipt(mid, 'delivered')
        self.assertTrue(delivered['data']['changed'])
        self.assertEqual(delivered['data']['observer_ids'], [self.alice['id']])
        _, read = await self.receipt(mid, 'read')
        _, noop = await self.receipt(mid, 'delivered')
        self.assertEqual(noop['data']['status'], 'read')
        self.assertFalse(noop['data']['changed'])
        self.assertIsNone(noop['data']['status_event_id'])
        self.assertEqual(noop['data']['observer_ids'], [])
        self.assertEqual(noop['data']['updated_at'], read['data']['updated_at'])
        _, detail = await self.request('GET', f'/api/v1/conversations/{self.conversation}', self.b)
        self.assertEqual(detail['data']['unread_count'], 0)
        _, history = await self.request('GET', f'/api/v1/conversations/{self.conversation}/messages', self.a)
        self.assertEqual(history['data']['items'][0]['receipt']['status'], 'read')
        async with self.runtime.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval("SELECT count(*) FROM user_feed WHERE envelope->>'event'='message.status'"), 2)

    async def test_group_last_admin_join_rejoin_and_group_receipt_projection(self):
        await self.setup_direct()
        headers = {'Idempotency-Key': str(uuid.uuid4())}
        status, group = await self.request('POST', '/api/v1/conversations/groups', self.a,
                                          json={'title': 'Group', 'member_ids': []}, headers=headers)
        self.assertEqual(status, 201)
        gid = group['data']['id']
        status, conflict = await self.request('PATCH', f'/api/v1/conversations/{gid}/members/{self.alice["id"]}', self.a,
                                              json={'role': 'member'})
        self.assertEqual(conflict['error']['code'], 'CONFLICT')
        _, before = await self.send('before join', conversation=gid)
        await self.request('POST', f'/api/v1/conversations/{gid}/members', self.a, json={'user_id': self.bob['id']})
        _, after = await self.send('after join', conversation=gid)
        _, history = await self.request('GET', f'/api/v1/conversations/{gid}/messages', self.b)
        self.assertEqual([m['text'] for m in history['data']['items']], ['after join'])
        _, receipt = await self.receipt(after['data']['message_id'], 'read', conversation=gid)
        self.assertIsNone(receipt['data']['status_event_id'])
        self.assertEqual(receipt['data']['observer_ids'], [])
        _, history = await self.request('GET', f'/api/v1/conversations/{gid}/messages', self.a)
        self.assertTrue(all(m['receipt'] is None for m in history['data']['items']))
        await self.request('DELETE', f'/api/v1/conversations/{gid}/members/{self.bob["id"]}', self.a)
        await self.request('POST', f'/api/v1/conversations/{gid}/members', self.a, json={'user_id': self.bob['id']})
        _, history = await self.request('GET', f'/api/v1/conversations/{gid}/messages', self.b)
        self.assertEqual(history['data']['items'], [])
        status, rejected = await self.receipt(before['data']['message_id'], 'read', conversation=gid)
        self.assertEqual(status, 403)
        self.assertEqual(rejected['error']['code'], 'FORBIDDEN')

    async def test_profile_privacy_and_current_presence_target_contact_authority(self):
        await self.setup_direct()
        _, summary = await self.request('GET', f'/api/v1/users/{self.bob["id"]}', self.a)
        self.assertNotIn('email', summary['data'])
        await self.request('POST', '/api/v1/contacts', self.a, json={'user_id': self.bob['id']})
        payload = {key: self.binding[key] for key in ('subject_id', 'session_id', 'session_generation')}
        payload.update(limit=1, contact_user_id=self.bob['id'])
        _, targets = await self.api.internal('readPresenceTargets', payload)
        self.assertEqual([t['user_id'] for t in targets['data']['targets']], [self.bob['id']])
        await self.request('DELETE', f'/api/v1/contacts/{self.bob["id"]}', self.a)
        _, targets = await self.api.internal('readPresenceTargets', payload)
        self.assertEqual(targets['data']['targets'], [])
        _, contacts = await self.request('GET', '/api/v1/contacts?limit=0', self.a)
        self.assertEqual(contacts['error']['code'], 'INVALID_ARGUMENT')
        _, rejected = await self.send('', access=self.b, conversation='x' * 129)
        self.assertEqual(rejected['error']['code'], 'INVALID_ARGUMENT')

    async def test_valid_unicode_zero_codepoint_roundtrips_without_normalization(self):
        await self.setup_direct()
        text = ' e\u0301\u0000😀 '
        private = {key:self.binding[key] for key in ('subject_id','session_id','session_generation')}
        _, initial = await self.api.internal('readBootstrap', {**private,'reason':'first_login'})
        c1 = str(uuid.uuid4())
        _, sent = await self.send(text, c1)
        await self.api.restart()
        _, history = await self.request('GET', f'/api/v1/conversations/{self.conversation}/messages', self.a)
        self.assertEqual(history['data']['items'][0]['text'], text)
        self.assertEqual(history['data']['items'][0]['id'], sent['data']['message_id'])
        _, repeated = await self.send(text, c1)
        self.assertEqual(repeated['data']['event_id'],sent['data']['event_id'])
        _, batch = await self.api.internal('readFeed', {**private,'cursor':initial['data']['start_cursor'],'limit':100})
        self.assertEqual([event['payload']['text'] for event in batch['data']['events']], [text])
        _, snapshot = await self.api.internal('readBootstrap', {**private,'reason':'first_login'})
        self.assertEqual(snapshot['data']['conversations'][0]['recent_messages'][0]['text'],text)
        title = 'Title\u0000😀'
        status, group = await self.request('POST', '/api/v1/conversations/groups', self.a,
            json={'title': title, 'member_ids': []}, headers={'Idempotency-Key': str(uuid.uuid4())})
        self.assertEqual(status, 201)
        self.assertEqual(group['data']['title'], title)
        status, absent = await self.request('GET', '/api/v1/users/opaque%00id', self.a)
        self.assertEqual(status, 404)
        self.assertEqual(absent['error']['code'], 'NOT_FOUND')
        await self.request('POST', '/api/v1/contacts', self.a, json={'user_id': self.bob['id']})
        payload = {key: self.binding[key] for key in ('subject_id', 'session_id', 'session_generation')}
        _, targets = await self.api.internal('readPresenceTargets', {**payload, 'limit': 100, 'contact_user_id': 'opaque\u0000id'})
        self.assertEqual(targets['data']['targets'], [])

    async def test_group_idempotency_noop_member_key_and_admin_event_mapping(self):
        await self.setup_direct()
        key = str(uuid.uuid4())
        payload = {'title': 'Group', 'member_ids': [self.bob['id']]}
        _, first = await self.request('POST', '/api/v1/conversations/groups', self.a,
            json=payload, headers={'Idempotency-Key': key})
        _, same = await self.request('POST', '/api/v1/conversations/groups', self.a,
            json=payload, headers={'Idempotency-Key': key})
        self.assertEqual(same['data'], first['data'])
        _, collision = await self.request('POST', '/api/v1/conversations/groups', self.a,
            json={**payload, 'title': 'Different'}, headers={'Idempotency-Key': key})
        self.assertEqual(collision['error']['code'], 'IDEMPOTENCY_CONFLICT')
        gid = first['data']['id']
        member_key = str(uuid.uuid4())
        status, _ = await self.request('POST', f'/api/v1/conversations/{gid}/members', self.a,
            json={'user_id': self.bob['id']}, headers={'Idempotency-Key': member_key})
        self.assertEqual(status, 200)
        _, collision = await self.request('POST', f'/api/v1/conversations/{gid}/members', self.a,
            json={'user_id': self.alice['id']}, headers={'Idempotency-Key': member_key})
        self.assertEqual(collision['error']['code'], 'IDEMPOTENCY_CONFLICT')
        await self.request('PATCH', f'/api/v1/conversations/{gid}', self.a, json={'title': 'New title'})
        await self.request('PATCH', f'/api/v1/conversations/{gid}/members/{self.bob["id"]}', self.a,
            json={'role': 'admin'})
        await self.request('DELETE', f'/api/v1/conversations/{gid}/members/{self.alice["id"]}', self.a)
        async with self.runtime.pool.acquire() as conn:
            records = await conn.fetch('SELECT user_id,envelope FROM user_feed ORDER BY user_id,position')
        events = [r['envelope'] for r in records if r['envelope']['conversation_id']==gid]
        self.assertEqual(sum(e['event']=='conversation.member_added' for e in events), 4)
        self.assertEqual(sum(e['event']=='conversation.updated' for e in events), 4)
        own_removal = next(r['envelope'] for r in records if r['user_id']==self.alice['id'] and r['envelope']['event']=='conversation.member_removed')
        self.assertNotIn('actor_id', own_removal['payload'])

    async def test_group_limit_counts_creator_and_full_group_rejects_addition(self):
        await self.setup_direct()
        _, invalid = await self.request('POST', '/api/v1/conversations/groups', self.a,
            json={'title':'Overfull','member_ids':[str(uuid.uuid4()) for _ in range(51)]},
            headers={'Idempotency-Key':str(uuid.uuid4())})
        self.assertEqual(invalid['error']['code'], 'INVALID_ARGUMENT')
        profiles = [await self.api.signup(display_name='Member') for _ in range(49)]
        _, full = await self.request('POST', '/api/v1/conversations/groups', self.a,
            json={'title':'Full','member_ids':[profile['id'] for profile in profiles]},
            headers={'Idempotency-Key':str(uuid.uuid4())})
        self.assertEqual(len(full['data']['member_ids']), 50)
        _, conflict = await self.request('POST', f'/api/v1/conversations/{full["data"]["id"]}/members',
            self.a, json={'user_id':self.bob['id']})
        self.assertEqual(conflict['error']['code'], 'CONFLICT')

    async def test_contacts_cursor_scope_and_limits_and_direct_pair_reuse(self):
        await self.setup_direct()
        charlie, _ = await self.account('charlie')
        for profile in (self.bob,charlie):
            status, _ = await self.request('POST','/api/v1/contacts',self.a,json={'user_id':profile['id']})
            self.assertEqual(status,201)
        status, _existing = await self.request('POST','/api/v1/contacts',self.a,json={'user_id':self.bob['id']})
        self.assertEqual(status,200)
        _, first = await self.request('GET','/api/v1/contacts?limit=1',self.a)
        self.assertEqual(first['data']['items'][0]['presence'],'unknown')
        cursor = first['meta']['next_cursor']
        _, second = await self.request('GET','/api/v1/contacts?cursor='+cursor+'&limit=1',self.a)
        self.assertIsNone(second['meta']['next_cursor'])
        self.assertNotEqual(first['data']['items'][0]['user']['id'],second['data']['items'][0]['user']['id'])
        _, invalid = await self.request('GET','/api/v1/contacts?cursor='+cursor,self.b)
        self.assertEqual(invalid['error']['code'],'CURSOR_INVALID')
        for query in ('limit=0','limit=51','limit=1&limit=1','limit=null','limit=1.5','cursor='):
            _, invalid = await self.request('GET','/api/v1/contacts?'+query,self.a)
            self.assertEqual(invalid['error']['code'],'CURSOR_INVALID' if query=='cursor=' else 'INVALID_ARGUMENT')
        status, direct = await self.request('POST','/api/v1/conversations/direct',self.b,json={'peer_user_id':self.alice['id']})
        self.assertEqual(status,200)
        self.assertEqual(direct['data']['id'],self.conversation)

    async def test_raw_utf8_title_cannot_create_undeliverable_internal_payload(self):
        import json
        await self.setup_direct()
        status, failure = await self.api.request('POST','/api/v1/conversations/groups',session=self.a,
            raw=json.dumps({'title':'😀'*90000,'member_ids':[]},ensure_ascii=False).encode(),
            headers={'Content-Type':'application/json','Idempotency-Key':str(uuid.uuid4())})
        self.assertEqual(status,413)
        self.assertEqual(failure['error']['code'],'PAYLOAD_TOO_LARGE')
        async with self.runtime.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval("SELECT count(*) FROM conversations WHERE type='group'"),0)

    async def test_confirmed_database_rollback_returns_persistence_failed_without_mapping(self):
        await self.setup_direct()
        async with self.runtime.pool.acquire() as conn:
            await conn.execute("""CREATE FUNCTION reject_product_message() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION 'controlled persistence failure' USING ERRCODE='23514'; END $$;
                CREATE TRIGGER reject_product_message BEFORE INSERT ON messages
                FOR EACH ROW EXECUTE FUNCTION reject_product_message()""")
        status, failure = await self.send('valid intent')
        self.assertEqual(status,503)
        self.assertEqual(failure['error']['code'],'PERSISTENCE_FAILED')
        async with self.runtime.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM messages'),0)
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM user_feed'),0)
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM message_quota'),0)

    async def test_group_unknown_initial_member_uses_declared_conflict_without_events(self):
        await self.setup_direct()
        status, result = await self.request('POST','/api/v1/conversations/groups',self.a,
            json={'title':'Group','member_ids':['unknown-but-canonical']},
            headers={'Idempotency-Key':str(uuid.uuid4())})
        self.assertEqual(status,409)
        self.assertEqual(result['error']['code'],'CONFLICT')
        async with self.runtime.pool.acquire() as conn:
            self.assertEqual(await conn.fetchval('SELECT count(*) FROM user_feed'),0)

    async def test_real_ba_websocket_commit_receipt_sync_and_multi_device_presence(self):
        import json
        import os
        from datetime import datetime, timezone

        from aiohttp.test_utils import TestServer
        from hine_realtime.config import Settings
        from hine_realtime.server import create_app
        from redis.asyncio import Redis

        await self.setup_direct()
        configuration = dict(self.api.settings_env)
        redis_url = os.environ.get('HINE_TEST_REDIS_URL')
        if redis_url:
            configuration.pop('REDIS_URL_SECRET_REF',None)
            configuration['REDIS_URL'] = redis_url
        if not configuration.get('REDIS_URL') and not configuration.get('REDIS_URL_SECRET_REF'):
            raise RuntimeError('Real Redis required for BA product path: HINE_TEST_REDIS_URL')
        caller_refs = json.loads(configuration['INTERNAL_ALLOWED_CALLERS'])
        prefix = 'product-domain-' + uuid.uuid4().hex
        configuration.update(API_INTERNAL_URL=self.api.base_url,
            INTERNAL_CALLER_TOKEN_SECRET_REF=caller_refs['realtime'],
            INTERNAL_ALLOWED_CALLERS=json.dumps({'api':self.api.settings_env['INTERNAL_CALLER_TOKEN_SECRET_REF']}),
            REALTIME_REDIS_PREFIX=prefix, INVALIDATION_POLL_SECONDS='5',
            INVALIDATION_STALE_SECONDS='15', NOTICE_CATCHUP_HOLD_MS='1000',
            HEARTBEAT_INTERVAL_SECONDS='30', HEARTBEAT_TIMEOUT_SECONDS='90')
        settings = Settings.from_env(configuration)
        self.assertTrue(settings.valid)
        server = TestServer(create_app(settings))
        sockets = []

        def frame(event, payload, conversation=None):
            result = {'event':event,'event_id':str(uuid.uuid4()),
                'timestamp':datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),'payload':payload}
            if conversation is not None:
                result['conversation_id'] = conversation
            return result

        async def receive(socket, event, timeout=10):
            async with asyncio.timeout(timeout):
                while True:
                    value = await socket.receive_json()
                    if value['event']==event:
                        return value
                    self.assertNotEqual(value['event'],'error',value)

        async def connect(access):
            socket = await self.client.ws_connect(server.make_url('/ws/v1'),headers={'Origin':self.api.origin})
            sockets.append(socket)
            await socket.send_json(frame('auth.authenticate',{'access_token':access['access_token'],'device_id':access['device_id']}))
            accepted = await receive(socket,'auth.accepted')
            self.assertEqual(accepted['payload']['user_id'],access['user_id'])
            return socket

        try:
            await server.start_server()
            async with asyncio.timeout(10):
                while True:
                    async with self.client.get(server.make_url('/health/ready')) as reply:
                        if reply.status==200:
                            break
                    await asyncio.sleep(0.05)
            self.api.settings_env['REALTIME_INTERNAL_URL'] = str(server.make_url('/')).rstrip('/')
            await self.api.restart()
            alice_ws, bob_ws = await connect(self.a), await connect(self.b)
            second_access = await self.api.login(self.bob['email'])
            second_ws = await connect(second_access)
            await self.request('POST','/api/v1/contacts',self.a,json={'user_id':self.bob['id']})
            _, contacts = await self.request('GET','/api/v1/contacts',self.a)
            self.assertEqual(contacts['data']['items'][0]['presence'],'online')
            presence = await receive(alice_ws,'presence.changed')
            self.assertEqual(presence['payload'],{'user_id':self.bob['id'],'presence':'online'})
            await bob_ws.close()
            _, contacts = await self.request('GET','/api/v1/contacts',self.a)
            self.assertEqual(contacts['data']['items'][0]['presence'],'online')
            await second_ws.send_json(frame('sync.bootstrap.request',{'reason':'first_login'}))
            bootstrap = await receive(second_ws,'sync.bootstrap.page')
            c1, text = str(uuid.uuid4()),' Native\u0000😀 '
            await alice_ws.send_json(frame('message.send',{'client_message_id':c1,'type':'text','text':text},self.conversation))
            ack = await receive(alice_ws,'message.ack')
            message = await receive(second_ws,'message.created')
            self.assertEqual(message['payload']['message_id'],ack['payload']['message_id'])
            self.assertEqual(message['payload']['text'],text)
            self.assertNotIn('client_message_id',message['payload'])
            await alice_ws.send_json(frame('message.send',{'client_message_id':c1,'type':'text','text':text},self.conversation))
            repeated = await receive(alice_ws,'message.ack')
            self.assertEqual(repeated['payload']['message_id'],ack['payload']['message_id'])
            await second_ws.send_json(frame('message.read',{'message_id':ack['payload']['message_id']},self.conversation))
            receipt = await receive(second_ws,'receipt.ack')
            self.assertEqual(receipt['payload']['status'],'read')
            observed = await receive(alice_ws,'message.status')
            self.assertEqual(observed['payload']['recipient_id'],self.bob['id'])
            await second_ws.send_json(frame('sync.request',{'cursor':bootstrap['payload']['start_cursor']}))
            batch = await receive(second_ws,'sync.batch')
            created = [event for event in batch['payload']['events'] if event['event']=='message.created']
            self.assertEqual([event['event_id'] for event in created],[message['event_id']])
            self.assertEqual(created[0]['payload']['text'],text)
            async with self.runtime.pool.acquire() as conn:
                self.assertEqual(await conn.fetchval('SELECT count(*) FROM messages'),1)
        finally:
            for socket in sockets:
                await socket.close()
            await server.close()
            redis = Redis.from_url(settings.redis_url,decode_responses=True)
            try:
                async for key in redis.scan_iter(match=prefix+':*',count=100):
                    await redis.delete(key)
            finally:
                await redis.aclose()

    async def test_canonical_payload_validation_precedes_invalid_session(self):
        await self.setup_direct()
        binding = {key:self.binding[key] for key in ('subject_id','device_id','session_id','session_generation')}
        binding['session_id'] = 'nonexistent-session'
        for text, expected in (('', 'INVALID_ARGUMENT'),('A'*4097,'INVALID_ARGUMENT'),('\ud800','INVALID_ARGUMENT'),('A','UNAUTHENTICATED')):
            _, result = await self.api.internal('persistIfAbsent',{**binding,
                'conversation_id':self.conversation,'client_message_id':str(uuid.uuid4()),
                'type':'text','payload':{'text':text},'request_event_id':str(uuid.uuid4())})
            self.assertEqual(result['error']['code'],expected)
            if expected=='UNAUTHENTICATED':
                self.assertEqual(result['error']['details']['auth_layer'],'user_session')

    async def test_old_group_history_cursor_and_receive_authority_do_not_grant_rejoin_history(self):
        await self.setup_direct()
        _, group = await self.request('POST','/api/v1/conversations/groups',self.a,
            json={'title':'Group','member_ids':[self.bob['id']]},
            headers={'Idempotency-Key':str(uuid.uuid4())})
        gid = group['data']['id']
        _, first = await self.send('first',conversation=gid)
        await self.send('second',conversation=gid)
        _, history = await self.request('GET',f'/api/v1/conversations/{gid}/messages?limit=1',self.b)
        cursor = history['meta']['next_cursor']
        await self.request('DELETE',f'/api/v1/conversations/{gid}/members/{self.bob["id"]}',self.a)
        status, denied = await self.request('GET',f'/api/v1/conversations/{gid}/messages?before={cursor}',self.b)
        self.assertEqual(status,404)
        self.assertEqual(denied['error']['code'],'NOT_FOUND')
        await self.request('POST',f'/api/v1/conversations/{gid}/members',self.a,json={'user_id':self.bob['id']})
        _, history = await self.request('GET',f'/api/v1/conversations/{gid}/messages?before={cursor}',self.b)
        self.assertEqual(history['data']['items'],[])
        binding = await self.api.binding(self.b)
        _, authorization = await self.api.internal('authorize',{
            **{key:binding[key] for key in ('subject_id','device_id','session_id','session_generation')},
            'action':'receive','resource_type':'message','resource_id':first['data']['message_id']})
        self.assertFalse(authorization['data']['allowed'])

    async def test_malformed_presence_dependency_is_unknown_not_false_online(self):
        from aiohttp import web
        from aiohttp.test_utils import TestServer
        await self.setup_direct()
        await self.request('POST','/api/v1/contacts',self.a,json={'user_id':self.bob['id']})

        async def malformed_provider(request):
            # Deliberately isolate a malformed external provider, never BB authority.
            return web.json_response({'data':{'online':'online'}})

        app = web.Application()
        app.router.add_post('/internal/v1/getDevicePresence',malformed_provider)
        async with TestServer(app) as server:
            self.api.settings_env['REALTIME_INTERNAL_URL'] = str(server.make_url('/')).rstrip('/')
            await self.api.restart()
            status, contacts = await self.request('GET','/api/v1/contacts',self.a)
            self.assertEqual(status,200)
            self.assertEqual(contacts['data']['items'][0]['presence'],'unknown')
