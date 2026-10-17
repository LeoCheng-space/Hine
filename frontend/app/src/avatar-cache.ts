import { ownerPartition } from './api';
import type { SessionController } from './session';

export interface AvatarDeps { load(attachmentId: string, signal: AbortSignal): Promise<Blob>; createURL(blob: Blob): string; revokeURL(url: string): void; accept(): boolean }
/** One component's hold on an avatar. `release` only affects the entry this handle acquired and is idempotent. */
export interface AvatarHandle { url: Promise<string | null>; release(): void }
interface Entry { refs: number; url: string | null; promise: Promise<string | null>; settle(value: string | null): void }

/** Owner-scoped object-URL cache for avatar bytes: shared downloads, reference counts, idle LRU, bounded concurrency. Failures are not cached. */
export class AvatarCache {
  private entries = new Map<string, Entry>();
  private idle: string[] = [];
  private queue: (() => void)[] = [];
  private running = 0;
  private epoch = 0;
  private abort = new AbortController();
  private readonly idleLimit: number;
  private readonly limit: number;
  constructor(private readonly deps: AvatarDeps, options: { idleLimit?: number; concurrency?: number } = {}) { this.idleLimit = options.idleLimit ?? 48; this.limit = options.concurrency ?? 4; }
  acquire(attachmentId: string): AvatarHandle {
    let entry = this.entries.get(attachmentId);
    if (entry) { entry.refs++; this.idle = this.idle.filter(id => id !== attachmentId); }
    else entry = this.start(attachmentId);
    const owned = entry; let released = false;
    return { url: owned.promise, release: () => { if (released) return; released = true; this.release(attachmentId, owned); } };
  }
  private start(attachmentId: string): Entry {
    const epoch = this.epoch, signal = this.abort.signal, { promise, resolve } = Promise.withResolvers<string | null>();
    const entry: Entry = { refs: 1, url: null, promise, settle: resolve };
    this.entries.set(attachmentId, entry);
    this.queue.push(() => {
      if (this.entries.get(attachmentId) !== entry) { entry.settle(null); return; }
      this.running++;
      this.deps.load(attachmentId, signal).then(blob => {
        if (epoch !== this.epoch || !this.deps.accept() || this.entries.get(attachmentId) !== entry) { entry.settle(null); return; }
        entry.url = this.deps.createURL(blob); entry.settle(entry.url);
      }, () => { if (this.entries.get(attachmentId) === entry) this.entries.delete(attachmentId); entry.settle(null); })
        .finally(() => { this.running--; this.pump(); });
    });
    this.pump();
    return entry;
  }
  private release(attachmentId: string, entry: Entry): void {
    if (this.entries.get(attachmentId) !== entry || entry.refs === 0) return;
    entry.refs--; if (entry.refs > 0) return;
    if (entry.url === null) { this.entries.delete(attachmentId); return; }
    this.idle.push(attachmentId);
    while (this.idle.length > this.idleLimit) {
      const oldest = this.idle.shift()!, evicted = this.entries.get(oldest);
      this.entries.delete(oldest); if (evicted?.url) this.deps.revokeURL(evicted.url);
    }
  }
  private pump(): void { while (this.running < this.limit && this.queue.length) this.queue.shift()!(); }
  reset(): void {
    this.epoch++; this.abort.abort(); this.abort = new AbortController();
    for (const entry of this.entries.values()) { if (entry.url) this.deps.revokeURL(entry.url); entry.settle(null); }
    this.queue = []; this.entries.clear(); this.idle = [];
  }
}

let current: { owner: string; cache: AvatarCache; unsubscribe: () => void } | null = null;
/** The avatar cache for the session's current owner; switching owner aborts downloads and revokes every URL. `load` is injected to avoid importing page modules. */
export function avatarCacheFor(session: SessionController, load: (attachmentId: string, signal: AbortSignal) => Promise<Blob>): AvatarCache {
  const context = session.getSnapshot().context, owner = ownerPartition(context.user_id, context.device_id);
  if (current?.owner === owner) return current.cache;
  current?.unsubscribe(); current?.cache.reset();
  const accept = (): boolean => { const now = session.getSnapshot().context; return now.state === 'authenticated' && ownerPartition(now.user_id, now.device_id) === owner; };
  const cache = new AvatarCache({ load, createURL: blob => URL.createObjectURL(blob), revokeURL: url => URL.revokeObjectURL(url), accept });
  const unsubscribe = session.subscribe(() => { const now = session.getSnapshot().context; if (ownerPartition(now.user_id, now.device_id) !== owner) cache.reset(); });
  current = { owner, cache, unsubscribe };
  return cache;
}
