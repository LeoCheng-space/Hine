"""BB-owned snapshots/feed, with current read permission at socket delivery."""
import asyncio

from . import protocol as p
from .internal import Fault


def _receipt(value):
    p.keys(value, ['kind', 'message_id', 'recipient_id', 'status', 'updated_at'])
    p.check(value['kind'] == 'direct' and value['status'] in {'delivered', 'read'})
    p.uuid(value['message_id'])
    p.string(value['recipient_id'], True)
    p.timestamp(value['updated_at'])


def _snapshot(value, conversation, viewer):
    p.obj(value)
    p.check(value.get('type') in {'text', 'image', 'file'})
    content = 'text' if value['type'] == 'text' else 'attachment_id'
    p.keys(value, ['id', 'event_id', 'conversation_id', 'sender_id', 'created_at',
                   'order_key', 'type', 'receipt', content], ['client_message_id'])
    p.uuid(value['id'])
    p.uuid(value['event_id'])
    p.check(value['conversation_id'] == conversation['id'])
    p.string(value['sender_id'], True)
    p.timestamp(value['created_at'])
    p.order_key(value['order_key'])
    p.string(value[content], True)
    if 'client_message_id' in value:
        p.uuid(value['client_message_id'])
        p.check(value['sender_id'] == viewer)
    if value['receipt'] is not None:
        p.check(conversation['type'] == 'direct')
        _receipt(value['receipt'])
        p.check(value['receipt']['message_id'] == value['id'])


def _feed_event(value, viewer):
    p.envelope(value)
    p.check(value['event'] in {'message.created', 'message.status',
                             'conversation.member_added', 'conversation.member_removed',
                             'conversation.updated'})
    required = ['event', 'event_id', 'timestamp', 'payload', 'conversation_id']
    if value['event'] == 'message.created':
        required.append('sender_id')
    p.keys(value, required)
    p.string(value['conversation_id'], True)
    payload = value['payload']
    if value['event'] == 'message.created':
        p.string(value['sender_id'], True)
        content = p.message_payload(payload, received=True)
        p.string(payload[content], True)
        p.check('client_message_id' not in payload or value['sender_id'] == viewer)
    elif value['event'] == 'message.status':
        _receipt(payload)
    elif value['event'] == 'conversation.member_added':
        p.keys(payload, ['member_id', 'role', 'actor_id', 'membership_version'])
        p.string(payload['member_id'], True)
        p.string(payload['actor_id'], True)
        p.check(payload['role'] in {'admin', 'member'})
        p.integer(payload['membership_version'], 1)
    elif value['event'] == 'conversation.member_removed':
        p.keys(payload, ['member_id', 'change', 'membership_version'], ['actor_id'])
        p.string(payload['member_id'], True)
        p.check(payload['change'] == 'removed')
        p.integer(payload['membership_version'], 1)
        if payload['member_id'] == viewer:
            p.check('actor_id' not in payload)
            return True
        if 'actor_id' in payload:
            p.string(payload['actor_id'], True)
    else:
        p.keys(payload, ['changes', 'actor_id', 'membership_version'])
        p.string(payload['actor_id'], True)
        p.integer(payload['membership_version'], 1)
        changes = p.obj(payload['changes'])
        p.check(changes.get('kind') in {'title', 'role'})
        if changes['kind'] == 'title':
            p.keys(changes, ['kind', 'title'])
            p.string(changes['title'])
        else:
            p.keys(changes, ['kind', 'member_id', 'role'])
            p.string(changes['member_id'], True)
            p.check(changes['role'] in {'admin', 'member'})
    return False


def _bootstrap(value, request, viewer, limit):
    p.keys(value, ['snapshot_id', 'start_cursor', 'conversations', 'next_page_token', 'has_more'])
    p.string(value['snapshot_id'], True)
    p.string(value['start_cursor'], True)
    p.boolean(value['has_more'])
    if value['has_more']:
        p.string(value['next_page_token'], True)
    else:
        p.check(value['next_page_token'] is None)
    if 'snapshot_id' in request:
        p.check(value['snapshot_id'] == request['snapshot_id'])
    p.check(isinstance(value['conversations'], list))
    count = len(value['conversations'])
    refs = set()
    conversations = set()
    for conversation in value['conversations']:
        p.keys(conversation, ['id', 'type', 'title', 'unread_count', 'my_role', 'recent_messages'])
        cid = p.string(conversation['id'], True)
        p.check(conversation['type'] in {'direct', 'group'})
        p.integer(conversation['unread_count'])
        if conversation['type'] == 'direct':
            p.check(conversation['title'] is None and conversation['my_role'] is None)
        else:
            p.string(conversation['title'])
            p.check(conversation['my_role'] is None or conversation['my_role'] in {'admin', 'member'})
        p.check(isinstance(conversation['recent_messages'], list))
        count += len(conversation['recent_messages'])
        p.check(count <= limit)
        conversations.add(cid)
        refs.add(('history', 'conversation', cid))
        for message in conversation['recent_messages']:
            _snapshot(message, conversation, viewer)
            refs.add(('read', 'message', message['id']))
    p.check(count <= limit)
    return refs, conversations, []


def _batch(value, request, viewer, limit):
    p.keys(value, ['snapshot_boundary', 'events', 'next_cursor', 'has_more'])
    p.string(value['snapshot_boundary'], True)
    p.string(value['next_cursor'], True)
    p.boolean(value['has_more'])
    if 'snapshot_boundary' in request:
        p.check(value['snapshot_boundary'] == request['snapshot_boundary'])
    p.check(isinstance(value['events'], list) and len(value['events']) <= limit)
    refs = set()
    conversations = set()
    removals = []
    for event in value['events']:
        own_removal = _feed_event(event, viewer)
        cid = event['conversation_id']
        if own_removal:
            removals.append((cid, event['payload']['membership_version']))
            continue
        conversations.add(cid)
        if event['event'] in {'message.created', 'message.status'}:
            refs.add(('read', 'message', event['payload']['message_id']))
        else:
            refs.add(('history', 'conversation', cid))
    return refs, conversations, removals


def _live(runtime, connection):
    if not connection.valid():
        raise Fault('UNAUTHENTICATED', False, user_session=True)
    if not runtime.invalidations.fresh():
        raise Fault()


class SyncGuard:
    """Per-response read references and request-start A18 revisions; no cursor state."""

    def __init__(self, runtime, correlation, refs, conversations, removed_versions):
        self.runtime = runtime
        self.correlation = correlation
        self.refs = refs
        self.removed_versions = {cid: removed_versions.get(cid) for cid in conversations}

    def allows(self, connection):
        return all(connection.removed_versions.get(cid) == version
                   for cid, version in self.removed_versions.items())

    async def authorize(self, connection):
        _live(self.runtime, connection)
        if not self.allows(connection):
            raise Fault()
        try:
            # A page contains at most sync_page_limit distinct logical items.
            # One deadline bounds every current authorization, not each HTTP call.
            async with asyncio.timeout(self.runtime.settings.dependency_timeout):
                for action, resource_type, resource_id in sorted(self.refs):
                    result = await self.runtime.client.call('authorize', {
                        **connection.session_binding(), 'action': action,
                        'resource_type': resource_type, 'resource_id': resource_id})
                    p.keys(result, ['allowed', 'authorization_version'])
                    p.boolean(result['allowed'])
                    p.string(result['authorization_version'], True)
                    if not result['allowed']:
                        raise Fault('FORBIDDEN', False)
        except (TimeoutError, p.Invalid, TypeError, KeyError):
            raise Fault() from None
        _live(self.runtime, connection)
        if not self.allows(connection):
            raise Fault()


async def handle(runtime, connection, frame):
    """Handle W13/W15; public response remains the validated authority payload."""
    request = frame['payload']
    if frame['event'] == 'sync.bootstrap.request':
        p.keys(request, ['reason'], ['snapshot_id', 'page_token'])
        p.check(request['reason'] in {'first_login', 'cursor_reset'})
        p.check(('snapshot_id' in request) == ('page_token' in request))
        if 'snapshot_id' in request:
            p.string(request['snapshot_id'], True)
            p.string(request['page_token'], True)
        operation, response, validate = 'readBootstrap', 'sync.bootstrap.page', _bootstrap
    else:
        p.check(frame['event'] == 'sync.request')
        p.keys(request, ['cursor'], ['snapshot_boundary'])
        p.string(request['cursor'], True)
        if 'snapshot_boundary' in request:
            p.string(request['snapshot_boundary'], True)
        operation, response, validate = 'readFeed', 'sync.batch', _batch
    _live(runtime, connection)
    removed_versions = connection.removed_versions.copy()
    body = {key: connection.binding[key] for key in ['subject_id', 'session_id', 'session_generation']}
    body.update(request)
    if operation == 'readFeed':
        body['limit'] = runtime.settings.sync_page_limit
    result = await runtime.client.call(operation, body)
    try:
        refs, conversations, removals = validate(result, request, connection.binding['user_id'],
                                               runtime.settings.sync_page_limit)
    except (p.Invalid, TypeError, KeyError):
        raise Fault() from None
    guard = SyncGuard(runtime, frame['event_id'], refs, conversations, removed_versions)
    # Apply only fully validated minimal own W12 before ANY subsequent await.
    for cid, version in removals:
        for current in runtime.connections:
            if current.binding is not None and current.binding['user_id'] == connection.binding['user_id']:
                current.apply_group_removal(cid, version)
    if not guard.allows(connection):
        raise Fault()
    try:
        # The public read result has no invalidation position. A complete new
        # catchup, never a guessed position/cached freshness gate, is required.
        async with asyncio.timeout(runtime.settings.dependency_timeout):
            await runtime.invalidations.catchup()
    except TimeoutError:
        raise Fault() from None
    _live(runtime, connection)
    if not guard.allows(connection):
        raise Fault()
    connection.enqueue(p.event(response, result, correlation=frame['event_id']), sync_guard=guard)
