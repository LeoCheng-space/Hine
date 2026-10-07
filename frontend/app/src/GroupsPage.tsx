import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { ApiError, describeError, isRecord, ownerPartition } from './api';
import type { SessionController } from './session';
import type { ChatController } from './chat';
import type { ConversationCreateResult, ConversationDetail, ConversationMutationResult, MemberMutationResult } from './types';
export interface GroupCreatePayload { title: string; member_ids: string[] }
export interface GroupCreateIntent { key: string; payload: GroupCreatePayload }
export class GroupCreationIntentStore {
  private readonly storageKey: string;
  constructor(owner: string, private readonly storage?: Storage) { this.storageKey = `hine-group-intent:${owner}`; }
  read(): GroupCreateIntent | null {
    const saved = (this.storage ?? localStorage).getItem(this.storageKey);
    if (!saved) return null;
    const value: unknown = JSON.parse(saved);
    if (!isRecord(value) || typeof value.key !== 'string' || !value.key || !isRecord(value.payload) || typeof value.payload.title !== 'string' || !Array.isArray(value.payload.member_ids) || !value.payload.member_ids.every((id: unknown) => typeof id === 'string')) throw new ApiError('STORAGE_UNAVAILABLE');
    return { key: value.key, payload: { title: value.payload.title, member_ids: value.payload.member_ids } };
  }
  begin(payload: GroupCreatePayload): GroupCreateIntent {
    const unresolved = this.read();
    if (unresolved) return unresolved;
    const intent = { key: crypto.randomUUID(), payload: { title: payload.title, member_ids: [...payload.member_ids] } };
    (this.storage ?? localStorage).setItem(this.storageKey, JSON.stringify(intent));
    return intent;
  }
  confirm(key: string): void { if (this.read()?.key === key) (this.storage ?? localStorage).removeItem(this.storageKey); }
}
export function CreateGroup({ session, onCreated }: { session: SessionController; onCreated: (id: string) => void }) {
  const context = session.getSnapshot().context, owner = ownerPartition(context.user_id, context.device_id);
  const store = useMemo(() => new GroupCreationIntentStore(owner), [owner]);
  const [open, setOpen] = useState(false), [title, setTitle] = useState(''), [members, setMembers] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState<string | null>(null), [pending, setPending] = useState<GroupCreateIntent | null>(null);
  const active = useRef(false);
  useEffect(() => {
    active.current = true;
    try { const unresolved = store.read(); if (unresolved) { setPending(unresolved); setTitle(unresolved.payload.title); setMembers(unresolved.payload.member_ids.join('\n')); setOpen(true); } }
    catch (error) { session.failStorage(error); }
    return () => { active.current = false; };
  }, [store, session]);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy) return; setError(null);
    if (!title) { setError('請輸入群組名稱。'); event.currentTarget.querySelector('input')?.focus(); return; }
    const member_ids = members.split('\n').filter(id => id !== '');
    if (new Set(member_ids).size > 49) { setError('群組最多 50 人，包含您自己。'); event.currentTarget.querySelector('textarea')?.focus(); return; }
    let intent: GroupCreateIntent;
    try { intent = store.begin({ title, member_ids }); setPending(intent); } catch (error) { session.failStorage(error); return; }
    setBusy(true);
    try {
      const result = await session.request<ConversationCreateResult>('/conversations/groups', { method: 'POST', json: intent.payload, idempotencyKey: intent.key });
      try { store.confirm(intent.key); } catch (error) { session.failStorage(error); return; }
      const current = session.getSnapshot().context;
      if (!active.current || current.state !== 'authenticated' || ownerPartition(current.user_id, current.device_id) !== owner) return;
      setPending(null); setOpen(false); setTitle(''); setMembers(''); onCreated(result.data.id);
    } catch (error) { if (active.current) setError(describeError(error)); }
    finally { if (active.current) setBusy(false); }
  }
  function resolveIntent() {
    if (!pending || !window.confirm('確認您已核對原建立操作的結果，並要結束此意圖？這不會刪除任何已建立的群組。')) return;
    try { store.confirm(pending.key); setPending(null); setTitle(''); setMembers(''); setError(null); } catch (error) { session.failStorage(error); }
  }
  return <div className="group-create">
    <button onClick={() => setOpen(value => !value)} aria-expanded={open}>{open ? '收起建立群組' : '＋ 建立群組'}</button>
    {open && <form className="compact-form" onSubmit={submit}>
      {pending && <p className="notice" role="status">原建立意圖已保留。重試會核對相同群組，不會另建一個；請先確認結果再修改內容。</p>}
      <label htmlFor="group-title">群組名稱</label><input id="group-title" value={title} onChange={event => setTitle(event.target.value)} disabled={busy || !!pending} />
      <label htmlFor="group-members">初始成員公開 ID（每行一位）</label><textarea id="group-members" value={members} onChange={event => setMembers(event.target.value)} disabled={busy || !!pending} />
      <p className="small muted">您會自動加入並成為管理員。新成員只能查看加入之後的訊息。</p>
      {error && <p className="notice error" role="alert">{error}</p>}
      <button className="primary" disabled={busy}>{busy ? '核對建立結果…' : pending ? '以原意圖重試 / 核對' : '建立群組並開啟'}</button>
      {pending && <button type="button" disabled={busy} onClick={resolveIntent}>已核對結果，結束原意圖</button>}
    </form>}
  </div>;
}
export function GroupInfoDialog({ detail, names, onClose, onManage, returnFocus }: { detail: ConversationDetail; names: Record<string, string>; onClose: () => void; onManage: () => void; returnFocus: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null), closeButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const element = dialog.current;
    if (!element) return;
    element.showModal(); closeButton.current?.focus(); window.dispatchEvent(new Event('hine-overlay-change'));
    return () => { element.close(); window.dispatchEvent(new Event('hine-overlay-change')); returnFocus(); };
  }, [returnFocus]);
  return <dialog ref={dialog} id="group-info-dialog" className="card group-info-dialog" aria-modal="true" aria-labelledby="group-info-title"
    onCancel={event => { event.preventDefault(); onClose(); }}
    onKeyDown={event => {
      if (event.key !== 'Tab' || !dialog.current) return;
      const controls = dialog.current.querySelectorAll<HTMLButtonElement>('button:not(:disabled)'), first = controls[0], last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }}>
    <header className="group-info-header"><h2 id="group-info-title">群組資訊</h2><button ref={closeButton} type="button" onClick={onClose} aria-label="關閉群組資訊">關閉</button></header>
    <h3>{detail.title}</h3><p className="muted">{detail.members.length} / 50 位成員 · 版本 {detail.membership_version}</p>
    <ul className="member-list">{detail.members.map(member => <li key={member.user_id}><div><strong>{names[member.user_id] ?? member.user_id}</strong><span className="badge">{member.role === 'admin' ? '管理員' : '成員'}</span><p className="identifier">{member.user_id}</p></div></li>)}</ul>
    <div className="actions"><button type="button" className="primary" onClick={onManage}>前往群組管理</button></div>
  </dialog>;
}
export function GroupsPage({ session, chat, conversationId, onNavigate }: { session: SessionController; chat: ChatController; conversationId: string; onNavigate: (path: string) => void }) {
  const [detail, setDetail] = useState<ConversationDetail | null>(null), [title, setTitle] = useState(''), [newMember, setNewMember] = useState(''), [busy, setBusy] = useState(false), [loading, setLoading] = useState(true), [error, setError] = useState<string | null>(null), [notice, setNotice] = useState<string | null>(null);
  const memberIntent = useRef<Record<string,string>>({});
  const path = `/conversations/${encodeURIComponent(conversationId)}`;
  async function load() { setLoading(true); try { const result = await session.request<ConversationDetail>(path); if (result.data.type !== 'group') throw new Error('這不是群組對話。'); setDetail(result.data); setTitle(result.data.title ?? ''); setError(null); } catch (error) { setDetail(null); setError(describeError(error)); } finally { setLoading(false); } }
  useEffect(() => { void load(); }, [conversationId]);
  const me = session.getSnapshot().context.user_id, isAdmin = detail?.members.some(member => member.user_id === me && member.role === 'admin') === true;
  async function mutate(operation: 'title' | 'add' | 'role' | 'remove', userId?: string, role?: 'admin' | 'member') {
    setBusy(true); setError(null); setNotice(null);
    try {
      if (operation === 'title') await session.request<ConversationMutationResult>(path, { method: 'PATCH', json: { title } });
      if (operation === 'add') { const id = newMember; memberIntent.current[id] ??= crypto.randomUUID(); await session.request<MemberMutationResult>(`${path}/members`, { method: 'POST', json: { user_id: id }, idempotencyKey: memberIntent.current[id] }); delete memberIntent.current[id]; setNewMember(''); }
      if (operation === 'role' && userId) await session.request<MemberMutationResult>(`${path}/members/${encodeURIComponent(userId)}`, { method: 'PATCH', json: { role } });
      if (operation === 'remove' && userId) { await session.request<void>(`${path}/members/${encodeURIComponent(userId)}`, { method: 'DELETE' }); if (userId === me) { await chat.withdraw(conversationId); onNavigate('/chats'); return; } }
      await load(); setNotice('群組資料已更新。');
    } catch (error) { setError(describeError(error)); } finally { setBusy(false); }
  }
  const chatDetail = chat.getSnapshot().details[conversationId];
  useEffect(() => { if (chat.getSnapshot().denied.includes(conversationId)) { setDetail(null); onNavigate('/chats'); } else if (detail && chatDetail && chatDetail.membership_version !== detail.membership_version) { void load(); } }, [chatDetail?.membership_version, chat.getSnapshot().denied, conversationId]);
  return <section className="page-content group-page"><button className="text-button" onClick={() => onNavigate(`/chats/${encodeURIComponent(conversationId)}`)}>← 返回對話</button><p className="eyebrow">GROUP SETTINGS</p><h1 tabIndex={-1}>群組管理</h1>{loading && <p role="status">正在確認群組權限…</p>}{error && <p className="notice error" role="alert">{error}</p>}{notice && <p className="notice success" role="status">{notice}</p>}{!detail && !loading && <button onClick={() => { void load(); }}>重新核對權限</button>}{detail && <><div className="card"><h2>{detail.title}</h2><p className="muted">{detail.members.length} / 50 位成員 · 版本 {detail.membership_version}</p><p className="small muted">管理權限由伺服器核對；不能移除、降級或退出最後一位管理員。</p>{isAdmin && <form onSubmit={event => { event.preventDefault(); if (!title) { setError('請輸入群組名稱。'); event.currentTarget.querySelector('input')?.focus(); return; } void mutate('title'); }}><label htmlFor="rename-group">群組名稱</label><div className="input-action"><input id="rename-group" value={title} onChange={event => setTitle(event.target.value)} disabled={busy} /><button disabled={busy}>儲存名稱</button></div></form>}</div><div className="card"><h2>成員</h2><ul className="member-list">{detail.members.map(member => <li key={member.user_id}><div><strong className="identifier">{member.user_id}</strong>{member.user_id === me && <span className="badge">您</span>}<p className="muted small">{member.role === 'admin' ? '管理員' : '成員'}</p></div>{isAdmin && <div className="actions"><button disabled={busy} onClick={() => { void mutate('role', member.user_id, member.role === 'admin' ? 'member' : 'admin'); }}>{member.role === 'admin' ? '改為成員' : '設為管理員'}</button>{member.user_id !== me && <button className="danger" disabled={busy} onClick={() => { void mutate('remove', member.user_id); }}>移除</button>}</div>}</li>)}</ul>{isAdmin && <form onSubmit={event => { event.preventDefault(); if (!newMember) { setError('請輸入成員的公開 ID。'); event.currentTarget.querySelector('input')?.focus(); return; } void mutate('add'); }}><label htmlFor="new-member">新增成員的公開 ID</label><div className="input-action"><input id="new-member" value={newMember} onChange={event => setNewMember(event.target.value)} disabled={busy} /><button disabled={busy}>加入成員</button></div></form>}</div><div className="card danger-zone"><h2>退出群組</h2><p>退出後不能繼續查看群組內容。重新加入只會取得新的加入界線之後的訊息。</p><button className="danger" disabled={busy} onClick={() => { if (me) void mutate('remove', me); }}>退出群組</button></div></>}</section>;
}
