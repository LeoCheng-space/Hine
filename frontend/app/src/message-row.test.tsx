import { expect, test } from 'bun:test';
import { renderToStaticMarkup } from 'react-dom/server';
import { DateSeparator, IntentRow, MessageRow } from './MessageRow';
import type { SendIntent } from './repository';
import type { MessageView } from './types';

const id = '9f1c2b0e-1d2c-4e5f-8a9b-0c1d2e3f4a5b';
const message: MessageView = { id, event_id: '9f1c2b0e-1d2c-4e5f-8a9b-0c1d2e3f4a5c', conversation_id: 'c', sender_id: 'me', created_at: '2026-10-17T01:00:00Z', order_key: '00000000000000000001', receipt: { kind: 'direct', message_id: id, recipient_id: 'b', status: 'read', updated_at: '2026-10-17T01:00:01Z' }, type: 'text', text: '你好' };

test('a message renders exactly one UUID data-message-id and keeps status text in its meta', () => {
  const html = renderToStaticMarkup(<ol><MessageRow item={{ kind: 'message', message, groupStart: true, groupEnd: true }} own kind="direct" readEligible={false} senderName="我" accent={1}><p className="message-text">你好</p></MessageRow></ol>);
  expect(html.match(/data-message-id="/g)?.length).toBe(1);
  expect(html).toContain(`data-message-id="${id}"`);
  expect(html).toContain('data-read-eligible="false"');
  expect(html.slice(html.indexOf('message-meta'))).toContain('已讀');
});
test('a group message from someone else names the sender only at the start of a group', () => {
  const peer = { ...message, sender_id: 'ann', receipt: null };
  const start = renderToStaticMarkup(<ol><MessageRow item={{ kind: 'message', message: peer, groupStart: true, groupEnd: false }} own={false} kind="group" readEligible senderName="Ann" accent={2}><p>hi</p></MessageRow></ol>);
  const middle = renderToStaticMarkup(<ol><MessageRow item={{ kind: 'message', message: peer, groupStart: false, groupEnd: false }} own={false} kind="group" readEligible senderName="Ann" accent={2}><p>hi</p></MessageRow></ol>);
  expect(start).toContain('message-sender');
  expect(middle).not.toContain('message-sender');
  expect(start).toContain('data-read-eligible="true"');
});
test('date separators never carry message ids or read occlusion', () => {
  const html = renderToStaticMarkup(<ol><DateSeparator label="今天" /></ol>);
  expect(html).not.toContain('data-message-id');
  expect(html).not.toContain('data-read-occlusion');
  expect(html).toContain('今天');
});
test('a pending intent has no message id, keeps its status wording and offers original-intent retry', () => {
  const intent: SendIntent = { clientMessageId: 'c1', conversationId: 'c', payload: { type: 'text', text: 'x' }, createdAt: '2026-10-17T01:00:00Z', status: 'unknown', messageId: null, error: null, retryAt: null };
  const html = renderToStaticMarkup(<ol><IntentRow intent={intent} connectionReady onRetry={() => {}}><p>x</p></IntentRow></ol>);
  expect(html).not.toContain('data-message-id');
  expect(html).toContain('pending-message');
  expect(html).toContain('結果尚未確認');
  expect(html).toContain('以原意圖重試');
});
