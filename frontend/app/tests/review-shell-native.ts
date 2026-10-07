import { createElement } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from '../src/App';
import { ChatController } from '../src/chat';
import { ChatRepository, record } from '../src/repository';
import { BrowserRouter } from '../src/router';
import { DeviceStore, type SessionController } from '../src/session';
import type { AccessSession, ApiResult, ConversationCreateResult, ConversationSummary, Page, UserProfile } from '../src/types';
export { SessionController } from '../src/session';

// Parent bundles these exports and runs them in a fresh owned native HTTPS Chrome
// context. All API/WSS/IDB/Storage behavior remains real. The only faults below delay
// successful real A11 results; they never fabricate responses or auth authority.
export const nativeShellCases = [
  'remote group join refreshes /chats without navigation',
  'remote group rename refreshes /chats without navigation',
  'remote group removal refreshes /chats without navigation',
  'event bursts coalesce and a delayed old A11 cannot win',
  'A11 pagination and server unread remain authoritative',
  'an old-owner successful A11 cannot commit after account switch',
  'an unseen full-casefold login retains the original device partition',
  'the original device draft and pending intent survive native reload',
] as const;
export const nativeShellDiagnostic: { stage: string } = { stage: 'not_started' };
function assert(condition: unknown, message: string): asserts condition { if (!condition) throw new Error(message); }
async function until(predicate: () => boolean, message: string): Promise<void> {
  const expires = performance.now() + 20_000;
  while (!predicate()) {
    assert(performance.now() < expires, message);
    await new Promise<void>(resolve => window.setTimeout(resolve, 20));
  }
}
async function within<T>(promise: Promise<T>, message: string): Promise<T> {
  let timer: number | undefined;
  try { return await Promise.race([promise, new Promise<never>((_, reject) => { timer = window.setTimeout(() => reject(new Error(message)), 20_000); })]); }
  finally { window.clearTimeout(timer); }
}
async function peerApi<T>(session: SessionController, peer: AccessSession, path: string, method: string, json?: unknown): Promise<T> {
  const response = await fetch(`${session.config.API_BASE_URL}${path}`, {
    method, credentials: 'omit', headers: { Authorization: `Bearer ${peer.access_token}`, 'Content-Type': 'application/json', 'Idempotency-Key': crypto.randomUUID() },
    ...(json === undefined ? {} : { body: JSON.stringify(json) }), signal: AbortSignal.timeout(10_000),
  });
  assert(response.ok, 'Actual separately authenticated peer mutation failed.');
  return (response.status === 204 ? undefined : record(await response.json()).data) as T;
}
async function peerText(session: SessionController, peer: AccessSession, id: string): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    const socket = new WebSocket(session.config.WS_URL), auth = crypto.randomUUID(), send = crypto.randomUUID(), c1 = crypto.randomUUID();
    const timer = window.setTimeout(() => { socket.close(); reject(new Error('Actual peer W05/W06 timed out.')); }, 10_000);
    const finish = (error?: unknown): void => { window.clearTimeout(timer); socket.close(); if (error) reject(error); else resolve(); };
    socket.onopen = () => socket.send(JSON.stringify({ event: 'auth.authenticate', event_id: auth, timestamp: new Date().toISOString(), payload: { access_token: peer.access_token, device_id: peer.device_id } }));
    socket.onmessage = event => {
      try {
        const frame = record(JSON.parse(String(event.data))), payload = record(frame.payload);
        assert(frame.event !== 'error', 'Actual peer WSS rejected the fixture.');
        if (frame.event === 'auth.accepted' && frame.correlation_id === auth) {
          assert(payload.user_id === peer.user_id && payload.device_id === peer.device_id, 'Actual peer W02 binding mismatch.');
          socket.send(JSON.stringify({ event: 'message.send', event_id: send, timestamp: new Date().toISOString(), conversation_id: id, payload: { client_message_id: c1, type: 'text', text: `native unread fixture ${crypto.randomUUID()}` } }));
        }
        if (frame.event === 'message.ack' && frame.correlation_id === send) {
          assert(payload.status === 'persisted' && payload.client_message_id === c1, 'Actual W06 was not a persisted original C1.'); finish();
        }
      } catch (error) { finish(error); }
    };
    socket.onerror = () => finish(new Error('Actual peer WSS failed.'));
  });
}
interface ListObservation { path: string; result: ApiResult<Page<ConversationSummary>> }
interface NativeListObserver {
  observations: ListObservation[];
  readonly active: number;
  readonly maxActive: number;
  readonly starts: number;
  arm(): { reached: Promise<void>; release: () => void };
  resetPeak(): void;
  restore(): void;
}
interface MountedShell { router: BrowserRouter; dispose(): void }
function observeLists(session: SessionController): NativeListObserver {
  const original = session.request, observations: ListObservation[] = [];
  let active = 0, maxActive = 0, starts = 0, armed = false, released = true;
  let saw!: () => void, release!: () => void;
  let reached = Promise.resolve(), held = Promise.resolve();
  session.request = new Proxy(original, {
    async apply(target, _thisArg, args) {
      const path: unknown = args[0];
      if (typeof path !== 'string' || !path.startsWith('/conversations?')) return Reflect.apply(target, session, args);
      ++active; ++starts; maxActive = Math.max(maxActive, active);
      const shouldHold = armed; if (shouldHold) armed = false;
      try {
        const result: unknown = await Reflect.apply(target, session, args);
        const data = record(record(result).data); assert(Array.isArray(data.items), 'Actual A11 omitted items.');
        // Hold after SessionController has validated the actual HTTP result, so a
        // late consumer continuation still needs its own owner/lifetime guard.
        if (shouldHold) { saw(); await held; }
        observations.push({ path, result: result as ApiResult<Page<ConversationSummary>> });
        return result;
      } finally { --active; }
    },
  });
  return {
    observations,
    get active(): number { return active; },
    get maxActive(): number { return maxActive; },
    get starts(): number { return starts; },
    arm() {
      assert(released && !armed, 'The previous native response gate is still held.');
      released = false; armed = true;
      reached = new Promise<void>(resolve => { saw = resolve; });
      held = new Promise<void>(resolve => { release = resolve; });
      return { reached, release: () => { released = true; release(); } };
    },
    resetPeak(): void { maxActive = active; },
    restore(): void { session.request = original; if (!released) { released = true; release(); } },
  };
}
function mountShell(session: SessionController, chat: ChatController): MountedShell {
  assert(!document.querySelector('.app-shell'), 'Use a fresh parent-owned harness, not a second production App.');
  history.replaceState(null, '', '/chats');
  const router = new BrowserRouter(), host = document.createElement('div');
  document.body.append(host); const root = createRoot(host);
  root.render(createElement(App, { session, chat, router }));
  return { router, dispose(): void { root.unmount(); router.dispose(); host.remove(); } };
}
function row(id: string): HTMLButtonElement | null {
  return [...document.querySelectorAll<HTMLButtonElement>('.chat-list .list-item')].find(button => button.querySelector('.identifier')?.textContent === id) ?? null;
}
function verifySummary(summary: ConversationSummary): void {
  const button = row(summary.id); assert(button, 'Actual A11 summary is absent from the rendered list.');
  assert(button.querySelector('strong')?.textContent === (summary.title ?? '一對一對話'), 'Rendered title disagrees with actual A11.');
  const unread = button.querySelector('.unread');
  assert(summary.unread_count > 0 ? unread?.textContent === String(summary.unread_count) && unread.getAttribute('aria-label') === `${summary.unread_count} 則伺服器查詢未讀` : unread === null, 'The list invented a client-side unread count instead of displaying A11.');
}
async function listReady(observation: NativeListObserver): Promise<void> {
  await until(() => observation.observations.length > 0 && observation.active === 0 && !!document.querySelector('.chat-list') && !document.querySelector('.chat-list [role="status"]'), 'Actual initial A11 did not render.');
}

export async function runNativeChatListChanges(session: SessionController, peer: AccessSession, caseOnly: 'join' | 'rename' | 'remove' | 'all' = 'all'): Promise<{ case: string; groupId: string; listRequests: number }> {
  const owner = session.getSnapshot().context; assert(owner.state === 'authenticated' && owner.user_id !== peer.user_id, 'Two distinct real authenticated actors are required.');
  const initialTitle = `native list ${crypto.randomUUID()}`, renamedTitle = `${initialTitle} renamed`;
  // Creating a one-member peer group then A16-add keeps these regressions independent
  // of the separate A14 multi-event fanout bug.
  const created = await peerApi<ConversationCreateResult>(session, peer, '/conversations/groups', 'POST', { title: initialTitle, member_ids: [] });
  const id = created.id, path = `/conversations/${encodeURIComponent(id)}`, chat = new ChatController(session);
  let mounted: MountedShell | null = null;
  const observation = observeLists(session);
  try {
    nativeShellDiagnostic.stage = `list_${caseOnly}_setup`;
    if (caseOnly !== 'join' && caseOnly !== 'all') await peerApi(session, peer, `${path}/members`, 'POST', { user_id: owner.user_id });
    await chat.start(); await until(() => chat.getSnapshot().connection === 'ready', 'Actual owner W02 missing.');
    await chat.reconcile(); mounted = mountShell(session, chat); await listReady(observation);
    if (caseOnly === 'join' || caseOnly === 'all') {
      assert(row(id) === null, 'Unjoined peer group leaked into the owner list.');
      nativeShellDiagnostic.stage = 'remote_join_same_chats';
      await peerApi(session, peer, `${path}/members`, 'POST', { user_id: owner.user_id });
      await chat.reconcile();
      await until(() => !!chat.getSnapshot().conversations[id], 'Real A16 event did not install the current authorized projection.');
      await until(() => row(id)?.querySelector('strong')?.textContent === initialTitle, 'Remote join reconciled but /chats never displayed its new group.');
    } else assert(row(id), 'Existing joined fixture did not load through actual A11.');
    if (caseOnly === 'rename' || caseOnly === 'all') {
      nativeShellDiagnostic.stage = 'remote_rename_same_chats';
      await peerApi(session, peer, path, 'PATCH', { title: renamedTitle }); await chat.reconcile();
      await until(() => chat.getSnapshot().conversations[id]?.title === renamedTitle, 'Real A15 did not reach ChatController.');
      await until(() => row(id)?.querySelector('strong')?.textContent === renamedTitle, 'Remote title reconciled but the fixed /chats list stayed stale.');
    }
    if (caseOnly === 'all') {
      nativeShellDiagnostic.stage = 'actual_server_unread_same_chats';
      await peerText(session, peer, id); await chat.reconcile();
      await until(() => observation.observations.some(page => page.result.data.items.some(item => item.id === id && item.unread_count > 0)), 'Actual A11 unread fixture never refreshed.');
      const queried = observation.observations.flatMap(page => page.result.data.items).filter(item => item.id === id).at(-1); assert(queried && queried.unread_count > 0, 'Actual server unread fixture must be nonzero.'); verifySummary(queried);
    }
    if (caseOnly === 'remove' || caseOnly === 'all') {
      nativeShellDiagnostic.stage = 'remote_remove_same_chats';
      await peerApi(session, peer, `${path}/members/${encodeURIComponent(owner.user_id)}`, 'DELETE'); await chat.reconcile();
      await until(() => chat.getSnapshot().denied.includes(id), 'Real A17 self-removal did not reach the projection.');
      await until(() => row(id) === null, 'Remote removal reconciled but the fixed /chats list retained the old group.');
    }
    assert(location.pathname === '/chats' && mounted.router.getSnapshot() === '/chats', 'The test refreshed by navigation instead of consuming conversation changes.');
    return { case: caseOnly, groupId: id, listRequests: observation.starts };
  } finally { observation.restore(); mounted?.dispose(); await chat.stop(); }
}

export async function runNativeChatListBurstRace(session: SessionController, peer: AccessSession): Promise<{ listRequestsDuringBurst: number; maxConcurrent: number }> {
  const owner = session.getSnapshot().context; assert(owner.state === 'authenticated', 'Actual authenticated owner required.');
  const oldTitle = `native gated list ${crypto.randomUUID()}`, newTitle = `${oldTitle} current`;
  const created = await peerApi<ConversationCreateResult>(session, peer, '/conversations/groups', 'POST', { title: oldTitle, member_ids: [] });
  const id = created.id, path = `/conversations/${encodeURIComponent(id)}`;
  await peerApi(session, peer, `${path}/members`, 'POST', { user_id: owner.user_id });
  const chat = new ChatController(session), observation = observeLists(session); let mounted: MountedShell | null = null;
  try {
    await chat.start(); await until(() => chat.getSnapshot().connection === 'ready', 'Actual W02 missing.'); await chat.reconcile();
    mounted = mountShell(session, chat); await listReady(observation); assert(row(id), 'Actual joined A11 fixture missing.');
    observation.resetPeak(); const before = observation.starts, gate = observation.arm();
    nativeShellDiagnostic.stage = 'old_successful_A11_held_before_burst';
    window.dispatchEvent(new Event('hine-conversations-changed'));
    await within(gate.reached, 'Existing conversation-change event never requested A11.');
    await peerApi(session, peer, path, 'PATCH', { title: newTitle }); await chat.reconcile();
    for (let index = 0; index < 32; index++) window.dispatchEvent(new Event('hine-conversations-changed'));
    await new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
    assert(observation.starts === before + 1 && observation.active === 1, 'A burst started overlapping A11 requests instead of coalescing a trailing current refresh.');
    nativeShellDiagnostic.stage = 'release_old_A11_then_current_trailing_refresh'; gate.release();
    await until(() => row(id)?.querySelector('strong')?.textContent === newTitle && observation.active === 0, 'The delayed old A11 won, or the coalesced trailing refresh was lost.');
    assert(observation.maxActive === 1, 'A11 refreshes overlapped during the burst.');
    assert(observation.starts - before <= 3, 'Stable event listener caused a refresh storm after the burst.');
    assert(location.pathname === '/chats', 'The burst test navigated to force a refresh.');
    return { listRequestsDuringBurst: observation.starts - before, maxConcurrent: observation.maxActive };
  } finally { observation.restore(); mounted?.dispose(); await chat.stop(); }
}

export async function runNativeChatListPaging(session: SessionController): Promise<{ firstPage: number; nextPage: number; uniqueRendered: number }> {
  assert(session.getSnapshot().context.state === 'authenticated', 'Actual authenticated owner required.');
  nativeShellDiagnostic.stage = 'actual_A11_paging_fixture_21_groups';
  for (let index = 0; index < 21; index++) await session.request('/conversations/groups', { method: 'POST', idempotencyKey: crypto.randomUUID(), json: { title: `native page ${index} ${crypto.randomUUID()}`, member_ids: [] } });
  // No second chat runtime is started: paging is real HTTP and the existing event
  // is dispatched only after a real, current A11 has been validated.
  const chat = new ChatController(session), observation = observeLists(session), mounted = mountShell(session, chat);
  const nextButton = () => [...document.querySelectorAll<HTMLButtonElement>('.chat-list .actions button')].find(button => button.textContent === '載入下一頁');
  try {
    await listReady(observation);
    const first = observation.observations.at(-1)!; assert(first.result.data.items.length === 20 && first.result.meta?.next_cursor, 'Actual A11 fixture must expose a 20-item cursor page.');
    first.result.data.items.forEach(verifySummary); assert(nextButton(), 'A11 continuation has no consumer control.');
    nativeShellDiagnostic.stage = 'actual_A11_next_page'; nextButton()!.click();
    await until(() => observation.observations.length >= 2 && observation.active === 0 && !document.querySelector('.chat-list [role="status"]'), 'Actual A11 next page never rendered.');
    const next = observation.observations.at(-1)!;
    assert(new URL(next.path, location.origin).searchParams.get('cursor') === first.result.meta.next_cursor, 'The list substituted a SyncCursor or stale cursor for the actual A11 continuation.');
    const expected = [...first.result.data.items.filter(item => !next.result.data.items.some(incoming => incoming.id === item.id)), ...next.result.data.items];
    expected.forEach(verifySummary);
    const rendered = [...document.querySelectorAll('.chat-list .identifier')].map(element => element.textContent);
    assert(rendered.length === expected.length && new Set(rendered).size === rendered.length, 'A11 page merge duplicated or discarded a loaded conversation.');
    const beforeRefresh = observation.observations.length;
    window.dispatchEvent(new Event('hine-conversations-changed'));
    await until(() => observation.observations.length > beforeRefresh && observation.active === 0, 'A current conversation-change event did not reset A11 pagination.');
    const refreshed = observation.observations.at(-1)!;
    assert(new URL(refreshed.path, location.origin).searchParams.get('cursor') === null, 'Refresh continued an old page cursor rather than starting a fresh A11 query.');
    refreshed.result.data.items.forEach(verifySummary);
    assert(nextButton() && !nextButton()!.disabled, 'Refresh broke the server continuation control.');
    return { firstPage: first.result.data.items.length, nextPage: next.result.data.items.length, uniqueRendered: rendered.length };
  } finally { observation.restore(); mounted.dispose(); await chat.stop(); }
}

export async function runNativeChatListOwnerRace(session: SessionController, alternate: { email: string; password: string }): Promise<{ ownerChanged: true; oldResponseRejected: true }> {
  const owner = session.getSnapshot().context; assert(owner.state === 'authenticated', 'Actual original owner required.');
  const chat = new ChatController(session), observation = observeLists(session), mounted = mountShell(session, chat);
  const oldKey = `hine-list:${JSON.stringify([owner.user_id, owner.device_id])}:conversations`;
  try {
    await listReady(observation); const oldCache = localStorage.getItem(oldKey), gate = observation.arm();
    nativeShellDiagnostic.stage = 'successful_old_owner_A11_held_after_session_validation';
    window.dispatchEvent(new Event('hine-conversations-changed'));
    await within(gate.reached, 'Existing change event never requested the old-owner A11.');
    await session.logout(); await session.login(alternate.email, alternate.password); mounted.router.navigate('/chats', true);
    const current = session.getSnapshot().context; assert(current.state === 'authenticated' && current.user_id !== owner.user_id, 'Alternate credentials must identify a distinct real owner.');
    const newKey = `hine-list:${JSON.stringify([current.user_id, current.device_id])}:conversations`;
    await until(() => localStorage.getItem(newKey) !== null && !!document.querySelector('.chat-list') && !document.querySelector('.chat-list [role="status"]'), 'The alternate real owner A11 did not render.');
    const newCache = localStorage.getItem(newKey), newDom = document.querySelector('.chat-list .item-list')?.textContent;
    nativeShellDiagnostic.stage = 'release_successful_old_owner_A11_after_account_switch'; gate.release();
    await until(() => observation.active === 0, 'Held old-owner A11 never settled.');
    await new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
    assert(localStorage.getItem(oldKey) === oldCache, 'A no-longer-authorized A11 continuation still committed the old-owner cache.');
    assert(localStorage.getItem(newKey) === newCache && document.querySelector('.chat-list .item-list')?.textContent === newDom, 'A successful old-owner A11 leaked into the new-owner list or partition.');
    assert(!document.querySelector('.chat-list [role="alert"]'), 'A stale request failure polluted the alternate owner UI.');
    return { ownerChanged: true, oldResponseRejected: true };
  } finally { observation.restore(); mounted.dispose(); await chat.stop(); }
}

export interface NativeDeviceProof { userId: string; deviceId: string; conversationId: string; clientMessageId: string; marker: string }
async function verifyDevicePartition(session: SessionController, proof: NativeDeviceProof): Promise<void> {
  const owner = session.getSnapshot().context;
  assert(owner.state === 'authenticated' && owner.user_id === proof.userId && owner.device_id === proof.deviceId, 'Casefold-equivalent login lost the original actual server DeviceID.');
  const repository = new ChatRepository(owner.user_id, owner.device_id);
  try {
    const state = await repository.open();
    assert(state.drafts[proof.conversationId] === proof.marker, 'Original native draft partition became inaccessible.');
    const intent = state.intents[proof.clientMessageId];
    assert(intent?.conversationId === proof.conversationId && intent.status === 'unknown' && intent.payload.type === 'text' && intent.payload.text === proof.marker && intent.clientMessageId === proof.clientMessageId, 'Original native pending C1 partition was replaced or lost.');
  } finally { await repository.close(); }
}
export async function runNativeCasefoldDevicePartition(session: SessionController, ownerCredentials: { canonicalEmail: string; unseenEmail: string; password: string }, alternate: { email: string; password: string }): Promise<NativeDeviceProof> {
  // The parent must initially log in with the canonical spelling and must not
  // previously submit unseenEmail. Examples: strasse/straße, οσ/ος, office/oﬃce.
  const owner = session.getSnapshot().context; assert(owner.state === 'authenticated', 'Actual canonical initial login required.');
  const profile = (await session.request<UserProfile>('/users/me')).data;
  assert(profile.id === owner.user_id && profile.email === ownerCredentials.canonicalEmail, 'Canonical fixture must come from the unchanged Python auth authority.');
  const bindings = record(JSON.parse(localStorage.getItem('hine-device-store') ?? '{}')), aliases = record(bindings.aliases);
  assert(!Object.hasOwn(aliases, ownerCredentials.unseenEmail.toLowerCase()), 'The new spelling is already a saved legacy alias and would mask the regression.');
  const created = (await session.request<ConversationCreateResult>('/conversations/groups', { method: 'POST', idempotencyKey: crypto.randomUUID(), json: { title: 'native device partition fixture', member_ids: [] } })).data;
  const proof: NativeDeviceProof = { userId: owner.user_id, deviceId: owner.device_id, conversationId: created.id, clientMessageId: crypto.randomUUID(), marker: `native durable identity ${crypto.randomUUID()}` };
  const repository = new ChatRepository(owner.user_id, owner.device_id);
  try {
    await repository.open(); await repository.writeDraft(created.id, proof.marker, () => true);
    await repository.update(state => {
      state.intents[proof.clientMessageId] = { clientMessageId: proof.clientMessageId, conversationId: created.id, payload: { type: 'text', text: proof.marker }, createdAt: new Date().toISOString(), status: 'unknown', messageId: null, error: null, retryAt: null, authorizationVersion: created.membership_version, autoRetryStopped: true };
    });
  } finally { await repository.close(); }
  let submittedDevice: string | null | undefined; const originalFetch = window.fetch;
  window.fetch = new Proxy(originalFetch, {
    apply(target, thisArg, args) {
      const input: unknown = args[0], init: unknown = args[1], url = new URL(input instanceof Request ? input.url : String(input), location.href);
      if (url.pathname === `${new URL(session.config.API_BASE_URL).pathname}/auth/login` && init && typeof init === 'object' && 'body' in init && typeof init.body === 'string') {
        const body = record(JSON.parse(init.body)); if (body.email === ownerCredentials.unseenEmail) { assert(body.device_id === null || typeof body.device_id === 'string', 'Actual login device field malformed.'); submittedDevice = body.device_id; }
      }
      return Reflect.apply(target, thisArg, args);
    },
  });
  try {
    nativeShellDiagnostic.stage = 'actual_unseen_casefold_login';
    await session.logout(); await session.login(ownerCredentials.unseenEmail, ownerCredentials.password);
    assert(submittedDevice === proof.deviceId, 'The actual login sent null/new DeviceID for a never-saved fold-equivalent spelling.');
    assert(new DeviceStore().lookup(ownerCredentials.unseenEmail) === proof.deviceId, 'Reloaded native DeviceStore does not preserve the canonical server mapping.');
    await verifyDevicePartition(session, proof);
    nativeShellDiagnostic.stage = 'actual_alternate_owner_partition';
    await session.logout(); await session.login(alternate.email, alternate.password);
    const other = session.getSnapshot().context; assert(other.state === 'authenticated' && other.user_id !== proof.userId, 'Cross-owner fixture requires a distinct real account.');
    const otherRepository = new ChatRepository(other.user_id, other.device_id);
    try { const state = await otherRepository.open(); assert(state.drafts[proof.conversationId] === undefined && state.intents[proof.clientMessageId] === undefined, 'Original draft/outbox leaked into a different owner partition.'); }
    finally { await otherRepository.close(); }
    await session.logout(); await session.login(ownerCredentials.canonicalEmail, ownerCredentials.password); await verifyDevicePartition(session, proof);
    return proof;
  } finally { window.fetch = originalFetch; }
}
export async function verifyNativeDeviceIdentityAfterReload(session: SessionController, proof: NativeDeviceProof): Promise<{ nativeReloadPreserved: true }> {
  // Parent performs an actual top-level browser reload/new page and initializes a
  // fresh real SessionController before invoking this export with the token-free proof.
  nativeShellDiagnostic.stage = 'actual_browser_reload_original_device_partition';
  await verifyDevicePartition(session, proof);
  return { nativeReloadPreserved: true };
}
