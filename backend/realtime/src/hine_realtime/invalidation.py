"""Contiguous invalidation positions, monotonic freshness and admission locking."""
import asyncio
import time
from collections import OrderedDict

from . import protocol as p
from .internal import Fault


class Invalidations:
    def __init__(self, settings, client, connections):
        self.settings = settings
        self.client = client
        self.connections = connections
        self.lock = asyncio.Lock()
        self.catchup_lock = asyncio.Lock()
        self.applied_position = None
        self.last_complete_start = None
        self.known = OrderedDict()
        self.floor = 0
        self.pending = set()

    def fresh(self):
        return self.last_complete_start is not None and time.monotonic() - self.last_complete_start <= self.settings.stale_seconds

    @staticmethod
    def matches(entry, binding):
        return binding is not None and entry["session_id"] == binding["session_id"] and (entry["min_valid_generation"] is None or binding["session_generation"] < entry["min_valid_generation"])

    def _apply_locked(self, entry):
        position = entry["position"]
        existing = self.known.get(position)
        if existing is not None:
            if existing != entry:
                self.last_complete_start = None
                raise Fault()
            return
        self.known[position] = entry
        if self.applied_position is not None and position > self.applied_position:
            self.pending.add(position)
        for connection in tuple(self.connections):
            if self.matches(entry, connection.binding):
                connection.invalidate()
        while len(self.known) > 10000:
            old_position, _ = self.known.popitem(last=False)
            self.floor = max(self.floor, old_position)
        # Bound out-of-order hint storage. Missing positions are reread from BB;
        # never infer a contiguous frontier from an untrusted high hint.
        if len(self.pending) > 10000:
            self.pending.clear()
        if self.applied_position is not None:
            while self.applied_position + 1 in self.pending:
                self.applied_position += 1
                self.pending.remove(self.applied_position)

    async def apply(self, entry):
        p.invalidation(entry)
        async with self.lock:
            self._apply_locked(entry)

    async def _page(self, after):
        value = await self.client.call("readSessionInvalidations", {"after_position": after, "limit": 500})
        try:
            return p.invalidation_page(value, after)
        except (p.Invalid, TypeError, KeyError):
            raise Fault() from None

    async def catchup(self):
        async with self.catchup_lock:
            started = time.monotonic()
            if self.applied_position is None:
                head = await self._page(None)
                async with self.lock:
                    self.applied_position = head["head_position"]
                    self.floor = self.applied_position
                    self.pending = {position for position in self.pending if position > self.applied_position}
            after = self.applied_position
            while True:
                try:
                    page = await self._page(after)
                except Fault as failure:
                    if failure.code == "CURSOR_INVALID":
                        async with self.lock:
                            self.last_complete_start = None
                            for connection in tuple(self.connections):
                                connection.invalidate(Fault("DEPENDENCY_UNAVAILABLE"))
                            self.applied_position = None
                            self.known.clear()
                            self.pending.clear()
                            self.floor = 0
                        # Reset to BB's latest head only after closing every old
                        # local session; the next cycle establishes freshness.
                        head = await self._page(None)
                        async with self.lock:
                            self.applied_position = head["head_position"]
                            self.floor = self.applied_position
                    raise
                async with self.lock:
                    for entry in page["entries"]:
                        self._apply_locked(entry)
                    # The validated page proves contiguity from its starting
                    # position even if bounded hint storage was pruned earlier.
                    self.applied_position = max(self.applied_position, page["next_position"])
                    self.pending = {position for position in self.pending if position > self.applied_position}
                    while self.applied_position + 1 in self.pending:
                        self.applied_position += 1
                        self.pending.remove(self.applied_position)
                    if not page["has_more"]:
                        self.last_complete_start = started
                        return
                after = page["next_position"]

    async def gate(self, position):
        if self.applied_position is not None and position <= self.applied_position:
            return self.fresh()
        try:
            async with asyncio.timeout(self.settings.catchup_ms / 1000):
                await self.catchup()
            return self.fresh() and self.applied_position is not None and position <= self.applied_position
        except (Fault, TimeoutError):
            return False

    async def register(self, connection, binding):
        position = binding["invalidation_position"]
        covered_through = position
        historical_invalid = False
        # Retention may advance during HTTP awaits. Recheck coverage under the
        # admission lock and reread rather than losing an evicted revocation.
        async with asyncio.timeout(self.settings.catchup_ms / 1000):
            while True:
                if position < self.floor and covered_through < self.floor:
                    after = position
                    try:
                        while True:
                            page = await self._page(after)
                            historical_invalid = historical_invalid or any(self.matches(entry, binding) for entry in page["entries"])
                            async with self.lock:
                                for entry in page["entries"]:
                                    self._apply_locked(entry)
                            if not page["has_more"]:
                                covered_through = page["head_position"]
                                break
                            after = page["next_position"]
                    except Fault as failure:
                        if failure.code == "CURSOR_INVALID":
                            async with self.lock:
                                for current in tuple(self.connections):
                                    current.invalidate(Fault())
                                self.last_complete_start = None
                                self.applied_position = None
                                self.known.clear()
                                self.pending.clear()
                                self.floor = 0
                        raise Fault() from None
                if not await self.gate(position):
                    raise Fault()
                async with self.lock:
                    if not self.fresh():
                        raise Fault()
                    if historical_invalid or any(entry["position"] > position and self.matches(entry, binding) for entry in self.known.values()):
                        raise Fault("UNAUTHENTICATED", False, user_session=True)
                    if connection.invalid or connection.closed or binding["expires_monotonic"] <= time.monotonic():
                        raise Fault("UNAUTHENTICATED", False, user_session=True)
                    if position < self.floor and covered_through < self.floor:
                        continue
                    # No await: notification and final check+registration are
                    # mutually exclusive even for early out-of-order hints.
                    connection.binding = binding
                    return
