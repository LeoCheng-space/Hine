import { createRoot } from 'react-dom/client';
import { App } from './App';
import { SessionController } from './session';
import { ChatController } from './chat';
import { BrowserRouter } from './router';
import { describeError } from './api';
const element = document.getElementById('root');
if (!element) throw new Error('Missing application root.');
const session = new SessionController();
const chat = new ChatController(session);
const router = new BrowserRouter();
const root = createRoot(element);
root.render(<App session={session} chat={chat} router={router} />);
void session.start().then(() => chat.start()).catch(error => {
  root.render(<main className="status-page"><h1>無法完成聊天初始化</h1><p role="alert">{describeError(error)}</p><button onClick={() => location.reload()}>重新載入並核對</button></main>);
});
window.addEventListener('pagehide', () => { void chat.stop(); session.dispose(); router.dispose(); root.unmount(); }, { once: true });
window.addEventListener('pageshow', event => { if (event.persisted) location.reload(); });
