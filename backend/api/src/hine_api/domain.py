"""Current PostgreSQL authority shared by public and private domain consumers."""
import secrets
import uuid as uuid_module
from contextlib import asynccontextmanager
from datetime import timezone

import asyncpg

from .support import Fault, entity, integer, keys, lookup_entity, string, uuid

ZERO_UUID = uuid_module.UUID(int=0)


def timestamp(value):
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def identifier():
    return secrets.token_urlsafe(24)


def valid_string(value, minimum=1, maximum=None):
    string(value, minimum > 0)
    if not isinstance(value, str) or len(value) < minimum or (maximum is not None and len(value) > maximum):
        raise Fault('INVALID_ARGUMENT')
    try:
        value.encode('utf-8', errors='strict')
    except UnicodeError:
        raise Fault('INVALID_ARGUMENT') from None
    return value


def required_keys(value, required, optional=()):
    return keys(value, required, optional)


def canonical_binding(value, *, device=True):
    fields = ['subject_id', 'session_id', 'session_generation']
    if device:
        fields.append('device_id')
    for key in fields:
        if key not in value:
            raise Fault('INVALID_ARGUMENT')
    entity(value['subject_id'])
    entity(value['session_id'])
    integer(value['session_generation'], 1)
    if device:
        valid_string(value['device_id'])


def parse_uuid(value):
    return uuid_module.UUID(uuid(value))


@asynccontextmanager
async def transaction(runtime, *, isolation='read_committed', write=True):
    async with runtime.pool.acquire() as conn:
        tx = conn.transaction(isolation=isolation)
        await tx.start()
        try:
            yield conn
        except BaseException as failure:
            if not conn.is_closed() and conn.is_in_transaction():
                try:
                    await tx.rollback()
                except (asyncpg.PostgresError, asyncpg.InterfaceError, OSError, TimeoutError):
                    pass
            if isinstance(failure, (asyncpg.PostgresError, asyncpg.InterfaceError, OSError, TimeoutError)):
                # COMMIT was never sent: product writes cannot have escaped this transaction.
                raise Fault('PERSISTENCE_FAILED' if write else 'DEPENDENCY_UNAVAILABLE', retryable=True) from None
            raise
        else:
            try:
                await tx.commit()
            except (asyncpg.PostgresError, asyncpg.InterfaceError, OSError, TimeoutError):
                raise Fault('OUTCOME_UNCONFIRMED' if write else 'DEPENDENCY_UNAVAILABLE', retryable=True) from None


async def current_member(conn, user_id, conversation_id):
    return await conn.fetchrow('SELECT * FROM memberships WHERE conversation_id=$1 AND user_id=$2 AND active', lookup_entity(conversation_id), user_id)


async def can_read_conversation(conn, user_id, conversation_id):
    return await current_member(conn, user_id, conversation_id) is not None


async def can_read_message(conn, user_id, message_id):
    try:
        mid = uuid_module.UUID(str(message_id))
    except ValueError:
        return False
    return bool(await conn.fetchval('''SELECT EXISTS (
        SELECT 1 FROM messages m JOIN memberships p ON p.conversation_id=m.conversation_id
        WHERE m.message_id=$1 AND p.user_id=$2 AND p.active
          AND (m.order_value,m.message_id)>(p.joined_order,p.joined_message_id))''', mid, user_id))


async def visible_avatar(conn, viewer_id, owner_id):
    if viewer_id == owner_id:
        return True
    return bool(await conn.fetchval('''SELECT EXISTS(SELECT 1 FROM contacts WHERE owner_id=$1 AND contact_id=$2)
        OR EXISTS(SELECT 1 FROM memberships a JOIN memberships b USING(conversation_id)
          WHERE a.user_id=$1 AND b.user_id=$2 AND a.active AND b.active)''', viewer_id, owner_id))


async def can_read_attachment(conn, user_id, attachment_id):
    attachment = await conn.fetchrow('SELECT * FROM attachments WHERE attachment_id=$1', lookup_entity(attachment_id))
    if attachment is None:
        return False
    if attachment['scope'] == 'avatar':
        if attachment['uploader_id'] == user_id:
            return True
        selected = await conn.fetchval('SELECT avatar_attachment_id FROM users WHERE user_id=$1', attachment['uploader_id'])
        return selected == attachment_id and await visible_avatar(conn, user_id, attachment['uploader_id'])
    if not await can_read_conversation(conn, user_id, attachment['conversation_id']):
        return False
    referenced = await conn.fetchval('SELECT EXISTS(SELECT 1 FROM messages WHERE conversation_id=$1 AND attachment_id=$2)',
                                    attachment['conversation_id'], attachment_id)
    if not referenced:
        return attachment['uploader_id'] == user_id
    return bool(await conn.fetchval('''SELECT EXISTS(SELECT 1 FROM messages m
        JOIN memberships p ON p.conversation_id=m.conversation_id
        WHERE m.conversation_id=$1 AND m.attachment_id=$2
          AND p.user_id=$3 AND p.active
          AND (m.order_value,m.message_id)>(p.joined_order,p.joined_message_id))''',
        attachment['conversation_id'], attachment_id, user_id))


async def get_public_profile(conn, user_id, viewer_id):
    row = await conn.fetchrow('SELECT user_id,display_name,avatar_attachment_id FROM users WHERE user_id=$1', lookup_entity(user_id))
    if row is None:
        raise Fault('NOT_FOUND')
    avatar = row['avatar_attachment_id']
    if avatar is not None:
        ready = await conn.fetchval("SELECT EXISTS(SELECT 1 FROM attachments WHERE attachment_id=$1 AND state='ready' AND scope='avatar' AND uploader_id=$2)", avatar, user_id)
        if not ready or not await visible_avatar(conn, viewer_id, user_id):
            avatar = None
    return {'id': row['user_id'], 'display_name': row['display_name'], 'avatar_attachment_id': avatar}


async def conversation_member(conn, user_id, conversation_id, *, lock=None, absent='FORBIDDEN'):
    query = 'SELECT * FROM conversations WHERE conversation_id=$1'
    if lock == 'write':
        query += ' FOR UPDATE'
    elif lock == 'share':
        query += ' FOR SHARE'
    conversation = await conn.fetchrow(query, lookup_entity(conversation_id))
    if conversation is None:
        raise Fault('NOT_FOUND')
    member = await current_member(conn, user_id, conversation_id)
    if member is None:
        raise Fault(absent)
    return conversation, member


async def authority_position(conn):
    return await conn.fetchval('SELECT position FROM authority_state WHERE id=1')


async def authorize(runtime, value):
    required_keys(value, ('subject_id','device_id','session_id','session_generation','action','resource_type','resource_id'))
    canonical_binding(value)
    entity(value['resource_id'])
    action, kind = value['action'], value['resource_type']
    if action not in ('send','receive','read','history','attachment','manage_group') or kind not in ('conversation','message','attachment'):
        raise Fault('INVALID_ARGUMENT')
    async with transaction(runtime, isolation='repeatable_read', write=False) as conn:
        binding = await runtime.auth.binding(conn, value)
        user_id = binding['user_id']
        version = 0
        if kind == 'conversation':
            row = await conn.fetchrow('SELECT * FROM conversations WHERE conversation_id=$1', lookup_entity(value['resource_id']))
            if row is None:
                raise Fault('NOT_FOUND')
            member = await current_member(conn, user_id, value['resource_id'])
            allowed = member is not None
            if action == 'manage_group':
                allowed = allowed and row['type'] == 'group' and member['role'] == 'admin'
            version = row['membership_version'] or 0
        elif kind == 'message':
            try:
                mid = uuid_module.UUID(value['resource_id'])
            except ValueError:
                raise Fault('NOT_FOUND') from None
            row = await conn.fetchrow('SELECT conversation_id,membership_version FROM messages WHERE message_id=$1', mid)
            if row is None:
                raise Fault('NOT_FOUND')
            allowed = action in ('receive','read','history') and await can_read_message(conn, user_id, mid)
            version = await conn.fetchval('SELECT membership_version FROM conversations WHERE conversation_id=$1', row['conversation_id']) or 0
        else:
            exists = await conn.fetchval('SELECT EXISTS(SELECT 1 FROM attachments WHERE attachment_id=$1)', lookup_entity(value['resource_id']))
            if not exists:
                raise Fault('NOT_FOUND')
            allowed = action == 'attachment' and await can_read_attachment(conn, user_id, value['resource_id'])
        position = await authority_position(conn)
        return {'allowed': bool(allowed), 'authorization_version': f'{position}:{version}'}


async def publish_group(runtime, source, conversation_id, version, deliveries, position, committed_at):
    """Notices are acceleration only; every matching feed record already committed."""
    batches, batch, size = [], [], 0
    from hine_realtime import protocol as p
    for delivery in deliveries:
        encoded_size = len(p.dumps(delivery).encode('utf-8')) + 1
        if batch and size + encoded_size > 700_000:
            batches.append(batch)
            batch, size = [], 0
        batch.append(delivery)
        size += encoded_size
    if batch:
        batches.append(batch)
    for batch in batches:
        await runtime.notify({'notice_id': str(uuid_module.uuid4()), 'type': 'conversation_events',
            'committed_at': timestamp(committed_at), 'invalidation_position': position,
            'conversation_events': {'source': source, 'conversation_id': conversation_id,
                'membership_version': version, 'deliveries': batch}})


def register(app):
    from . import conversations, messages, profiles
    profiles.register(app)
    conversations.register(app)
    messages.register(app)


async def internal(runtime, operation, value):
    from . import messages, receipts, synchronization
    operations = {'authorize': authorize, 'persistIfAbsent': messages.persist,
        'persistReceipt': receipts.persist, 'readBootstrap': synchronization.bootstrap,
        'readFeed': synchronization.feed, 'readPresenceTargets': synchronization.presence_targets}
    handler = operations.get(operation)
    if handler is None:
        raise Fault('INVALID_ARGUMENT')
    return await handler(runtime, value)
