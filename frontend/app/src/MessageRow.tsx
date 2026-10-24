import { useEffect, useRef, useState, type ReactNode, type RefObject } from 'react';
import { CLOCK, dateLabel, intentStatus, messageStatus, type StatusIcon, type TimelineItem } from './chat-presentation';
import { Icon, type IconName } from './icons';
import type { SendIntent } from './repository';
import type { MessageView } from './types';

const STATUS_ICON: Record<StatusIcon, IconName> = { clock: 'clock', check: 'check', double: 'checks', 'double-read': 'checks', warn: 'warn' };

function Status({ icon, text }: { icon: StatusIcon; text: string }) {
  return <span className={`message-status status-${icon}`}><Icon name={STATUS_ICON[icon]} /><span className="visually-hidden">{text}</span></span>;
}

/** A day boundary inside the scroller. Never carries a message id or read occlusion (design §7.2). */
export function DateSeparator({ label }: { label: string }) {
  return <li className="date-separator" role="separator"><span>{label}</span></li>;
}

/** One persisted message. The bubble is the only element carrying `data-message-id`. */
export function MessageRow({ item, own, kind, readEligible, senderName, accent, avatar, children }: { item: Extract<TimelineItem, { kind: 'message' }>; own: boolean; kind: 'direct' | 'group'; readEligible: boolean; senderName: string; accent: number; avatar?: ReactNode; children: ReactNode }) {
  const { message, groupStart, groupEnd } = item, status = own ? messageStatus(message, kind) : null;
  return <li className={`message-row ${own ? 'own' : 'peer'}${groupStart ? ' group-start' : ''}${groupEnd ? ' group-end' : ''}`}>
    {kind === 'group' && !own && <span className="message-avatar" aria-hidden="true">{groupEnd ? avatar : null}</span>}
    <article className="message-bubble" data-message-id={message.id} data-read-eligible={readEligible ? 'true' : 'false'} aria-label={`${own ? '你' : senderName}的訊息`}>
      {kind === 'group' && !own && groupStart && <strong className={`message-sender accent-text-${accent}`}>{senderName}</strong>}
      {children}
      <footer className="message-meta"><time dateTime={message.created_at}>{CLOCK.format(new Date(message.created_at))}</time>{status && <Status {...status} />}</footer>
    </article>
  </li>;
}

/** A local send intent not yet matched to a persisted message; keeps the original-intent retry. */
export function IntentRow({ intent, connectionReady, onRetry, children }: { intent: SendIntent; connectionReady: boolean; onRetry: () => void; children: ReactNode }) {
  return <li className="message-row own group-start group-end">
    <article className={`message-bubble pending-message${intent.status === 'rejected' ? ' rejected-message' : ''}`} aria-label="你的待確認訊息">
      {children}
      <footer className="message-meta"><Status {...intentStatus(intent.status)} /></footer>
      {intent.error && <p className="intent-error">{intent.error === 'RATE_LIMITED' ? '傳送速度受限，請等待後重試。' : intent.error === 'FORBIDDEN' ? '對話權限已變更。' : '這則訊息尚未完成傳送，內容已保留；重試會沿用原本的訊息。'}</p>}
      {intent.status !== 'persisted' && <button type="button" disabled={!connectionReady || intent.retryAt !== null && intent.retryAt > Date.now()} onClick={onRetry}>重試傳送</button>}
    </article>
  </li>;
}

const DATE_PILL_IDLE_MS = 1200;
/** Floating date for the first visible message while the user scrolls. Lives outside the scroller, measures at most once per frame, hides after a short idle and near the top or bottom. */
export function DatePill({ scroller, messages, now }: { scroller: RefObject<HTMLElement | null>; messages: MessageView[]; now: Date }) {
  const [label, setLabel] = useState<string | null>(null), pill = useRef<HTMLDivElement>(null);
  const latest = useRef({ messages, now });
  latest.current = { messages, now };
  useEffect(() => {
    const element = scroller.current; if (!element) return;
    let frame = 0, idle = 0;
    const measure = (): void => {
      frame = 0;
      const top = element.getBoundingClientRect().top, edge = element.scrollTop < 48 || element.scrollHeight - element.clientHeight - element.scrollTop <= 48;
      const first = edge ? undefined : [...element.querySelectorAll<HTMLElement>('[data-message-id]')].find(node => node.getBoundingClientRect().bottom > top);
      const message = first ? latest.current.messages.find(item => item.id === first.dataset.messageId) : undefined;
      const next = message ? dateLabel(new Date(message.created_at), latest.current.now) : null;
      if (pill.current) pill.current.style.top = `${element.offsetTop + 8}px`;
      setLabel(current => (current === next ? current : next));
    };
    const onScroll = (): void => {
      if (!frame) frame = requestAnimationFrame(measure);
      clearTimeout(idle); idle = window.setTimeout(() => setLabel(null), DATE_PILL_IDLE_MS);
    };
    element.addEventListener('scroll', onScroll, { passive: true });
    return () => { element.removeEventListener('scroll', onScroll); if (frame) cancelAnimationFrame(frame); clearTimeout(idle); };
  }, [scroller]);
  return <div ref={pill} className="date-pill" data-read-occlusion aria-hidden="true" hidden={label === null}>{label}</div>;
}
