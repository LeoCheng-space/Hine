import { describe, expect, test } from 'bun:test';
import { parseRoute, routePath } from '../src/router';
import { validateConfig, retryDelay, ownerPartition } from '../src/api';
import { decodeAccessSession } from '../src/session';

describe('protected route boundaries', () => {
  test('an opaque Unicode and slash-containing conversation survives one encoded segment', () => {
    const route = parseRoute('/chats/%E7%B5%84%2F%3F%23');
    expect(route).toEqual({ kind: 'chat', conversationId: '組/?#' });
    expect(route && routePath(route)).toBe('/chats/%E7%B5%84%2F%3F%23');
  });
  test('external returns, malformed escapes and extra path segments are never routes', () => {
    for (const path of ['https://evil.test/chats', '//evil.test/chats', '/chats/a/b', '/chats/%', '/chats/a?x', '/chats/a#x', '/groups/a/manage/extra', '/admin']) expect(parseRoute(path)).toBeNull();
  });
  test('a management deep link keeps its opaque group ID', () => {
    expect(parseRoute('/groups/a%2Fb/manage')).toEqual({ kind: 'group', conversationId: 'a/b' });
  });
});
describe('authentication retry boundaries', () => {
  test('missing malformed or unsafe rate delay never becomes an immediate retry', () => {
    for (const value of [undefined, null, '0', -1, 1.5, Infinity, 9007199254740992]) expect(retryDelay(value)).toBeUndefined();
    expect(retryDelay(0)).toBe(0);
    expect(retryDelay(1200)).toBe(1200);
  });
  test('runtime endpoints must be secure, same origin and exact reconciliation cadence', () => {
    expect(validateConfig({ API_BASE_URL: 'https://hine.test/api/v1', WS_URL: 'wss://hine.test/ws', SYNC_RECONCILE_SECONDS: 10 }, 'https://hine.test').WS_URL).toBe('wss://hine.test/ws');
    for (const overrides of [{ API_BASE_URL: 'https://evil.test/api/v1' }, { WS_URL: 'ws://hine.test/ws' }, { WS_URL: 'wss://hine.test/ws?access_token=x' }, { SYNC_RECONCILE_SECONDS: 0 }]) expect(() => validateConfig({ API_BASE_URL: 'https://hine.test/api/v1', WS_URL: 'wss://hine.test/ws', SYNC_RECONCILE_SECONDS: 10, ...overrides }, 'https://hine.test')).toThrow();
  });
});
describe('access-session installation', () => {
  const access = { access_token: 'opaque-access', expires_at: '2100-01-01T00:00:00Z', user_id: 'public-a', device_id: 'server-device-a', session_generation: 2 };
  test('a refresh cannot silently switch public identity, device or regress generation', () => {
    const previous = { state: 'authenticated' as const, ...access, session_generation: 1 };
    expect(decodeAccessSession(access, previous)).toEqual(access);
    for (const changed of [{ user_id: 'public-b' }, { device_id: 'server-device-b' }, { session_generation: 1 }]) expect(() => decodeAccessSession({ ...access, ...changed }, previous)).toThrow();
  });
  test('malformed and already expired access never becomes usable auth', () => {
    for (const value of [null, {}, { ...access, device_id: null }, { ...access, session_generation: 1.5 }, { ...access, expires_at: '2000-01-01T00:00:00Z' }]) expect(() => decodeAccessSession(value)).toThrow();
  });
});
test('opaque user/device IDs cannot collide across local owner partitions', () => {
  expect(ownerPartition('a:b', 'c')).not.toBe(ownerPartition('a', 'b:c'));
  expect(ownerPartition('組', 'device')).toBe('[\"組\",\"device\"]');
});
