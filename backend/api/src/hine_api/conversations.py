"""Conversation projections and transactionally published membership changes."""
import json
import uuid

from aiohttp import web
from hine_realtime import protocol as p

from . import db
from .domain import (
    ZERO_UUID,
    authority_position,
    conversation_member,
    entity,
    identifier,
    publish_group,
    required_keys,
    timestamp,
    transaction,
    valid_string,
)
from .server import RUNTIME
from .support import Fault, body, list_response, lookup_entity, response


def valid_title(value):
    valid_string(value, minimum=0)
    # Bound transport bytes, not a speculative character-count product policy.
    # Reserve worst-case Unicode EntityIDs plus the notice/sync envelope overhead.
    if len(p.dumps(value).encode('utf-8')) + 8192 > 1048576:
        raise Fault('PAYLOAD_TOO_LARGE')
    return value


async def unread(conn, user_id, conversation_id):
    return await conn.fetchval('''SELECT count(*) FROM messages m JOIN memberships p USING(conversation_id)
        LEFT JOIN receipts r ON r.message_id=m.message_id AND r.user_id=$1
        WHERE p.user_id=$1 AND p.active AND m.conversation_id=$2 AND m.sender_id<>$1
          AND (m.order_value,m.message_id)>(p.joined_order,p.joined_message_id)
          AND (r.status IS NULL OR r.status<>'read')''', user_id, conversation_id)


async def summary(conn, row, user_id):
    return {'id': row['conversation_id'], 'type': row['type'], 'title': row['title'],
            'unread_count': await unread(conn, user_id, row['conversation_id'])}


async def list_conversations(request):
    from .synchronization import rest_arguments, rest_load, rest_store
    limit, cursor = rest_arguments(request, 'cursor')
    runtime = request.app[RUNTIME]
    async with transaction(runtime, isolation='repeatable_read', write=False) as conn:
        binding = await runtime.auth.access(request, conn)
        user_id = binding['user_id']
        state = await rest_load(runtime, conn, cursor, user_id, 'conversations') if cursor else {}
        rows = await conn.fetch('''SELECT c.* FROM conversations c JOIN memberships p USING(conversation_id)
            WHERE p.user_id=$1 AND p.active AND c.conversation_id COLLATE "C">$2
            ORDER BY c.conversation_id COLLATE "C" LIMIT $3''', user_id, state.get('after', ''), limit + 1)
        items = [await summary(conn, row, user_id) for row in rows[:limit]]
        cursor = await rest_store(runtime, conn, user_id, 'conversations', {'after': rows[limit - 1]['conversation_id']}) if len(rows)>limit else None
    return list_response(items, cursor)


async def detail(request):
    cid = entity(request.match_info['conversation_id'])
    runtime = request.app[RUNTIME]
    async with transaction(runtime, isolation='repeatable_read', write=False) as conn:
        binding = await runtime.auth.access(request, conn)
        row, _ = await conversation_member(conn, binding['user_id'], cid, absent='NOT_FOUND')
        result = await summary(conn, row, binding['user_id'])
        members = await conn.fetch('SELECT user_id,role FROM memberships WHERE conversation_id=$1 AND active ORDER BY user_id COLLATE "C"', cid)
        result.update(members=[dict(member) for member in members], created_at=timestamp(row['created_at']),
                      membership_version=row['membership_version'])
    return response(result)


def idempotency_key(request, *, required=False):
    values = request.headers.getall('Idempotency-Key', [])
    if not values:
        if required:
            raise Fault('INVALID_ARGUMENT')
        return None
    if len(values)!=1:
        raise Fault('INVALID_ARGUMENT')
    return valid_string(values[0], maximum=1024)


async def mutation_existing(conn, user_id, key, operation, payload):
    if key is None:
        return None
    # Serialize even missing keys, without introducing a second authority table.
    await conn.execute('SELECT pg_advisory_xact_lock(hashtextextended($1,1))', user_id + '\x1f' + key)
    row = await conn.fetchrow('SELECT * FROM mutation_keys WHERE user_id=$1 AND key=$2', user_id, key)
    if row is None:
        return None
    if row['operation'] != operation or row['payload'] != payload:
        raise Fault('IDEMPOTENCY_CONFLICT')
    return row['result']


async def mutation_save(conn, user_id, key, operation, payload, result):
    if key is not None:
        await conn.execute('INSERT INTO mutation_keys(user_id,key,operation,payload,result) VALUES($1,$2,$3,$4,$5)',
                           user_id, key, operation, payload, result)


def creation(row, members):
    return {'id': row['conversation_id'], 'type': row['type'], 'title': row['title'],
            'member_ids': members, 'membership_version': row['membership_version']}


async def direct(request):
    value = await body(request)
    required_keys(value, ('peer_user_id',))
    peer = entity(value['peer_user_id'])
    key = idempotency_key(request)
    runtime = request.app[RUNTIME]
    async with transaction(runtime) as conn:
        await db.frontier(conn)
        binding = await runtime.auth.access(request, conn, lock=True)
        user_id = binding['user_id']
        if user_id == peer:
            raise Fault('CONFLICT')
        if not await conn.fetchval('SELECT EXISTS(SELECT 1 FROM users WHERE user_id=$1)', lookup_entity(peer)):
            raise Fault('NOT_FOUND')
        old = await mutation_existing(conn, user_id, key, 'A13', value)
        if old is not None:
            return response(old)
        pair = json.dumps(sorted([user_id, peer]), ensure_ascii=True, separators=(',', ':'))
        await conn.execute('SELECT pg_advisory_xact_lock(hashtextextended($1,2))', pair)
        row = await conn.fetchrow('SELECT * FROM conversations WHERE direct_pair=$1', pair)
        created = row is None
        if created:
            cid = identifier()
            row = await conn.fetchrow("INSERT INTO conversations(conversation_id,type,direct_pair) VALUES($1,'direct',$2) RETURNING *", cid, pair)
            await conn.executemany("INSERT INTO memberships(conversation_id,user_id,role) VALUES($1,$2,'member')", [(cid, user_id),(cid,peer)])
        result = creation(row, sorted([user_id,peer]))
        await mutation_save(conn, user_id, key, 'A13', value, result)
        await authority_position(conn)
    return response(result, status=201 if created else 200)


def envelope(event, cid, payload, now, event_id=None):
    return {'event': event, 'event_id': event_id or str(uuid.uuid4()), 'timestamp': timestamp(now),
            'conversation_id': cid, 'payload': payload}


async def members(conn, cid):
    return await conn.fetch('SELECT user_id,role FROM memberships WHERE conversation_id=$1 AND active ORDER BY user_id COLLATE "C"', cid)


async def append_group(conn, recipients, envelopes):
    deliveries = [{'recipient_user_id': recipient['user_id'], 'envelope': event}
                  for event in envelopes for recipient in recipients]
    await db.append_events(conn, deliveries)
    return deliveries


async def create_group(request):
    value = await body(request)
    required_keys(value, ('title','member_ids'))
    valid_title(value['title'])
    if not isinstance(value['member_ids'], list):
        raise Fault('INVALID_ARGUMENT')
    for member in value['member_ids']:
        entity(member)
    if len(set(value['member_ids'])) > 50:
        raise Fault('INVALID_ARGUMENT')
    key = idempotency_key(request, required=True)
    runtime = request.app[RUNTIME]
    async with transaction(runtime) as conn:
        await db.frontier(conn)
        binding = await runtime.auth.access(request, conn, lock=True)
        user_id = binding['user_id']
        user_ids = sorted(set(value['member_ids']) | {user_id})
        if len(user_ids)>50:
            raise Fault('INVALID_ARGUMENT')
        count = await conn.fetchval('SELECT count(*) FROM users WHERE user_id=ANY($1::text[])', [lookup_entity(uid) for uid in user_ids])
        if count != len(user_ids):
            raise Fault('CONFLICT')
        old = await mutation_existing(conn, user_id, key, 'A14', value)
        if old is not None:
            # A saved result is not a membership credential.
            await conversation_member(conn, user_id, old['id'])
            return response(old, status=201)
        cid = identifier()
        row = await conn.fetchrow("INSERT INTO conversations(conversation_id,type,title,membership_version) VALUES($1,'group',$2,1) RETURNING *", cid, value['title'])
        await conn.executemany('INSERT INTO memberships(conversation_id,user_id,role,joined_version) VALUES($1,$2,$3,1)',
                              [(cid, uid, 'admin' if uid==user_id else 'member') for uid in user_ids])
        recipients = await members(conn, cid)
        now = await conn.fetchval('SELECT clock_timestamp()')
        events = [envelope('conversation.member_added', cid, {'member_id': recipient['user_id'],
            'role': recipient['role'], 'actor_id': user_id, 'membership_version': 1}, now) for recipient in recipients]
        deliveries = await append_group(conn, recipients, events)
        result = creation(row, user_ids)
        await mutation_save(conn, user_id, key, 'A14', value, result)
        position = await authority_position(conn)
    await publish_group(runtime, 'A14', cid, 1, deliveries, position, now)
    return response(result, status=201)


async def locked_admin(conn, user_id, cid):
    row, member = await conversation_member(conn, user_id, cid, lock='write')
    if row['type'] != 'group':
        raise Fault('FORBIDDEN')
    if member['role'] != 'admin':
        raise Fault('FORBIDDEN')
    return row, member


async def increment(conn, cid):
    return await conn.fetchval('UPDATE conversations SET membership_version=membership_version+1 WHERE conversation_id=$1 RETURNING membership_version', cid)


async def rename(request):
    cid = entity(request.match_info['conversation_id'])
    value = await body(request)
    required_keys(value, ('title',))
    valid_title(value['title'])
    runtime = request.app[RUNTIME]
    async with transaction(runtime) as conn:
        await db.frontier(conn)
        binding = await runtime.auth.access(request, conn, lock=True)
        row, _ = await locked_admin(conn, binding['user_id'], cid)
        version = row['membership_version']
        deliveries = []
        now = await conn.fetchval('SELECT clock_timestamp()')
        if row['title'] != value['title']:
            await conn.execute('UPDATE conversations SET title=$1 WHERE conversation_id=$2', value['title'], cid)
            version = await increment(conn, cid)
            event = envelope('conversation.updated', cid, {'changes': {'kind': 'title', 'title': value['title']},
                'actor_id': binding['user_id'], 'membership_version': version}, now)
            deliveries = await append_group(conn, await members(conn, cid), [event])
        result = {'id': cid, 'type': 'group', 'title': value['title'], 'membership_version': version}
        position = await authority_position(conn)
    if deliveries:
        await publish_group(runtime, 'A15', cid, version, deliveries, position, now)
    return response(result)


async def add_member(request):
    cid = entity(request.match_info['conversation_id'])
    value = await body(request)
    required_keys(value, ('user_id',))
    target = entity(value['user_id'])
    key = idempotency_key(request)
    runtime = request.app[RUNTIME]
    async with transaction(runtime) as conn:
        await db.frontier(conn)
        binding = await runtime.auth.access(request, conn, lock=True)
        row, _ = await locked_admin(conn, binding['user_id'], cid)
        if not await conn.fetchval('SELECT EXISTS(SELECT 1 FROM users WHERE user_id=$1)', lookup_entity(target)):
            raise Fault('NOT_FOUND')
        canonical = {'conversation_id': cid, **value}
        old = await mutation_existing(conn, binding['user_id'], key, 'A16', canonical)
        if old is not None:
            return response(old)
        existing = await conn.fetchrow('SELECT role FROM memberships WHERE conversation_id=$1 AND user_id=$2 AND active', cid, target)
        if existing:
            result = {'user_id': target, 'role': existing['role'], 'membership_version': row['membership_version']}
            await mutation_save(conn, binding['user_id'], key, 'A16', canonical, result)
            return response(result)
        recipients = await members(conn, cid)
        if len(recipients)>=50:
            raise Fault('CONFLICT')
        boundary = await conn.fetchrow('SELECT order_value,message_id FROM messages WHERE conversation_id=$1 ORDER BY order_value DESC,message_id DESC LIMIT 1', cid)
        version = await increment(conn, cid)
        await conn.execute('''INSERT INTO memberships(conversation_id,user_id,role,joined_order,joined_message_id,joined_version)
            VALUES($1,$2,'member',$3,$4,$5) ON CONFLICT(conversation_id,user_id) DO UPDATE
            SET role='member',active=TRUE,joined_order=EXCLUDED.joined_order,
                joined_message_id=EXCLUDED.joined_message_id,joined_version=EXCLUDED.joined_version''',
            cid, target, boundary['order_value'] if boundary else 0, boundary['message_id'] if boundary else ZERO_UUID, version)
        now = await conn.fetchval('SELECT clock_timestamp()')
        event = envelope('conversation.member_added', cid, {'member_id': target, 'role': 'member',
            'actor_id': binding['user_id'], 'membership_version': version}, now)
        deliveries = await append_group(conn, await members(conn, cid), [event])
        result = {'user_id': target, 'role': 'member', 'membership_version': version}
        await mutation_save(conn, binding['user_id'], key, 'A16', canonical, result)
        position = await authority_position(conn)
    await publish_group(runtime, 'A16', cid, version, deliveries, position, now)
    return response(result, status=201)


async def protect_admin(conn, cid, target):
    role = await conn.fetchval('SELECT role FROM memberships WHERE conversation_id=$1 AND user_id=$2 AND active', cid, target)
    if role == 'admin' and await conn.fetchval("SELECT count(*) FROM memberships WHERE conversation_id=$1 AND active AND role='admin'", cid)==1:
        raise Fault('CONFLICT')


async def change_role(request):
    cid, target = entity(request.match_info['conversation_id']), entity(request.match_info['user_id'])
    value = await body(request)
    required_keys(value, ('role',))
    if value['role'] not in ('admin','member'):
        raise Fault('INVALID_ARGUMENT')
    runtime = request.app[RUNTIME]
    async with transaction(runtime) as conn:
        await db.frontier(conn)
        binding = await runtime.auth.access(request, conn, lock=True)
        row, _ = await locked_admin(conn, binding['user_id'], cid)
        existing = await conn.fetchrow('SELECT role FROM memberships WHERE conversation_id=$1 AND user_id=$2 AND active', cid, lookup_entity(target))
        if existing is None:
            raise Fault('NOT_FOUND')
        version = row['membership_version']
        now = await conn.fetchval('SELECT clock_timestamp()')
        deliveries = []
        if existing['role'] != value['role']:
            await protect_admin(conn, cid, target)
            await conn.execute('UPDATE memberships SET role=$1 WHERE conversation_id=$2 AND user_id=$3', value['role'], cid, target)
            version = await increment(conn, cid)
            event = envelope('conversation.updated', cid, {'changes': {'kind': 'role','member_id': target,'role': value['role']},
                'actor_id': binding['user_id'],'membership_version': version}, now)
            deliveries = await append_group(conn, await members(conn, cid), [event])
        result = {'user_id': target, 'role': value['role'], 'membership_version': version}
        position = await authority_position(conn)
    if deliveries:
        await publish_group(runtime, 'A17', cid, version, deliveries, position, now)
    return response(result)


async def remove_member(request):
    cid, target = entity(request.match_info['conversation_id']), entity(request.match_info['user_id'])
    runtime = request.app[RUNTIME]
    async with transaction(runtime) as conn:
        await db.frontier(conn)
        binding = await runtime.auth.access(request, conn, lock=True)
        user_id = binding['user_id']
        row = await conn.fetchrow('SELECT * FROM conversations WHERE conversation_id=$1 FOR UPDATE', lookup_entity(cid))
        if row is None:
            raise Fault('NOT_FOUND')
        actor = await conn.fetchrow('SELECT role,active FROM memberships WHERE conversation_id=$1 AND user_id=$2', cid, user_id)
        existing = await conn.fetchrow('SELECT role,active FROM memberships WHERE conversation_id=$1 AND user_id=$2', cid, lookup_entity(target))
        if row['type']!='group' or actor is None or (not actor['active'] and not (user_id==target and existing is not None)):
            raise Fault('FORBIDDEN')
        if user_id!=target and actor['role']!='admin':
            raise Fault('FORBIDDEN')
        if existing is None or not existing['active']:
            return web.Response(status=204)
        await protect_admin(conn, cid, target)
        recipients = await members(conn, cid)
        await conn.execute('UPDATE memberships SET active=FALSE WHERE conversation_id=$1 AND user_id=$2', cid, target)
        version = await increment(conn, cid)
        now = await conn.fetchval('SELECT clock_timestamp()')
        event_id = str(uuid.uuid4())
        deliveries = []
        for recipient in recipients:
            payload = {'member_id': target, 'change': 'removed', 'membership_version': version}
            if recipient['user_id'] != target:
                payload['actor_id'] = user_id
            deliveries.append({'recipient_user_id': recipient['user_id'],
                'envelope': envelope('conversation.member_removed', cid, payload, now, event_id)})
        await db.append_events(conn, deliveries)
        position = await authority_position(conn)
    await publish_group(runtime, 'A18', cid, version, deliveries, position, now)
    return web.Response(status=204)


def register(app):
    app.add_routes([web.get('/api/v1/conversations', list_conversations),
        web.post('/api/v1/conversations/direct', direct), web.post('/api/v1/conversations/groups', create_group),
        web.get('/api/v1/conversations/{conversation_id}', detail), web.patch('/api/v1/conversations/{conversation_id}', rename),
        web.post('/api/v1/conversations/{conversation_id}/members', add_member),
        web.patch('/api/v1/conversations/{conversation_id}/members/{user_id}', change_role),
        web.delete('/api/v1/conversations/{conversation_id}/members/{user_id}', remove_member)])
