import { useEffect, useRef, type ReactNode, type RefObject } from 'react';
import { Icon, type IconName } from './icons';

export interface AppMenuItem { label: string; icon: IconName; avatar?: ReactNode; active?: boolean; onSelect: () => void }

export function AppMenu({ open, items, header, onClose, triggerRef }: { open: boolean; items: AppMenuItem[]; header?: ReactNode; onClose: () => void; triggerRef: RefObject<HTMLButtonElement | null> }) {
  const dialog = useRef<HTMLDialogElement>(null), first = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const element = dialog.current; if (!element) return;
    element.showModal(); first.current?.focus(); window.dispatchEvent(new Event('hine-overlay-change'));
    return () => {
      element.close(); window.dispatchEvent(new Event('hine-overlay-change'));
      const trigger = triggerRef.current;
      if (trigger?.isConnected && trigger.getClientRects().length > 0) trigger.focus();
      else document.querySelector<HTMLElement>('[data-route-heading]')?.focus();
    };
  }, [open, triggerRef]);
  if (!open) return null;
  return <dialog ref={dialog} className="app-menu" aria-modal="true" aria-label="選單"
    onCancel={event => { event.preventDefault(); onClose(); }}
    onClick={event => { if (event.target === dialog.current) onClose(); }}>
    <nav aria-label="主要導覽" className="app-menu-panel">
      <div className="app-menu-brand" aria-hidden="true"><span className="brand-mark">H</span><strong>HINE</strong></div>
      {header}
      <ul>{items.map((item, index) => <li key={item.label}>
        <button ref={index === 0 ? first : undefined} type="button" className={item.active ? 'active' : undefined} aria-current={item.active ? 'page' : undefined} onClick={() => { onClose(); item.onSelect(); }}>
          <span className="nav-icon">{item.avatar ?? <Icon name={item.icon} />}</span>{item.label}
        </button>
      </li>)}</ul>
    </nav>
  </dialog>;
}
