"""C1 deduplication, authoritative quota, recipient snapshots and stable replay."""
import math
import uuid

from aiohttp import web

from . import db
from .domain import (
    authority_position,
    can_read_attachment,
    canonical_binding,
    conversation_member,
    entity,
    parse_uuid,
    required_keys,
    timestamp,
    transaction,
    valid_string,
)
from .server import RUNTIME
from .support import Fault, list_response, lookup_entity


async def project(conn, row, viewer_id, conversation_type):
    result = {'id': str(row['message_id']), 'event_id': str(row['event_id']),
        'conversation_id': row['conversation_id'], 'sender_id': row['sender_id'],
        'created_at': timestamp(row['created_at']), 'order_key': f"{row['order_value']:020d}",
        'type': row['type'], 'receipt': None, **row['payload']}
    if row['sender_id'] == viewer_id:
        result['client_message_id'] = str(row['client_message_id'])
    if conversation_type == 'direct' and row['sender_id'] == viewer_id:
        receipt = await conn.fetchrow('SELECT * FROM receipts WHERE message_id=$1 AND user_id<>$2', row['message_id'], row['sender_id'])
        if receipt:
            result['receipt'] = {'kind': 'direct', 'message_id': str(row['message_id']),
                'recipient_id': receipt['user_id'], 'status': receipt['status'], 'updated_at': timestamp(receipt['updated_at'])}
    return result


def persisted(row):
    return {'message_id': str(row['message_id']), 'event_id': str(row['event_id']),
        'order_key': f"{row['order_value']:020d}", 'created_at': timestamp(row['created_at']),
        'recipient_ids': list(row['recipient_ids']), 'status': 'persisted',
        'invalidation_position': row['invalidation_position'], 'membership_version': row['membership_version']}


def canonical_send(value):
    required_keys(value, ('subject_id','device_id','session_id','session_generation','conversation_id',
                          'client_message_id','type','payload','request_event_id'))
    canonical_binding(value)
    entity(value['conversation_id'])
    c1, request_id = parse_uuid(value['client_message_id']), parse_uuid(value['request_event_id'])
    if value['type'] == 'text':
        required_keys(value['payload'], ('text',))
        valid_string(value['payload']['text'], maximum=4096)
    elif value['type'] in ('image','file'):
        required_keys(value['payload'], ('attachment_id',))
        entity(value['payload']['attachment_id'])
    else:
        raise Fault('INVALID_ARGUMENT')
    return c1, request_id


async def quota(conn, subject_id):
    now = await conn.fetchval('SELECT clock_timestamp()')
    row = await conn.fetchrow('SELECT * FROM message_quota WHERE subject_id=$1 FOR UPDATE', subject_id)
    available = 10.0 if row is None else min(10.0, row['tokens'] + max(0.0, (now-row['updated_at']).total_seconds()) * 5)
    if available < 1:
        raise Fault('RATE_LIMITED', retryable=True, retry_after_ms=max(1, math.ceil((1-available) * 200)))
    await conn.execute('''INSERT INTO message_quota(subject_id,tokens,updated_at) VALUES($1,$2,$3)
        ON CONFLICT(subject_id) DO UPDATE SET tokens=EXCLUDED.tokens,updated_at=EXCLUDED.updated_at''', subject_id, available-1, now)


async def persist(runtime, value):
    c1, _ = canonical_send(value)
    async with transaction(runtime) as conn:
        await db.frontier(conn)
        binding = await runtime.auth.binding(conn, value, lock=True)
        # Subject-wide lock precedes C1 inspection, including different-device races.
        await conn.execute('SELECT pg_advisory_xact_lock(hashtextextended($1,3))', binding['subject_id'])
        conversation, _ = await conversation_member(conn, binding['user_id'], value['conversation_id'], lock='share')
        if value['type'] != 'text':
            attachment = await conn.fetchrow('SELECT * FROM attachments WHERE attachment_id=$1 FOR SHARE', lookup_entity(value['payload']['attachment_id']))
            if attachment is None or attachment['scope']!='conversation' or attachment['conversation_id']!=value['conversation_id'] or attachment['kind']!=value['type']:
                raise Fault('FORBIDDEN')
            if attachment['state']!='ready':
                raise Fault('UPLOAD_NOT_READY')
            if attachment['uploader_id']!=binding['user_id'] and not await can_read_attachment(conn, binding['user_id'], attachment['attachment_id']):
                raise Fault('FORBIDDEN')
        previous = await conn.fetchrow('SELECT * FROM messages WHERE subject_id=$1 AND client_message_id=$2', binding['subject_id'], c1)
        if previous is not None:
            if previous['conversation_id']!=value['conversation_id'] or previous['type']!=value['type'] or previous['payload']!=value['payload']:
                raise Fault('IDEMPOTENCY_CONFLICT')
            return persisted(previous)
        await quota(conn, binding['subject_id'])
        recipients = [r['user_id'] for r in await conn.fetch('SELECT user_id FROM memberships WHERE conversation_id=$1 AND active ORDER BY user_id COLLATE "C"', value['conversation_id'])]
        position = await authority_position(conn)
        row = await conn.fetchrow('''INSERT INTO messages(message_id,event_id,conversation_id,sender_id,subject_id,
            client_message_id,type,payload,order_value,invalidation_position,membership_version,recipient_ids,attachment_id)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,nextval('message_order'),$9,$10,$11,$12) RETURNING *''',
            uuid.uuid4(), uuid.uuid4(), value['conversation_id'], binding['user_id'], binding['subject_id'], c1,
            value['type'], value['payload'], position, conversation['membership_version'], recipients, value['payload'].get('attachment_id'))
        deliveries = []
        for recipient in recipients:
            payload = {'message_id': str(row['message_id']), 'type': row['type'],
                       'order_key': f"{row['order_value']:020d}", **row['payload']}
            if recipient == binding['user_id']:
                payload['client_message_id'] = str(c1)
            event = {'event': 'message.created', 'event_id': str(row['event_id']),
                'timestamp': timestamp(row['created_at']), 'conversation_id': value['conversation_id'],
                'sender_id': binding['user_id'], 'payload': payload}
            deliveries.append({'recipient_user_id': recipient, 'envelope': event})
        await db.append_events(conn, deliveries)
        # Shared frontier lock keeps W unchanged; read at final authorization statement.
        final_position = await authority_position(conn)
        result = persisted(row)
        result['invalidation_position'] = final_position
    return result


async def history(request):
    from .synchronization import rest_arguments, rest_load, rest_store
    cid = entity(request.match_info['conversation_id'])
    limit, cursor = rest_arguments(request, 'before')
    runtime = request.app[RUNTIME]
    async with transaction(runtime, isolation='repeatable_read', write=False) as conn:
        binding = await runtime.auth.access(request, conn)
        user_id = binding['user_id']
        conversation, member = await conversation_member(conn, user_id, cid, absent='NOT_FOUND')
        scope = 'history:' + cid
        state = await rest_load(runtime, conn, cursor, user_id, scope) if cursor else {}
        order = state.get('order', 9223372036854775807)
        mid = uuid.UUID(state.get('message_id', 'ffffffff-ffff-ffff-ffff-ffffffffffff'))
        rows = await conn.fetch('''SELECT * FROM messages WHERE conversation_id=$1
            AND (order_value,message_id)>($2,$3) AND (order_value,message_id)<($4,$5)
            ORDER BY order_value DESC,message_id DESC LIMIT $6''', cid, member['joined_order'], member['joined_message_id'], order, mid, limit+1)
        items = [await project(conn, row, user_id, conversation['type']) for row in rows[:limit]]
        next_cursor = await rest_store(runtime, conn, user_id, scope, {'order': rows[limit-1]['order_value'], 'message_id': str(rows[limit-1]['message_id'])}) if len(rows)>limit else None
    return list_response(items, next_cursor)


def register(app):
    app.add_routes([web.get('/api/v1/conversations/{conversation_id}/messages', history)])
