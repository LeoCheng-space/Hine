import { expect, test } from 'bun:test';
import { ActivityBook, DeniedMemory, accentIndex, activityBookFor, buildTimeline, deniedMemoryFor, entryAnimationIds, formatListTime, intentStatus, messageStatus, previewText, sortConversations } from './chat-presentation';
import type { MessageView } from './types';

const now = new Date(2026, 9, 17, 15, 0);
const at = (y: number, m: number, d: number, h = 9, min = 5) => new Date(y, m - 1, d, h, min).toISOString();
function text(id: string, sender: string, body: string, order: string): MessageView {
  return { id, event_id: id, conversation_id: 'c', sender_id: sender, created_at: at(2026, 10, 17), order_key: order, receipt: null, type: 'text', text: body };
}

test('list time shows 24-hour clock today, 昨天, weekday within a week, then dates', () => {
  expect(formatListTime(at(2026, 10, 17, 0, 5), now)).toBe('00:05');
  expect(formatListTime(at(2026, 10, 17, 9, 5), now)).toBe('09:05');
  expect(formatListTime(at(2026, 10, 16), now)).toBe('昨天');
  expect(formatListTime(at(2026, 10, 12), now)).toBe('週一');
  expect(formatListTime(at(2026, 10, 9), now)).toBe('10/9');
  expect(formatListTime(at(2025, 12, 31), now)).toBe('2025/12/31');
});
test('preview prefixes own and group senders, folds whitespace and labels attachments', () => {
  const nameOf = (id: string) => (id === 'ann' ? 'Ann' : id);
  expect(previewText(undefined, 'direct', 'me', nameOf)).toBe('—');
  expect(previewText(text('1', 'me', '你好', '1'), 'direct', 'me', nameOf)).toBe('你：你好');
  expect(previewText(text('1', 'ann', '嗨', '1'), 'direct', 'me', nameOf)).toBe('嗨');
  expect(previewText(text('1', 'ann', '嗨', '1'), 'group', 'me', nameOf)).toBe('Ann：嗨');
  expect(previewText(text('1', 'ann', '第一行\n  第二行', '1'), 'direct', 'me', nameOf)).toBe('第一行 第二行');
  const image: MessageView = { ...text('2', 'ann', '', '2'), type: 'image', attachment_id: 'a', text: undefined };
  const file: MessageView = { ...text('3', 'ann', '', '3'), type: 'file', attachment_id: 'f', text: undefined };
  expect(previewText(image, 'direct', 'me', nameOf)).toBe('📷 圖片');
  expect(previewText(file, 'group', 'me', nameOf)).toBe('Ann：📄 檔案');
});
test('activity only moves forward and survives temporarily empty snapshots', () => {
  const book = new ActivityBook();
  book.observe('c', '2026-10-17T01:00:05.000Z');
  book.observe('c', undefined);
  book.observe('c', '2026-10-17T01:00:03.000Z');
  expect(book.get('c')).toBe(Date.parse('2026-10-17T01:00:05.000Z'));
  book.drop('c');
  expect(book.get('c')).toBeUndefined();
});
test('unparseable timestamps are ignored', () => {
  const book = new ActivityBook();
  book.observe('c', 'not-a-time');
  expect(book.get('c')).toBeUndefined();
});
test('sorting puts conversations with activity first, newest first, and keeps A11 order otherwise', () => {
  const book = new ActivityBook();
  book.observe('b', '2026-10-17T01:00:02.000Z');
  book.observe('d', '2026-10-17T01:00:09.000Z');
  expect(sortConversations([{ id: 'a' }, { id: 'b' }, { id: 'c' }, { id: 'd' }], book).map(item => item.id)).toEqual(['d', 'b', 'a', 'c']);
});
test('a new message moves only its conversation and equal times keep A11 order', () => {
  const book = new ActivityBook(), items = [{ id: 'a' }, { id: 'b' }, { id: 'c' }];
  for (const id of ['a', 'b', 'c']) book.observe(id, '2026-10-17T01:00:00.000Z');
  expect(sortConversations(items, book).map(item => item.id)).toEqual(['a', 'b', 'c']);
  book.observe('c', '2026-10-17T01:00:01.000Z');
  expect(sortConversations(items, book).map(item => item.id)).toEqual(['c', 'a', 'b']);
});
test('activity books and denied memories are isolated per owner', () => {
  activityBookFor('["u1","d1"]').observe('c', '2026-10-17T01:00:00.000Z');
  deniedMemoryFor('["u1","d1"]').hide('g');
  expect(activityBookFor('["u2","d2"]').get('c')).toBeUndefined();
  expect(deniedMemoryFor('["u2","d2"]').has('g')).toBe(false);
  expect(activityBookFor('["u1","d1"]').get('c')).toBeUndefined();
});
test('denied memory hides until the next completed list reload', () => {
  const memory = new DeniedMemory();
  memory.hide('g');
  expect(memory.has('g')).toBe(true);
  memory.clear();
  expect(memory.has('g')).toBe(false);
});
test('accent index is deterministic and within one to six', () => {
  expect(accentIndex('user-a')).toBe(accentIndex('user-a'));
  for (const id of ['a', 'b', 'c', 'dd', 'eee', '中文']) { expect(accentIndex(id)).toBeGreaterThanOrEqual(1); expect(accentIndex(id)).toBeLessThanOrEqual(6); }
});

function stamped(id: string, sender: string, created: Date, order: string): MessageView {
  return { id, event_id: id, conversation_id: 'c', sender_id: sender, created_at: created.toISOString(), order_key: order, receipt: null, type: 'text', text: id };
}
test('timeline groups one sender within five minutes on the same day', () => {
  const items = buildTimeline([
    stamped('m1', 'ann', new Date(2026, 9, 16, 23, 58), '1'),
    stamped('m2', 'ann', new Date(2026, 9, 17, 0, 1), '2'),
    stamped('m3', 'ann', new Date(2026, 9, 17, 0, 4), '3'),
    stamped('m4', 'bob', new Date(2026, 9, 17, 0, 5), '4'),
    stamped('m5', 'bob', new Date(2026, 9, 17, 0, 11), '5'),
  ], new Date(2026, 9, 17, 12, 0));
  expect(items.map(item => item.kind === 'date' ? `${item.key}|${item.label}` : `${item.message.id}:${+item.groupStart}${+item.groupEnd}`)).toEqual([
    'date:2026-10-16|昨天', 'm1:11', 'date:2026-10-17|今天', 'm2:10', 'm3:01', 'm4:11', 'm5:11',
  ]);
});
test('date labels show month and day this year and the year otherwise', () => {
  const now = new Date(2026, 9, 17, 12, 0);
  const label = (date: Date) => { const item = buildTimeline([stamped('m', 'a', date, '1')], now)[0]; return item.kind === 'date' ? item.label : null; };
  expect(label(new Date(2026, 9, 10, 9))).toBe('10月10日');
  expect(label(new Date(2025, 11, 31, 9))).toBe('2025年12月31日');
});
test('date keys are not message ids and stay stable when history is prepended', () => {
  const now = new Date(2026, 9, 17, 12, 0), sameDay = new Date(2026, 9, 17, 9, 0);
  const keys = (list: MessageView[]) => buildTimeline(list, now).filter(item => item.kind === 'date').map(item => item.key);
  expect(keys([stamped('m1', 'a', sameDay, '1'), stamped('m2', 'a', sameDay, '2')])).toEqual(keys([stamped('m2', 'a', sameDay, '2')]));
  for (const key of keys([stamped('m2', 'a', sameDay, '2')])) expect(key.startsWith('date:')).toBe(true);
});
test('status text matches the existing message meta wording', () => {
  const base = stamped('m', 'me', new Date(2026, 9, 17, 9), '1');
  const receipt = (status: 'delivered' | 'read') => ({ kind: 'direct' as const, message_id: 'm', recipient_id: 'b', status, updated_at: base.created_at });
  expect(messageStatus(base, 'direct')).toEqual({ icon: 'check', text: '已持久保存' });
  expect(messageStatus({ ...base, receipt: receipt('delivered') }, 'direct')).toEqual({ icon: 'double', text: '已送達' });
  expect(messageStatus({ ...base, receipt: receipt('read') }, 'direct')).toEqual({ icon: 'double-read', text: '已讀' });
  expect(messageStatus(base, 'group')).toEqual({ icon: 'check', text: '已持久保存' });
  expect(intentStatus('pending')).toEqual({ icon: 'clock', text: '等待傳送' });
  expect(intentStatus('persisted')).toEqual({ icon: 'clock', text: '已持久保存，正在核對訊息' });
  expect(intentStatus('unknown')).toEqual({ icon: 'warn', text: '結果尚未確認' });
  expect(intentStatus('rejected')).toEqual({ icon: 'warn', text: '未傳送' });
});
test('only a few messages appended after an established baseline animate', () => {
  expect(entryAnimationIds(null, ['a', 'b'], new Set())).toEqual([]);
  expect(entryAnimationIds([], ['a'], new Set())).toEqual([]);
  expect(entryAnimationIds(['b', 'c'], ['a', 'b', 'c'], new Set())).toEqual([]);
  expect(entryAnimationIds(['a', 'b'], ['a', 'b', 'c', 'd'], new Set())).toEqual(['c', 'd']);
  expect(entryAnimationIds(['a', 'b'], ['a', 'b', 'c'], new Set(['c']))).toEqual([]);
  expect(entryAnimationIds(['x'], ['a', 'b'], new Set())).toEqual([]);
  expect(entryAnimationIds(['a'], ['a', 'b', 'c', 'd', 'e'], new Set())).toEqual([]);
});
