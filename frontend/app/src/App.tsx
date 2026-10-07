import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { AccountPage } from './AccountPages';
import { ContactsPage, usePagedList } from './ContactsPage';
import { CreateGroup, GroupsPage } from './GroupsPage';
import { ProfilePage } from './ProfilePage';
import { Chat } from './ChatView';
import { describeError, ownerPartition } from './api';
import { parseRoute, type BrowserRouter } from './router';
import type { SessionController } from './session';
import type { ChatController } from './chat';
import type { ConversationDetail, ConversationSummary } from './types';
import './Shell.css';
function ChatList({ session, path, onNavigate }: { session: SessionController; path: string; onNavigate: (path: string) => void }) {
  const list = usePagedList<ConversationSummary>(session, 'conversations', item => item.id), [filter, setFilter] = useState('');
  useEffect(() => { void list.load(true); }, [path, list.load]);
  useEffect(() => {
    const changed = () => { void list.load(true); };
    window.addEventListener('hine-conversations-changed', changed);
    return () => window.removeEventListener('hine-conversations-changed', changed);
  }, [list.load]);
  const items = list.items.filter(item => (item.title ?? '').toLocaleLowerCase().includes(filter.toLocaleLowerCase()));
  return <aside className="list-panel chat-list"><header className="panel-header"><p className="eyebrow">STAY CONNECTED</p><h1 tabIndex={-1}>聊天</h1><p className="muted">每段關係，從一句話開始。</p></header><CreateGroup session={session} onCreated={id => onNavigate(`/chats/${encodeURIComponent(id)}`)} /><label htmlFor="chat-filter">篩選已載入的對話標題</label><input id="chat-filter" type="search" value={filter} onChange={event => setFilter(event.target.value)} /><p className="small muted">僅篩選已載入項目。一對一對話沒有標題。</p>{list.error && <p role="alert" className="notice error">{list.error}</p>}<ul className="item-list">{items.map(item => <li key={item.id}><button className={`list-item ${path === `/chats/${encodeURIComponent(item.id)}` ? 'selected' : ''}`} onClick={() => onNavigate(`/chats/${encodeURIComponent(item.id)}`)}><span className="avatar" aria-hidden="true">{item.type === 'group' ? '群' : '聊'}</span><span className="item-copy"><strong>{item.title ?? '一對一對話'}</strong><span className="small muted identifier">{item.id}</span></span>{item.unread_count > 0 && <span className="unread" aria-label={`${item.unread_count} 則伺服器查詢未讀`}>{item.unread_count}</span>}</button></li>)}</ul>{list.busy && <p role="status">載入對話…</p>}{!items.length && !list.busy && <div className="empty-state"><strong>{filter ? '沒有符合的已載入對話' : '還沒有對話'}</strong><p>選擇聯絡人開始聊天，或建立您的群組。</p><button onClick={() => onNavigate('/contacts')}>前往聯絡人</button></div>}<div className="actions"><button disabled={list.busy} onClick={() => { void list.load(true); }}>重新整理</button>{list.cursor && <button disabled={list.busy} onClick={() => { void list.load(); }}>載入下一頁</button>}</div></aside>;
}
export function App({ session, chat, router }: { session: SessionController; chat: ChatController; router: BrowserRouter }) {
  const snapshot = useSyncExternalStore(session.subscribe, session.getSnapshot), chatSnapshot = useSyncExternalStore(chat.subscribe, chat.getSnapshot), path = useSyncExternalStore(router.subscribe, router.getSnapshot);
  const route = parseRoute(path), requested = useRef<string | null>(route && !['root', 'login', 'register'].includes(route.kind) ? path : null);
  const [allowedKey, setAllowedKey] = useState<string | null>(null), [routeError, setRouteError] = useState<string | null>(null), [shellNotice, setShellNotice] = useState<string | null>(null);
  const redirecting = useRef<Promise<void> | null>(null);
  const context = snapshot.context, key = JSON.stringify([ownerPartition(context.user_id, context.device_id), path]);
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
  useEffect(() => { if (allowedKey === key || route?.kind === 'login' || route?.kind === 'register') document.querySelector<HTMLElement>('h1')?.focus(); }, [path, allowedKey]);
  if (snapshot.phase === 'unsupported' || snapshot.phase === 'blocked') return <main className="status-page"><span className="brand-mark">H</span><h1>{snapshot.phase === 'blocked' ? '聊天已在另一個分頁開啟' : '無法啟用安全聊天'}</h1><p role="alert">{snapshot.error}</p><p className="muted">{snapshot.phase === 'blocked' ? '請關閉另一個操作分頁，再重新載入此頁面。' : '請使用 HTTPS 與新版 Chrome / Edge，並允許 Cookie 與本機儲存。'}</p><button onClick={() => location.reload()}>重新載入</button></main>;
  if (snapshot.phase === 'initializing' || context.state === 'refreshing') return <main className="status-page"><span className="brand-mark">H</span><h1>正在安全初始化</h1><p role="status">確認工作階段與本機儲存…</p></main>;
  if (!route) return <main className="status-page"><h1>找不到這個頁面</h1><button onClick={() => router.navigate('/', true)}>返回首頁</button></main>;
  if (context.state === 'logged_out') return route.kind === 'login' || route.kind === 'register' ? <><AccountPage key={route.kind} session={session} mode={route.kind} onNavigate={router.navigate} onAuthenticated={returnAfterLogin} />{snapshot.error && <div className="session-notice notice error" role="alert">{snapshot.error}</div>}</> : <main className="status-page"><p role="status">導向登入頁…</p></main>;
  if (route.kind === 'root' || route.kind === 'login' || route.kind === 'register') return <main className="status-page"><p role="status">確認返回頁面權限…</p></main>;
  const titles: Record<string,string> = { chats: '聊天', chat: '聊天', contacts: '聯絡人', profile: '個人檔案', group: '群組管理' };
  let content;
  if (routeError) content = <section className="page-content"><h1 tabIndex={-1}>無法存取此頁面</h1><p className="notice error" role="alert">{routeError}</p><button onClick={() => router.navigate('/chats', true)}>返回聊天清單</button></section>;
  else if (allowedKey !== key) content = <section className="page-content"><p role="status">正在確認頁面權限…</p></section>;
  else if (route.kind === 'contacts') content = <ContactsPage session={session} chat={chat} onNavigate={router.navigate} />;
  else if (route.kind === 'profile') content = <ProfilePage session={session} />;
  else if (route.kind === 'group') content = <GroupsPage session={session} chat={chat} conversationId={route.conversationId} onNavigate={router.navigate} />;
  else content = <section className={`split-page chats-page ${route.kind === 'chat' ? 'detail-selected' : ''}`}><ChatList session={session} path={path} onNavigate={router.navigate} /><div className="detail-panel chat-detail">{route.kind === 'chat' && <button className="narrow-back text-button" onClick={() => router.navigate('/chats')}>← 返回聊天清單</button>}<Chat session={session} chat={chat} conversationId={route.kind === 'chat' ? route.conversationId : null} onNavigate={router.navigate} /></div></section>;
  return <div className="app-shell"><a className="skip-link" href="#main-content">跳至主要內容</a><nav className="app-nav" aria-label="主要導覽"><button className="brand-button" aria-label="HINE 聊天首頁" onClick={() => router.navigate('/chats')}><span className="brand-mark">H</span><strong>HINE</strong></button><div className="nav-links">{[{ path: '/chats', label: '聊天', symbol: '◷', active: route.kind === 'chats' || route.kind === 'chat' || route.kind === 'group' }, { path: '/contacts', label: '聯絡人', symbol: '◎', active: route.kind === 'contacts' }, { path: '/profile', label: '個人檔案', symbol: '◉', active: route.kind === 'profile' }].map(item => <button key={item.path} className={item.active ? 'active' : ''} aria-current={item.active ? 'page' : undefined} onClick={() => router.navigate(item.path)}><span aria-hidden="true">{item.symbol}</span>{item.label}</button>)}</div><button className="logout-button" onClick={() => { void session.logout().catch(error => setShellNotice(describeError(error))); }}>登出</button></nav><div className="workspace"><header className="workspace-header"><span>{titles[route.kind]}</span><span className="connection-indicator">● {chatSnapshot.connection}</span></header>{shellNotice && <div className="notice" role="status">{shellNotice}<button className="text-button" onClick={() => setShellNotice(null)} aria-label="關閉提示">×</button></div>}<main id="main-content">{content}</main></div></div>;
}
