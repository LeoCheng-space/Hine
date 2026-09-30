# HINE-IC-0.4 — Six Role PRDs

**Status:** Role ownership and acceptance specification, pending product approval. This document pairs with [the HINE-IC-0.4 shared interface contract](HINE-IC-0.4-contract.md), which is the sole source for field types, nullability, REST envelopes, WSS envelopes, error codes, and candidate limits. These are six role PRDs, one for each delivery role; this document does not claim implementation, deployment, product testing, or load-test results.

<a id="web-rwd"></a>
## Web / RWD 共用 UI 規格

### [CONFIRMED] Web delivery model and shared runtime

- HINE is one Web application used in desktop, tablet, and mobile browsers; this scope does not infer a native App or PWA.
- Frontend A and Frontend B are feature areas in the same Web project, not separate desktop/mobile clients. They share one SessionContext owner (FB), public REST API, WSS events/models, and one app-scoped WSS owner (FA).
- Responsive layout is presentation only: it does not create another login/session, socket, account SyncCursor, or business API. BA/BB do not expose duplicated desktop/mobile APIs or schemas.

### [PROPOSED] Responsive page and shared-component rules

This is one reviewable candidate layout, not an approved design. The width bands below are defined only here; all later references use the band names.

| Available Web viewport width | Layout band |
|---|---|
| `320 <= w < 768` CSS px | Narrow |
| `768 <= w < 1200` CSS px | Medium |
| `w >= 1200` CSS px | Wide |

Candidate UI-only routes are `/login`, `/register`, `/contacts`, `/chats`, `/chats/{conversation_id}`, `/profile`, and `/groups/{conversation_id}/manage`. They add no backend route or API. Login/register are public; protected routes wait for authorization and disclose no protected content before it. After login, return only to an authorized requested UI route. Browser back/forward restores the prior UI route/state; direct deep links and refresh enter the same guard/return flow. Image/file preview is an in-app surface opened from an authorized page, not a new route in this candidate.

| Page family | Narrow | Medium | Wide |
|---|---|---|---|
| Login and registration | One full-height, single-column form surface; form and submit action remain visible while scrolling. | Centered form surface with compact brand/header area and one-column fields. | Two columns: brand/information pane and readable-width form pane; form remains the primary action area. |
| Contacts/directory | One surface with header, search/filter, and full-height contact list; selecting a contact opens its detail as a drill-in with back action. | App navigation rail beside contacts content; selected contact details occupy a second content pane when selected. | App navigation, contacts list, and selected contact details are three persistent panes. |
| Chat list (`/chats`) | One surface with conversation list/search; selecting a conversation navigates to its thread. | App navigation rail plus chat list/content area; no empty third pane is required. | App navigation, conversation list, and thread are three panes once a conversation is selected. |
| Chat thread and composer | Thread is the sole content surface with explicit back-to-list action; composer stays above the virtual keyboard and within the visible viewport. | Chat list and thread are the two chat panes; composer is fixed to the thread's visible bottom. | Chat list and thread remain side by side; composer stays in the thread's visible bottom region. |
| Profile/avatar | One-column profile form with avatar preview and explicit save/cancel actions. | App navigation rail beside a centered, readable-width profile form with avatar preview. | App navigation and profile form; avatar preview/actions occupy a contextual side pane. |
| Group management | One section at a time in a single surface; section selection drills into details with back action and persistent save/cancel actions. | App navigation rail, group-management section list, and active section content in two work panes. | App navigation, section list, and active settings/member content are three panes. |
| Image/file preview | Full-screen viewer with top close/action bar; metadata/details open as a dismissible bottom sheet. | Viewer in the content area with collapsible details panel. | Centered constrained viewer with persistent metadata/details side panel. |

- **Shared forms and controls:** Every field has a programmatic and visible label. Validation messages identify the field and corrective action; invalid submission focuses the first invalid field. Submit, disabled, loading, success, empty, and error states are distinct. Empty/error surfaces offer an appropriate next action (for example, create/search, retry, or return). Toasts are non-blocking, announced accessibly, and never replace inline validation or critical recovery.
- **Touch, focus, and overlays [candidate]:** Minimum touch target is 44 CSS px, pending approval. On narrow, modal content uses an edge-to-edge sheet/dialog and navigation drawers use a full-height drawer; on medium/wide, dialogs are centered and navigation/context drawers are docked or side panels. A modal/drawer traps focus only while modal, Escape closes the topmost dismissible overlay, close returns focus to its trigger, and route changes place focus at the new page heading. Keep visible keyboard focus and logical tab order.
- **Content bounds:** Text uses `overflow-wrap:anywhere` where needed; media, metadata, and file names have `max-width:100%` and cannot widen the page or chat thread. Images remain inspectable within the viewer bounds; signed storage URLs are never displayed as UI text.
- **Navigation and return:** The listed route patterns are the candidate allowlist for Web-shell fallback. Keep browser history meaningful for route entry, chat selection, and preview open/close; do not intercept normal back/forward. This is UI routing only: no route change creates another login/session, WSS, SyncCursor, or business API.

### [PROPOSED] FA chat input, scroll, and read behavior

- Physical keyboard behavior is width-independent: Enter sends and Shift+Enter inserts a newline. With a soft keyboard, Enter inserts a newline and an explicit Send button submits. Set an IME-composing guard on `compositionstart`; suppress Enter-to-send while the guard or `event.isComposing` is true, and consume the Enter used to commit composition as composition input, not as send. Release the guard on `compositionend`; composition Enter MUST NOT submit.
- Track `visualViewport` height/offset so the composer remains visible above the virtual keyboard without losing draft, thread, or focus. Resizing/orientation preserves each conversation's draft and pending C1 state.
- Preserve the reading anchor as `message_id` plus its pixel offset through resize/orientation and when older history is prepended. Do not force scroll to bottom during history browsing. Auto-follow a new message only when the user is within a candidate 48 CSS px of the bottom; otherwise preserve position and show an unread count / Jump to latest action.
- W08 may be sent after durable local receipt independent of read state. Candidate W09 eligibility requires a visible browser, that conversation active, and the actual message intersecting at least 50% continuously for 500 ms. These visibility thresholds are proposed pending product/QA approval; thread open or W08 alone never establishes read.

### [PROPOSED] Web push scope

A23/A24 and `DeviceTokenStatus.platform` remain `ios|android`; they do not define browser subscription/provider payloads. Any Web Push provider, subscription lifecycle, permission, foreground suppression, and service-worker behavior require an explicit product/provider contract and approval. This PRD defines governance and acceptance only: do not ship fake browser-push behavior or infer native App/PWA support from the existing push-token API.

## Shared delivery rules

- IDs and interface names refer to the shared contract; do not introduce role-specific schema variants.
- Backend B/PostgreSQL is authoritative. Backend A Redis/Pub/Sub is ephemeral. Persisted ACK follows the complete message/C1/feed commit. Live events never advance the cursor; FE-A applies sync projection and candidate cursor atomically.
- Frontend B owns the only SessionContext and app route owner; Frontend A owns the only app-scoped WSS and chat surface. `openChat(conversation_id)` is provided by FA and called by FB.
- A03 refresh means FB publishes the fresh AccessSession, FA closes the old WSS, establishes a new WSS with W01/W02, reports initial W21, and resumes from saved cursor. A04 logs out the current device session and stops its socket.
- Every scenario below defines future acceptance behavior, not a test already executed. Numeric limits remain candidates unless separately approved.

## 1. Frontend A (FA) — Chat, real-time, and synchronization

**Purpose/boundary:** Own chat UI, app-scoped WSS, message state, and local sync projection. Provide `openChat(conversation_id)`. Do not own refresh cookies, issue JWTs, sign GCS URLs, or send push notifications.

### FA-01 — WSS session establishment and state
**Trace:** REQ-01, REQ-02, REQ-15; W01–W04, W17, W21.
- **Precondition:** FB supplies the current authenticated SessionContext (public user_id, device_id, access token, generation).
- **Normal flow:** Establish the unique WSS; send W01 as first business frame; validate W02 identity/device/generation; use W02 `heartbeat_interval_seconds` to schedule W03 and `heartbeat_timeout_seconds` to detect missing W04; after successful auth report initial W21.
- **Failure flow:** On W17, disconnect, expiry, or revoked session, stop sending business commands; ask FB to refresh/re-authenticate. Do not preserve a second socket as fallback.
- **Acceptance:** Route changes do not create another socket. A03 handoff causes a new socket, not same-socket authentication. A04 promptly tears down the current connection and clears account-local auth state.
- **Handoff:** SessionContext/authentication transition with FB; W01/W02 and session validation with BA/BB.

### FA-02 — Token refresh and logout teardown
**Trace:** REQ-02; A03/A04, W01/W02, W13–W17.
- **Precondition:** Existing WSS and saved user feed cursor.
- **Normal flow:** After FB publishes A03's new AccessSession, stop business frames on old socket, close it, open a new socket, send W01/receive W02, send W21, and resume from the saved cursor. On A04, close the socket and clear the current account's active projection.
- **Failure flow:** Refresh failure does not trigger same-socket W01; a disconnect retains any unconfirmed send's original C1.
- **Acceptance:** No same-socket reauthentication path; refresh uses a new connection and saved cursor, while logout tears down current-account realtime state.
- **Handoff:** Connection replacement state machine with FB; authentication/session enforcement with BA; lifecycle scenarios with QA.

### FA-03 — Realtime send and persisted ACK
**Trace:** REQ-06, REQ-07; W05–W07, W17.
- **Precondition:** Authorized conversation and authenticated socket.
- **Normal flow:** Persist a pending local send with stable C1; issue W05; merge W06 and sender W07 into the same visible message M1.
- **Failure flow:** On lost ACK, disconnect, or OUTCOME_UNCONFIRMED, keep and retry the original C1 and payload. A different payload with the same C1 surfaces conflict; never silently mint a replacement C1 for the same intent.
- **Acceptance:** Same C1 yields one visible/persisted M1; `persisted` is not rendered as delivered/read. ACK can arrive before or after W07 without duplication. A known rollback is not shown as success.
- **Handoff:** W05–W07 sequencing with BA; atomic persistence result with BB; failure scenarios with QA.

### FA-04 — Delivery and read receipts
**Trace:** REQ-12; W08–W10, W19, W16.
- **Precondition:** Authorized message is durably stored locally; actual read occurs before marking read.
- **Normal flow:** Send W08 after durable receipt; send W09 only after user views message; reconcile W19 and W10.
- **Failure flow:** Repeated receipt is idempotent; delayed older status does not move read backward. On reconnect, sync restores status.
- **Acceptance:** Client never reports read merely because a message arrived; `read` is monotonic and implies delivered. Receipt status can recover when no new message is sent.
- **Handoff:** W08/W09 transition to BA and canonical receipt with BB.

### FA-05 — Chat navigation, history, bootstrap, and synchronization
**Trace:** REQ-04 and REQ-08–REQ-11; A12, A19, `openChat`, W07, W11–W17.
- **Precondition:** FB routes an authorized conversation ID to FA, or the authenticated client has a saved feed cursor/first-login state.
- **Normal flow:** Provide `openChat(conversation_id)` for FB to call; mount/switch chat UI, obtain detail with A12, and load newest-to-oldest history with A19. Separately request W13/W14 snapshot, stage all pages for one snapshot_id, merge concurrently received live items, atomically switch the local projection, and only then install start_cursor. Use W15/W16 for reconnect, foreground, and reconciliation; use A19 for older history outside snapshot window.
- **Failure flow:** A12 denial removes inaccessible view. A19 cursor failure restarts only its history query and never invokes W13. Never save start_cursor after partial pages; retain already observed live E41/C1 through snapshot switch; advance W16 cursor only with atomically applied projection. A WSS feed reset requests fresh W13; revoked content stays filtered without blocking other feed rows.
- **Acceptance:** FB owns routing and calls FA's `openChat`; FA owns chat display and uses one app-scoped socket. History/list cursors remain local; no gap across H, no duplicate after merging live and snapshot data, and no unauthorized post-revocation body. Responsive chat layout follows the [central Web/RWD chapter](#web-rwd).
- **Handoff:** `openChat` and detail/history with FB/BB; W13–W16 safe scan and projection barrier with BA/BB; cursor atomicity and recovery with QA.

### FA-06 — Conversation attachments, renewal, and downloads
**Trace:** REQ-13; A20–A22, A25, W05/W07.
- **Precondition:** Current authorization for conversation and selected supported file.
- **Normal flow:** A20 with `scope=conversation`, upload bytes to signed URL, A21 complete, then send attachment W05. Obtain a short-lived URL through A22 for permitted display/download.
- **Failure flow:** An expired URL uses A25 with a new idempotency key; old attempt cannot complete. Hash/type/size mismatch or lost authorization blocks use; do not send an unready attachment.
- **Acceptance:** Binary bytes do not travel over WSS. Message uses the same C1/ACK/sync guarantees as text. No signed URL is placed in messages or logs; current conversation permission is rechecked on download. Responsive image/file preview follows the central Web/RWD chapter.
- **Handoff:** Grant/metadata lifecycle with BB; transfer and runtime config with DevOps.

### FA-07 — App activity and lease renewal
**Trace:** REQ-14, REQ-15; W02, W18, W21/W22, W15/W16.
- **Precondition:** W02 accepted the active device/session generation.
- **Normal flow:** Report initial W21 after W02; report foreground/background transition; renew before W22 valid_until; reconcile feed when returning foreground.
- **Failure flow:** Lost background frame, expired lease, or Redis uncertainty is shown as unknown, not foreground. Ignore late activity acknowledgements for an older session generation.
- **Acceptance:** Backend can decide push eligibility per device; heartbeat is not foreground state; opening app triggers normal authorized sync.
- **Handoff:** App lifecycle lease to BA; FB provides generation/token updates; BB consumes per-device state for push.

### FA-08 — Responsive Web chat interaction
**Trace:** REQ-19/20; shared UI chapter, A12, A19, W08/W09.
- **Precondition:** Authenticated Web session, available chat route, and one app-scoped WSS.
- **Normal flow:** Apply the shared Web/RWD chat behavior. On a narrow layout, conversation-list selection opens a thread with a back action. Preserve per-conversation draft, pending C1, and read position through resize/orientation. Keep the composer usable with a virtual keyboard; wide keyboard sends with Enter/newline with Shift+Enter, narrow layout offers explicit send. IME composition Enter MUST NOT send. Keep history browsing position, constrain long content/media/file names, and send W09 only for actually visible content in an active, visible browser.
- **Failure flow:** Layout changes never log in again, open another WSS, or change/reset the SyncCursor. W08 may be sent after durable local receipt without sending W09. If visibility state is uncertain, do not infer that a message was read.
- **Acceptance:** Interaction follows the single shared UI chapter; C1 pending state and read position survive reflow; W08 and W09 remain distinct. Visibility threshold/dwell time for W09 are proposed and require product/QA approval.
- **Handoff:** Shared UI decisions and `openChat` with FB; W08/W09/read model with BA/BB; browser input/visibility cases with QA.

## 2. Frontend B (FB) — Authentication, contacts, routing, and push token

**Purpose/boundary:** Sole frontend SessionContext, auth-cookie, profile/contact/group-entry, push-token, and top-level route owner. Calls FA `openChat`. Does not own `subject_id`, create another WSS, or redefine wire format.

### FB-01 — Registration, login, and device binding
**Trace:** REQ-01; A01/A02, W01/W02.
- **Precondition:** Logged out; DeviceStore may have a DeviceID for this same account or none on a new install.
- **Normal flow:** A01 registers and returns UserProfile only. A02 sends the same-account DeviceStore DeviceID when present, or `device_id:null` for first-install issuance; save the returned DeviceID back to that account's DeviceStore and keep the returned AccessSession/refresh cookie in FB-owned session state, then give FA the authenticated context. Logout clears SessionContext, not the separate installation-scoped DeviceStore.
- **Failure flow:** If the stored ID is lost or the server refuses reuse, adopt returned server DeviceID. DeviceID is not authentication; errors and login throttling are surfaced without account enumeration.
- **Acceptance:** A02 user_id, W02 user_id, and A05 UserProfile.id agree as the public identity; A02 AccessSession device_id/generation match W02. The logged_out SessionContext remains all-null while DeviceStore is separate. Internal subject_id never enters SessionContext.
- **Handoff:** AccessSession to FA; account/session/device binding with BB/BA.

### FB-02 — Refresh and logout
**Trace:** REQ-02; A03/A04, FA handoff, W01/W02/W21.
- **Precondition:** Current authenticated SessionContext.
- **Normal flow:** A03 refreshes cookie and publishes new access session/generation to FA; A04 completes, clears current device auth, and tells FA to stop WSS.
- **Failure flow:** If refresh fails, require re-login and do not let FA use stale credentials. Resolve A03/A04 race according to Backend B session result.
- **Acceptance:** Refresh always replaces old socket and uses saved cursor; logout revokes current device and push binding under proposal and does not log out unrelated devices.
- **Handoff:** New generation and teardown ordering to FA/BA; serialized session outcome with BB.

### FB-03 — Profile and avatar, including zero-conversation account
**Trace:** REQ-03; A05/A06/A20–A22/A25.
- **Precondition:** Logged-in owner; no conversation is required.
- **Normal flow:** Read/update profile; upload avatar with A20 `scope=avatar,conversation_id:null`, transfer, complete A21, assign ready attachment through A06; retrieve with A22.
- **Failure flow:** Renew an expired grant through A25/new key. Do not assign an unready or non-owned attachment. Null avatar assignment removes it.
- **Acceptance:** Avatar upload and display work for an account with no chats; private email stays self-only; attachment URL is short-lived. The responsive profile/avatar surface follows the central Web/RWD chapter.
- **Handoff:** Profile/attachment authorization with BB, transfer setup with DevOps.

### FB-04 — Contacts, directory, and local cursor recovery
**Trace:** REQ-03; A07–A10.
- **Precondition:** Authenticated user.
- **Normal flow:** Find authorized summaries, page contacts, add/remove contact, display explicit online/offline/unknown presence.
- **Failure flow:** A08 REST cursor error refetches only first contacts page; it does not request W13 or clear FA feed. Unknown presence is shown as unknown.
- **Acceptance:** No email disclosure through summaries; duplicate add does not create duplicate contacts; removal does not delete conversation history. Responsive contacts/directory layout follows the central Web/RWD chapter.
- **Handoff:** Contact projection/authorization with BB; ephemeral presence with BA/FA.

### FB-05 — Conversation navigation and group management
**Trace:** REQ-04, REQ-05, REQ-11; A11–A18, W11/W12/W20, `openChat`.
- **Precondition:** Authenticated user; admin-only actions require current admin authorization.
- **Normal flow:** List/direct-create/group-create/update members through REST. For opening a chat, FB updates app route and calls FA-provided `openChat`. REST caller updates its own successful operation; other devices consume post-commit events.
- **Failure flow:** A11 REST cursor error restarts only the conversation list. Membership version gap is reconciled by A12. On own removal, clear group route after A18 success/minimal W12.
- **Acceptance:** A14/A16→W11, A15/A17→W20, A18→W12. No ban endpoint or behavior. Unauthorized member cannot continue to fetch detail/history/content; responsive group controls follow the central Web/RWD chapter.
- **Handoff:** REST group operation to BB; group event distribution to FA; route interface to FA.

### FB-06 — Push-token registration and cleanup
**Trace:** REQ-14; A02/A04/A23/A24.
- **Precondition:** Authenticated device and OS notification permission/provider token.
- **Normal flow:** Register/update token for AccessSession.device_id with A23; revoke with A24 when disabled.
- **Failure flow:** Do not expose token in UI/logs. A04 current-device logout removes its binding per proposal; other devices remain registered.
- **Acceptance:** Token registration is bound to current account/device; push is only a hint and opening it invokes normal authenticated sync.
- **Handoff:** Device/session checks and token storage with BB; lifecycle/activity from FA/BA.

### FB-07 — Responsive Web shell, non-chat pages, and route return
**Trace:** REQ-19/21; shared UI chapter, A01–A18, `openChat`.
- **Precondition:** One Web build shared by FA and FB; routes and existing auth state are available.
- **Normal flow:** Apply the shared shell/layout to registration/login, contacts/directory, profile/avatar, and group management. Own browser history, protected route guard, deep-link route entry, post-login return, and call FA's `openChat` for chat content.
- **Failure flow:** Unauthenticated/unauthorized deep links do not render protected data; login returns only to the authorized requested route. Reflow does not create another session or WSS. Preserve existing API/event/model contracts across layouts.
- **Acceptance:** Browser navigation and responsive non-chat pages share one SessionContext/router policy; FA remains chat UI owner. Use the central shared UI chapter without restating its viewport bands.
- **Handoff:** Route and login-return behavior with FA; authorization with BB; browser route/fallback with DO; matrix cases with QA.

## 3. Backend A (BA) — Realtime messaging service

**Purpose/boundary:** WSS handshake, connection/heartbeat, ephemeral Redis/presence, activity leases, event routing, and sync ingress. Backend B owns JWT/session authority, authorization decisions, durable state, and PostgreSQL schema. Browser layout does not create a separate realtime API, event model, connection, or cursor.

### BA-01 — WSS authentication and session termination
**Trace:** REQ-01/02; W01/W02/W17, `validateAccess`.
- **Precondition:** New WSS connection.
- **Normal flow:** Require W01 first; validate token with BB, verify W01 device binding, return W02 public user/device/session generation and configured heartbeat values.
- **Failure flow:** Reject expired, revoked, wrong-device, or stale-generation session; stop new operations and close old socket when A03/A04 revocation takes effect. W17 may be sent before close but is not guaranteed.
- **Acceptance:** Never trust client subject_id; successful refreshed auth uses a new connection; a single device failure does not revoke other devices.
- **Handoff:** `validateAccess`/session state with BB; session replacement notification with FA/FB.

### BA-02 — Heartbeat and user-level presence
**Trace:** REQ-15; W03/W04/W18, `getDevicePresence`.
- **Precondition:** Authenticated socket.
- **Normal flow:** W03/W04 track connection liveness. Aggregate valid user connections for W18 online transitions; query device/activity separately.
- **Failure flow:** Heartbeat timeout clears that socket only. Redis unavailable means presence unknown, not offline/online certainty.
- **Acceptance:** Presence describes aggregate connectivity and never implies app foreground or message receipt.
- **Handoff:** Presence query with BB and display with FA/FB.

### BA-03 — Message ingress and persisted ACK
**Trace:** REQ-06/07; W05–W07/W17, `authorize`, `persistIfAbsent`.
- **Precondition:** Authenticated principal, authorized conversation, valid message C1.
- **Normal flow:** Validate type/content, authorize, call transactional persistence; emit W06 only after complete persisted result; route W07 to authorized recipients.
- **Failure flow:** Known rollback yields no successful ACK; unknown result is OUTCOME_UNCONFIRMED; lost ACK is recovered by same C1. Redis publication failure is recoverable through W16.
- **Acceptance:** The ACK never precedes message+C1 mapping+required feeds commit. Same C1 maps to same M1/event; changed payload conflicts.
- **Handoff:** Persistence transaction output and recipient list with BB; UI retry/merge with FA/QA.

### BA-04 — Delivery/read receipt forwarding
**Trace:** REQ-12; W08–W10/W19, `persistReceipt`.
- **Precondition:** Authenticated device and authorized message recipient.
- **Normal flow:** Persist monotonic receipt through BB; correlate W19 to requesting W08/W09; fan out W10 to permitted observers and allow feed recovery.
- **Failure flow:** Reject spoofed/unrelated receipt; duplicate reports are no-ops; `read` cannot regress.
- **Acceptance:** W19 request result is distinct from W10 projection; canonical state is BB.
- **Handoff:** Receipt projection/audience with BB and FA.

### BA-05 — Cross-node fanout and group event routing
**Trace:** REQ-05/08/11; W07/W11/W12/W20.
- **Precondition:** BB transaction committed message or membership change.
- **Normal flow:** Redis Pub/Sub accelerates event delivery to currently authorized sockets; preserve recipient-specific event identity.
- **Failure flow:** Lost publication is repaired through W16. Recheck authorization at delivery; revoked member receives only own minimal W12 and no later body.
- **Acceptance:** Group mutation event mapping is exact; ephemeral broker data is never treated as durable success.
- **Handoff:** Committed membership/feed rows with BB; inter-node behavior with DevOps.

### BA-06 — Bootstrap and feed sync ingress
**Trace:** REQ-09–REQ-11; W13–W17, `readBootstrap`, `readFeed`.
- **Precondition:** Valid authenticated principal.
- **Normal flow:** W13/W14 proxy consistent snapshot pages; W15/W16 proxy pinned safe feed batches.
- **Failure flow:** Expired user SyncCursor returns W17 SYNC_RESET_REQUIRED. Do not reset for A08/A11/A19 REST cursors. A page sequence with incomplete snapshot must not claim start cursor installed.
- **Acceptance:** Hidden positions can safely advance; unauthorized content is filtered; one revoked conversation cannot stall the rest of the feed.
- **Handoff:** Read contracts and auth-filtered event rows with BB; cursor commit protocol with FA/QA.

### BA-07 — Device activity leases
**Trace:** REQ-14/15; W21/W22, `recordActivity`, `getDevicePresence`.
- **Precondition:** W02 accepted active session and device.
- **Normal flow:** Verify W21 device and generation; record current foreground/background state; reply W22 with server validity deadline. Expose device-level query to BB.
- **Failure flow:** Reject stale session generation; duplicate state report is idempotent; Redis failure/expiry yields unknown.
- **Acceptance:** Activity never grants chat permission, is not heartbeat, and can safely inform per-device push audience.
- **Handoff:** W21/W22 lifecycle with FA; push decision with BB.

### BA-08 — Rate limiting, frame defense, and WSS errors
**Trace:** REQ-16; W17 and shared candidate limits.
- **Precondition:** Any unauthenticated/authenticated frame.
- **Normal flow:** Enforce approved limits and frame constraints; emit shared W17 code/message/retryable/correlation shape.
- **Failure flow:** Bound per-socket output for slow consumers; on disconnected socket do not claim error was delivered; never log token or body.
- **Acceptance:** No successful outcome is fabricated; all eventual numeric limits remain configurable and unapproved until PM/QA decision.
- **Handoff:** Security/error fields with QA and operational settings with DevOps.

## 4. Backend B (BB) — REST API and database

**Purpose/boundary:** A01–A25, account/session authority, PostgreSQL canonical state, object metadata/GCS grants, durable feed and push intents. Does not own client sockets and does not use Redis as message storage. All browser layouts use the same REST contracts, models, authorization, and durable feeds; do not duplicate business APIs by device form factor.

### BB-01 — Accounts, session, and device identity
**Trace:** REQ-01/02; A01–A04, AccessSession, internal `validateAccess`.
- **Precondition:** Registration/login/refresh/logout request.
- **Normal flow:** Persist account credentials safely; authenticate A02; bind or issue device_id; issue AccessSession; advance session generation on A03; revoke current device/session on A04.
- **Failure flow:** Serialize refresh/logout race; stale/revoked cookie cannot issue a still-valid socket session. Device ID alone cannot authenticate or cross-bind another user.
- **Acceptance:** A05 `UserProfile.id` equals only the public `user_id` in the current A02/A03 AccessSession and W02. Compare `device_id` and `session_generation` strictly between the matching A02/A03 AccessSession and W02; A05 has neither field. Never expose `subject_id`.
- **Handoff:** AccessSession to FB; session validation to BA.

### BB-02 — Profiles and contacts
**Trace:** REQ-03; A05–A10, UserProfile/UserSummary/ContactView.
- **Precondition:** Authenticated caller and relevant user/contact authorization.
- **Normal flow:** Maintain own profile/contacts, return distinct self Profile vs public Summary, require ready own avatar on A06.
- **Failure flow:** Prevent email or hidden avatar disclosure; report unknown transient presence as unknown; invalid list cursor affects only its REST query.
- **Acceptance:** Required projection fields/nullability match common dictionary; contact duplicate does not duplicate row; removal does not erase conversation data.
- **Handoff:** Profile/contact responses to FB; summaries to FA; ephemeral presence via BA.

### BB-03 — Conversations, groups, and authorization
**Trace:** REQ-04/05/11; A11–A18 and W11/W12/W20.
- **Precondition:** Current member/admin/self-leave policy for requested operation.
- **Normal flow:** Read direct/group projections; create unique direct conversation; transact membership/title/role and required feed updates.
- **Failure flow:** Reject unauthorized operation, protect last-admin invariant, enforce post-removal authorization on history/download and future feed. No ban state/operation.
- **Acceptance:** A14/A16 emit W11, A15/A17 W20, A18 W12. Membership version and REST response correspond to committed state; feed mutation is committed before Pub/Sub.
- **Handoff:** REST projection to FB; committed events to BA/FA; policy decisions to PM.

### BB-04 — Transactional messages, idempotency, and durable push intent
**Trace:** REQ-06–REQ-08/14; `persistIfAbsent`, W05–W07.
- **Precondition:** Authorized sender, message shape, stable C1.
- **Normal flow:** Transactionally write canonical message, C1 mapping, every required per-user feed row, and eligible per-device push intent. Return `created` or `existing_same` with persisted result.
- **Failure flow:** Different payload under same C1 is conflict; distinguish known rollback from uncertain outcome; never write successful ACK evidence before required rows commit.
- **Acceptance:** Retried send produces same M1 and stable event ID; push provider failure cannot alter message/receipt state.
- **Handoff:** Transaction contract with BA; C1 merge with FA; fault outcomes with QA.

### BB-05 — History and receipt authority
**Trace:** REQ-09/12; A19, W08–W10/W19, `persistReceipt`.
- **Precondition:** Current permission to read message/history or report receipt.
- **Normal flow:** Query history by separate history cursor; persist delivery/read monotonically; include old-message status corrections in feed/bootstrap projection.
- **Failure flow:** A19 cursor error affects only that history view; authorization loss blocks further content. Duplicate receipt does not create redundant status event.
- **Acceptance:** Same canonical message ID appears in live, history, and sync; A19 order is independent of user feed cursor.
- **Handoff:** Message/receipt projection to FA/BA.

### BB-06 — Snapshot and durable user feed
**Trace:** REQ-09–REQ-11; `readBootstrap`, `readFeed`, W13–W16.
- **Precondition:** Authenticated subject and supported snapshot/feed cursor.
- **Normal flow:** Read authorized snapshot content and H from one consistent view; paginate by same snapshot id; scan per-user feed in safe committed order with pinned continuation boundary.
- **Failure flow:** Snapshot expiry creates a fresh consistent snapshot; do not install H before all pages and local switch. Filter revoked body while allowing safe advancement and other conversation rows.
- **Acceptance:** The agreed bounded bootstrap scope and current state at H are represented by the completed snapshot; later durable feed positions remain accessible through W16, and older authorized history remains available through A19. REST cursor errors do not reset the feed.
- **Handoff:** Sync read semantics with BA and cursor application with FA/QA.

### BB-07 — Attachments, avatars, and signed transfer
**Trace:** REQ-03/13; A06, A20–A22, A25.
- **Precondition:** Owner and valid scope; conversation authorization where applicable.
- **Normal flow:** Store metadata, create short-lived GCS upload/download grant, verify bytes and hash on completion, permit ready attachment use; renewal preserves attachment ID and creates current attempt.
- **Failure flow:** Reject old attempts, wrong metadata/type/size and unauthorized downloads. Avatar scope must have null conversation_id and work without a chat.
- **Acceptance:** A22 reauthorizes each retrieval; signed URL and GCS object key remain private; failed upload does not become ready.
- **Handoff:** Transfer and metadata contract with FE-A/FE-B; bucket and secret config with DevOps.

### BB-08 — Push token store and background dispatch
**Trace:** REQ-14; A23/A24, `getDevicePresence`, `dispatchPushIntent`.
- **Precondition:** Valid bound device token and committed eligible message.
- **Normal flow:** Store token securely; after durable commit evaluate each recipient device activity; suppress fresh foreground, send generic hint for background/unknown.
- **Failure flow:** Provider failure retries durable intent; permanent invalid token retires binding. A04 current-device logout revokes binding per proposal. No message body in push; no receipt mutation.
- **Acceptance:** Push is a hint, not delivery/read evidence; opening notification gets authorized content through sync. A23/A24 remain the iOS/android token contract; browser push has no subscription/provider schema here and is pending the Web-push policy/contract decision, not an implied implementation.
- **Handoff:** Activity state to BA; token workflow to FB; credentials/monitoring to DevOps.

## 5. DevOps (DO) — Infrastructure and delivery

**Purpose/boundary:** Provide the specified host routing, configuration/secret bindings, delivery pipeline, monitoring, and repeatable verification environment. GCP compute architecture is not selected; do not assume Kubernetes.

### DO-01 — Domain, TLS, ingress, and routes
**Trace:** REQ-17; REST/WSS base routes and internal health paths.
- **Precondition:** Approved domain and target environment.
- **Normal flow:** Route public HTTPS REST `/api/v1` and WSS `/ws/v1` under `hine.run.place`; keep probes internal.
- **Failure flow:** TLS, routing, or required dependency failure prevents readiness/deployment acceptance.
- **Acceptance:** Single public contract; internal health is not exposed as user API. Web-shell refresh fallback is limited to approved UI paths and preserves API/WSS routes.
- **Handoff:** Required ports/health behavior with BA/BB; smoke specification with QA.

### DO-02 — Typed environment and secret management
**Trace:** REQ-17; contract §6 setting names.
- **Precondition:** Approved environment inventory and least-privilege ownership.
- **Normal flow:** Inject typed config and secret references per service/environment; only BB receives JWT signing authority; protect GCS and push provider credentials.
- **Failure flow:** Missing required config fails closed or readiness; never substitute fake credentials or log secret material.
- **Acceptance:** Each setting has service owner, sensitivity, requirement, and missing-value behavior. Secret values do not enter PRDs/logs.
- **Handoff:** Required config with BA/BB; test-matrix with QA.

### DO-03 — GitHub Actions delivery
**Trace:** REQ-17; GitHub Actions.
- **Precondition:** Approved quality gates and controlled deployment environment.
- **Normal flow:** PR checks → controlled test deployment → health/REST/WSS smoke → authorized production promotion with recoverable version.
- **Failure flow:** Missing config or failed check stops promotion and retains traceable artifact/version.
- **Acceptance:** GitHub Actions is the CI/CD baseline (not GitLab); pipeline specification identifies inputs, outputs, approvals, and rollback artifact. This PRD does not claim it is implemented.
- **Handoff:** Build/runtime requirements across six roles.

### DO-04 — Health, monitoring, alerting, and log privacy
**Trace:** REQ-16/17; HealthResponse and `/health/live`/`/health/ready`.
- **Precondition:** BA/BB expose health and non-sensitive metrics.
- **Normal flow:** Distinguish liveness from dependency readiness; monitor ACK, live delivery, recovery, activity expiry, and push failures.
- **Failure flow:** Missing config reason is diagnosable (e.g. CONFIG_MISSING) without exposing secrets, body, token, or high-cardinality public user-ID labels.
- **Acceptance:** Dependency failure returns unready/503; logs and metric labels remain privacy-safe.
- **Handoff:** Health dependencies with BA/BB; alert thresholds and acceptance with QA.

### DO-05 — Reproducible performance-verification environment
**Trace:** REQ-18; approved operational configuration.
- **Precondition:** QA workload and PM thresholds are specified.
- **Normal flow:** Record software version, compute/resource, network, DB pool, Redis, and config references needed to reproduce a run.
- **Failure flow:** Incomparable environments do not share capacity conclusions; untested scale is never reported passed.
- **Acceptance:** Environment description is sufficient to reproduce future measurements; no performance result is claimed in this spec.
- **Handoff:** Environment record to QA.

### DO-06 — Web assets and protected deep-route fallback
**Trace:** REQ-21; Web UI route inventory, auth-guard/route-return behavior, `/api/v1`, `/ws/v1`.
- **Precondition:** Approved Web asset build and known UI route namespace.
- **Normal flow:** Serve the same Web project assets and allow refresh/deep-link fallback only for the listed candidate UI route patterns: `/login`, `/register`, `/contacts`, `/chats`, `/chats/{conversation_id}`, `/profile`, and `/groups/{conversation_id}/manage`. Retain `/api/v1` REST and `/ws/v1` WSS routing as separate backend routes.
- **Failure flow:** Never rewrite `/api/v1` or `/ws/v1` paths or failures to the Web shell. Unknown UI routes show controlled not-found state; protected routes wait for authorization and do not disclose content.
- **Acceptance:** Refresh/direct navigation to each listed UI route reaches the same auth guard and authorized route return; the Web-shell fallback is restricted to those UI route patterns, and API/WSS paths and status behavior remain unchanged.
- **Handoff:** Route namespace with FB; origin/ingress rules with BA/BB; deep-link matrix with QA.

## 6. QA — Test and acceptance

**Purpose/boundary:** Define behavior, schema, privacy, recovery, and performance acceptance. Only run product tests once an implementation and approved test environment exist; this PRD records no test execution.

### QA-01 — Interface contract and schema compliance
**Trace:** REQ-01–REQ-06 and A01–A25/W01–W22.
- **Precondition:** One version of common dictionary, endpoint/event registry, and sample payloads.
- **Normal flow:** Validate required fields, nullability, method/path, response status, correlation, authorization, and event mapping.
- **Failure flow:** Missing/extra wrong-state fields, wrong event mapping, summary used in place of detail, or leaked subject_id are contract failures.
- **Acceptance:** Every consumer references the shared contract and the central Web/RWD chapter; no role duplicates its layout bands or creates platform-specific business schemas.
- **Handoff:** Schema/report findings to FA/FB/BA/BB.

### QA-02 — Session, refresh, activity, and multi-device behavior
**Trace:** REQ-01/02/14/15; A02–A04, W01/W02/W21/W22.
- **Precondition:** Valid account, two device sessions, controllable socket lifecycle.
- **Normal flow:** Verify login/session binding; refresh, close old socket, create new W01/W02, send first W21, and resume saved cursor; exercise background/foreground and lease renewal.
- **Failure flow:** Exercise refresh/logout race, old-generation late activity, missed background frame, lease expiry, and Redis uncertainty.
- **Acceptance:** No same-socket reauthentication; stale session cannot resume; lease expiry becomes unknown; failure of one device does not log out another.
- **Handoff:** State transition cases to FB/FA/BA/BB.

### QA-03 — Snapshot/feed recovery and cursor isolation
**Trace:** REQ-09–REQ-11; A08/A11/A19 and W13–W17.
- **Precondition:** Multi-page snapshot with one snapshot_id and independent REST list/history cursors.
- **Normal flow:** Ensure intermediate page does not install H; after all staged pages and atomic local switch, install H and continue feed. Exercise hidden filtered positions.
- **Failure flow:** Expire each REST cursor independently, then expire user feed cursor.
- **Acceptance:** Each A08/A11/A19 failure refetches only its own query; only WSS feed reset triggers W13. No missed authorized event or unauthorized body; a revoked conversation does not block another.
- **Handoff:** Cursor boundaries and expected local state to FA/FB/BA/BB.

### QA-04 — Cross-module behavior and failure injection
**Trace:** REQ-03–REQ-08, REQ-12–REQ-14; A01–A25/W05–W22.
- **Precondition:** Isolated users, conversations, attachment storage, and push provider test setup.
- **Normal flow:** Exercise zero-conversation avatar, A25 renewal, group A14–A18 mappings, ACK recovery, receipt recovery, background hint, and return-to-app sync.
- **Failure flow:** Inject known rollback, commit-before-ACK loss, ACK-before-publication interruption, stale upload attempt, wrong MIME, revoked membership, and provider failure.
- **Acceptance:** Original C1 recovers one M1; complete commit precedes ACK; A14/A16→W11, A15/A17→W20, A18→W12; provider errors do not alter receipts.
- **Handoff:** Reproducible failure checkpoints with FA/BA/BB.

### QA-05 — Privacy, configuration, and performance acceptance
**Trace:** REQ-16–REQ-18; common errors, health, metrics, and approved limits.
- **Precondition:** PM-approved operating values/workload and isolated credentials.
- **Normal flow:** Validate missing-config/readiness response, privacy-safe logs, and independently measured ACK, end-to-end delivery, reconnect, sync recovery, and feed contention.
- **Failure flow:** Reject secret/body leakage, false healthy state, and untested scale claims. Keep unapproved historical SLOs out of pass/fail criteria.
- **Acceptance:** Results state exact environment/workload; no capacity claim without measurement. No product test or performance result is asserted by these PRDs.
- **Handoff:** Findings to PM, DevOps, BA, BB.

### QA-06 — Web responsive, input, route, and push-policy acceptance
**Trace:** REQ-19–REQ-22; shared UI chapter, W08/W09, A23/A24 and existing route/session behavior.
- **Precondition:** One shared Web build, candidate-supported browsers, controllable viewport/input/orientation, test accounts, and proposed acceptance criteria.
- **Normal flow:** Run browser/version × sample viewport × orientation × zoom cases, using mouse/touch and physical/virtual keyboard plus Chinese IME on applicable controls. Sample viewports are 320, 375, 767, 768, 1024, 1199, 1200, and 1440 CSS px (test sizes, not breakpoint definitions); include portrait/landscape, 200% zoom, all page families and candidate UI deep links/auth return. Exercise composer visibility, anchor preservation through orientation/history prepend, candidate auto-follow/read visibility thresholds, and browser-push scope as governance only. Browser/version selections are candidates pending product/QA approval and must be recorded.
- **Failure flow:** Verify no second WSS/session/cursor on reflow, no IME accidental send, no forced history scroll, no W09 without the candidate actual-visibility conditions, no protected data before authorization, and no API/WSS path handled by Web-shell fallback. Do not infer browser push from A23/A24 or native App/PWA behavior.
- **Acceptance:** Record browser/version, viewport/orientation/zoom, input modality, route, and observed layout/state per case. Distinguish proposed layout and interaction thresholds from approved behavior; W08 remains independent of W09, and REQ-22 remains a browser-push approval/contract prerequisite. No product test result is asserted here.
- **Handoff:** Browser/width/input/state findings and policy prerequisites to FA/FB/DO/BA/BB and PM.

## 7. Cross-module REQ acceptance and ownership matrix

Rows describe observable future acceptance. Primary owner precedes collaborators.

| Requirement | Primary / collaborators | Interfaces | Acceptance summary |
|---|---|---|---|
| REQ-01 Account verification and login identity | FB / BB, BA, FA, QA | A01/A02, W01/W02 | First-device login binds server device; A02, W02, A05 public user identity agrees; internal subject_id stays server-side. |
| REQ-02 Credential refresh and logout transition | FB / FA, BB, BA, QA | A03/A04, W01/W02/W21 | Refresh closes old WSS, opens new one, sends initial activity, resumes saved cursor; logout stops current device and has no same-socket reauth. |
| REQ-03 Profile, avatar, and contacts | FB / BB, FA, DevOps | A05–A10, A20–A22, A25 | A zero-conversation account can upload/assign/read avatar; contact cursors recover locally; no email/avatar disclosure beyond policy. |
| REQ-04 Direct-chat navigation and creation | FB / FA, BB | A11–A13, `openChat` | Repeated direct creation returns the unique pair conversation; FB routes to FA chat without another socket. |
| REQ-05 Group management, permissions, and membership changes | BB / FB, BA, FA | A14–A18, W11/W12/W20 | Exact mapping A14/A16→W11, A15/A17→W20, A18→W12; unauthorized actions/content blocked. |
| REQ-06 Text messaging and durable ACK | BA / BB, FA | W05–W07, A19 | ACK follows complete transaction; sender and recipient converge on same M1; message appears in history. |
| REQ-07 Lost ACK, retry, and deduplication | BB / BA, FA, QA | W05–W07, W17 | Known rollback has no success ACK; committed-but-unacknowledged send retries same C1 and returns same M1; changed content conflicts. |
| REQ-08 Cross-node live broadcast and missed-delivery recovery | BA / BB, FA, DevOps | W07, W15/W16 | Dropped Pub/Sub notice is recovered by feed reconciliation; UI displays one message. |
| REQ-09 First login, authorized snapshot, and history separation | BB / BA, FA, QA | W13–W16, A19 | Multi-page same-snapshot bootstrap installs H only after complete projection; the agreed bounded bootstrap scope/current state at H is represented, >H feed positions are accessible, and older authorized history remains A19. |
| REQ-10 Snapshot switch and live projection merge | FA / BA, BB | W07, W13–W16 | Concurrently observed C1/event survives switch; candidate cursor advances only atomically with projection. |
| REQ-11 Revocation filtering, self-notice, and multi-group sync | BB / BA, FA, FB | A18, W12/W16, A19/A22 | No unauthorized body after removal; user sees own minimal W12 and can continue other authorized feed rows. |
| REQ-12 Delivered/read receipt state machine | BB / BA, FA | W08–W10/W19/W16 | Durable receipt is monotonic, recovered after reconnect, and does not mark read merely on receipt. |
| REQ-13 Images, files, and upload renewal | BB / FA, FB, DevOps | A20–A22/A25, W05/W07 | New key creates new attempt for same attachment; old attempt cannot complete; ready authorized file can be sent/downloaded. |
| REQ-14 Device activity and background push | BB / FA, FB, BA, DevOps, QA | A23/A24, W21/W22, W15/W16 | Per-device foreground suppresses push; background/unknown receives generic body-free hint; push never upgrades receipt; notification open syncs. |
| REQ-15 Presence and multi-device liveness | BA / FA, BB, QA | W03/W04/W18/W21/W22, A08 | One device loss does not make all devices offline; user online and device foreground remain distinct; uncertainty is unknown. |
| REQ-16 Unified errors and privacy protection | QA / BA, BB, FA, FB, DevOps | Common error, W17, A22 | Error/correlation meanings are consistent; no credentials, signed URL, body, SQL, or private user identifiers leak. |
| REQ-17 Infrastructure, health probes, and CI delivery | DevOps / BA, BB, QA | routes, health, A01/W01, GitHub Actions | Public routes and private probes match contract; missing dependencies/config fail readiness; GitHub Actions is delivery baseline. |
| REQ-18 Performance validation and capacity boundaries | QA / PM, BA, BB, DevOps | W05–W16, A19, metrics | PM approves workload/thresholds; measure ACK/end-to-end/recovery independently and report only tested environment and scale. |
| REQ-19 Shared responsive Web pages | FB / FA, DO, QA | Central Web/RWD page-family matrix and candidate UI routes | One shared Web project and SessionContext; the proposed band-by-page layout and shared controls are consistent across supported browsers. |
| REQ-20 Responsive chat interaction and read state | FA / FB, BA, BB, QA | Central Web/RWD chat rules; A12/A19; W08/W09 | Input/IME, composer, draft/C1, message_id+offset anchor, conditional auto-follow, and candidate W09 visibility policy follow the central chapter; W08 remains independent. |
| REQ-21 Web deep links and authorized route return | FB / DO, FA, BB, QA | Candidate UI route allowlist; `openChat`; A12/A13; `/api/v1`, `/ws/v1` | Listed UI routes use auth guard and authorized return; only those UI routes fall back to Web shell; API/WSS paths never do. |
| REQ-22 Web Push policy scope and acceptance governance | PM / BB, FB, DO, QA | Policy record; A23/A24 are iOS/android only; no browser subscription API/event is defined | Approve browser/provider/subscription scope and acceptance contract before implementation; do not fake browser push or infer App/PWA behavior. |


### REQ-19–REQ-22 detailed Web acceptance

| Requirement | Owner | Collaborators | Interfaces | Precondition | Action | Expected |
|---|---|---|---|---|---|---|
| REQ-19 Shared responsive Web pages | FB | FA, DO, QA | Central Web/RWD chapter; candidate UI route allowlist; existing REST/API models | One shared Web build and authorized UI routes | Exercise every page family in each named layout band and candidate route/deep-link behavior | Each band uses the prescribed page-family layout; shared session/API/event/model contracts remain unchanged; responsive reflow is presentation only. |
| REQ-20 Responsive chat interaction and read state | FA | FB, BA, BB, QA | Central Web/RWD chapter; A12/A19; W08/W09 | Authenticated browser, active conversation, saved draft/pending C1/read anchor | Exercise keyboard/soft-keyboard/IME input, resize/orient, prepend history, and vary actual message intersection/visibility | Physical and soft-keyboard rules hold; draft/C1 and message_id+offset survive; older-history anchoring is stable; auto-follow/read conditions follow the candidate policy; W08 is independent. |
| REQ-21 Web deep links and authorized route return | FB | DO, FA, BB, QA | Candidate UI route allowlist; `openChat`, A12/A13, `/api/v1`, `/ws/v1` | Logged-out and authenticated route cases; known UI route namespace | Load/refresh each candidate deep link, complete auth, navigate back/forward, and request API/WSS paths | Return only to authorized UI route; only candidate UI paths reach Web shell; API/WSS paths and failures remain backend-owned and unchanged. |
| REQ-22 Web Push policy scope and acceptance governance | PM | BB, FB, DO, QA | Existing A23/A24 and iOS/android DeviceTokenStatus only; browser subscription/provider contract is not defined | Product/provider/legal/permission scope is reviewed before any browser-push implementation | Record whether Web Push is in scope, its browser/provider/subscription lifecycle and acceptance contract, or explicitly defer it | No fake browser-push feature or implied native App/PWA support; A23/A24 and existing native push policy remain unchanged until a separately approved contract exists. |

## 8. Shared decisions and change ledger

Pending approval: DeviceID issue/reuse across reinstall/account switch; W21/W22 lease and unknown-state push behavior; Web/RWD layout and accessibility thresholds; production sync/file/heartbeat/rate values; group limits and role policy; group receipt visibility; history before joining/after leaving; supported attachment policy; Web Push provider/subscription scope; and validity of prior performance/reconnect objectives. The added Web feature IDs are FA-08, FB-07, DO-06, QA-06 and the added documented requirements are REQ-19–REQ-22; none adds or renames a REST API/WSS event. A01–A25/W01–W22 names and IDs remain unchanged. This document contains requirements, not verification results.
