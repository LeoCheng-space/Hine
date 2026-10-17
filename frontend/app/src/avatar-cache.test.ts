import { expect, test } from 'bun:test';
import { AvatarCache, type AvatarHandle } from './avatar-cache';

interface Deferred<T> { promise: Promise<T>; resolve(value: T): void; reject(reason?: unknown): void }
function harness(options: { idleLimit?: number; concurrency?: number } = {}) {
  const loads: { id: string; signal: AbortSignal; done: Deferred<Blob> }[] = [], revoked: string[] = [];
  let next = 0;
  const cache = new AvatarCache({
    load: (id, signal) => { const done = Promise.withResolvers<Blob>(); loads.push({ id, signal, done }); return done.promise; },
    createURL: () => `blob:${++next}`,
    revokeURL: url => { revoked.push(url); },
    accept: () => true,
  }, { idleLimit: options.idleLimit ?? 48, concurrency: options.concurrency ?? 4 });
  return { cache, loads, revoked };
}
// Drains promise reactions (no wall-clock timer): the cache's internal `finally` has no exposed promise to await.
async function drainMicrotasks(): Promise<void> { for (let i = 0; i < 5; i++) await Promise.resolve(); }
const blob = () => new Blob(['x']);

test('concurrent acquires share one download and one object URL', async () => {
  const { cache, loads } = harness();
  const a = cache.acquire('p'), b = cache.acquire('p');
  expect(loads.length).toBe(1);
  loads[0].done.resolve(blob());
  expect(await a.url).toBe('blob:1'); expect(await b.url).toBe('blob:1');
});
test('a released avatar is reused without downloading again', async () => {
  const { cache, loads } = harness();
  const first = cache.acquire('p'); loads[0].done.resolve(blob()); await first.url;
  first.release();
  expect(await cache.acquire('p').url).toBe('blob:1');
  expect(loads.length).toBe(1);
});
test('idle avatars beyond the limit are revoked oldest first; in-use ones are kept', async () => {
  const { cache, loads, revoked } = harness({ idleLimit: 1 });
  const handles: AvatarHandle[] = [];
  for (const id of ['a', 'b', 'c']) { const handle = cache.acquire(id); loads.at(-1)!.done.resolve(blob()); await handle.url; handles.push(handle); }
  handles[0].release(); handles[1].release();
  expect(revoked).toEqual(['blob:1']);
  expect(await cache.acquire('c').url).toBe('blob:3');
});
test('failures are not cached and resolve to null', async () => {
  const { cache, loads } = harness();
  const first = cache.acquire('p'); loads[0].done.reject(new Error('expired'));
  expect(await first.url).toBeNull();
  first.release();
  void cache.acquire('p');
  expect(loads.length).toBe(2);
});
test('a stale handle from a failed download cannot release a newer entry', async () => {
  const { cache, loads, revoked } = harness({ idleLimit: 0 });
  const first = cache.acquire('p'); loads[0].done.reject(new Error('expired'));
  expect(await first.url).toBeNull();
  const second = cache.acquire('p');
  first.release(); first.release();
  loads[1].done.resolve(blob());
  expect(await second.url).toBe('blob:1');
  expect(revoked).toEqual([]);
});
test('no more than the configured number of downloads run at once', async () => {
  const { cache, loads } = harness({ concurrency: 2 });
  for (const id of ['a', 'b', 'c']) void cache.acquire(id);
  expect(loads.length).toBe(2);
  loads[0].done.resolve(blob()); await drainMicrotasks();
  expect(loads.length).toBe(3);
});
test('reset aborts downloads, revokes every URL and settles pending acquires with null', async () => {
  const { cache, loads, revoked } = harness();
  const held = cache.acquire('a'); loads[0].done.resolve(blob()); await held.url;
  const pending = cache.acquire('b');
  cache.reset();
  expect(loads[1].signal.aborted).toBe(true);
  expect(await pending.url).toBeNull();
  expect(revoked).toEqual(['blob:1']);
  loads[1].done.resolve(blob()); await drainMicrotasks();
  held.release();
  expect(revoked.length).toBe(1);
});
