import { expect, test } from 'bun:test';
import { AuthOperations, DeviceStore } from '../src/session';
import { GroupCreationIntentStore } from '../src/GroupsPage';
import { AvatarSaveRecovery } from '../src/ProfilePage';
import { ContactLookupLifetime } from '../src/ContactsPage';
import { AttachmentTransferError } from '../src/attachment-transfer';
import type { AttachmentView } from '../src/types';
class TestStorage implements Storage {
  private values = new Map<string,string>();
  get length() { return this.values.size; }
  clear() { this.values.clear(); }
  getItem(key: string) { return this.values.get(key) ?? null; }
  key(index: number) { return [...this.values.keys()][index] ?? null; }
  removeItem(key: string) { this.values.delete(key); }
  setItem(key: string, value: string) { this.values.set(key, value); }
}
test('pending logout excludes a new cookie-producing auth operation until it settles', async () => {
  const operations = new AuthOperations(); let finish!: () => void; let cookie = 'old';
  const logout = operations.run(async () => { await new Promise<void>(resolve => { finish = resolve; }); cookie = ''; });
  await Promise.resolve();
  const login = operations.run(async () => { cookie = 'new'; });
  await Promise.resolve(); expect(cookie).toBe('old');
  finish(); await logout; await login; expect(cookie).toBe('new');
});
test('failed auth releases the queue without bypassing a preceding operation', async () => {
  const operations = new AuthOperations();
  const first = operations.run(async () => { throw new Error('service failure'); });
  const second = operations.run(async () => 'new login');
  await expect(first).rejects.toThrow('service failure'); expect(await second).toBe('new login');
});
test('server canonical email and submitted Unicode alias reuse the same public-owner device', () => {
  const store = new DeviceStore(new TestStorage());
  store.save({ id: 'public-a', email: 'strasse@example.test', display_name: 'A', avatar_attachment_id: null }, 'server-device-a', 'straße@example.test');
  expect(store.lookup('straße@example.test')).toBe('server-device-a');
  expect(store.lookup('strasse@example.test')).toBe('server-device-a');
  expect(store.lookup('other@example.test')).toBeNull();
});
test('uncertain A14 retains its exact key and payload through remount and isolates owners', () => {
  const storage = new TestStorage(), first = new GroupCreationIntentStore('owner-a', storage);
  const intent = first.begin({ title: 'Original', member_ids: ['public-b'] });
  const remounted = new GroupCreationIntentStore('owner-a', storage);
  expect(remounted.begin({ title: 'Changed', member_ids: [] })).toEqual(intent);
  expect(new GroupCreationIntentStore('owner-b', storage).read()).toBeNull();
  remounted.confirm(intent.key); expect(first.read()).toBeNull();
  expect(first.begin({ title: 'Next', member_ids: [] }).key).not.toBe(intent.key);
});
const ready: AttachmentView = { id: 'ready-a', scope: 'avatar', conversation_id: null, uploader_id: 'public-a', kind: 'image', filename: 'avatar.png', content_type: 'image/png', size_bytes: 1, sha256: 'a'.repeat(64), state: 'ready', created_at: '2026-10-01T00:00:00Z' };
test('avatar recovery reconciles original transfer then reuses readiness for failed A06', async () => {
  const recovery = new AvatarSaveRecovery(); const file = new File(['x'], 'avatar.png', { type: 'image/png' }); recovery.select(file);
  let uploads = 0, reconciles = 0;
  const upload = async () => { ++uploads; throw new AttachmentTransferError('TRANSFER_UNCONFIRMED', true, async () => { ++reconciles; return ready; }); };
  await expect(recovery.attachment(upload)).rejects.toThrow();
  expect(await recovery.attachment(upload)).toBe('ready-a');
  expect(await recovery.attachment(upload)).toBe('ready-a');
  expect(uploads).toBe(1); expect(reconciles).toBe(1);
  recovery.select(new File(['y'], 'new.png', { type: 'image/png' }));
  expect(recovery.readyId).toBeNull(); expect(recovery.retry).toBeNull();
});
test('a late contact lookup cannot apply global history after a newer selection or route teardown', () => {
  const lifetime = new ContactLookupLifetime(), history: string[] = [];
  const lookup = lifetime.begin();
  lifetime.invalidate();
  expect(lifetime.apply(lookup, () => history.push('/contacts'))).toBe(false);
  const later = lifetime.begin();
  lifetime.dispose();
  expect(lifetime.apply(later, () => history.push('/contacts'))).toBe(false);
  expect(history).toEqual([]);
  lifetime.activate();
  const current = lifetime.begin();
  expect(lifetime.apply(current, () => history.push('/contacts'))).toBe(true);
  expect(history).toEqual(['/contacts']);
});
test('corrupt DeviceStore cannot send an invented device or bypass persistence failure', () => {
  const storage = new TestStorage(); storage.setItem('hine-device-store', '{broken');
  expect(() => new DeviceStore(storage).lookup('a@example.test')).toThrow('本機儲存不可用');
});
