import { expect, test } from 'bun:test';
import { UserDirectory, directoryFor, type DirectorySummary } from './user-directory';
import type { SessionController } from './session';

interface Deferred<T> { promise: Promise<T>; resolve(value: T): void; reject(reason?: unknown): void }
interface Call { id: string; signal: AbortSignal; done: Deferred<DirectorySummary> }
function harness(options: { concurrency?: number; accept?: () => boolean } = {}) {
  const calls: Call[] = [];
  let time = 0;
  const directory = new UserDirectory({
    fetchSummary: (id, signal) => { const done = Promise.withResolvers<DirectorySummary>(); calls.push({ id, signal, done }); return done.promise; },
    now: () => time,
    accept: options.accept ?? (() => true),
  }, { ttlMs: 300_000, concurrency: options.concurrency ?? 4, failureBackoffMs: 30_000 });
  return { directory, calls, advance: (ms: number) => { time += ms; } };
}

test('concurrent ensures for one user share a single request', () => {
  const { directory, calls } = harness();
  void directory.ensure('u'); void directory.ensure('u');
  expect(calls.length).toBe(1);
});
test('no more than the configured number of requests run at once', async () => {
  const { directory, calls } = harness({ concurrency: 4 });
  const pending = ['a', 'b', 'c', 'd', 'e', 'f'].map(id => directory.ensure(id));
  expect(calls.length).toBe(4);
  calls[0].done.resolve({ display_name: 'A', avatar_attachment_id: null }); await pending[0];
  expect(calls.length).toBe(5);
});
test('reset aborts requests, discards late responses and settles queued work', async () => {
  const { directory, calls } = harness({ concurrency: 1 });
  const running = directory.ensure('u'), queued = directory.ensure('v');
  directory.reset();
  expect(calls[0].signal.aborted).toBe(true);
  await queued;
  calls[0].done.resolve({ display_name: 'Old account', avatar_attachment_id: 'old' }); await running;
  expect(directory.get('u')).toBeUndefined();
  expect(calls.length).toBe(1);
});
test('failures resolve quietly, are not cached and back off before retrying', async () => {
  const { directory, calls, advance } = harness();
  const first = directory.ensure('u');
  calls[0].done.reject(new Error('DEPENDENCY_UNAVAILABLE'));
  await first;
  expect(directory.get('u')).toBeUndefined();
  await directory.ensure('u'); expect(calls.length).toBe(1);
  advance(30_001); void directory.ensure('u');
  expect(calls.length).toBe(2);
});
test('a request cancelled by a token refresh is retried without backoff', async () => {
  const { directory, calls } = harness();
  const first = directory.ensure('u');
  calls[0].done.reject(Object.assign(new Error('refresh'), { code: 'UNAUTHENTICATED' }));
  await first;
  void directory.ensure('u');
  expect(calls.length).toBe(2);
});
test('a newer put is not overwritten by an older in-flight response', async () => {
  const { directory, calls } = harness();
  const first = directory.ensure('me');
  directory.put('me', { display_name: 'New name', avatar_attachment_id: null });
  calls[0].done.resolve({ display_name: 'Old name', avatar_attachment_id: null }); await first;
  expect(directory.get('me')?.displayName).toBe('New name');
});
test('an in-flight request made stale by a version change is replaced, not reused', async () => {
  const { directory, calls } = harness();
  const old = directory.ensure('u');
  directory.markAvatarsStale(['u']);
  const fresh = directory.ensure('u');
  expect(calls.length).toBe(2);
  calls[0].done.resolve({ display_name: 'Ann', avatar_attachment_id: 'old' }); await old;
  expect(directory.get('u')).toBeUndefined();
  calls[1].done.resolve({ display_name: 'Ann', avatar_attachment_id: 'new' }); await fresh;
  expect(directory.get('u')?.avatarId).toBe('new');
});
test('marking avatars stale forces a refetch that clears the stale flag', async () => {
  const { directory, calls } = harness();
  const first = directory.ensure('u');
  calls[0].done.resolve({ display_name: 'Ann', avatar_attachment_id: 'x' }); await first;
  await directory.ensure('u'); expect(calls.length).toBe(1);
  directory.markAvatarsStale(['u']);
  expect(directory.get('u')?.avatarStale).toBe(true);
  const again = directory.ensure('u');
  calls[1].done.resolve({ display_name: 'Ann', avatar_attachment_id: 'y' }); await again;
  expect(directory.get('u')).toMatchObject({ avatarId: 'y', avatarStale: false });
});
test('marking avatars stale refetches users already shown, without waiting for another ensure', async () => {
  const { directory, calls } = harness();
  const first = directory.ensure('u');
  calls[0].done.resolve({ display_name: 'Ann', avatar_attachment_id: 'x' }); await first;
  directory.markAvatarsStale(['u', 'never-shown']);
  expect(calls.map(call => call.id)).toEqual(['u', 'u']);
  calls[1].done.resolve({ display_name: 'Ann', avatar_attachment_id: 'y' }); await directory.ensure('u');
  expect(directory.get('u')).toMatchObject({ avatarId: 'y', avatarStale: false });
});
test('fresh entries are reused and expired entries are revalidated', async () => {
  const { directory, calls, advance } = harness();
  const first = directory.ensure('u');
  calls[0].done.resolve({ display_name: 'Ann', avatar_attachment_id: null }); await first;
  await directory.ensure('u'); expect(calls.length).toBe(1);
  advance(300_001); void directory.ensure('u');
  expect(calls.length).toBe(2);
});
test('responses and puts are discarded when the owner is no longer accepted', async () => {
  let accepted = true;
  const { directory, calls } = harness({ accept: () => accepted });
  const first = directory.ensure('u');
  accepted = false;
  calls[0].done.resolve({ display_name: 'Ann', avatar_attachment_id: null }); await first;
  directory.put('v', { display_name: 'Leaked', avatar_attachment_id: 'a' });
  expect(directory.get('u')).toBeUndefined();
  expect(directory.get('v')).toBeUndefined();
});
test('a group membership version increase marks only that group members stale', async () => {
  const { directory, calls } = harness();
  for (const id of ['a', 'b', 'c']) { const done = directory.ensure(id); calls.at(-1)!.done.resolve({ display_name: id, avatar_attachment_id: null }); await done; }
  directory.observeMembership('g', 3, ['a', 'b']);
  expect(directory.get('a')?.avatarStale).toBe(false);
  directory.observeMembership('g', 3, ['a', 'b']);
  directory.observeMembership('g', null, ['a', 'b']);
  expect(directory.get('a')?.avatarStale).toBe(false);
  directory.observeMembership('g', 4, ['a', 'b']);
  expect(directory.get('a')?.avatarStale).toBe(true);
  expect(directory.get('b')?.avatarStale).toBe(true);
  expect(directory.get('c')?.avatarStale).toBe(false);
});
test('subscribe works when passed unbound', () => {
  const { directory } = harness();
  const { subscribe, getVersion } = directory;
  const unsubscribe = subscribe(() => {});
  expect(typeof getVersion()).toBe('number');
  unsubscribe();
});
test('switching account resets the directory and ignores the old account response', async () => {
  let snapshot = { context: { state: 'authenticated', user_id: 'A', device_id: 'd' } };
  const listeners = new Set<() => void>(), pending: Deferred<{ data: DirectorySummary }>[] = [];
  const fake = {
    getSnapshot: () => snapshot,
    subscribe: (listener: () => void) => { listeners.add(listener); return () => listeners.delete(listener); },
    request: () => { const done = Promise.withResolvers<{ data: DirectorySummary }>(); pending.push(done); return done.promise; },
  };
  // Structural fake: only the members directoryFor touches are implemented.
  const session = fake as unknown as SessionController;
  const first = directoryFor(session);
  const loading = first.ensure('x');
  snapshot = { context: { state: 'authenticated', user_id: 'B', device_id: 'd' } };
  for (const listener of listeners) listener();
  pending[0].resolve({ data: { display_name: 'From A', avatar_attachment_id: null } }); await loading;
  first.put('y', { display_name: 'A view of y', avatar_attachment_id: 'a' });
  const second = directoryFor(session);
  expect(second).not.toBe(first);
  expect(first.get('x')).toBeUndefined();
  expect(first.get('y')).toBeUndefined();
  expect(second.get('x')).toBeUndefined();
  expect(second.get('y')).toBeUndefined();
});
