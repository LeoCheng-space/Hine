import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { ownerPartition } from './api';
import { Avatar, usePagedList } from './ContactsPage';
import { CreateGroup } from './GroupsPage';
import { accentIndex, activityBookFor, deniedMemoryFor, formatListTime, previewText, sortConversations } from './chat-presentation';
import { RepositoryCancelled } from './repository';
import { directoryFor } from './user-directory';
import type { ChatController } from './chat';
import type { SessionController } from './session';
import type { ConversationSummary } from './types';

const PEER_REFRESH_LIMIT = 4;

export function ChatList({ session, chat, path, onNavigate }: { session: SessionController; chat: ChatController; path: string; onNavigate: (path: string) => void }) {
  const list = usePagedList<ConversationSummary>(session, 'conversations', item => item.id), [filter, setFilter] = useState('');
  const snapshot = useSyncExternalStore(chat.subscribe, chat.getSnapshot);
  const context = session.getSnapshot().context, me = context.user_id ?? '', owner = ownerPartition(context.user_id, context.device_id);
  const directory = directoryFor(session);
  const directoryVersion = useSyncExternalStore(directory.subscribe, directory.getVersion);
  const book = activityBookFor(owner), denied = deniedMemoryFor(owner);
  for (const id of snapshot.denied) { book.drop(id); denied.hide(id); }
  for (const item of list.items) book.observe(item.id, snapshot.messages[item.id]?.at(-1)?.created_at);

  useEffect(() => { void list.load(true); }, [path, list.load]);
  useEffect(() => {
    const changed = (): void => { void list.load(true); };
    window.addEventListener('hine-conversations-changed', changed);
    return () => window.removeEventListener('hine-conversations-changed', changed);
  }, [list.load]);

  // A completed A11 reload is authoritative: forget remembered revocations and allow one peer refresh per conversation again.
  const requestedPeers = useRef(new Set<string>()), wasBusy = useRef(list.busy);
  useEffect(() => {
    if (wasBusy.current && !list.busy && !list.error) { denied.clear(); requestedPeers.current.clear(); }
    wasBusy.current = list.busy;
  }, [list.busy, list.error, denied]);

  const [now, setNow] = useState(() => new Date());
  useEffect(() => { const timer = setInterval(() => setNow(new Date()), 60_000); return () => clearInterval(timer); }, []);

  const [visible, setVisible] = useState<ReadonlySet<string>>(() => new Set()), listRef = useRef<HTMLUListElement>(null);

  const peers = useMemo(() => {
    const result: Record<string, string> = {};
    for (const item of list.items) {
      if (item.type !== 'direct') continue;
      const peer = snapshot.messages[item.id]?.find(message => message.sender_id !== me)?.sender_id ?? snapshot.details[item.id]?.members.find(member => member.user_id !== me)?.user_id;
      if (peer) result[item.id] = peer;
    }
    return result;
  }, [list.items, snapshot.messages, snapshot.details, me]);

  const rows = useMemo(() => sortConversations(list.items.filter(item => !denied.has(item.id)), book).map(item => {
    const last = snapshot.messages[item.id]?.at(-1), peer = peers[item.id];
    const title = item.type === 'group' ? item.title ?? '群組' : peer ? directory.get(peer)?.displayName ?? peer : '一對一對話';
    return { item, last, peer, title };
  }), [list.items, snapshot.messages, snapshot.denied, peers, book, denied, directory, directoryVersion]);
  const term = filter.trim().toLocaleLowerCase();
  const shown = term ? rows.filter(row => row.title.toLocaleLowerCase().includes(term)) : rows;
  const rowIds = shown.map(row => row.item.id).join(',');
  useEffect(() => {
    const root = listRef.current; if (!root) return;
    const observer = new IntersectionObserver(entries => setVisible(current => {
      let next: Set<string> | null = null;
      for (const entry of entries) {
        if (!(entry.target instanceof HTMLElement)) continue;
        const id = entry.target.dataset.conversationId; if (!id || entry.isIntersecting === current.has(id)) continue;
        next ??= new Set(current);
        if (entry.isIntersecting) next.add(id); else next.delete(id);
      }
      return next ?? current;
    }));
    for (const node of root.querySelectorAll('[data-conversation-id]')) observer.observe(node);
    return () => observer.disconnect();
  }, [rowIds]);

  const missingPeers = rows.filter(row => row.item.type === 'direct' && !row.peer && visible.has(row.item.id)).map(row => row.item.id).sort().join(',');
  useEffect(() => {
    const ids = missingPeers.split(',').filter(id => id && !requestedPeers.current.has(id));
    let cancelled = false;
    const worker = async (): Promise<void> => {
      for (let id = ids.shift(); id !== undefined && !cancelled; id = ids.shift()) {
        requestedPeers.current.add(id);
        try { await chat.refreshConversation(id); }
        catch (error) {
          // Cancelled reads (closed database, session turnover) may retry on the next load cycle; other failures keep the fallback title.
          if (error instanceof RepositoryCancelled || (error instanceof Error && 'code' in error && error.code === 'UNAUTHENTICATED')) requestedPeers.current.delete(id);
        }
      }
    };
    for (let i = 0; i < Math.min(PEER_REFRESH_LIMIT, ids.length); i++) void worker();
    return () => { cancelled = true; };
  }, [missingPeers, chat]);

  const nameIds = useMemo(() => {
    const ids = new Set<string>();
    for (const row of rows) {
      if (!visible.has(row.item.id)) continue;
      if (row.peer) ids.add(row.peer);
      if (row.item.type === 'group' && row.last && row.last.sender_id !== me) ids.add(row.last.sender_id);
    }
    return [...ids].sort().join(',');
  }, [rows, visible, me]);
  useEffect(() => { for (const id of nameIds.split(',').filter(Boolean)) void directory.ensure(id); }, [nameIds, directory]);
  useEffect(() => {
    for (const detail of Object.values(snapshot.details)) if (detail.type === 'group') directory.observeMembership(detail.id, detail.membership_version, detail.members.map(member => member.user_id));
  }, [snapshot.details, directory]);

  return <aside className="list-panel chat-list">
    <header className="chat-list-header">
      <h1 tabIndex={-1} data-route-heading={path === '/chats' ? '' : undefined}>聊天</h1>
      <label className="visually-hidden" htmlFor="chat-filter">搜尋已載入的對話</label>
      <input id="chat-filter" className="chat-search" type="search" placeholder="搜尋" value={filter} onChange={event => setFilter(event.target.value)} />
      {term && <p className="small muted list-hint">只篩選已載入項目</p>}
    </header>
    <CreateGroup session={session} onCreated={id => onNavigate(`/chats/${encodeURIComponent(id)}`)} />
    {list.error && <p role="alert" className="notice error">{list.error}</p>}
    {list.items.length === 0 && list.busy
      ? <ul className="item-list skeleton-list" aria-hidden="true">{[0, 1, 2, 3, 4, 5].map(index => <li key={index}><span className="list-item skeleton-row"><span className="avatar" /><span className="item-copy"><span className="skeleton-bar" /><span className="skeleton-bar short" /></span></span></li>)}</ul>
      : <ul ref={listRef} className="item-list" aria-label="對話清單">{shown.map(({ item, last, peer, title }) => {
          const target = `/chats/${encodeURIComponent(item.id)}`, selected = path === target, entry = peer ? directory.get(peer) : undefined;
          return <li key={item.id}><button type="button" data-conversation-id={item.id} className={`list-item${selected ? ' selected' : ''}`} aria-current={selected ? 'page' : undefined} onClick={() => onNavigate(target)}>
            <span className={`avatar-accent accent-${accentIndex(peer ?? item.id)}`} aria-hidden="true"><Avatar session={session} attachmentId={entry && !entry.avatarStale ? entry.avatarId : null} name={title} /></span>
            <span className="item-copy">
              <span className="item-line"><strong>{title}</strong>{last && <time className="item-time" dateTime={last.created_at}>{formatListTime(last.created_at, now)}</time>}</span>
              <span className="item-line"><span className="item-preview">{previewText(last, item.type, me, id => directory.get(id)?.displayName ?? id)}</span>{item.unread_count > 0 && <span className="unread" aria-label={`${item.unread_count} 則伺服器查詢未讀`}>{item.unread_count}</span>}</span>
            </span>
          </button></li>;
        })}</ul>}
    {list.busy && <p role="status" className="visually-hidden">載入對話…</p>}
    {!shown.length && !list.busy && <div className="empty-state"><strong>{term ? '沒有符合的已載入對話' : '還沒有對話'}</strong><p>選擇聯絡人開始聊天，或建立您的群組。</p><button type="button" onClick={() => onNavigate('/contacts')}>到聯絡人開始聊天</button></div>}
    <div className="actions">{list.cursor && <button type="button" disabled={list.busy} onClick={() => { void list.load(); }}>載入下一頁</button>}<button type="button" className="text-button" disabled={list.busy} onClick={() => { void list.load(true); }}>重新整理</button></div>
  </aside>;
}
