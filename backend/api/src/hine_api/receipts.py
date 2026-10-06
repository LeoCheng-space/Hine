"""Per-user monotone receipt state; direct senders alone observe W10."""
import uuid

from . import db
from .domain import (
    authority_position,
    can_read_message,
    canonical_binding,
    conversation_member,
    entity,
    parse_uuid,
    required_keys,
    timestamp,
    transaction,
)
from .support import Fault


async def persist(runtime, value):
    required_keys(value, ('subject_id','device_id','session_id','session_generation','conversation_id','message_id','kind','request_event_id'))
    canonical_binding(value)
    entity(value['conversation_id'])
    message_id = parse_uuid(value['message_id'])
    parse_uuid(value['request_event_id'])
    if value['kind'] not in ('delivered','read'):
        raise Fault('INVALID_ARGUMENT')
    async with transaction(runtime) as conn:
        await db.frontier(conn)
        binding = await runtime.auth.binding(conn, value, lock=True)
        conversation, _ = await conversation_member(conn, binding['user_id'], value['conversation_id'], lock='share')
        message = await conn.fetchrow('SELECT * FROM messages WHERE message_id=$1 FOR UPDATE', message_id)
        if message is None or message['conversation_id']!=value['conversation_id']:
            raise Fault('NOT_FOUND')
        user_id = binding['user_id']
        if message['sender_id']==user_id or user_id not in message['recipient_ids'] or not await can_read_message(conn, user_id, message_id):
            raise Fault('FORBIDDEN')
        prior = await conn.fetchrow('SELECT * FROM receipts WHERE message_id=$1 AND user_id=$2', message_id, user_id)
        changed = prior is None or (prior['status']=='delivered' and value['kind']=='read')
        observers, status_event_id = [], None
        if changed:
            status = value['kind']
            now = await conn.fetchval('SELECT clock_timestamp()')
            if conversation['type']=='direct' and await can_read_message(conn, message['sender_id'], message_id):
                observers = [message['sender_id']]
                status_event_id = uuid.uuid4()
            await conn.execute('''INSERT INTO receipts(message_id,user_id,status,updated_at,status_event_id)
                VALUES($1,$2,$3,$4,$5) ON CONFLICT(message_id,user_id) DO UPDATE
                SET status=EXCLUDED.status,updated_at=EXCLUDED.updated_at,status_event_id=EXCLUDED.status_event_id''',
                message_id, user_id, status, now, status_event_id)
            if status_event_id is not None:
                projection = {'kind': 'direct', 'message_id': str(message_id), 'recipient_id': user_id,
                              'status': status, 'updated_at': timestamp(now)}
                event = {'event': 'message.status', 'event_id': str(status_event_id), 'timestamp': timestamp(now),
                         'conversation_id': value['conversation_id'], 'payload': projection}
                await db.append_events(conn, [{'recipient_user_id': observer, 'envelope': event} for observer in observers])
        else:
            status, now = prior['status'], prior['updated_at']
        position = await authority_position(conn)
        result = {'message_id': str(message_id), 'status': status, 'changed': changed,
            'updated_at': timestamp(now), 'status_event_id': str(status_event_id) if status_event_id else None,
            'invalidation_position': position, 'observer_ids': observers,
            'membership_version': conversation['membership_version']}
    return result
