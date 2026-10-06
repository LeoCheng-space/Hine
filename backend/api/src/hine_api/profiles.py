"""Self-only profiles, known-ID summaries and owner-scoped contacts."""
import asyncio

import aiohttp
from aiohttp import web

from . import db
from .domain import (
    authority_position,
    entity,
    get_public_profile,
    required_keys,
    timestamp,
    transaction,
    valid_string,
)
from .server import RUNTIME
from .support import Fault, body, list_response, lookup_entity, response


async def self_profile(conn, user_id):
    profile = await get_public_profile(conn, user_id, user_id)
    profile['email'] = await conn.fetchval('SELECT email FROM users WHERE user_id=$1', user_id)
    return profile


async def me(request):
    runtime = request.app[RUNTIME]
    async with transaction(runtime, isolation='repeatable_read', write=False) as conn:
        binding = await runtime.auth.access(request, conn)
        result = await self_profile(conn, binding['user_id'])
    return response(result)


async def update_me(request):
    value = await body(request)
    required_keys(value, (), ('display_name','avatar_attachment_id'))
    if not value:
        raise Fault('INVALID_ARGUMENT')
    if 'display_name' in value:
        valid_string(value['display_name'])
    if value.get('avatar_attachment_id') is not None:
        entity(value['avatar_attachment_id'])
    runtime = request.app[RUNTIME]
    async with transaction(runtime) as conn:
        await db.frontier(conn)
        binding = await runtime.auth.access(request, conn, lock=True)
        user_id = binding['user_id']
        if value.get('avatar_attachment_id') is not None:
            attachment = await conn.fetchrow('SELECT * FROM attachments WHERE attachment_id=$1 FOR SHARE', lookup_entity(value['avatar_attachment_id']))
            if attachment is None or attachment['uploader_id'] != user_id or attachment['scope'] != 'avatar':
                raise Fault('FORBIDDEN')
            if attachment['state'] != 'ready':
                raise Fault('UPLOAD_NOT_READY')
        if 'display_name' in value:
            await conn.execute('UPDATE users SET display_name=$1 WHERE user_id=$2', value['display_name'], user_id)
        if 'avatar_attachment_id' in value:
            await conn.execute('UPDATE users SET avatar_attachment_id=$1 WHERE user_id=$2', value['avatar_attachment_id'], user_id)
        result = await self_profile(conn, user_id)
        await authority_position(conn)
    return response(result)


async def summary(request):
    user_id = entity(request.match_info['user_id'])
    if request.query:
        raise Fault('INVALID_ARGUMENT')
    runtime = request.app[RUNTIME]
    async with transaction(runtime, isolation='repeatable_read', write=False) as conn:
        binding = await runtime.auth.access(request, conn)
        result = await get_public_profile(conn, user_id, binding['user_id'])
    return response(result)


async def contact_presence(runtime, subject_id, device_ids):
    """Never infer offline from a missing/unconfirmed dependency response."""
    entity(subject_id)
    if not device_ids:
        return 'offline'
    semaphore = asyncio.Semaphore(8)
    async def read(device_id):
        async with semaphore:
            try:
                async with runtime.http.post(runtime.settings.realtime_url + '/internal/v1/getDevicePresence',
                    json={'subject_id': subject_id, 'device_id': device_id},
                    headers={'Authorization': 'Bearer ' + runtime.settings.outbound_token},
                    timeout=aiohttp.ClientTimeout(total=3), allow_redirects=False) as reply:
                    if reply.status != 200:
                        return 'unknown'
                    result = await reply.json()
                    data = result.get('data') if isinstance(result, dict) else None
                    if (not isinstance(data, dict) or set(data)!= {'online','activity','valid_until'}
                        or data['online'] not in ('online','offline','unknown')
                        or data['activity']!='unknown' or data['valid_until'] is not None):
                        return 'unknown'
                    return data['online']
            except (aiohttp.ClientError, TimeoutError, ValueError):
                return 'unknown'
    states = []
    async def collect(device):
        states.append(await read(device))
    try:
        async with asyncio.timeout(3):
            await asyncio.gather(*(collect(device) for device in device_ids))
    except TimeoutError:
        states.append('unknown')
    if 'online' in states:
        return 'online'
    return 'unknown' if 'unknown' in states else 'offline'


async def list_contacts(request):
    from .synchronization import rest_arguments, rest_load, rest_store
    limit, cursor = rest_arguments(request, 'cursor')
    runtime = request.app[RUNTIME]
    async with transaction(runtime, isolation='repeatable_read', write=False) as conn:
        binding = await runtime.auth.access(request, conn)
        user_id = binding['user_id']
        state = await rest_load(runtime, conn, cursor, user_id, 'contacts') if cursor else {}
        after = state.get('after', '')
        rows = await conn.fetch('''SELECT c.contact_id,c.added_at,u.subject_id FROM contacts c
            JOIN users u ON u.user_id=c.contact_id WHERE c.owner_id=$1 AND c.contact_id COLLATE "C">$2
            ORDER BY c.contact_id COLLATE "C" LIMIT $3''', user_id, after, limit + 1)
        items, targets = [], []
        for row in rows[:limit]:
            items.append({'user': await get_public_profile(conn, row['contact_id'], user_id),
                          'added_at': timestamp(row['added_at']), 'presence': 'unknown'})
            devices = await conn.fetch('''SELECT DISTINCT d.device_id FROM devices d JOIN sessions s USING(device_id,subject_id)
                WHERE d.subject_id=$1 AND NOT s.revoked AND s.access_expires_at>clock_timestamp()''', row['subject_id'])
            targets.append((row['subject_id'], [r['device_id'] for r in devices]))
        next_cursor = await rest_store(runtime, conn, user_id, 'contacts', {'after': rows[limit - 1]['contact_id']}) if len(rows) > limit else None
    states = await asyncio.gather(*(contact_presence(runtime, subject, devices) for subject, devices in targets))
    for item, state in zip(items, states):
        item['presence'] = state
    return list_response(items, next_cursor)


async def add_contact(request):
    value = await body(request)
    required_keys(value, ('user_id',))
    target = entity(value['user_id'])
    runtime = request.app[RUNTIME]
    async with transaction(runtime) as conn:
        await db.frontier(conn)
        binding = await runtime.auth.access(request, conn, lock=True)
        user_id = binding['user_id']
        if not await conn.fetchval('SELECT EXISTS(SELECT 1 FROM users WHERE user_id=$1)', lookup_entity(target)):
            raise Fault('NOT_FOUND')
        added = await conn.fetchval('''INSERT INTO contacts(owner_id,contact_id) VALUES($1,$2)
            ON CONFLICT DO NOTHING RETURNING added_at''', user_id, target)
        created = added is not None
        if not created:
            added = await conn.fetchval('SELECT added_at FROM contacts WHERE owner_id=$1 AND contact_id=$2', user_id, target)
        # Adding a contact can make its selected avatar visible within this transaction.
        summary_value = await get_public_profile(conn, target, user_id)
        result = {'user': summary_value, 'added_at': timestamp(added)}
        await authority_position(conn)
    return response(result, status=201 if created else 200)


async def remove_contact(request):
    target = entity(request.match_info['user_id'])
    runtime = request.app[RUNTIME]
    async with transaction(runtime) as conn:
        await db.frontier(conn)
        binding = await runtime.auth.access(request, conn, lock=True)
        await conn.execute('DELETE FROM contacts WHERE owner_id=$1 AND contact_id=$2', binding['user_id'], lookup_entity(target))
        await authority_position(conn)
    return web.Response(status=204)


def register(app):
    app.add_routes([web.get('/api/v1/users/me', me), web.patch('/api/v1/users/me', update_me),
        web.get('/api/v1/users/{user_id}', summary), web.get('/api/v1/contacts', list_contacts),
        web.post('/api/v1/contacts', add_contact), web.delete('/api/v1/contacts/{user_id}', remove_contact)])
