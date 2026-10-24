import type { SendIntent } from './repository';
import type { MessageView } from './types';

/** 24-hour clock shared by list times and message meta. */
export const CLOCK = new Intl.DateTimeFormat('zh-TW', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
const WEEKDAY = ['週日', '週一', '週二', '週三', '週四', '週五', '週六'];
const DAY_MS = 86_400_000, GROUP_WINDOW_MS = 5 * 60_000;
/** Bursts larger than this (offline catch-up, reconnect) never animate. */
export const MAX_ENTRY_ANIMATIONS = 3;

function dayStart(value: Date): number { return new Date(value.getFullYear(), value.getMonth(), value.getDate()).getTime(); }

export function formatListTime(iso: string, now: Date): string {
  const value = new Date(iso), days = Math.round((dayStart(now) - dayStart(value)) / DAY_MS);
  if (days <= 0) return CLOCK.format(value);
  if (days === 1) return '昨天';
  if (days < 7) return WEEKDAY[value.getDay()];
  if (value.getFullYear() === now.getFullYear()) return `${value.getMonth() + 1}/${value.getDate()}`;
  return `${value.getFullYear()}/${value.getMonth() + 1}/${value.getDate()}`;
}

export function dateLabel(value: Date, now: Date): string {
  const days = Math.round((dayStart(now) - dayStart(value)) / DAY_MS);
  if (days <= 0) return '今天';
  if (days === 1) return '昨天';
  return value.getFullYear() === now.getFullYear() ? `${value.getMonth() + 1}月${value.getDate()}日` : `${value.getFullYear()}年${value.getMonth() + 1}月${value.getDate()}日`;
}

export type TimelineItem = { kind: 'date'; key: string; label: string } | { kind: 'message'; message: MessageView; groupStart: boolean; groupEnd: boolean };
/** Date separators keyed by calendar day (never by message id) and sender groups of consecutive messages within five minutes on one day. */
export function buildTimeline(messages: MessageView[], now: Date): TimelineItem[] {
  const items: TimelineItem[] = [];
  let previous: MessageView | null = null, lastDay = '';
  for (const message of messages) {
    const created = new Date(message.created_at);
    const day = `date:${created.getFullYear()}-${String(created.getMonth() + 1).padStart(2, '0')}-${String(created.getDate()).padStart(2, '0')}`;
    if (day !== lastDay) { items.push({ kind: 'date', key: day, label: dateLabel(created, now) }); lastDay = day; previous = null; }
    const joins = previous !== null && previous.sender_id === message.sender_id && Date.parse(message.created_at) - Date.parse(previous.created_at) <= GROUP_WINDOW_MS;
    const last = items.at(-1);
    if (joins && last?.kind === 'message') last.groupEnd = false;
    items.push({ kind: 'message', message, groupStart: !joins, groupEnd: true });
    previous = message;
  }
  return items;
}

export type StatusIcon = 'clock' | 'check' | 'double' | 'double-read' | 'warn';
export function messageStatus(message: MessageView, kind: 'direct' | 'group'): { icon: StatusIcon; text: string } {
  if (kind === 'direct' && message.receipt) return message.receipt.status === 'read' ? { icon: 'double-read', text: '已讀' } : { icon: 'double', text: '已送達' };
  return { icon: 'check', text: '已送出' };
}
export function intentStatus(status: SendIntent['status']): { icon: StatusIcon; text: string } {
  if (status === 'persisted') return { icon: 'clock', text: '已送出，正在確認' };
  if (status === 'rejected') return { icon: 'warn', text: '未傳送' };
  if (status === 'unknown') return { icon: 'warn', text: '結果尚未確認' };
  return { icon: 'clock', text: '等待傳送' };
}

/** Messages to animate: appended after the previous render's last message, not replacing a shown intent, at most MAX_ENTRY_ANIMATIONS. No baseline (first render, reconnect) animates nothing. */
export function entryAnimationIds(baseline: readonly string[] | null, next: readonly string[], replaced: ReadonlySet<string>): string[] {
  if (!baseline?.length) return [];
  const index = next.indexOf(baseline[baseline.length - 1]); if (index < 0) return [];
  const known = new Set(baseline);
  const entering = next.slice(index + 1).filter(id => !known.has(id) && !replaced.has(id));
  return entering.length > MAX_ENTRY_ANIMATIONS ? [] : entering;
}

export function previewText(message: MessageView | undefined, kind: 'direct' | 'group', me: string, nameOf: (userId: string) => string): string {
  if (!message) return '—';
  const body = message.type === 'text' ? message.text.replace(/\s+/g, ' ').trim() : message.type === 'image' ? '📷 圖片' : '📄 檔案';
  if (message.sender_id === me) return `你：${body}`;
  return kind === 'group' ? `${nameOf(message.sender_id)}：${body}` : body;
}

/** Latest server `created_at` seen per conversation. Only moves forward; `order_key` is never compared across conversations (contract C11). */
export class ActivityBook {
  private readonly times = new Map<string, number>();
  observe(conversationId: string, createdAt: string | undefined): void {
    if (createdAt === undefined) return;
    const value = Date.parse(createdAt); if (Number.isNaN(value)) return;
    const current = this.times.get(conversationId);
    if (current === undefined || value > current) this.times.set(conversationId, value);
  }
  drop(conversationId: string): void { this.times.delete(conversationId); }
  get(conversationId: string): number | undefined { return this.times.get(conversationId); }
}

/** Conversations observed as denied; kept until the next completed A11 reload because `disconnect()` forgets them. */
export class DeniedMemory {
  private readonly ids = new Set<string>();
  hide(conversationId: string): void { this.ids.add(conversationId); }
  has(conversationId: string): boolean { return this.ids.has(conversationId); }
  clear(): void { this.ids.clear(); }
}

let scopedOwner: string | null = null, scopedBook = new ActivityBook(), scopedDenied = new DeniedMemory();
function scope(owner: string): void {
  if (owner === scopedOwner) return;
  scopedOwner = owner; scopedBook = new ActivityBook(); scopedDenied = new DeniedMemory();
}
export function activityBookFor(owner: string): ActivityBook { scope(owner); return scopedBook; }
export function deniedMemoryFor(owner: string): DeniedMemory { scope(owner); return scopedDenied; }

export function sortConversations<T extends { id: string }>(items: T[], book: ActivityBook): T[] {
  return items.map((item, index) => ({ item, index, key: book.get(item.id) }))
    .sort((a, b) => {
      if (a.key !== undefined && b.key !== undefined && a.key !== b.key) return b.key - a.key;
      if ((a.key === undefined) !== (b.key === undefined)) return a.key === undefined ? 1 : -1;
      return a.index - b.index;
    })
    .map(entry => entry.item);
}

export function accentIndex(id: string): 1 | 2 | 3 | 4 | 5 | 6 {
  let hash = 0x811c9dc5;
  for (const char of id) hash = Math.imul(hash ^ char.codePointAt(0)!, 0x01000193) >>> 0;
  return (hash % 6 + 1) as 1 | 2 | 3 | 4 | 5 | 6;
}
