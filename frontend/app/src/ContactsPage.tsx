import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { ApiError, describeError, ownerPartition } from './api';
import { downloadAttachment } from './attachment-transfer';
import type { SessionController } from './session';
import type { ChatController } from './chat';
import type { ContactView, ConversationCreateResult, Page, UserSummary, DownloadGrant } from './types';
interface PageCache<T> { items: T[]; cursor: string | null }
export function usePagedList<T>(session: SessionController, scope: 'contacts' | 'conversations', identify: (item: T) => string) {
  const context = session.getSnapshot().context;
  const key = `hine-list:${ownerPartition(context.user_id, context.device_id)}:${scope}`;
  const identifyRef = useRef(identify); identifyRef.current = identify;
  const [view, setView] = useState<PageCache<T> & { key: string; busy: boolean; error: string | null }>({ key, items: [], cursor: null, busy: true, error: null });
  const lifecycle = useMemo(() => {
    let page: PageCache<T> = { items: [], cursor: null }, active = false, epoch = 0, queuedReset = false;
    let running: Promise<void> | null = null, activeAbort: AbortController | null = null;
    const publish = (busy: boolean, error: string | null = null) => setView({ key, ...page, busy, error });
    const load = (reset = false): Promise<void> => {
      if (!active) return Promise.resolve();
      if (running) { if (reset) queuedReset = true; return running; }
      const source = session.getSnapshot().context, requestEpoch = epoch;
      if (source.state !== 'authenticated' || source.user_id !== context.user_id || source.device_id !== context.device_id) return Promise.resolve();
      const valid = () => {
        const current = session.getSnapshot().context;
        return active && requestEpoch === epoch && current.state === 'authenticated' && current.user_id === source.user_id && current.device_id === source.device_id && current.session_generation === source.session_generation && current.access_token === source.access_token;
      };
      let task!: Promise<void>;
      task = (async () => {
        let resetPage = reset;
        publish(true);
        try {
          do {
            queuedReset = false;
            const abort = new AbortController(); activeAbort = abort;
            try {
              const result = await session.request<Page<T>>(`/${scope}?limit=20${!resetPage && page.cursor ? `&cursor=${encodeURIComponent(page.cursor)}` : ''}`, { signal: abort.signal });
              if (!valid()) return;
              // A change arrived while A11 was in flight. Do not display/cache the
              // now-obsolete page; one trailing reset consumes the current server state.
              if (!queuedReset) {
                const incoming = result.data.items, next = result.meta?.next_cursor ?? null;
                let merged = incoming;
                if (!resetPage) {
                  const incomingIds = new Set(incoming.map(item => identifyRef.current(item)));
                  merged = [...page.items.filter(item => !incomingIds.has(identifyRef.current(item))), ...incoming];
                }
                const updated = { items: merged, cursor: next };
                try { localStorage.setItem(key, JSON.stringify(updated)); } catch (error) { session.failStorage(error); throw error; }
                page = updated; publish(true);
              }
            } catch (error) {
              if (!valid()) return;
              if (error instanceof ApiError && (error.code === 'CURSOR_INVALID' || error.code === 'CURSOR_EXPIRED') && !resetPage) queuedReset = true;
              if (!queuedReset) publish(true, describeError(error));
            } finally { if (activeAbort === abort) activeAbort = null; }
            resetPage = true;
          } while (queuedReset && valid());
        } finally {
          if (running === task) running = null;
          if (valid()) setView(current => ({ ...current, busy: false }));
        }
      })();
      running = task; return task;
    };
    return {
      load,
      activate() {
        active = true; ++epoch; page = { items: [], cursor: null }; publish(true);
        try {
          const cached = scope === 'contacts' ? localStorage.getItem(key) : null;
          if (cached) {
            const value: unknown = JSON.parse(cached);
            if (typeof value === 'object' && value !== null && 'items' in value && Array.isArray(value.items) && 'cursor' in value && (value.cursor === null || typeof value.cursor === 'string')) {
              page = value as PageCache<T>; publish(false); return;
            }
          }
        } catch (error) { session.failStorage(error); return; }
        // REST cursors are owner/device/query scoped, never the chat SyncCursor.
        if (scope === 'contacts') void load(true);
      },
      dispose() { active = false; ++epoch; queuedReset = false; activeAbort?.abort(); activeAbort = null; running = null; },
    };
  }, [session, key, scope, context.user_id, context.device_id]);
  useEffect(() => { lifecycle.activate(); return () => lifecycle.dispose(); }, [lifecycle]);
  const current = view.key === key ? view : { items: [], cursor: null, busy: true, error: null };
  return { items: current.items, cursor: current.cursor, busy: current.busy, error: current.error, load: lifecycle.load };
}
export async function fetchAvatarBytes(grant: DownloadGrant, fetcher: (url: string, init: globalThis.RequestInit) => Promise<Response> = fetch, signal?: AbortSignal): Promise<Blob> {
  if (!['image/jpeg', 'image/png'].includes(grant.content_type)) throw new Error('頭像類型不正確，請重新取得授權。');
  const response = await fetcher(grant.download_url, { credentials: 'omit', redirect: 'error', cache: 'no-store', referrerPolicy: 'no-referrer', signal });
  if (!response.ok) throw new Error('頭像固定版本無法載入，請重新取得授權。');
  const blob = await response.blob();
  if (blob.size !== grant.size_bytes) throw new Error('頭像位元組與已核驗版本不符。');
  return blob;
}
export function Avatar({ session, attachmentId, name }: { session: SessionController; attachmentId: string | null; name: string }) {
  const [url, setUrl] = useState<string | null>(null), [failed, setFailed] = useState(false);
  useEffect(() => {
    const before = session.getSnapshot().context, abort = new AbortController();
    let active = true, objectUrl: string | undefined; setUrl(null); setFailed(false);
    const bindingCurrent = () => {
      const now = session.getSnapshot().context;
      return before.state === 'authenticated' && now.state === 'authenticated' && before.user_id === now.user_id && before.device_id === now.device_id && before.session_generation === now.session_generation && before.access_token === now.access_token;
    };
    const timeout = window.setTimeout(() => abort.abort(), 30_000);
    if (attachmentId && before.state === 'authenticated') void (async () => {
      try {
        const grant = await downloadAttachment(session, attachmentId);
        if (!active || abort.signal.aborted || !bindingCurrent()) return;
        const blob = await fetchAvatarBytes(grant, fetch, abort.signal);
        if (!active || abort.signal.aborted || !bindingCurrent()) return;
        objectUrl = URL.createObjectURL(blob); setUrl(objectUrl);
      } catch { if (active && bindingCurrent()) setFailed(true); }
      finally { clearTimeout(timeout); }
    })();
    else clearTimeout(timeout);
    return () => { active = false; clearTimeout(timeout); abort.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [session, attachmentId]);
  return <span className="avatar" aria-label={failed ? '頭像載入失敗' : name}>{url ? <img src={url} alt={`${name}的頭像`} /> : <span aria-hidden="true">{Array.from(name)[0] ?? 'H'}</span>}</span>;
}
export class ContactLookupLifetime {
  private active = true;
  private version = 0;
  begin(): number { return ++this.version; }
  invalidate(): void { ++this.version; }
  activate(): void { this.active = true; ++this.version; }
  dispose(): void { this.active = false; ++this.version; }
  apply(version: number, action: () => void): boolean { if (!this.active || version !== this.version) return false; action(); return true; }
}
export function ContactsPage({ session, chat, onNavigate }: { session: SessionController; chat: ChatController; onNavigate: (path: string) => void }) {
  const list = usePagedList<ContactView>(session, 'contacts', item => item.user.id);
  const [filter, setFilter] = useState(''), [knownId, setKnownId] = useState(''), [selected, setSelected] = useState<UserSummary | null>(null), [busy, setBusy] = useState(false), [error, setError] = useState<string | null>(null), [notice, setNotice] = useState<string | null>(null);
  const partition = ownerPartition(session.getSnapshot().context.user_id, session.getSnapshot().context.device_id);
  const lifetime = useMemo(() => new ContactLookupLifetime(), []);
  function ownerActive(): boolean {
    const current = session.getSnapshot().context;
    return location.pathname === '/contacts' && current.state === 'authenticated' && ownerPartition(current.user_id, current.device_id) === partition;
  }
  function selectUser(user: UserSummary | null, requestVersion?: number) {
    if (!ownerActive()) return;
    if (requestVersion === undefined) lifetime.invalidate();
    const applySelection = () => {
      history.pushState({ hineContact: user?.id ?? null, owner: partition }, '', '/contacts');
      setSelected(user); setBusy(false); setError(null); setNotice(null);
      requestAnimationFrame(() => { if (ownerActive()) document.querySelector<HTMLElement>(user ? '.contact-detail h2' : '.panel-header h1')?.focus(); });
    };
    if (requestVersion === undefined) applySelection(); else lifetime.apply(requestVersion, applySelection);
  }
  useEffect(() => {
    lifetime.activate();
    const restore = () => {
      const value: unknown = history.state, version = lifetime.begin();
      if (!ownerActive()) return;
      setBusy(false);
      if (typeof value === 'object' && value !== null && 'owner' in value && value.owner === partition && 'hineContact' in value && typeof value.hineContact === 'string') {
        void session.request<UserSummary>(`/users/${encodeURIComponent(value.hineContact)}`).then(result => { if (ownerActive()) lifetime.apply(version, () => setSelected(result.data)); }).catch(error => { if (ownerActive()) lifetime.apply(version, () => { setSelected(null); setError(describeError(error)); }); });
      } else setSelected(null);
    };
    restore(); window.addEventListener('popstate', restore);
    return () => { lifetime.dispose(); window.removeEventListener('popstate', restore); };
  }, [partition, lifetime]);
  async function lookup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy) return;
    if (!knownId) { setError('請輸入對方分享的公開 ID。'); event.currentTarget.querySelector('input')?.focus(); return; }
    const version = lifetime.begin(); setBusy(true); setError(null);
    try { const result = await session.request<UserSummary>(`/users/${encodeURIComponent(knownId)}`); selectUser(result.data, version); }
    catch (error) { if (ownerActive()) lifetime.apply(version, () => { setSelected(null); setError(describeError(error)); }); }
    finally { if (ownerActive()) lifetime.apply(version, () => setBusy(false)); }
  }
  async function action(kind: 'add' | 'remove' | 'chat') {
    if (!selected || busy) return; const version = lifetime.begin(); setBusy(true); setError(null); setNotice(null);
    try {
      if (kind === 'chat') {
        const result = await session.request<ConversationCreateResult>('/conversations/direct', { method: 'POST', json: { peer_user_id: selected.id } });
        if (ownerActive()) lifetime.apply(version, () => onNavigate(`/chats/${encodeURIComponent(result.data.id)}`));
      } else {
        await session.request<void | ContactView>(kind === 'add' ? '/contacts' : `/contacts/${encodeURIComponent(selected.id)}`, { method: kind === 'add' ? 'POST' : 'DELETE', ...(kind === 'add' ? { json: { user_id: selected.id } } : {}) });
        await list.load(true); if (ownerActive()) lifetime.apply(version, () => setNotice(kind === 'add' ? '已加入聯絡人。' : '已移除聯絡人，聊天歷史不受影響。'));
      }
    } catch (error) { if (ownerActive()) lifetime.apply(version, () => setError(describeError(error))); }
    finally { if (ownerActive()) lifetime.apply(version, () => setBusy(false)); }
  }
  const loaded = list.items.filter(item => item.user.display_name.toLocaleLowerCase().includes(filter.toLocaleLowerCase()));
  return <section className={`split-page contacts-page ${selected ? 'detail-selected' : ''}`}>
    <div className="list-panel">
      <header className="panel-header"><p className="eyebrow">YOUR PEOPLE</p><h1 tabIndex={-1}>聯絡人</h1><p className="muted">分享公開 ID，開啟新的對話。</p></header>
      <form className="lookup-form" onSubmit={lookup}><label htmlFor="known-id">已知公開 ID</label><div className="input-action"><input id="known-id" value={knownId} onChange={event => setKnownId(event.target.value)} placeholder="貼上對方分享的 ID" /><button disabled={busy}>查詢</button></div></form>
      <label htmlFor="contact-filter">篩選已載入的聯絡人</label><input id="contact-filter" type="search" value={filter} onChange={event => setFilter(event.target.value)} /><p className="small muted">僅篩選已載入項目，不是全站找人。</p>
      {list.error && <p className="notice error" role="alert">{list.error}</p>}{error && !selected && <p className="notice error" role="alert">{error}</p>}
      <ul className="item-list">{loaded.map(item => <li key={item.user.id}><button className={`list-item ${selected?.id === item.user.id ? 'selected' : ''}`} onClick={() => selectUser(item.user)}><Avatar session={session} attachmentId={item.user.avatar_attachment_id} name={item.user.display_name} /><span className="item-copy"><strong>{item.user.display_name}</strong><span className="muted small">{chat.getSnapshot().presence[item.user.id] ?? item.presence ?? 'unknown'}</span></span><span aria-hidden="true">›</span></button></li>)}</ul>
      {!loaded.length && !list.busy && <div className="empty-state"><strong>{filter ? '沒有符合的已載入項目' : '還沒有聯絡人'}</strong><p>輸入對方的公開 ID，核對後加入。</p></div>}{list.busy && <p role="status">載入聯絡人…</p>}
      <div className="actions"><button disabled={list.busy} onClick={() => { void list.load(true); }}>重新整理</button>{list.cursor && <button disabled={list.busy} onClick={() => { void list.load(); }}>載入下一頁</button>}</div>
    </div>
    <div className="detail-panel">{selected ? <>
      <button className="narrow-back text-button" onClick={() => selectUser(null)}>← 返回聯絡人</button>
      <div className="contact-detail"><Avatar session={session} attachmentId={selected.avatar_attachment_id} name={selected.display_name} /><h2 tabIndex={-1}>{selected.display_name}</h2><p className="muted">公開 ID</p><p className="identifier">{selected.id}</p>
        <div className="actions"><button className="primary" disabled={busy} onClick={() => { void action('chat'); }}>開始聊天</button>{list.items.some(item => item.user.id === selected.id) ? <button className="danger" disabled={busy} onClick={() => { void action('remove'); }}>移除聯絡人</button> : <button disabled={busy} onClick={() => { void action('add'); }}>確認加入聯絡人</button>}</div>
        {error && <p className="notice error" role="alert">{error}</p>}{notice && <p className="notice success" role="status">{notice}</p>}
      </div>
    </> : <div className="empty-state"><span className="empty-symbol">◎</span><h2>選擇一位聯絡人</h2><p>檢視公開資料，或開始一對一聊天。</p></div>}</div>
  </section>;
}
