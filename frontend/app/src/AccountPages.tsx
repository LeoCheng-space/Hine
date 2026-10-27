import { useEffect, useRef, useState, type FormEvent } from 'react';
import { describeError, ApiError } from './api';
import { passwordProblems } from './password';
import type { SessionController } from './session';
export function AccountPage({ session, mode, onNavigate, onAuthenticated }: { session: SessionController; mode: 'login' | 'register'; onNavigate: (path: string) => void; onAuthenticated: () => Promise<void> }) {
  const [email, setEmail] = useState(''), [password, setPassword] = useState(''), [name, setName] = useState('');
  const [busy, setBusy] = useState(false), [error, setError] = useState<string | null>(null), [success, setSuccess] = useState<string | null>(null);
  const [fields, setFields] = useState<Record<string,string>>({});
  const [retryAt, setRetryAt] = useState(0);
  // Inputs are disabled while a request is in flight, which drops focus to <body>. When the request ends without
  // leaving the page, put focus where the user continues: the password (selected) after wrong credentials, the
  // email after other failures, and「前往登入」after a successful registration.
  const emailInput = useRef<HTMLInputElement>(null), passwordInput = useRef<HTMLInputElement>(null), loginLink = useRef<HTMLButtonElement>(null);
  const refocus = useRef<'email' | 'password' | 'login' | null>(null), [rejected, setRejected] = useState(false);
  useEffect(() => {
    if (busy || !refocus.current) return;
    const target = refocus.current; refocus.current = null;
    if (target === 'login') { loginLink.current?.focus(); return; }
    const input = target === 'password' ? passwordInput.current : emailInput.current; input?.focus(); input?.select();
  }, [busy]);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy) return;
    const errors: Record<string,string> = {};
    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) errors.email = '請輸入完整電子郵件地址。';
    if (!password) errors.password = '請輸入密碼。';
    else if (mode === 'register') { const problems = passwordProblems(password, email); if (problems.length) errors.password = problems.join(' '); }
    if (mode === 'register' && !name) errors.display_name = '請輸入顯示名稱。';
    setFields(errors); setError(null); setSuccess(null); setRejected(false);
    const first = Object.keys(errors)[0]; if (first) { event.currentTarget.elements.namedItem(first) instanceof HTMLElement && (event.currentTarget.elements.namedItem(first) as HTMLElement).focus(); return; }
    if (Date.now() < retryAt) { setError(`請等待至 ${new Date(retryAt).toLocaleTimeString()} 後再試。`); return; }
    setBusy(true);
    try {
      if (mode === 'register') { const profile = await session.register(email, password, name); setSuccess(`帳號 ${profile.display_name} 已建立。請登入，不會自動為您登入。`); setPassword(''); }
      else { await session.login(email, password); setPassword(''); await onAuthenticated(); }
    } catch (error) {
      if (error instanceof ApiError && error.code === 'RATE_LIMITED' && error.retryAfterMs !== undefined) setRetryAt(current => Math.max(current, Date.now() + error.retryAfterMs!));
      const wrongCredentials = error instanceof ApiError && mode === 'login' && error.code === 'UNAUTHENTICATED';
      // A01 returns 409 CONFLICT only for an already-registered email; the generic CONFLICT text talks about group admins.
      const emailTaken = error instanceof ApiError && mode === 'register' && error.code === 'CONFLICT';
      setError(wrongCredentials ? '電子郵件或密碼不正確。' : emailTaken ? '這個電子郵件已經註冊，請直接登入。' : describeError(error)); setRejected(wrongCredentials);
      refocus.current = wrongCredentials ? 'password' : 'email';
    } finally { if (mode === 'register' && refocus.current === null) refocus.current = 'login'; setBusy(false); }
  }
  return <main className="account-page"><div className="brand-lockup"><span className="brand-mark">H</span><div><strong>HINE</strong><p>讓每一次對話，更靠近。</p></div></div><section className="card account-card"><p className="eyebrow">歡迎使用 HINE</p><h1 tabIndex={-1} data-route-heading>{mode === 'login' ? '歡迎回來' : '建立您的帳號'}</h1><p className="muted">{mode === 'login' ? '登入後接續您的聯絡人與對話。' : '使用電子郵件註冊，與重要的人保持聯繫。'}</p><form noValidate onSubmit={submit}>
    <label htmlFor="email">電子郵件</label><input ref={emailInput} id="email" name="email" type="email" autoComplete="email" value={email} onChange={event => setEmail(event.target.value)} aria-invalid={!!fields.email || rejected} aria-describedby={[fields.email ? 'email-error' : '', error ? 'form-error' : ''].filter(Boolean).join(' ') || undefined} disabled={busy} />{fields.email && <p id="email-error" className="field-error">{fields.email}</p>}
    {mode === 'register' && <><label htmlFor="display_name">顯示名稱</label><input id="display_name" name="display_name" autoComplete="nickname" value={name} onChange={event => setName(event.target.value)} aria-invalid={!!fields.display_name} aria-describedby={fields.display_name ? 'name-error' : undefined} disabled={busy} />{fields.display_name && <p id="name-error" className="field-error">{fields.display_name}</p>}</>}
    <label htmlFor="password">密碼</label><input ref={passwordInput} id="password" name="password" type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} value={password} onChange={event => setPassword(event.target.value)} aria-invalid={!!fields.password || rejected} aria-describedby={[mode === 'register' ? 'password-hint' : '', fields.password ? 'password-error' : '', error ? 'form-error' : ''].filter(Boolean).join(' ') || undefined} disabled={busy} />{mode === 'register' && <p id="password-hint" className="field-hint">8–128 個字元，包含大寫、小寫、數字、符號（含空格）其中至少 2 種；不可包含電子郵件帳號名稱，或 aaaa、1234、abcd 這類連續字元。</p>}{fields.password && <p id="password-error" className="field-error">{fields.password}</p>}
    {error && <p id="form-error" className="notice error" role="alert">{error}</p>}{success && <p className="notice success" role="status">{success} <button ref={loginLink} type="button" className="text-button" onClick={() => onNavigate('/login')}>前往登入</button></p>}
    <button className="primary" disabled={busy} type="submit">{busy ? '處理中…' : mode === 'login' ? '登入' : '建立帳號'}</button></form><p className="account-alternative">{mode === 'login' ? '還沒有帳號？' : '已經有帳號？'} <button className="text-button" onClick={() => onNavigate(mode === 'login' ? '/register' : '/login')}>{mode === 'login' ? '免費註冊' : '登入'}</button></p></section><p className="security-note">安全連線 · 同時只能開一個聊天分頁 · 登入資訊不存放在這台裝置</p></main>;
}
