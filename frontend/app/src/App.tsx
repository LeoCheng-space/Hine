import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { AppMenu, type AppMenuItem } from './AppMenu';
import { Icon } from './icons';
import { AccountPage } from './AccountPages';
import { ChatList } from './ChatList';
import { Avatar, ContactsPage } from './ContactsPage';
import { GroupsPage } from './GroupsPage';
import { ProfilePage } from './ProfilePage';
import { Chat } from './ChatView';
import { describeError, ownerPartition } from './api';
import { parseRoute, type BrowserRouter } from './router';
import type { SessionController } from './session';
import type { ChatController } from './chat';
import { directoryFor } from './user-directory';
import type { ConversationDetail } from './types';
import './Shell.css';

// Must equal the CSS breakpoint text exactly. `(width < 768px)` is rewritten by the bundler to max-width:767.999px, which Chrome rounds to 768px.
const NARROW_QUERY = '(max-width: 767.98px)';
function subscribeNarrow(listener: () => void): () => void { const query = matchMedia(NARROW_QUERY); query.addEventListener('change', listener); return () => query.removeEventListener('change', listener); }
function narrowSnapshot(): boolean { return matchMedia(NARROW_QUERY).matches; }
export function App({ session, chat, router }: { session: SessionController; chat: ChatController; router: BrowserRouter }) {
  const snapshot = useSyncExternalStore(session.subscribe, session.getSnapshot), chatSnapshot = useSyncExternalStore(chat.subscribe, chat.getSnapshot), path = useSyncExternalStore(router.subscribe, router.getSnapshot);
  const route = parseRoute(path), requested = useRef<string | null>(route && !['root', 'login', 'register'].includes(route.kind) ? path : null);
  const [allowedKey, setAllowedKey] = useState<string | null>(null), [routeError, setRouteError] = useState<string | null>(null), [shellNotice, setShellNotice] = useState<string | null>(null);
  const redirecting = useRef<Promise<void> | null>(null);
  const narrow = useSyncExternalStore(subscribeNarrow, narrowSnapshot), [menuOpen, setMenuOpen] = useState(false), menuButton = useRef<HTMLButtonElement>(null);
  useEffect(() => { setMenuOpen(false); }, [path, narrow]);
  const context = snapshot.context, key = JSON.stringify([ownerPartition(context.user_id, context.device_id), path]);
  const directory = directoryFor(session);
  useSyncExternalStore(directory.subscribe, directory.getVersion);
  useEffect(() => { if (context.state === 'authenticated') void directory.ensure(context.user_id); }, [directory, context.state, context.user_id]);
  async function authorizedDestination(target: string): Promise<string> {
    const next = parseRoute(target); if (!next || ['root', 'login', 'register'].includes(next.kind)) return '/chats';
    if (next.kind === 'chat' || next.kind === 'group') { try { const detail = (await session.request<ConversationDetail>(`/conversations/${encodeURIComponent(next.conversationId)}`)).data; if (next.kind === 'group' && detail.type !== 'group') return '/chats'; } catch (error) { setShellNotice('無法返回原頁面：' + describeError(error)); return '/chats'; } }
    return target;
  }
  function returnAfterLogin(): Promise<void> {
    if (redirecting.current) return redirecting.current;
    redirecting.current = (async () => { const target = await authorizedDestination(requested.current ?? '/chats'); requested.current = null; router.navigate(target, true); })().finally(() => { redirecting.current = null; });
    return redirecting.current;
  }
  useEffect(() => {
    let active = true; setAllowedKey(null); setRouteError(null);
    if (snapshot.phase !== 'ready' || context.state === 'refreshing') return;
    if (!route) return;
    if (context.state === 'logged_out') { if (route.kind !== 'login' && route.kind !== 'register') { if (route.kind !== 'root') requested.current = path; router.navigate('/login', true); } return; }
    if (route.kind === 'root') { router.navigate('/chats', true); return; }
    if (route.kind === 'login' || route.kind === 'register') { void returnAfterLogin(); return; }
    if (route.kind !== 'chat') chat.closeChat();
    if (route.kind === 'chat' || route.kind === 'group') {
      void session.request<ConversationDetail>(`/conversations/${encodeURIComponent(route.conversationId)}`).then(result => {
        if (!active) return;
        if (route.kind === 'group' && result.data.type !== 'group') throw new Error('這不是群組對話。');
        setAllowedKey(key);
      }).catch(error => { if (active) { setAllowedKey(null); setRouteError(describeError(error)); chat.closeChat(); } });
    } else setAllowedKey(key);
    return () => { active = false; };
  }, [path, snapshot.phase, context.state, context.user_id, context.device_id, context.session_generation]);
  useEffect(() => {
    if ((route?.kind === 'chat' || route?.kind === 'group') && chatSnapshot.denied.includes(route.conversationId)) { setAllowedKey(null); setShellNotice('您已離開或被移出這個群組。'); router.navigate('/chats', true); }
  }, [chatSnapshot.denied, path]);
  useEffect(() => { if (allowedKey === key || routeError || route?.kind === 'login' || route?.kind === 'register') document.querySelector<HTMLElement>('[data-route-heading]')?.focus(); }, [path, allowedKey, routeError]);
  if (snapshot.phase === 'unsupported' || snapshot.phase === 'blocked') return <main className="status-page"><span className="brand-mark">H</span><h1>{snapshot.phase === 'blocked' ? '聊天已在另一個分頁開啟' : '無法啟用安全聊天'}</h1><p role="alert">{snapshot.error}</p><p className="muted">{snapshot.phase === 'blocked' ? '請關閉另一個操作分頁，再重新載入此頁面。' : '請使用 HTTPS 與新版 Chrome / Edge，並允許 Cookie 與本機儲存。'}</p><button onClick={() => location.reload()}>重新載入</button></main>;
  if (snapshot.phase === 'initializing' || context.state === 'refreshing') return <main className="status-page"><span className="brand-mark">H</span><h1>正在安全初始化</h1><p role="status">確認工作階段與本機儲存…</p></main>;
  if (!route) return <main className="status-page"><h1>找不到這個頁面</h1><button onClick={() => router.navigate('/', true)}>返回首頁</button></main>;
  if (context.state === 'logged_out') return route.kind === 'login' || route.kind === 'register' ? <><AccountPage key={route.kind} session={session} mode={route.kind} onNavigate={router.navigate} onAuthenticated={returnAfterLogin} />{snapshot.error && <div className="session-notice notice error" role="alert">{snapshot.error}</div>}</> : <main className="status-page"><p role="status">導向登入頁…</p></main>;
  if (route.kind === 'root' || route.kind === 'login' || route.kind === 'register') return <main className="status-page"><p role="status">確認返回頁面權限…</p></main>;
  const titles: Record<string,string> = { chats: '聊天', chat: '聊天', contacts: '聯絡人', profile: '個人檔案', group: '群組管理' };
  let content;
  if (routeError) content = <section className="page-content"><h1 tabIndex={-1} data-route-heading>無法存取此頁面</h1><p className="notice error" role="alert">{routeError}</p><button onClick={() => router.navigate('/chats', true)}>返回聊天清單</button></section>;
  // Chat routes keep one ChatList instance across conversation switches; only the room waits for its A12 authorization (design R13).
  else if (route.kind === 'chats' || route.kind === 'chat') content = <section className={`split-page chats-page ${route.kind === 'chat' ? 'detail-selected' : ''}`}><ChatList session={session} chat={chat} path={path} onNavigate={router.navigate} /><div className="detail-panel chat-detail">{allowedKey === key
    ? <>{route.kind === 'chat' && <button className="narrow-back text-button" onClick={() => router.navigate('/chats')}>← 返回聊天清單</button>}<Chat session={session} chat={chat} conversationId={route.kind === 'chat' ? route.conversationId : null} onNavigate={router.navigate} /></>
    : <p role="status" className="chat-loading">正在確認頁面權限…</p>}</div></section>;
  else if (allowedKey !== key) content = <section className="page-content"><p role="status">正在確認頁面權限…</p></section>;
  else if (route.kind === 'contacts') content = <ContactsPage session={session} chat={chat} onNavigate={router.navigate} />;
  else if (route.kind === 'profile') content = <ProfilePage session={session} />;
  else if (route.kind === 'group') content = <GroupsPage session={session} chat={chat} conversationId={route.conversationId} onNavigate={router.navigate} />;
  const self = context.user_id ? directory.get(context.user_id) : undefined, selfName = self?.displayName ?? '我';
  const selfAvatar = <span className="nav-avatar" aria-hidden="true"><Avatar session={session} attachmentId={self && !self.avatarStale ? self.avatarId : null} name={selfName} /></span>;
  const navItems: AppMenuItem[] = [
    { label: '聊天', icon: 'chat', active: route.kind === 'chats' || route.kind === 'chat' || route.kind === 'group', onSelect: () => router.navigate('/chats') },
    { label: '聯絡人', icon: 'contacts', active: route.kind === 'contacts', onSelect: () => router.navigate('/contacts') },
    { label: '個人檔案', icon: 'profile', avatar: selfAvatar, active: route.kind === 'profile', onSelect: () => router.navigate('/profile') },
  ];
  const brand = <button type="button" className="brand-button" aria-label="HINE 聊天首頁" onClick={() => router.navigate('/chats')}><span className="brand-mark" aria-hidden="true">H</span>{narrow && <strong aria-hidden="true">HINE</strong>}</button>;
  return <div className={`app-shell${narrow ? ' narrow' : ''}`}><a className="skip-link" href="#main-content">跳至主要內容</a>
    {narrow
      ? <header className="app-nav app-topbar">
          <button ref={menuButton} type="button" className="icon-button" aria-label="開啟選單" aria-haspopup="dialog" aria-expanded={menuOpen} onClick={() => setMenuOpen(true)}><Icon name="menu" /></button>
          {brand}<span className="topbar-title" aria-hidden="true">{titles[route.kind]}</span>
        </header>
      : <nav className="app-nav app-rail" aria-label="主要導覽">
          {brand}
          <div className="nav-links">{navItems.map(item => <button key={item.label} type="button" className={item.active ? 'active' : undefined} aria-current={item.active ? 'page' : undefined} onClick={item.onSelect}><span className="nav-icon">{item.avatar ?? <Icon name={item.icon} />}</span><span className="nav-label">{item.label}</span></button>)}</div>
          <button type="button" className="logout-button" onClick={() => { void session.logout().catch(error => setShellNotice(describeError(error))); }}><span className="nav-icon"><Icon name="logout" /></span><span className="nav-label">登出</span></button>
        </nav>}
    {narrow && <AppMenu open={menuOpen} triggerRef={menuButton} onClose={() => setMenuOpen(false)} header={<div className="app-menu-self">{selfAvatar}<strong>{selfName}</strong></div>} items={[...navItems, { label: '登出', icon: 'logout', onSelect: () => { void session.logout().catch(error => setShellNotice(describeError(error))); } }]} />}
    <div className="workspace">{shellNotice && <div className="notice" role="status">{shellNotice}<button className="text-button" onClick={() => setShellNotice(null)} aria-label="關閉提示">×</button></div>}<main id="main-content">{content}</main></div>
  </div>;
}
