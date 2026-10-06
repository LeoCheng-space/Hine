import type { ApiResult, RuntimeConfig } from './types';
export function retryDelay(value: unknown): number | undefined { return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 ? value : undefined; }
export function ownerPartition(userId: string | null, deviceId: string | null): string { return JSON.stringify([userId, deviceId]); }
export function validateConfig(value: unknown, origin: string): RuntimeConfig {
  if (!isRecord(value) || typeof value.API_BASE_URL !== 'string' || typeof value.WS_URL !== 'string' || value.SYNC_RECONCILE_SECONDS !== 10) throw new Error('缺少有效的網站設定。');
  const base = new URL(value.API_BASE_URL), ws = new URL(value.WS_URL), site = new URL(origin);
  if (site.protocol !== 'https:' || base.protocol !== 'https:' || base.origin !== site.origin || base.pathname.replace(/\/$/, '') !== '/api/v1' || base.search || base.hash || base.username || base.password || ws.protocol !== 'wss:' || ws.host !== site.host || ws.username || ws.password || ws.search || ws.hash) throw new Error('網站必須使用 HTTPS 與同來源 API / WSS。');
  return Object.freeze({ API_BASE_URL: base.href.replace(/\/$/, ''), WS_URL: ws.href, SYNC_RECONCILE_SECONDS: 10 });
}
export function isRecord(value: unknown): value is Record<string, unknown> { return typeof value === 'object' && value !== null && !Array.isArray(value); }
export class ApiError extends Error {
  constructor(public readonly code: string, public readonly retryable: boolean = false, public readonly retryAfterMs?: number, public readonly authLayer?: string) { super(errorMessage(code)); this.name = 'ApiError'; }
}
export function errorMessage(code: string): string {
  const messages: Record<string,string> = { UNAUTHENTICATED: '登入已失效，請重新登入。', INVALID_ARGUMENT: '資料格式不正確，請檢查欄位。', FORBIDDEN: '目前沒有此操作的權限。', NOT_FOUND: '找不到資料，或您已無法存取。', CONFLICT: '資料衝突；群組不能移除或降級最後一位管理員，且最多 50 人。', IDEMPOTENCY_CONFLICT: '這次操作的內容已改變，請確認原操作結果。', RATE_LIMITED: '操作太頻繁，請等待後再試。', DEPENDENCY_UNAVAILABLE: '服務暫時無法使用，請稍後再試。', OUTCOME_UNCONFIRMED: '無法確認操作結果，請先核對資料；不要重複建立。', UPLOAD_NOT_READY: '附件尚未核驗完成，請核對同一次上傳。', CURSOR_INVALID: '清單游標已失效，請重新載入首頁。', CURSOR_EXPIRED: '清單已過期，請重新載入首頁。', STORAGE_UNAVAILABLE: '本機儲存不可用，已停止操作以保護帳號資料。' };
  return messages[code] ?? '操作未完成，請重試或檢查輸入。';
}
export function describeError(error: unknown): string { return error instanceof Error ? error.message : '操作未完成，請稍後再試。'; }
export interface RequestInit { method?: string; json?: unknown; idempotencyKey?: string; signal?: AbortSignal }
export async function wireRequest<T>(config: RuntimeConfig, path: string, init: RequestInit = {}, token?: string, signal?: AbortSignal): Promise<ApiResult<T>> {
  if (!path.startsWith('/') || path.startsWith('//') || path.includes('#')) throw new ApiError('INVALID_ARGUMENT');
  const headers: Record<string,string> = { Accept: 'application/json' };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (init.json !== undefined) headers['Content-Type'] = 'application/json';
  if (init.idempotencyKey) headers['Idempotency-Key'] = init.idempotencyKey;
  let response: Response;
  try { response = await fetch(config.API_BASE_URL + path, { method: init.method ?? 'GET', headers, credentials: 'same-origin', cache: 'no-store', redirect: 'error', body: init.json === undefined ? undefined : JSON.stringify(init.json), signal: signal ?? init.signal }); }
  catch { throw new ApiError((init.method ?? 'GET') === 'GET' ? 'DEPENDENCY_UNAVAILABLE' : 'OUTCOME_UNCONFIRMED', true); }
  if (response.status === 204) return { data: undefined as T };
  let result: unknown;
  try { result = await response.json(); } catch { throw new ApiError(response.ok ? 'OUTCOME_UNCONFIRMED' : 'DEPENDENCY_UNAVAILABLE'); }
  if (!response.ok) {
    if (!isRecord(result) || !isRecord(result.error) || typeof result.error.code !== 'string') throw new ApiError('DEPENDENCY_UNAVAILABLE');
    const code = result.error.code;
    const error = result.error, details = isRecord(error.details) ? error.details : {};
    throw new ApiError(code, error.retryable === true, retryDelay(details.retry_after_ms), typeof details.auth_layer === 'string' ? details.auth_layer : undefined);
  }
  if (!isRecord(result) || !('data' in result)) throw new ApiError('OUTCOME_UNCONFIRMED');
  const meta = isRecord(result.meta) && (result.meta.next_cursor === null || typeof result.meta.next_cursor === 'string') ? { next_cursor: result.meta.next_cursor } : undefined;
  // The generic is the caller's public wire contract; security-sensitive auth is decoded separately.
  return { data: result.data as T, ...(meta ? { meta } : {}) };
}
