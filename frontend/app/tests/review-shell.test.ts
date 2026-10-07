import { expect, test } from 'bun:test';
import { DeviceStore } from '../src/session';
import { ownerPartition } from '../src/api';
import { emailCasefold } from '../src/email-casefold';
import type { UserProfile } from '../src/types';

// This is a Storage boundary fixture, not a replacement DeviceStore or auth authority.
class FixtureStorage implements Storage {
  private readonly values = new Map<string, string>();
  get length(): number { return this.values.size; }
  clear(): void { this.values.clear(); }
  getItem(key: string): string | null { return this.values.get(key) ?? null; }
  key(index: number): string | null { return [...this.values.keys()][index] ?? null; }
  removeItem(key: string): void { this.values.delete(key); }
  setItem(key: string, value: string): void { this.values.set(key, value); }
}
const profile = (id: string, email: string): UserProfile => ({ id, email, display_name: id, avatar_attachment_id: null });
let pythonFolds: Record<string, string> | undefined;
function authoritativeFolds(): Record<string, string> {
  if (pythonFolds) return pythonFolds;
  // Parent executes this test oracle, independently of the generated JS artifact.
  const authority = Bun.spawnSync([process.env.HINE_CASEFOLD_PYTHON ?? 'python3.12', '-c', [
    'import json, sys, unicodedata',
    'assert sys.version_info[:2] == (3, 12), "Python 3.12 is required"',
    'assert unicodedata.unidata_version == "15.0.0", "Unicode 15.0.0 is required"',
    'folds = {str(cp): chr(cp).casefold() for cp in range(0x110000) if not 0xD800 <= cp <= 0xDFFF and chr(cp).casefold() != chr(cp)}',
    'print(json.dumps(folds, ensure_ascii=True))',
  ].join('\n')]);
  expect(authority.exitCode, authority.stderr.toString()).toBe(0);
  pythonFolds = JSON.parse(authority.stdout.toString()) as Record<string, string>;
  return pythonFolds;
}


test('review: a never-saved fold-equivalent spelling reuses the server device after reload', () => {
  const storage = new FixtureStorage(), store = new DeviceStore(storage);
  // Saving both spellings would mask the original unknown-alias failure.
  store.save(profile('public-owner', 'strasse@example.test'), 'original-server-device');
  expect(new DeviceStore(storage).lookup('straße@example.test')).toBe('original-server-device');
});

test('review: legacy lowercase aliases migrate through canonical owners without losing either owner partition', () => {
  const storage = new FixtureStorage();
  storage.setItem('hine-device-store', JSON.stringify({
    owners: {
      'public-a': { device_id: 'original-a', canonical_email: 'strasse@example.test' },
      'public-b': { device_id: 'original-b', canonical_email: 'οσ@example.test' },
    },
    aliases: { 'straße@example.test': 'public-a', 'ος@example.test': 'public-b' },
  }));
  const reloaded = new DeviceStore(storage);
  expect(reloaded.lookup('STRAẞE@EXAMPLE.TEST')).toBe('original-a');
  expect(reloaded.lookup('ΟΣ@EXAMPLE.TEST')).toBe('original-b');
  reloaded.save(profile('public-a', 'strasse@example.test'), 'original-a', 'STRAẞE@EXAMPLE.TEST');
  expect(new DeviceStore(storage).lookup('straße@example.test')).toBe('original-a');
  expect(new DeviceStore(storage).lookup('ος@example.test')).toBe('original-b');
  expect(new DeviceStore(storage).lookup('nobody@example.test')).toBeNull();
});

test('review: canonical server binding replaces only that public owner and does not invent normalization equivalence', () => {
  const storage = new FixtureStorage(), store = new DeviceStore(storage);
  store.save(profile('public-a', 'strasse@example.test'), 'old-a');
  store.save(profile('public-b', 'οσ@example.test'), 'device-b');
  store.save(profile('public-a', 'strasse@example.test'), 'canonical-new-a', 'STRASSE@example.test');
  expect(new DeviceStore(storage).lookup('straße@example.test')).toBe('canonical-new-a');
  expect(new DeviceStore(storage).lookup('ος@example.test')).toBe('device-b');
  expect(store.lookup('stras\u0301se@example.test')).toBeNull();
  expect(store.lookup('ｓｔｒａｓｓｅ@example.test')).toBeNull();
  expect(ownerPartition('public-a', store.lookup('straße@example.test'))).toBe('["public-a","canonical-new-a"]');
  expect(ownerPartition('public-b', store.lookup('ος@example.test'))).toBe('["public-b","device-b"]');
});

test('review: DeviceStore lookup equals Python 3.12 Unicode 15 full casefold for every Unicode scalar', () => {
  const folds = authoritativeFolds();
  const storage = new FixtureStorage(), store = new DeviceStore(storage);
  for (let codepoint = 0; codepoint <= 0x10ffff; codepoint++) {
    if (codepoint >= 0xd800 && codepoint <= 0xdfff) continue;
    const input = String.fromCodePoint(codepoint), expected = folds[String(codepoint)] ?? input;
    storage.clear();
    store.save(profile('scalar-owner', `${expected}@example.test`), 'scalar-device');
    const actual = store.lookup(`${input}@example.test`);
    if (actual !== 'scalar-device') throw new Error(`DeviceStore disagrees with Python 3.12 Unicode 15 at U+${codepoint.toString(16).toUpperCase().padStart(4, '0')}`);
  }
}, 120_000);

test('review: exact runtime fold matches Python 3.12 Unicode 15 for every scalar including Cherokee capitals', () => {
  const folds = authoritativeFolds();
  for (let codepoint = 0; codepoint <= 0x10ffff; codepoint++) {
    if (codepoint >= 0xd800 && codepoint <= 0xdfff) continue;
    const input = String.fromCodePoint(codepoint), expected = folds[String(codepoint)] ?? input;
    if (emailCasefold(input) !== expected) throw new Error(`Exact fold differs from Python at U+${codepoint.toString(16).toUpperCase().padStart(4, '0')}`);
  }
  // Context-sensitive JS lowercase final-sigma behavior must not sneak back in.
  expect(emailCasefold('STRAẞE ΟΣ Ος oﬃce ꭰ İ')).toBe('strasse οσ οσ office Ꭰ i\u0307');
}, 30_000);
