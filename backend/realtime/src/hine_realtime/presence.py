"""Single-instance ephemeral presence; BB owns observer/contact authorization.

No JWT forwarding, persisted presence events, activity leases or Redis markers.
Every W18 is a current full state, authorized again under the socket write lock.
"""
import asyncio
import logging
import time
from collections import OrderedDict

from redis.exceptions import RedisError

from . import protocol as p
from .internal import Fault

LOG = logging.getLogger("hine_realtime")
PAGE_LIMIT = 100
MAX_TARGETS = 4096
POLL_SECONDS = 5


def binding(connection):
    return {key: connection.binding[key]
            for key in ("subject_id", "session_id", "session_generation")}


class Observer:
    def __init__(self):
        self.contacts = OrderedDict()
        self.delivered = {}
        self.pending = {}
        self.seen = set()
        self.cursor = None

    def forget(self, user):
        self.contacts.pop(user, None)
        self.delivered.pop(user, None)
        # Pending guards still retain this ID while queued/in-flight. Keep
        # counting it until the writer releases it; missing contacts deny send.

    def clear(self):
        self.contacts.clear()
        self.delivered.clear()
        self.pending.clear()
        self.seen.clear()
        self.cursor = None


class PresenceGuard:
    def __init__(self, owner, observer, user, subject):
        self.owner = owner
        self.observer = observer
        self.user = user
        self.subject = subject
        self.value = None
        self.redis_confirmed = False
        self.observed_monotonic = None
        self.observation_time = None
        self.position = None

    def release(self):
        if self.observer.pending.get(self.user) is self:
            self.observer.pending.pop(self.user)

    def allows(self, connection):
        invalidations = self.owner.runtime.invalidations
        if not (connection.valid() and invalidations.fresh()
                and self.observer.contacts.get(self.user) == self.subject
                and self.observer.pending.get(self.user) is self):
            return False
        if self.observed_monotonic is None:
            return True
        return (time.monotonic() - self.observed_monotonic <= invalidations.settings.stale_seconds
                and (self.position is None or (
                    invalidations.applied_position is not None
                    and self.position <= invalidations.applied_position))
                and self.owner.aggregate(self.subject, self.redis_confirmed) == self.value)

    async def prepare(self, connection):
        """Settle one bounded observation without an endless ping/auth cycle."""
        if not self.allows(connection):
            return None
        invalidations = self.owner.runtime.invalidations
        for attempt in range(2):
            result = await self.owner.read(connection, limit=1, contact_user_id=self.user)
            position = result["invalidation_position"]
            covered = (invalidations.applied_position is not None
                       and position <= invalidations.applied_position)
            if not await invalidations.gate(position):
                return None
            if not result["targets"]:
                self.observer.forget(self.user)
                return None
            target = result["targets"][0]
            p.check(target["user_id"] == self.user and target["subject_id"] == self.subject)
            if covered:
                break
            if attempt == 1:
                return None
        if not self.allows(connection):
            return None
        # The authority wait must precede this source observation. Capture the
        # aggregate and its timestamp together; never retimestamp an old PING.
        self.redis_confirmed = await self.owner.redis_available()
        self.value = self.owner.aggregate(self.subject, self.redis_confirmed)
        self.observed_monotonic = time.monotonic()
        self.observation_time = p.now()
        # PING itself awaits: an earlier allowed contact snapshot cannot survive
        # that await. This is the final authority point, with no further catchup.
        result = await self.owner.read(connection, limit=1, contact_user_id=self.user)
        self.position = result["invalidation_position"]
        if not result["targets"]:
            self.observer.forget(self.user)
            return None
        target = result["targets"][0]
        p.check(target["user_id"] == self.user and target["subject_id"] == self.subject)
        if not self.allows(connection):
            return None
        if self.observer.delivered.get(self.user) == self.value:
            return None
        return p.dumps(p.event("presence.changed", {"user_id": self.user, "presence": self.value},
                               time=self.observation_time))

    def sent(self, connection):
        # Record the observation actually sent, not a newer aggregate after
        # socket backpressure; otherwise its next transition could be skipped.
        if (self.observer.pending.get(self.user) is self
                and self.observer.contacts.get(self.user) == self.subject):
            self.observer.delivered[self.user] = self.value


class Presence:
    def __init__(self, runtime):
        self.runtime = runtime
        self.observers = {}
        self.offset = 0

    async def redis_available(self):
        try:
            return self.runtime.redis is not None and bool(await self.runtime.redis.ping())
        except (RedisError, OSError, TimeoutError):
            return False

    def aggregate(self, subject, redis_available, device=None):
        if not redis_available or not self.runtime.invalidations.fresh():
            return "unknown"
        return "online" if any(
            connection.valid() and connection.binding["subject_id"] == subject
            and (device is None or connection.binding["device_id"] == device)
            for connection in self.runtime.connections
        ) else "offline"

    async def read(self, connection, *, limit=PAGE_LIMIT, cursor=None, contact_user_id=None):
        if not connection.valid():
            raise Fault("UNAUTHENTICATED", False, user_session=True)
        body = {**binding(connection), "limit": limit}
        if cursor is not None:
            body["cursor"] = cursor
        if contact_user_id is not None:
            body["contact_user_id"] = contact_user_id
        result = await self.runtime.client.call("readPresenceTargets", body)
        try:
            p.presence_targets(result, limit)
            if contact_user_id is not None:
                p.check(result["next_cursor"] is None)
                p.check(all(target["user_id"] == contact_user_id for target in result["targets"]))
            if cursor is not None:
                p.check(result["next_cursor"] != cursor)
            return result
        except (p.Invalid, TypeError, KeyError):
            raise Fault() from None

    async def poll_observer(self, connection, redis_available):
        if not connection.valid() or not self.runtime.invalidations.fresh():
            return
        observer = self.observers.get(connection)
        if observer is None:
            observer = self.observers[connection] = Observer()
        try:
            result = await self.read(connection, cursor=observer.cursor)
            if not await self.runtime.invalidations.gate(result["invalidation_position"]):
                return
            if not connection.valid() or not self.runtime.invalidations.fresh():
                return
            targets = {target["user_id"]: target["subject_id"] for target in result["targets"]}
            if observer.seen.intersection(targets):
                raise Fault()
            retained = (set(observer.contacts) | observer.seen | observer.pending.keys()
                        | observer.delivered.keys() | targets.keys())
            if len(retained) > MAX_TARGETS:
                observer.clear()
                connection.invalidate(Fault())
                return
            for user, subject in targets.items():
                if user in observer.contacts and observer.contacts[user] != subject:
                    observer.forget(user)
                observer.contacts[user] = subject
            observer.seen.update(targets)
            observer.cursor = result["next_cursor"]
            if observer.cursor is None:
                # A failed/partial page can never imply that unseen contacts
                # were removed. Prune only after a complete authorized scan.
                for user in tuple(observer.contacts):
                    if user not in observer.seen:
                        observer.forget(user)
                observer.seen.clear()
            self.enqueue_changes(connection, observer, result["invalidation_position"], redis_available)
        except Fault as failure:
            if failure.user_session:
                connection.invalidate(failure)
                self.runtime.request_catchup()
            elif failure.code in {"CURSOR_INVALID", "CURSOR_EXPIRED"}:
                observer.cursor = None
                observer.seen.clear()
            else:
                LOG.warning("presence_authority_unavailable")

    def enqueue_changes(self, connection, observer, position, redis_available):
        # Share the existing output limits, but pace large initial snapshots
        # instead of filling a healthy socket's queue with thousands of W18s.
        room = min(PAGE_LIMIT, max(0, self.runtime.settings.max_outgoing_frames
                                  - connection.queue.qsize()))
        confirmed = redis_available and self.runtime.invalidations.fresh()
        subjects = {candidate.binding["subject_id"] for candidate in self.runtime.connections
                    if candidate.valid()} if confirmed else set()
        for user in tuple(observer.contacts):
            if room == 0:
                break
            subject = observer.contacts[user]
            observer.contacts.move_to_end(user)
            if user in observer.pending:
                continue
            value = "unknown" if not confirmed else ("online" if subject in subjects else "offline")
            if observer.delivered.get(user) == value:
                continue
            frame = p.event("presence.changed", {"user_id": user, "presence": value})
            size = len(p.dumps(frame))
            if size > self.runtime.settings.max_outgoing_bytes:
                # Draining cannot make an individually oversized frame fit.
                # Use existing resource cleanup, never defer it permanently.
                connection.invalidate(Fault())
                return
            if connection.queue_bytes + size > self.runtime.settings.max_outgoing_bytes:
                # This individually authorized state waits for byte capacity;
                # presence must not turn an ordinary initial snapshot into a
                # connection-wide overflow that discards unrelated output.
                break
            guard = PresenceGuard(self, observer, user, subject)
            observer.pending[user] = guard
            if not connection.enqueue(frame, position=position, presence_guard=guard):
                guard.release()
                return
            room -= 1

    async def run(self):
        period = min(POLL_SECONDS, self.runtime.settings.poll_seconds)
        while True:
            started = time.monotonic()
            current = tuple(connection for connection in self.runtime.connections if connection.valid())
            for connection in tuple(self.observers):
                if connection not in self.runtime.connections or not connection.valid():
                    self.observers.pop(connection).clear()
            if current and self.runtime.invalidations.fresh():
                # One task, one page/observer/pass, one bounded work window;
                # continuation state survives the window. Rotate for fairness.
                self.offset %= len(current)
                ordered = current[self.offset:] + current[:self.offset]
                completed = 0
                try:
                    async with asyncio.timeout(POLL_SECONDS):
                        available = await self.redis_available()
                        for connection in ordered:
                            await self.poll_observer(connection, available)
                            completed += 1
                except TimeoutError:
                    LOG.warning("presence_poll_window_exhausted")
                self.offset = (self.offset + max(1, completed)) % len(current)
            await asyncio.sleep(max(.01, period - (time.monotonic() - started)))

    async def device_presence(self, subject, device):
        """Use the same finite observation/last-authority discipline as W18."""
        candidate = None
        try:
            async with asyncio.timeout(self.runtime.settings.dependency_timeout):
                invalidations = self.runtime.invalidations
                async with asyncio.timeout(self.runtime.settings.catchup_ms / 1000):
                    await invalidations.catchup()
                if not invalidations.fresh():
                    return "unknown"
                candidates = tuple(connection for connection in self.runtime.connections
                                   if connection.valid() and connection.binding["subject_id"] == subject
                                   and connection.binding["device_id"] == device)
                uncertain = False
                for connection in candidates:
                    try:
                        result = await self.read(connection, limit=1)
                        if not await invalidations.gate(result["invalidation_position"]):
                            uncertain = True
                            continue
                        if connection.valid() and invalidations.fresh():
                            candidate = connection
                            break
                    except Fault as failure:
                        if failure.user_session:
                            connection.invalidate(failure)
                            self.runtime.request_catchup()
                        else:
                            uncertain = True
                if candidate is None and uncertain:
                    return "unknown"
                available = await self.redis_available()
                value = self.aggregate(subject, available, device)
                observed = time.monotonic()
                if candidate is not None:
                    result = await self.read(candidate, limit=1)
                    position = result["invalidation_position"]
                    if not candidate.valid():
                        return "unknown"
                else:
                    # Even offline needs an authority point after the PING,
                    # not a pre-PING absence of confirmed local bindings.
                    result = await self.runtime.client.call("readSessionInvalidations",
                                                            {"after_position": None, "limit": 500})
                    p.invalidation_page(result, None)
                    position = result["head_position"]
                if (not invalidations.fresh() or invalidations.applied_position is None
                        or position > invalidations.applied_position
                        or time.monotonic() - observed > self.runtime.settings.stale_seconds
                        or self.aggregate(subject, available, device) != value):
                    return "unknown"
                return value
        except Fault as failure:
            if failure.user_session and candidate is not None:
                candidate.invalidate(failure)
                self.runtime.request_catchup()
            return "unknown"
        except (TimeoutError, p.Invalid, TypeError, KeyError):
            return "unknown"
