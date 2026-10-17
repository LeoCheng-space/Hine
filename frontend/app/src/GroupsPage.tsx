import { useEffect, useMemo, useRef, useState, type FormEvent, type RefObject } from 'react';
import { ApiError, describeError, isRecord, ownerPartition } from './api';
import { Avatar, usePagedList } from './ContactsPage';
import { GROUP_OTHER_MEMBER_LIMIT, addMember, groupPayload, removeMember } from './group-selection';
import { directoryFor } from './user-directory';
import type { SessionController } from './session';
import type { ChatController } from './chat';
import type { ContactView, ConversationCreateResult, ConversationDetail, ConversationMutationResult, MemberMutationResult, UserSummary } from './types';
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
const ADD_RESULT_MESSAGE = { self: '您會自動成為群組成員與管理員。', duplicate: '這位成員已在名單中。', full: `群組最多 50 人，包含您自己；已選 ${GROUP_OTHER_MEMBER_LIMIT} 位。` } as const;
/** Two-step native dialog: pick members (contacts or a verified public ID), then name the group. Keeps the original creation intent and idempotency key across failures and reloads. */
export function CreateGroup({ session, open, onClose, triggerRef, onCreated }: { session: SessionController; open: boolean; onClose: () => void; triggerRef: RefObject<HTMLElement | null>; onCreated: (id: string) => void }) {
  const context = session.getSnapshot().context, owner = ownerPartition(context.user_id, context.device_id), me = context.user_id ?? '';
  const store = useMemo(() => new GroupCreationIntentStore(owner), [owner]);
  const dialog = useRef<HTMLDialogElement>(null), active = useRef(false);
  const [step, setStep] = useState<'members' | 'title'>('members'), [title, setTitle] = useState(''), [selected, setSelected] = useState<string[]>([]), [lookupId, setLookupId] = useState('');
  const [busy, setBusy] = useState(false), [lookupBusy, setLookupBusy] = useState(false), [error, setError] = useState<string | null>(null), [pending, setPending] = useState<GroupCreateIntent | null>(null);
  const contacts = usePagedList<ContactView>(session, 'contacts', item => item.user.id);
  const directory = directoryFor(session);
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  useEffect(() => {
    if (!open) return;
    try {
      const unresolved = store.read();
      if (unresolved) { setPending(unresolved); setTitle(unresolved.payload.title); setSelected([...unresolved.payload.member_ids]); setStep('title'); }
    } catch (error) { session.failStorage(error); }
  }, [open, store, session]);
  useEffect(() => {
    if (!open) return;
    const element = dialog.current; if (!element) return;
    element.showModal(); (element.querySelector<HTMLElement>('.create-group-step input:not(:disabled), .create-group-step button:not(:disabled)') ?? element.querySelector<HTMLElement>('button:not(:disabled)'))?.focus(); window.dispatchEvent(new Event('hine-overlay-change'));
    return () => {
      element.close(); window.dispatchEvent(new Event('hine-overlay-change'));
      const trigger = triggerRef.current;
      if (trigger?.isConnected && trigger.getClientRects().length > 0) trigger.focus();
      else document.querySelector<HTMLElement>('[data-route-heading]')?.focus();
    };
  }, [open, triggerRef]);
  const nameOf = (id: string): string => contacts.items.find(item => item.user.id === id)?.user.display_name ?? directory.get(id)?.displayName ?? id;
  function toggle(id: string, checked: boolean) {
    setError(null);
    if (!checked) { setSelected(current => removeMember(current, id)); return; }
    const next = addMember(selected, id, me);
    if (next.result === 'added') setSelected(next.selected); else setError(ADD_RESULT_MESSAGE[next.result]);
  }
  async function addById() {
    const id = lookupId.trim(); if (!id || lookupBusy) return;
    const lookupDirectory = directoryFor(session); setLookupBusy(true); setError(null);
    try {
      const result = await session.request<UserSummary>(`/users/${encodeURIComponent(id)}`);
      const current = session.getSnapshot().context;
      if (!active.current || current.state !== 'authenticated' || ownerPartition(current.user_id, current.device_id) !== owner) return;
      const next = addMember(selected, result.data.id, me);
      if (next.result !== 'added') { setError(ADD_RESULT_MESSAGE[next.result]); return; }
      lookupDirectory.put(result.data.id, result.data); setSelected(next.selected); setLookupId('');
    } catch (error) { if (active.current) setError(describeError(error)); }
    finally { if (active.current) setLookupBusy(false); }
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy) return; setError(null);
    if (!title) { setError('請輸入群組名稱。'); event.currentTarget.querySelector<HTMLInputElement>('#group-title')?.focus(); return; }
    let intent: GroupCreateIntent;
    try { intent = store.begin(groupPayload(title, selected)); setPending(intent); } catch (error) { session.failStorage(error); return; }
    setBusy(true);
    try {
      const result = await session.request<ConversationCreateResult>('/conversations/groups', { method: 'POST', json: intent.payload, idempotencyKey: intent.key });
      try { store.confirm(intent.key); } catch (error) { session.failStorage(error); return; }
      const current = session.getSnapshot().context;
      if (!active.current || current.state !== 'authenticated' || ownerPartition(current.user_id, current.device_id) !== owner) return;
      setPending(null); setStep('members'); setTitle(''); setSelected([]); onCreated(result.data.id);
    } catch (error) { if (active.current) setError(describeError(error)); }
    finally { if (active.current) setBusy(false); }
  }
  function resolveIntent() {
    if (!pending || !window.confirm('確認您已核對原建立操作的結果，並要結束此意圖？這不會刪除任何已建立的群組。')) return;
    try { store.confirm(pending.key); setPending(null); setStep('members'); setTitle(''); setSelected([]); setError(null); } catch (error) { session.failStorage(error); }
  }
  if (!open) return null;
  const locked = busy || !!pending;
  return <dialog ref={dialog} className="create-group-dialog" aria-modal="true" aria-labelledby="create-group-title" onCancel={event => { event.preventDefault(); if (!busy) onClose(); }}>
    <header className="create-group-header"><h2 id="create-group-title">建立群組</h2><button type="button" className="text-button" onClick={onClose} disabled={busy}>關閉</button></header>
    {pending && <p className="notice" role="status">原建立意圖已保留。重試會核對相同群組，不會另建一個；請先確認結果再修改內容。</p>}
    {error && <p className="notice error" role="alert">{error}</p>}
    <ul className="selected-members" aria-label="已選成員">{selected.map(id => <li key={id}><span>{nameOf(id)}</span>{!locked && <button type="button" className="text-button" aria-label={`移除 ${nameOf(id)}`} onClick={() => setSelected(current => removeMember(current, id))}>×</button>}</li>)}</ul>
    <p className="small muted selected-count">已選 {selected.length}／{GROUP_OTHER_MEMBER_LIMIT}</p>
    {step === 'members'
      ? <div className="create-group-step">
          <form className="input-action" onSubmit={event => { event.preventDefault(); void addById(); }}>
            <label className="visually-hidden" htmlFor="group-member-id">以公開 ID 加入</label>
            <input id="group-member-id" placeholder="以公開 ID 加入" value={lookupId} onChange={event => setLookupId(event.target.value)} disabled={locked} />
            <button type="submit" disabled={locked || lookupBusy || !lookupId.trim()}>{lookupBusy ? '查詢中…' : '加入'}</button>
          </form>
          <ul className="contact-picker" aria-label="聯絡人">{contacts.items.map(item => { const checked = selected.includes(item.user.id); return <li key={item.user.id}><label className="contact-option">
            <input type="checkbox" checked={checked} disabled={locked || (!checked && selected.length >= GROUP_OTHER_MEMBER_LIMIT)} onChange={event => toggle(item.user.id, event.target.checked)} />
            <span aria-hidden="true"><Avatar session={session} attachmentId={item.user.avatar_attachment_id} name={item.user.display_name} /></span><span>{item.user.display_name}</span>
          </label></li>; })}</ul>
          {contacts.busy && <p role="status" className="small muted">載入聯絡人…</p>}
          {!contacts.busy && !contacts.items.length && <p className="small muted">還沒有聯絡人，可直接以公開 ID 加入。</p>}
          {contacts.cursor && <button type="button" className="text-button" disabled={contacts.busy} onClick={() => { void contacts.load(); }}>載入下一頁</button>}
          <div className="actions"><button type="button" className="primary" onClick={() => { setError(null); setStep('title'); }}>下一步</button></div>
        </div>
      : <form className="create-group-step" onSubmit={submit}>
          <label htmlFor="group-title">群組名稱</label><input id="group-title" value={title} onChange={event => setTitle(event.target.value)} disabled={locked} />
          <p className="small muted">您會自動加入並成為管理員。新成員只能查看加入之後的訊息。</p>
          <div className="actions">
            {!pending && <button type="button" disabled={busy} onClick={() => setStep('members')}>上一步</button>}
            <button className="primary" type="submit" disabled={busy}>{busy ? '核對建立結果…' : pending ? '以原意圖重試 / 核對' : '建立群組'}</button>
            {pending && <button type="button" disabled={busy} onClick={resolveIntent}>已核對結果，結束原意圖</button>}
          </div>
        </form>}
  </dialog>;
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
  const memberIntent = useRef<Record<string,string>>({}), alive = useRef(false);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const path = `/conversations/${encodeURIComponent(conversationId)}`;
  async function load() { setLoading(true); try { const result = await session.request<ConversationDetail>(path); if (result.data.type !== 'group') throw new Error('這不是群組對話。'); setDetail(result.data); setTitle(result.data.title ?? ''); setError(null); } catch (error) { setDetail(null); setError(describeError(error)); } finally { setLoading(false); } }
  useEffect(() => { void load(); }, [conversationId]);
  const me = session.getSnapshot().context.user_id, isAdmin = detail?.members.some(member => member.user_id === me && member.role === 'admin') === true;
  async function mutate(operation: 'title' | 'add' | 'role' | 'remove', userId?: string, role?: 'admin' | 'member') {
    setBusy(true); setError(null); setNotice(null); const directory = directoryFor(session), target = operation === 'add' ? newMember : userId;
    try {
      if (operation === 'title') await session.request<ConversationMutationResult>(path, { method: 'PATCH', json: { title } });
      if (operation === 'add') { const id = newMember; memberIntent.current[id] ??= crypto.randomUUID(); await session.request<MemberMutationResult>(`${path}/members`, { method: 'POST', json: { user_id: id }, idempotencyKey: memberIntent.current[id] }); delete memberIntent.current[id]; setNewMember(''); }
      if (operation === 'role' && userId) await session.request<MemberMutationResult>(`${path}/members/${encodeURIComponent(userId)}`, { method: 'PATCH', json: { role } });
      // Leaving still withdraws the conversation locally, but a page the user already left must not navigate them back.
      if (operation === 'remove' && userId) { await session.request<void>(`${path}/members/${encodeURIComponent(userId)}`, { method: 'DELETE' }); if (userId === me) { await chat.withdraw(conversationId); if (alive.current) onNavigate('/chats'); return; } }
      if ((operation === 'add' || operation === 'remove') && target) directory.markAvatarsStale([target, ...(detail?.members.map(member => member.user_id) ?? [])]);
      await load(); setNotice('群組資料已更新。');
    } catch (error) { setError(describeError(error)); } finally { setBusy(false); }
  }
  const chatDetail = chat.getSnapshot().details[conversationId];
  useEffect(() => { if (chat.getSnapshot().denied.includes(conversationId)) { setDetail(null); onNavigate('/chats'); } else if (detail && chatDetail && chatDetail.membership_version !== detail.membership_version) { void load(); } }, [chatDetail?.membership_version, chat.getSnapshot().denied, conversationId]);
  return <section className="page-content group-page"><button className="text-button" onClick={() => onNavigate(`/chats/${encodeURIComponent(conversationId)}`)}>← 返回對話</button><p className="eyebrow">GROUP SETTINGS</p><h1 tabIndex={-1} data-route-heading>群組管理</h1>{loading && <p role="status">正在確認群組權限…</p>}{error && <p className="notice error" role="alert">{error}</p>}{notice && <p className="notice success" role="status">{notice}</p>}{!detail && !loading && <button onClick={() => { void load(); }}>重新核對權限</button>}{detail && <><div className="card"><h2>{detail.title}</h2><p className="muted">{detail.members.length} / 50 位成員 · 版本 {detail.membership_version}</p><p className="small muted">管理權限由伺服器核對；不能移除、降級或退出最後一位管理員。</p>{isAdmin && <form onSubmit={event => { event.preventDefault(); if (!title) { setError('請輸入群組名稱。'); event.currentTarget.querySelector('input')?.focus(); return; } void mutate('title'); }}><label htmlFor="rename-group">群組名稱</label><div className="input-action"><input id="rename-group" value={title} onChange={event => setTitle(event.target.value)} disabled={busy} /><button disabled={busy}>儲存名稱</button></div></form>}</div><div className="card"><h2>成員</h2><ul className="member-list">{detail.members.map(member => <li key={member.user_id}><div><strong className="identifier">{member.user_id}</strong>{member.user_id === me && <span className="badge">您</span>}<p className="muted small">{member.role === 'admin' ? '管理員' : '成員'}</p></div>{isAdmin && <div className="actions"><button disabled={busy} onClick={() => { void mutate('role', member.user_id, member.role === 'admin' ? 'member' : 'admin'); }}>{member.role === 'admin' ? '改為成員' : '設為管理員'}</button>{member.user_id !== me && <button className="danger" disabled={busy} onClick={() => { void mutate('remove', member.user_id); }}>移除</button>}</div>}</li>)}</ul>{isAdmin && <form onSubmit={event => { event.preventDefault(); if (!newMember) { setError('請輸入成員的公開 ID。'); event.currentTarget.querySelector('input')?.focus(); return; } void mutate('add'); }}><label htmlFor="new-member">新增成員的公開 ID</label><div className="input-action"><input id="new-member" value={newMember} onChange={event => setNewMember(event.target.value)} disabled={busy} /><button disabled={busy}>加入成員</button></div></form>}</div><div className="card danger-zone"><h2>退出群組</h2><p>退出後不能繼續查看群組內容。重新加入只會取得新的加入界線之後的訊息。</p><button className="danger" disabled={busy} onClick={() => { if (me) void mutate('remove', me); }}>退出群組</button></div></>}</section>;
}
