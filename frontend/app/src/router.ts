export type Route = { kind: 'root' | 'login' | 'register' | 'contacts' | 'chats' | 'profile' } | { kind: 'chat' | 'group'; conversationId: string };
export function parseRoute(path: string): Route | null {
  if (path.includes('?') || path.includes('#')) return null;
  const staticRoutes: Record<string, Route> = { '/': { kind: 'root' }, '/login': { kind: 'login' }, '/register': { kind: 'register' }, '/contacts': { kind: 'contacts' }, '/chats': { kind: 'chats' }, '/profile': { kind: 'profile' } };
  if (staticRoutes[path]) return staticRoutes[path];
  const match = /^\/chats\/([^/]+)$/.exec(path) ?? /^\/groups\/([^/]+)\/manage$/.exec(path);
  if (!match?.[1]) return null;
  try { const id = decodeURIComponent(match[1]); if (!id || Array.from(id).length > 128) return null; return { kind: path.startsWith('/chats/') ? 'chat' : 'group', conversationId: id }; } catch { return null; }
}
export function routePath(route: Route): string {
  if (route.kind === 'chat') return `/chats/${encodeURIComponent(route.conversationId)}`;
  if (route.kind === 'group') return `/groups/${encodeURIComponent(route.conversationId)}/manage`;
  return route.kind === 'root' ? '/' : `/${route.kind}`;
}
export class BrowserRouter {
  private listeners = new Set<() => void>();
  private path = location.pathname;
  private onPop = () => { this.path = location.pathname; for (const listener of this.listeners) listener(); };
  constructor() { window.addEventListener('popstate', this.onPop); }
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  getSnapshot = () => this.path;
  navigate = (path: string, replace = false) => {
    if (!parseRoute(path)) return;
    if (path === this.path) return;
    if (replace) history.replaceState(null, '', path); else history.pushState(null, '', path);
    this.onPop();
  };
  dispose(): void { window.removeEventListener('popstate', this.onPop); this.listeners.clear(); }
}
