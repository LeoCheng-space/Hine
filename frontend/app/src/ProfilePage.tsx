import { useEffect, useMemo, useRef, useState, useSyncExternalStore, type FormEvent } from 'react';
import { describeError, ownerPartition } from './api';
import { AttachmentTransferError, uploadAttachment } from './attachment-transfer';
import { Avatar } from './ContactsPage';
import type { SessionController } from './session';
import type { AttachmentView, UserProfile } from './types';
export interface AvatarRecoverySnapshot { file: File | null; readyId: string | null; name: string | null; avatarId: string | null | undefined; pending: boolean; expired: boolean; error: string | null; notice: string | null }
export class AvatarSaveRecovery {
  private snapshot: AvatarRecoverySnapshot = { file: null, readyId: null, name: null, avatarId: undefined, pending: false, expired: false, error: null, notice: null };
  private listeners = new Set<() => void>();
  private generation = 0;
  private inflight: Promise<string> | null = null;
  retry: (() => Promise<AttachmentView>) | null = null;
  get readyId(): string | null { return this.snapshot.readyId; }
  getSnapshot = (): AvatarRecoverySnapshot => this.snapshot;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  update(update: Partial<AvatarRecoverySnapshot>): void { this.snapshot = { ...this.snapshot, ...update }; for (const listener of this.listeners) listener(); }
  select(file: File | null): void { ++this.generation; this.retry = null; this.inflight = null; this.update({ file, readyId: null, expired: false, error: null, notice: null }); }
  attachment(upload: (file: File) => Promise<AttachmentView>): Promise<string> {
    if (this.snapshot.readyId) return Promise.resolve(this.snapshot.readyId);
    if (this.snapshot.expired) return Promise.reject(new AttachmentTransferError('UPLOAD_EXPIRED', false));
    if (!this.snapshot.file) return Promise.reject(new AttachmentTransferError('INVALID_ATTACHMENT', false));
    if (this.inflight) return this.inflight;
    const generation = this.generation, file = this.snapshot.file, transfer = this.retry;
    this.inflight = (transfer ? transfer() : upload(file)).then(attachment => {
      if (generation !== this.generation) throw new Error('已選擇其他頭像，舊上傳不會指派至個人檔案。');
      if (attachment.state !== 'ready') throw new AttachmentTransferError('UPLOAD_NOT_READY', true);
      this.retry = null; this.update({ readyId: attachment.id });
      return attachment.id;
    }).catch(error => {
      if (generation === this.generation && error instanceof AttachmentTransferError) {
        if (error.retry) this.retry = error.retry;
        if (error.code === 'UPLOAD_EXPIRED') { this.retry = null; this.update({ expired: true }); }
      }
      throw error;
    }).finally(() => { if (generation === this.generation) this.inflight = null; });
    return this.inflight;
  }
  confirmed(profile: UserProfile): void {
    this.select(null);
    this.update({ name: profile.display_name, avatarId: profile.avatar_attachment_id, pending: false, error: null, notice: '個人檔案已儲存。' });
  }
}
const avatarRecoveries = new Map<string, AvatarSaveRecovery>();
export function avatarRecoveryFor(owner: string): AvatarSaveRecovery {
  const existing = avatarRecoveries.get(owner);
  if (existing) return existing;
  const recovery = new AvatarSaveRecovery(); avatarRecoveries.set(owner, recovery); return recovery;
}
export function ProfilePage({ session }: { session: SessionController }) {
  const context = session.getSnapshot().context, owner = ownerPartition(context.user_id, context.device_id);
  const recovery = useMemo(() => avatarRecoveryFor(owner), [owner]);
  const draft = useSyncExternalStore(recovery.subscribe, recovery.getSnapshot);
  const [profile, setProfile] = useState<UserProfile | null>(null), [preview, setPreview] = useState<string | null>(null), [loading, setLoading] = useState(true), [loadError, setLoadError] = useState<string | null>(null);
  const active = useRef(false);
  function ownerActive(): boolean { const current = session.getSnapshot().context; return current.state === 'authenticated' && ownerPartition(current.user_id, current.device_id) === owner; }
  async function load() {
    setLoading(true); setLoadError(null);
    try {
      const result = await session.request<UserProfile>('/users/me');
      if (!active.current || !ownerActive()) return;
      setProfile(result.data);
      const saved = recovery.getSnapshot();
      recovery.update({ ...(saved.name === null ? { name: result.data.display_name } : {}), ...(saved.avatarId === undefined ? { avatarId: result.data.avatar_attachment_id } : {}) });
    } catch (error) { if (active.current && ownerActive()) setLoadError(describeError(error)); }
    finally { if (active.current) setLoading(false); }
  }
  useEffect(() => { active.current = true; void load(); return () => { active.current = false; }; }, [session, recovery]);
  useEffect(() => { if (!draft.file) { setPreview(null); return; } const url = URL.createObjectURL(draft.file); setPreview(url); return () => URL.revokeObjectURL(url); }, [draft.file]);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (draft.pending || !ownerActive()) return;
    recovery.update({ error: null, notice: null });
    const name = draft.name ?? '', file = draft.file;
    if (!name) { recovery.update({ error: '請輸入顯示名稱。' }); event.currentTarget.querySelector('input')?.focus(); return; }
    if (file && (!['image/jpeg', 'image/png'].includes(file.type) || file.size <= 0 || file.size > 10_485_760)) { recovery.update({ error: '頭像必須為 JPEG 或 PNG，檔案大於 0 且不超過 10 MiB。' }); event.currentTarget.querySelector<HTMLInputElement>('input[type=file]')?.focus(); return; }
    recovery.update({ pending: true });
    try {
      const attachmentId = file ? await recovery.attachment(uploadFile => uploadAttachment(session, uploadFile, 'avatar', null)) : draft.avatarId ?? null;
      if (!ownerActive()) throw new Error('工作階段正在變更；原頭像嘗試已保留，登入後請核對。');
      const result = await session.request<UserProfile>('/users/me', { method: 'PATCH', json: { display_name: name, avatar_attachment_id: attachmentId } });
      if (!ownerActive() || result.data.id !== session.getSnapshot().context.user_id) throw new Error('工作階段已變更，尚未確認這次個人檔案操作。');
      recovery.confirmed(result.data); if (active.current) setProfile(result.data);
    } catch (error) { recovery.update({ error: describeError(error) }); }
    finally { recovery.update({ pending: false }); }
  }
  const name = draft.name ?? '', avatar = draft.avatarId ?? null;
  return <section className="page-content profile-page">
    <p className="eyebrow">YOUR ACCOUNT</p><h1 tabIndex={-1}>個人檔案</h1><p className="muted">您的公開身分，以及只對您顯示的帳號資料。</p>
    {loading && <p role="status">載入個人檔案…</p>}{(loadError || draft.error) && <p className="notice error" role="alert">{loadError ?? draft.error}</p>}
    {!profile && !loading && <button onClick={() => { void load(); }}>重新載入</button>}
    {profile && <form className="card profile-form" onSubmit={save}>
      <label htmlFor="profile-name">顯示名稱</label><input id="profile-name" value={name} onChange={event => recovery.update({ name: event.target.value })} disabled={draft.pending} aria-invalid={!name} />
      <label htmlFor="profile-email">電子郵件（僅本人可見）</label><input id="profile-email" type="email" value={profile.email} readOnly />
      <label htmlFor="profile-id">公開 ID（分享給對方以加入聯絡人）</label><input id="profile-id" value={profile.id} readOnly />
      <div className="avatar-editor">
        {preview ? <img className="avatar-preview" src={preview} alt="待儲存頭像預覽" /> : <Avatar session={session} attachmentId={avatar} name={name} />}
        <div><label htmlFor="profile-avatar">更換頭像</label><input id="profile-avatar" type="file" accept="image/jpeg,image/png" disabled={draft.pending} onChange={event => recovery.select(event.target.files?.[0] ?? null)} />
          {draft.file && <p className="small">{draft.file.name}</p>}
          <p className="small muted">JPEG / PNG，最大 10 MiB。核驗完成後才會指派頭像。</p>
          <button type="button" disabled={draft.pending} onClick={() => { recovery.select(null); recovery.update({ avatarId: null }); }}>移除頭像</button>
        </div>
      </div>
      {draft.readyId && <p className="notice" role="status">頭像已核驗就緒。再次儲存只核對 A06 指派，不會重新上傳。</p>}
      {recovery.retry && !draft.readyId && <p className="notice" role="status">原上傳嘗試已保留。再次儲存會核对相同嘗試。</p>}
      {draft.expired && <p className="notice error" role="alert">原授權已過期。請重新選取檔案，明確建立新的上傳嘗試。</p>}
      {draft.notice && <p className="notice success" role="status">{draft.notice}</p>}
      <div className="actions"><button className="primary" disabled={draft.pending || draft.expired} type="submit">{draft.pending ? '核對上傳與儲存中…' : '儲存 / 核對原變更'}</button>
        <button disabled={draft.pending} type="button" onClick={() => { recovery.select(null); recovery.update({ name: profile.display_name, avatarId: profile.avatar_attachment_id, error: null, notice: null }); }}>取消變更</button>
      </div>
    </form>}
  </section>;
}
