import { ApiError, describeError, isRecord, validateConfig, wireRequest, type RequestInit } from './api';
import type { AccessSession, ApiResult, RuntimeConfig, SessionContext, UserProfile } from './types';
export interface SessionSnapshot { context: SessionContext; phase: 'initializing' | 'ready' | 'blocked' | 'unsupported'; error: string | null }
const loggedOut: SessionContext = Object.freeze({ state: 'logged_out', user_id: null, device_id: null, session_generation: null, access_token: null, expires_at: null });
export function decodeAccessSession(value: unknown, previous?: SessionContext): AccessSession {
  if (!isRecord(value) || typeof value.access_token !== 'string' || !value.access_token || typeof value.user_id !== 'string' || !value.user_id || typeof value.device_id !== 'string' || !value.device_id || typeof value.expires_at !== 'string' || !Number.isFinite(Date.parse(value.expires_at)) || Date.parse(value.expires_at) <= Date.now() || typeof value.session_generation !== 'number' || !Number.isSafeInteger(value.session_generation) || value.session_generation < 1) throw new ApiError('OUTCOME_UNCONFIRMED');
  if (previous && previous.state !== 'logged_out' && (value.user_id !== previous.user_id || value.device_id !== previous.device_id || value.session_generation <= previous.session_generation)) throw new ApiError('OUTCOME_UNCONFIRMED');
  return { access_token: value.access_token, user_id: value.user_id, device_id: value.device_id, expires_at: value.expires_at, session_generation: value.session_generation };
}
export class AuthOperations {
  private tail: Promise<unknown> = Promise.resolve();
  run<T>(operation: () => Promise<T>): Promise<T> {
    const result = this.tail.then(operation);
    this.tail = result.catch(() => undefined);
    return result;
  }
}
interface DeviceBindings { owners: Record<string, { device_id: string; canonical_email: string }>; aliases: Record<string, string> }
export class DeviceStore {
  constructor(private readonly storage?: Storage) {}
  private read(): DeviceBindings {
    const saved = (this.storage ?? localStorage).getItem('hine-device-store');
    if (!saved) return { owners: {}, aliases: {} };
    const value: unknown = JSON.parse(saved);
    if (!isRecord(value) || !isRecord(value.owners) || !isRecord(value.aliases)) throw new ApiError('STORAGE_UNAVAILABLE');
    const owners: DeviceBindings['owners'] = {}, aliases: DeviceBindings['aliases'] = {};
    for (const [id, binding] of Object.entries(value.owners)) {
      if (!isRecord(binding) || typeof binding.device_id !== 'string' || typeof binding.canonical_email !== 'string') throw new ApiError('STORAGE_UNAVAILABLE');
      Object.defineProperty(owners, id, { value: { device_id: binding.device_id, canonical_email: binding.canonical_email }, enumerable: true, configurable: true });
    }
    for (const [alias, id] of Object.entries(value.aliases)) {
      if (typeof id !== 'string' || !Object.hasOwn(owners, id)) throw new ApiError('STORAGE_UNAVAILABLE');
      Object.defineProperty(aliases, alias, { value: id, enumerable: true, configurable: true });
    }
    return { owners, aliases };
  }
  lookup(submittedEmail: string): string | null {
    try {
      const bindings = this.read(), alias = submittedEmail.toLowerCase();
      const owner = Object.hasOwn(bindings.aliases, alias) ? bindings.aliases[alias] : undefined;
      return owner && Object.hasOwn(bindings.owners, owner) ? bindings.owners[owner].device_id : null;
    } catch { throw new ApiError('STORAGE_UNAVAILABLE'); }
  }
  save(profile: UserProfile, deviceId: string, submittedEmail?: string): void {
    const bindings = this.read(), storage = this.storage ?? localStorage;
    Object.defineProperty(bindings.owners, profile.id, { value: { device_id: deviceId, canonical_email: profile.email }, enumerable: true, configurable: true });
    for (const alias of [profile.email.toLowerCase(), ...(submittedEmail ? [submittedEmail.toLowerCase()] : [])]) Object.defineProperty(bindings.aliases, alias, { value: profile.id, enumerable: true, configurable: true });
    storage.setItem('hine-device-store', JSON.stringify(bindings));
    // Clean cutover from this app's obsolete email-only storage; it is never read as a shim.
    const obsolete: string[] = [];
    for (let index = 0; index < storage.length; index++) { const key = storage.key(index); if (key?.startsWith('hine-device:')) obsolete.push(key); }
    for (const key of obsolete) storage.removeItem(key);
  }
}
export class SessionController {
  readonly config: RuntimeConfig;
  private snapshot: SessionSnapshot = { context: loggedOut, phase: 'initializing', error: null };
  private listeners = new Set<() => void>();
  private startPromise?: Promise<void>;
  private refreshPromise?: Promise<void>;
  private releaseLock?: () => void;
  private locked = false;
  private disposed = false;
  private timer?: number;
  private epoch = 0;
  private readonly authOperations = new AuthOperations();
  private deviceStore?: DeviceStore;
  private activeAbort?: AbortController;
  constructor() {
    try { this.config = validateConfig(window.HINE_CONFIG, location.origin); }
    catch (error) { this.config = { API_BASE_URL: '', WS_URL: '', SYNC_RECONCILE_SECONDS: 10 }; this.snapshot = { context: loggedOut, phase: 'unsupported', error: describeError(error) }; }
  }
  subscribe = (listener: () => void): (() => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  getSnapshot = (): SessionSnapshot => this.snapshot;
  private publish(context: SessionContext, phase = this.snapshot.phase, error: string | null = null): void { this.snapshot = { context, phase, error }; for (const listener of this.listeners) listener(); }
  start(): Promise<void> { return this.startPromise ??= this.initialize(); }
  private async initialize(): Promise<void> {
    if (this.snapshot.phase === 'unsupported' || this.disposed) return;
    try {
      if (!window.isSecureContext || location.protocol !== 'https:' || !navigator.cookieEnabled || !navigator.locks || !window.indexedDB || !window.WebSocket || !('visibilityState' in document)) throw new Error('此瀏覽器缺少安全聊天所需能力。請啟用 Cookie、本機儲存及使用新版 Chrome / Edge。');
      const probe = `hine-capability-${crypto.randomUUID()}`;
      localStorage.setItem(probe, '1'); if (localStorage.getItem(probe) !== '1') throw new Error('本機儲存不可用。'); localStorage.removeItem(probe);
      document.cookie = `${probe}=1; Path=/; Secure; SameSite=Strict`;
      const cookieWorks = document.cookie.split('; ').includes(`${probe}=1`);
      document.cookie = `${probe}=; Path=/; Secure; SameSite=Strict; Max-Age=0`;
      if (!cookieWorks) throw new Error('Cookie 已被停用。');
      await new Promise<void>((resolve, reject) => {
        const request = indexedDB.open('hine-capabilities', 1);
        request.onupgradeneeded = () => { request.result.createObjectStore('probe'); };
        request.onerror = () => reject(new Error('IndexedDB 不可用。'));
        request.onblocked = () => reject(new Error('IndexedDB 被阻擋。'));
        request.onsuccess = () => {
          const db = request.result, tx = db.transaction('probe', 'readwrite');
          tx.objectStore('probe').put(1, probe); tx.objectStore('probe').delete(probe);
          tx.oncomplete = () => { db.close(); resolve(); };
          tx.onerror = tx.onabort = () => { db.close(); reject(new Error('IndexedDB 無法保存資料。')); };
        };
      });
      await new Promise<void>((resolve, reject) => {
        void navigator.locks.request('hine-session', { mode: 'exclusive', ifAvailable: true }, async lock => {
          if (!lock || this.disposed) { this.publish(loggedOut, 'blocked', '聊天已在另一個分頁開啟'); resolve(); return; }
          this.locked = true;
          const held = new Promise<void>(release => { this.releaseLock = release; });
          resolve(); await held; this.locked = false;
        }).catch(reject);
      });
      if (!this.locked || this.disposed) return;
      this.publish(loggedOut, 'initializing');
      try { await this.refresh(); } catch { /* refresh publishes the only recovery state */ }
      if (!this.disposed && this.snapshot.phase === 'initializing') this.publish(this.snapshot.context, 'ready', this.snapshot.error);
    } catch (error) { this.clear(); this.publish(loggedOut, 'unsupported', describeError(error)); }
  }
  private requireLock(): void { if (!this.locked || this.disposed || this.snapshot.phase === 'unsupported') throw new Error('此分頁尚未取得安全聊天工作階段。'); }
  private clear(): void { ++this.epoch; clearTimeout(this.timer); this.timer = undefined; this.activeAbort?.abort(); this.activeAbort = undefined; this.publish(loggedOut); }
  private async install(value: unknown, submittedEmail?: string, previous?: SessionContext): Promise<void> {
    const access = decodeAccessSession(value, previous), epoch = this.epoch;
    const { data: profile } = await wireRequest<UserProfile>(this.config, '/users/me', {}, access.access_token, this.activeAbort?.signal);
    if (this.disposed || epoch !== this.epoch || profile.id !== access.user_id || typeof profile.email !== 'string') throw new ApiError('OUTCOME_UNCONFIRMED');
    try { (this.deviceStore ??= new DeviceStore()).save(profile, access.device_id, submittedEmail); }
    catch { throw new ApiError('STORAGE_UNAVAILABLE'); }
    this.publish({ state: 'authenticated', ...access }, 'ready');
    clearTimeout(this.timer);
    this.timer = window.setTimeout(() => { void this.refresh().catch(() => {}); }, Math.max(0, Date.parse(access.expires_at) - Date.now() - 30_000));
  }
  login(email: string, password: string): Promise<void> {
    this.requireLock();
    return this.authOperations.run(async () => {
      this.requireLock(); this.clear(); const epoch = this.epoch;
      try {
        const device_id = (this.deviceStore ??= new DeviceStore()).lookup(email);
        this.activeAbort = new AbortController();
        const { data } = await wireRequest<unknown>(this.config, '/auth/login', { method: 'POST', json: { email, password, device_id } }, undefined, this.activeAbort.signal);
        if (this.disposed || epoch !== this.epoch) return;
        await this.install(data, email);
      } catch (error) {
        if (!this.disposed && epoch === this.epoch) {
          if (error instanceof ApiError && error.code === 'STORAGE_UNAVAILABLE') this.failStorage(error);
          else { this.clear(); this.publish(loggedOut, 'ready', error instanceof ApiError && error.code === 'UNAUTHENTICATED' ? '電子郵件或密碼不正確。' : describeError(error)); }
        }
        throw error;
      } finally { this.activeAbort = undefined; }
    });
  }
  register(email: string, password: string, display_name: string): Promise<UserProfile> {
    this.requireLock();
    return this.authOperations.run(async () => { this.requireLock(); return (await wireRequest<UserProfile>(this.config, '/auth/register', { method: 'POST', json: { email, password, display_name } })).data; });
  }
  refresh(): Promise<void> {
    this.requireLock();
    if (this.refreshPromise) return this.refreshPromise;
    this.refreshPromise = this.authOperations.run(async () => {
      this.requireLock(); const previous = this.snapshot.context;
      clearTimeout(this.timer);
      if (previous.state !== 'logged_out') this.publish({ state: 'refreshing', user_id: previous.user_id, device_id: previous.device_id, session_generation: previous.session_generation, access_token: null, expires_at: null });
      const epoch = ++this.epoch, abort = new AbortController(); this.activeAbort = abort;
      let timeout: number | undefined;
      try {
        const operation = (async () => {
          let data: unknown;
          try { data = (await wireRequest<unknown>(this.config, '/auth/refresh', { method: 'POST' }, undefined, abort.signal)).data; }
          catch (error) {
            if (!(error instanceof ApiError) || error.code !== 'RATE_LIMITED' || error.retryAfterMs === undefined || error.retryAfterMs >= 10_000) throw error;
            await new Promise<void>((resolve, reject) => { const wait = window.setTimeout(resolve, error.retryAfterMs); abort.signal.addEventListener('abort', () => { clearTimeout(wait); reject(new ApiError('OUTCOME_UNCONFIRMED')); }, { once: true }); });
            if (abort.signal.aborted) throw new ApiError('OUTCOME_UNCONFIRMED');
            data = (await wireRequest<unknown>(this.config, '/auth/refresh', { method: 'POST' }, undefined, abort.signal)).data;
          }
          if (this.disposed || epoch !== this.epoch || abort.signal.aborted) throw new ApiError('OUTCOME_UNCONFIRMED');
          await this.install(data, undefined, previous);
        })();
        await Promise.race([operation, new Promise<never>((_, reject) => { timeout = window.setTimeout(() => { abort.abort(); reject(new ApiError('OUTCOME_UNCONFIRMED')); }, 10_000); })]);
      } catch (error) {
        if (!this.disposed && epoch === this.epoch) {
          if (error instanceof ApiError && error.code === 'STORAGE_UNAVAILABLE') this.failStorage(error);
          else { this.clear(); this.publish(loggedOut, 'ready', describeError(error)); }
        }
        throw error;
      }
      finally { clearTimeout(timeout); if (this.activeAbort === abort) this.activeAbort = undefined; }
    }).finally(() => { this.refreshPromise = undefined; });
    return this.refreshPromise;
  }
  logout(): Promise<void> {
    this.requireLock();
    return this.authOperations.run(async () => {
      this.requireLock(); this.clear(); const epoch = this.epoch;
      try { await wireRequest<void>(this.config, '/auth/logout', { method: 'POST' }); if (!this.disposed && epoch === this.epoch) this.publish(loggedOut, 'ready'); }
      catch (error) { if (!this.disposed && epoch === this.epoch) this.publish(loggedOut, 'ready', '本機已停止登入，但伺服器登出結果未確認。' + describeError(error)); throw error; }
    });
  }
  async request<T>(path: string, init: RequestInit = {}): Promise<ApiResult<T>> {
    this.requireLock(); let context = this.snapshot.context;
    if (context.state !== 'authenticated') throw new ApiError('UNAUTHENTICATED');
    if (Date.parse(context.expires_at) <= Date.now()) {
      await this.refresh(); context = this.snapshot.context;
      if (context.state !== 'authenticated') throw new ApiError('UNAUTHENTICATED');
    }
    const epoch = this.epoch;
    try { const result = await wireRequest<T>(this.config, path, init, context.access_token, init.signal); if (epoch !== this.epoch || this.disposed) throw new ApiError('UNAUTHENTICATED'); return result; }
    catch (error) { if (error instanceof ApiError && error.code === 'UNAUTHENTICATED' && error.authLayer !== 'service' && epoch === this.epoch) { this.clear(); this.publish(loggedOut, 'ready', error.message); } throw error; }
  }
  invalidateAuthentication(): void { this.clear(); this.publish(loggedOut, 'ready', '工作階段已失效，請重新登入。'); }
  failStorage(error: unknown): void { this.clear(); this.publish(loggedOut, 'unsupported', '本機儲存不可用，已停止聊天。' + describeError(error)); }
  dispose(): void { if (this.disposed) return; this.disposed = true; this.clear(); this.releaseLock?.(); this.releaseLock = undefined; this.listeners.clear(); }
}
