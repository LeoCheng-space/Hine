import { ownerPartition } from './api';
import type { SessionController } from './session';
import type { UserSummary } from './types';

export interface DirectoryEntry { displayName: string; avatarId: string | null; fetchedAt: number; avatarStale: boolean }
export type DirectorySummary = Pick<UserSummary, 'display_name' | 'avatar_attachment_id'>;
export interface DirectoryDeps { fetchSummary(userId: string, signal: AbortSignal): Promise<DirectorySummary>; now(): number; accept(): boolean }
interface Job { run(): void; cancel(): void }

/** Owner-scoped, in-memory cache of user names and avatar IDs. `ensure` never rejects; callers invoke it from effects only. */
export class UserDirectory {
  private entries = new Map<string, DirectoryEntry>();
  private versions = new Map<string, number>();
  private failedAt = new Map<string, number>();
  private memberships = new Map<string, number>();
  private inflight = new Map<string, { version: number; promise: Promise<void> }>();
  private queue: Job[] = [];
  private running = 0;
  private epoch = 0;
  private abort = new AbortController();
  private listeners = new Set<() => void>();
  private version = 0;
  private readonly ttl: number;
  private readonly limit: number;
  private readonly backoff: number;
  constructor(private readonly deps: DirectoryDeps, options: { ttlMs?: number; concurrency?: number; failureBackoffMs?: number } = {}) {
    this.ttl = options.ttlMs ?? 300_000; this.limit = options.concurrency ?? 4; this.backoff = options.failureBackoffMs ?? 30_000;
  }
  subscribe = (listener: () => void): (() => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  getVersion = (): number => this.version;
  get(userId: string): DirectoryEntry | undefined { return this.entries.get(userId); }
  private changed(): void { this.version++; for (const listener of this.listeners) listener(); }
  private versionOf(userId: string): number { return this.versions.get(userId) ?? 0; }
  private bump(userId: string): void { this.versions.set(userId, this.versionOf(userId) + 1); }
  ensure(userId: string): Promise<void> {
    const entry = this.entries.get(userId), now = this.deps.now();
    if (entry && !entry.avatarStale && now - entry.fetchedAt <= this.ttl) return Promise.resolve();
    const failed = this.failedAt.get(userId);
    if (failed !== undefined && now - failed <= this.backoff) return Promise.resolve();
    const version = this.versionOf(userId), existing = this.inflight.get(userId);
    if (existing && existing.version === version) return existing.promise;
    const epoch = this.epoch, signal = this.abort.signal, { promise, resolve } = Promise.withResolvers<void>();
    this.queue.push({
      cancel: resolve,
      run: () => {
        this.running++;
        this.deps.fetchSummary(userId, signal).then(summary => {
          if (epoch !== this.epoch || this.versionOf(userId) !== version || !this.deps.accept()) return;
          this.failedAt.delete(userId); this.store(userId, summary);
        }, error => {
          // A token refresh rejects in-flight requests with UNAUTHENTICATED (session.ts); that and aborts are cancellations, not failures (design §6.4).
          const cancelled = signal.aborted || (error instanceof Error && (('code' in error && error.code === 'UNAUTHENTICATED') || error.name === 'AbortError'));
          if (epoch === this.epoch && !cancelled) this.failedAt.set(userId, this.deps.now());
        })
          .finally(() => { this.running--; resolve(); this.pump(); });
      },
    });
    const tracked = promise.finally(() => { if (this.inflight.get(userId)?.promise === tracked) this.inflight.delete(userId); });
    this.inflight.set(userId, { version, promise: tracked });
    this.pump();
    return tracked;
  }
  private pump(): void { while (this.running < this.limit && this.queue.length) this.queue.shift()!.run(); }
  private store(userId: string, summary: DirectorySummary): void {
    this.entries.set(userId, { displayName: summary.display_name, avatarId: summary.avatar_attachment_id, fetchedAt: this.deps.now(), avatarStale: false });
    this.changed();
  }
  put(userId: string, summary: DirectorySummary): void { if (!this.deps.accept()) return; this.bump(userId); this.failedAt.delete(userId); this.store(userId, summary); }
  /** Long-lived views (list, rail, open room) only call `ensure` when their ID sets change, so users already shown are refetched here. */
  markAvatarsStale(userIds: string[]): void {
    const known: string[] = [];
    for (const id of userIds) {
      const entry = this.entries.get(id); this.bump(id);
      if (entry && !entry.avatarStale) { this.entries.set(id, { ...entry, avatarStale: true }); known.push(id); }
    }
    if (!known.length) return;
    this.changed();
    for (const id of known) void this.ensure(id);
  }
  observeMembership(groupId: string, version: number | null, memberIds: string[]): void {
    if (version === null) return;
    const previous = this.memberships.get(groupId);
    this.memberships.set(groupId, version);
    if (previous !== undefined && version > previous) this.markAvatarsStale(memberIds);
  }
  reset(): void {
    this.epoch++; this.abort.abort(); this.abort = new AbortController();
    for (const job of this.queue) job.cancel();
    this.queue = []; this.entries.clear(); this.versions.clear(); this.failedAt.clear(); this.memberships.clear(); this.inflight.clear();
    this.changed();
  }
}

let current: { owner: string; directory: UserDirectory; unsubscribe: () => void } | null = null;
/** The directory for the session's current owner. The session subscription resets a replaced owner's directory outside React render. */
export function directoryFor(session: SessionController): UserDirectory {
  const context = session.getSnapshot().context, owner = ownerPartition(context.user_id, context.device_id);
  if (current?.owner === owner) return current.directory;
  current?.unsubscribe();
  const accept = (): boolean => { const now = session.getSnapshot().context; return now.state === 'authenticated' && ownerPartition(now.user_id, now.device_id) === owner; };
  const directory = new UserDirectory({ fetchSummary: async (id, signal) => (await session.request<UserSummary>(`/users/${encodeURIComponent(id)}`, { signal })).data, now: () => Date.now(), accept });
  const unsubscribe = session.subscribe(() => { const now = session.getSnapshot().context; if (ownerPartition(now.user_id, now.device_id) !== owner) directory.reset(); });
  current = { owner, directory, unsubscribe };
  return directory;
}
