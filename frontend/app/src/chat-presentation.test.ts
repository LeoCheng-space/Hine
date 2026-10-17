import { expect, test } from 'bun:test';
import { ActivityBook, DeniedMemory, accentIndex, activityBookFor, deniedMemoryFor, formatListTime, previewText, sortConversations } from './chat-presentation';
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
