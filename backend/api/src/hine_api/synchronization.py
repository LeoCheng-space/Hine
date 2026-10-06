"""Opaque PostgreSQL cursors, frozen bootstrap snapshots and commit-safe feeds."""
import hmac
import re
import secrets
from base64 import urlsafe_b64encode
from uuid import UUID

from hine_realtime import protocol as p

from .domain import (
    authority_position,
    canonical_binding,
    current_member,
    entity,
    identifier,
    required_keys,
    transaction,
    valid_string,
)
from .support import Fault, lookup_entity

REST_CURSOR_SECONDS = 900
SYNC_CURSOR_SECONDS = 1209600
SNAPSHOT_SECONDS = 300
MAX_RESPONSE_BYTES = 1048576

_BUDGET_UUID = 'ffffffff-ffff-4fff-bfff-ffffffffffff'
_BUDGET_TIMESTAMP = '9999-12-31T23:59:59.999Z'
_INTERNAL_WRAPPER_BYTES = len(p.dumps({'data': {}}).encode('utf-8')) - 2
_SYNC_WRAPPER_BYTES = {
    event: len(p.dumps(p.event(event, {}, correlation=_BUDGET_UUID,
        event_id=_BUDGET_UUID, time=_BUDGET_TIMESTAMP)).encode('utf-8')) - 2
    for event in ('sync.bootstrap.page', 'sync.batch')
}


def rest_arguments(request, cursor_key):
    if set(request.query) - {'limit', cursor_key}:
        raise Fault('INVALID_ARGUMENT')
    limits = request.query.getall('limit', [])
    if len(limits)>1:
        raise Fault('INVALID_ARGUMENT')
    limit = 20
    if limits:
        if not re.fullmatch(r'[0-9]+', limits[0]) or len(limits[0])>10:
            raise Fault('INVALID_ARGUMENT')
        limit = int(limits[0])
        if not 1<=limit<=50:
            raise Fault('INVALID_ARGUMENT')
    values = request.query.getall(cursor_key, [])
    if len(values)>1 or (values and values[0] in ('','null')):
        raise Fault('CURSOR_INVALID')
    return limit, values[0] if values else None


def cursor_signature(runtime, user_id, scope, nonce):
    key = hmac.digest(runtime.settings.jwt_signing_key.encode('utf-8'), b'HINE cursor signing', 'sha256')
    message = scope.encode('utf-8') + b'\x00' + user_id.encode('utf-8') + b'\x00' + nonce.encode('utf-8')
    return urlsafe_b64encode(hmac.digest(key, message, 'sha256')).rstrip(b'=').decode('ascii')


def cursor_issue(runtime, user_id, scope):
    nonce = secrets.token_urlsafe(32)
    return nonce + '.' + cursor_signature(runtime, user_id, scope, nonce)


def cursor_verify(runtime, token, user_id, scope):
    valid_string(token)
    nonce, separator, signature = token.partition('.')
    expected = cursor_signature(runtime, user_id, scope, nonce)
    if not separator or not hmac.compare_digest(signature.encode('utf-8'), expected.encode('ascii')):
        raise Fault('CURSOR_INVALID')


async def rest_store(runtime, conn, user_id, scope, state, *, expires_at=None):
    token = cursor_issue(runtime, user_id, 'rest:'+scope)
    if expires_at is None:
        expires_at = await conn.fetchval("SELECT clock_timestamp()+($1::int * interval '1 second')", REST_CURSOR_SECONDS)
    await conn.execute('INSERT INTO rest_cursors(token,user_id,scope,state,expires_at) VALUES($1,$2,$3,$4,$5)',
                       token, user_id, scope, state, expires_at)
    return token


async def rest_load(runtime, conn, token, user_id, scope, *, sync=False, presence=False):
    cursor_verify(runtime, token, user_id, 'rest:'+scope)
    row = await conn.fetchrow('SELECT * FROM rest_cursors WHERE token=$1 AND user_id=$2 AND scope=$3', token, user_id, scope)
    if row is None:
        raise Fault('CURSOR_INVALID')
    now = await conn.fetchval('SELECT clock_timestamp()')
    if row['expires_at']<=now:
        raise Fault('SYNC_RESET_REQUIRED' if sync else 'CURSOR_INVALID' if presence else 'CURSOR_EXPIRED')
    return row['state']


async def sync_store(runtime, conn, user_id, position, *, boundary=None, kind='progress'):
    token = cursor_issue(runtime, user_id, 'sync:'+kind)
    await conn.execute("INSERT INTO sync_cursors(token,user_id,position,boundary,kind,expires_at) VALUES($1,$2,$3,$4,$5,clock_timestamp()+($6::int*interval '1 second'))",
                       token, user_id, position, boundary, kind, SYNC_CURSOR_SECONDS)
    return token


async def sync_load(runtime, conn, token, user_id, kind):
    cursor_verify(runtime, token, user_id, 'sync:'+kind)
    row = await conn.fetchrow('SELECT * FROM sync_cursors WHERE token=$1 AND user_id=$2 AND kind=$3', token, user_id, kind)
    if row is None:
        raise Fault('CURSOR_INVALID')
    if row['expires_at']<=await conn.fetchval('SELECT clock_timestamp()'):
        raise Fault('SYNC_RESET_REQUIRED')
    return row


def encoded_size(data, event):
    # BA embeds the same result in payload, with real UUID, millisecond UTC
    # timestamp and correlation fields. Their maximum encoded lengths are fixed
    # by p.event/p.now/p.uuid; count that actual wrapper as well as private HTTP.
    payload_bytes = len(p.dumps(data).encode('utf-8'))
    return payload_bytes + max(_INTERNAL_WRAPPER_BYTES, _SYNC_WRAPPER_BYTES[event])


def fits(data, event):
    return encoded_size(data, event) <= MAX_RESPONSE_BYTES


async def snapshot_content(conn, user_id, page_limit):
    from .conversations import unread
    from .messages import project
    rows = await conn.fetch('''SELECT c.*,m.role,m.joined_order,m.joined_message_id,m.joined_version FROM conversations c
        JOIN memberships m USING(conversation_id) WHERE m.user_id=$1 AND m.active
        ORDER BY c.conversation_id COLLATE "C"''', user_id)
    content = []
    for row in rows:
        messages = await conn.fetch('''SELECT * FROM messages WHERE conversation_id=$1
            AND (order_value,message_id)>($2,$3) ORDER BY order_value DESC,message_id DESC LIMIT $4''',
            row['conversation_id'], row['joined_order'], row['joined_message_id'], min(10, max(0,page_limit-1)))
        conversation = {'id': row['conversation_id'], 'type': row['type'], 'title': row['title'],
            'unread_count': await unread(conn, user_id, row['conversation_id']),
            'my_role': row['role'] if row['type']=='group' else None,
            'recent_messages': [await project(conn, message, user_id, row['type']) for message in reversed(messages)]}
        # The recent window is explicitly bounded; discard oldest entries only at H,
        # never truncate an already materialized continuation or message body.
        probe = {'snapshot_id': 'X'*32,'start_cursor':'X'*128,'conversations':[conversation],
                 'next_page_token':'X'*128,'has_more':False}
        while not fits(probe, 'sync.bootstrap.page') and conversation['recent_messages']:
            conversation['recent_messages'].pop(0)
        if not fits(probe, 'sync.bootstrap.page'):
            raise Fault('PAYLOAD_TOO_LARGE')
        content.append({'conversation': conversation, 'joined_order': row['joined_order'],
                        'joined_message_id': str(row['joined_message_id']), 'joined_version': row['joined_version']})
    return content


async def bootstrap(runtime, value):
    required_keys(value, ('subject_id','session_id','session_generation','reason'), ('snapshot_id','page_token'))
    canonical_binding(value, device=False)
    if value['reason'] not in ('first_login','cursor_reset'):
        raise Fault('INVALID_ARGUMENT')
    paired = 'snapshot_id' in value or 'page_token' in value
    if paired and not ('snapshot_id' in value and 'page_token' in value):
        raise Fault('INVALID_ARGUMENT')
    if paired:
        entity(value['snapshot_id'])
        valid_string(value['page_token'])
    async with transaction(runtime, isolation='repeatable_read', write=False) as conn:
        binding = await runtime.auth.binding(conn, value)
        user_id = binding['user_id']
        if not paired:
            head = await conn.fetchval('SELECT position FROM feed_heads WHERE user_id=$1', user_id)
            if head is None:
                raise Fault('PERSISTENCE_FAILED')
            sid = identifier()
            content = await snapshot_content(conn, user_id, runtime.settings.sync_page_limit)
            start = await sync_store(runtime, conn, user_id, head)
            expires = await conn.fetchval("SELECT clock_timestamp()+($1::int*interval '1 second')", SNAPSHOT_SECONDS)
            saved = {'conversations': content, 'start_cursor': start, 'reason': value['reason']}
            await conn.execute('INSERT INTO snapshots(snapshot_id,user_id,head_position,content,expires_at) VALUES($1,$2,$3,$4,$5)', sid, user_id, head, saved, expires)
            offset = 0
        else:
            sid = value['snapshot_id']
            snapshot = await conn.fetchrow('SELECT * FROM snapshots WHERE snapshot_id=$1 AND user_id=$2', lookup_entity(sid), user_id)
            if snapshot is None:
                raise Fault('CURSOR_INVALID')
            if snapshot['expires_at']<=await conn.fetchval('SELECT clock_timestamp()'):
                raise Fault('SYNC_RESET_REQUIRED')
            saved, expires = snapshot['content'], snapshot['expires_at']
            if saved['reason']!=value['reason']:
                raise Fault('CURSOR_INVALID')
            state = await rest_load(runtime, conn, value['page_token'], user_id, 'bootstrap:'+sid, sync=True)
            offset = state['offset']
            start = saved['start_cursor']
            content = saved['conversations']
        result = {'snapshot_id': sid, 'start_cursor': start, 'conversations': [], 'next_page_token': None, 'has_more': False}
        logical = 0
        while offset<len(content):
            entry = content[offset]
            conversation = entry['conversation']
            member = await current_member(conn, user_id, conversation['id'])
            if member is None or member['joined_version']!=entry['joined_version'] or member['joined_order']!=entry['joined_order'] or str(member['joined_message_id'])!=entry['joined_message_id']:
                offset += 1
                continue
            cost = 1+len(conversation['recent_messages'])
            if result['conversations'] and logical+cost>runtime.settings.sync_page_limit:
                break
            candidate = {**result, 'conversations': result['conversations']+[conversation],
                         'next_page_token':'X'*128,'has_more':False}
            if not fits(candidate, 'sync.bootstrap.page'):
                if result['conversations']:
                    break
                raise Fault('PAYLOAD_TOO_LARGE')
            result['conversations'].append(conversation)
            logical += cost
            offset += 1
        if offset<len(content):
            result['has_more'] = True
            result['next_page_token'] = await rest_store(runtime, conn, user_id, 'bootstrap:'+sid, {'offset': offset}, expires_at=expires)
    return result


def visible_event(user_id, event, members, readable_messages):
    cid = event['conversation_id']
    if event['event']=='conversation.member_removed' and event['payload']['member_id']==user_id:
        # Retain only the privacy-minimal self notification, even after rejoining.
        return {key: event[key] for key in ('event','event_id','timestamp','conversation_id')} | {
            'payload': {key: event['payload'][key] for key in ('member_id','change','membership_version')}}
    member = members.get(cid)
    if member is None:
        return None
    if event['event'] in ('message.created','message.status'):
        return event if event['payload']['message_id'] in readable_messages else None
    if event['event'] in ('conversation.member_added','conversation.member_removed','conversation.updated'):
        if not member['joined_version']<=event['payload']['membership_version']<=member['membership_version']:
            return None
        return event
    return None


async def feed_authority(conn, user_id, rows):
    if not rows:
        return {}, set()
    conversation_ids = list({row['envelope']['conversation_id'] for row in rows})
    membership_rows = await conn.fetch('''SELECT m.*,c.membership_version FROM memberships m
        JOIN conversations c USING(conversation_id) WHERE m.user_id=$1 AND m.active
          AND m.conversation_id=ANY($2::text[])''', user_id, conversation_ids)
    members = {row['conversation_id']: row for row in membership_rows}
    message_ids = [UUID(row['envelope']['payload']['message_id']) for row in rows
                   if row['envelope']['event'] in ('message.created','message.status')]
    readable = set()
    if message_ids:
        readable_rows = await conn.fetch('''SELECT m.message_id FROM messages m JOIN memberships p USING(conversation_id)
            WHERE p.user_id=$1 AND p.active AND m.message_id=ANY($2::uuid[])
              AND (m.order_value,m.message_id)>(p.joined_order,p.joined_message_id)''', user_id, message_ids)
        readable = {str(row['message_id']) for row in readable_rows}
    return members, readable


async def feed(runtime, value):
    required_keys(value, ('subject_id','session_id','session_generation','cursor','limit'), ('snapshot_boundary',))
    canonical_binding(value, device=False)
    valid_string(value['cursor'])
    limit = value['limit']
    if type(limit) is not int or not 1<=limit<=100:
        raise Fault('INVALID_ARGUMENT')
    if 'snapshot_boundary' in value:
        valid_string(value['snapshot_boundary'])
    async with transaction(runtime, isolation='repeatable_read', write=False) as conn:
        binding = await runtime.auth.binding(conn, value)
        user_id = binding['user_id']
        cursor = await sync_load(runtime, conn, value['cursor'], user_id, 'progress')
        head = await conn.fetchval('SELECT position FROM feed_heads WHERE user_id=$1', user_id)
        position = cursor['position']
        if head is None or position>head:
            raise Fault('CURSOR_INVALID')
        if 'snapshot_boundary' in value:
            boundary_cursor = await sync_load(runtime, conn, value['snapshot_boundary'], user_id, 'boundary')
            boundary, boundary_token = boundary_cursor['position'], value['snapshot_boundary']
            if boundary>head or position>boundary or (cursor['boundary'] is not None and cursor['boundary']!=boundary):
                raise Fault('CURSOR_INVALID')
        else:
            boundary = head
            boundary_token = await sync_store(runtime, conn, user_id, boundary, kind='boundary')
        rows = await conn.fetch('SELECT position,envelope FROM user_feed WHERE user_id=$1 AND position>$2 AND position<=$3 ORDER BY position LIMIT $4',
                                user_id, position, boundary, runtime.settings.sync_scan_limit)
        members, readable_messages = await feed_authority(conn, user_id, rows)
        result = {'snapshot_boundary': boundary_token, 'events': [], 'next_cursor': value['cursor'], 'has_more': False}
        packed_size = encoded_size({**result, 'next_cursor':'X'*128,'has_more':False}, 'sync.batch')
        scanned = position
        for row in rows:
            event = visible_event(user_id, row['envelope'], members, readable_messages)
            if event is not None:
                event_size = len(p.dumps(event).encode('utf-8')) + (1 if result['events'] else 0)
                if packed_size + event_size > MAX_RESPONSE_BYTES:
                    if not result['events']:
                        raise Fault('PAYLOAD_TOO_LARGE')
                    break
                result['events'].append(event)
                packed_size += event_size
            scanned = row['position']
            if len(result['events'])>=limit:
                break
        result['has_more'] = scanned<boundary
        if scanned!=position:
            result['next_cursor'] = await sync_store(runtime, conn, user_id, scanned, boundary=boundary)
    return result


async def presence_targets(runtime, value):
    required_keys(value, ('subject_id','session_id','session_generation','limit'), ('cursor','contact_user_id'))
    canonical_binding(value, device=False)
    limit = value['limit']
    if type(limit) is not int or not 1<=limit<=100:
        raise Fault('INVALID_ARGUMENT')
    target = value.get('contact_user_id')
    if 'contact_user_id' in value:
        entity(target)
    if 'cursor' in value:
        valid_string(value['cursor'])
    async with transaction(runtime, isolation='repeatable_read', write=False) as conn:
        binding = await runtime.auth.binding(conn, value)
        user_id = binding['user_id']
        scope = 'presence'
        state = await rest_load(runtime, conn, value['cursor'], user_id, scope, presence=True) if 'cursor' in value else {'after': '', 'target': target}
        if state.get('target')!=target:
            raise Fault('CURSOR_INVALID')
        rows = await conn.fetch('''SELECT u.user_id,u.subject_id FROM contacts c JOIN users u ON u.user_id=c.contact_id
            WHERE c.owner_id=$1 AND c.contact_id COLLATE "C">$2 AND ($3::boolean OR c.contact_id=$4)
            ORDER BY c.contact_id COLLATE "C" LIMIT $5''', user_id, state['after'], target is None, lookup_entity(target) if target is not None else None, limit+1)
        targets = [dict(row) for row in rows[:limit]]
        next_cursor = await rest_store(runtime, conn, user_id, scope, {'after': rows[limit-1]['user_id'],'target':target}) if len(rows)>limit else None
        position = await authority_position(conn)
    return {'targets': targets, 'next_cursor': next_cursor, 'invalidation_position': position}
