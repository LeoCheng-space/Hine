import type { MessageView } from './types';

const clock = new Intl.DateTimeFormat('zh-TW', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
const WEEKDAY = ['週日', '週一', '週二', '週三', '週四', '週五', '週六'];
const DAY_MS = 86_400_000;

export function dayStart(value: Date): number { return new Date(value.getFullYear(), value.getMonth(), value.getDate()).getTime(); }

export function formatListTime(iso: string, now: Date): string {
  const value = new Date(iso), days = Math.round((dayStart(now) - dayStart(value)) / DAY_MS);
  if (days <= 0) return clock.format(value);
  if (days === 1) return '昨天';
  if (days < 7) return WEEKDAY[value.getDay()];
  if (value.getFullYear() === now.getFullYear()) return `${value.getMonth() + 1}/${value.getDate()}`;
  return `${value.getFullYear()}/${value.getMonth() + 1}/${value.getDate()}`;
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
