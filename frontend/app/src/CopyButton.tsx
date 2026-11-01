import { useEffect, useState } from 'react';
import { Icon } from './icons';

/** Copies `value` and confirms in place for two seconds. The accessible name is the visible verb plus `subject`
 *  (WCAG 2.5.3), and the result is announced through a polite live region rather than `role="status"`. */
export function CopyButton({ value, subject }: { value: string; subject: string }) {
  const [state, setState] = useState<'idle' | 'copied' | 'failed'>('idle');
  useEffect(() => {
    if (state === 'idle') return;
    const timer = setTimeout(() => setState('idle'), 2000);
    return () => clearTimeout(timer);
  }, [state]);
  const verb = state === 'copied' ? '已複製' : state === 'failed' ? '無法複製' : '複製';
  return <>
    <button type="button" className={`copy-button${state === 'copied' ? ' copied' : ''}`} onClick={() => { navigator.clipboard.writeText(value).then(() => setState('copied'), () => setState('failed')); }}>
      <Icon name={state === 'copied' ? 'check' : 'copy'} /><span>{verb}</span><span className="visually-hidden">{subject}</span>
    </button>
    <span className="visually-hidden" aria-live="polite">{state === 'idle' ? '' : `${verb}${subject}`}</span>
  </>;
}
