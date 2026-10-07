import { expect, test } from 'bun:test';
import { validateDownloadGrant } from '../src/attachment-transfer';
import { fetchAvatarBytes } from '../src/ContactsPage';
const grant = { download_url: 'https://storage.googleapis.com/private/avatar?generation=17', expires_at: '2099-01-01T00:00:00Z', content_type: 'image/png', filename: 'avatar.png', size_bytes: 3 };
test('avatar A22 rejects an unpinned, expired, insecure or non-storage grant', () => {
  for (const changed of [
    { download_url: 'https://storage.googleapis.com/private/avatar' },
    { download_url: 'http://storage.googleapis.com/private/avatar?generation=17' },
    { download_url: 'https://other.test/avatar?generation=17' },
    { download_url: 'https://user:password@storage.googleapis.com/private/avatar?generation=17' },
    { expires_at: '2000-01-01T00:00:00Z' },
    { content_type: 'image/svg+xml' },
    { size_bytes: 0 },
  ]) expect(() => validateDownloadGrant({ ...grant, ...changed })).toThrow();
  expect(validateDownloadGrant(grant)).toEqual(grant);
});
test('avatar binary transfer omits credentials and forbids redirects without changing pinned URL', async () => {
  let received: globalThis.RequestInit | undefined;
  const blob = await fetchAvatarBytes(validateDownloadGrant(grant), async (url, init) => {
    expect(url).toBe('https://storage.googleapis.com/private/avatar?generation=17');
    received = init;
    return new Response(new Uint8Array([1, 2, 3]), { status: 200, headers: { 'Content-Type': 'image/png' } });
  });
  expect(received?.credentials).toBe('omit');
  expect(received?.redirect).toBe('error');
  expect(received?.referrerPolicy).toBe('no-referrer');
  expect(received?.headers).toBeUndefined();
  expect(blob.size).toBe(3);
});
test('avatar refuses an HTTP failure or bytes differing from verified metadata', async () => {
  await expect(fetchAvatarBytes(validateDownloadGrant(grant), async () => new Response(null, { status: 403 }))).rejects.toThrow();
  await expect(fetchAvatarBytes(validateDownloadGrant(grant), async () => new Response(new Uint8Array([1, 2]), { status: 200 }))).rejects.toThrow();
});
