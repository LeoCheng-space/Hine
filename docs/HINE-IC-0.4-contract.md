# HINE-IC-0.4 — Shared Interface Contract

**Status:** Integrated proposal, pending approval. This document is the single shared contract for [HINE-IC-0.4 role PRDs](HINE-IC-0.4-role-prds.md). It describes specified behavior, not implemented software or test results. Unless explicitly called confirmed/inherited, new fields and numeric values remain proposals. No product code, deployment, or product test is claimed.

## 1. Contract invariants and proposal status

- Public REST: `https://hine.run.place/api/v1`; WSS: `wss://hine.run.place/ws/v1`. Signed GCS URLs carry object bytes only; they are not HINE API routes. Internal `/health/live` and `/health/ready` are not public.
- PostgreSQL in Backend B is authoritative for messages, membership, receipts, attachment metadata, and sync feeds. Backend A Redis/Pub/Sub is ephemeral live fanout, never the message store.
- A successful W06 persisted ACK is permitted only after the canonical message, sender C1→M1 mapping, and every required per-user feed row are committed atomically. A lost ACK is resolved by retrying the same `client_message_id` (C1); same C1/same content returns the same M1, different content returns `IDEMPOTENCY_CONFLICT`. Commit does not guarantee the sender received an ACK.
- Live `message.created` may be displayed immediately but never advances the sync cursor. W16 `next_cursor` is a candidate and is stored only atomically with the completely applied local projection. History `before`, REST list cursors, and the user SyncCursor are distinct and not interchangeable.
- Bootstrap snapshot state and start cursor H share one consistent snapshot. All pages for the same `snapshot_id` must be staged and applied before H is installed. On restart or page failure, do not claim partial snapshot state is complete. Feed scanning advances over hidden unauthorized positions without returning their content; a removed user may receive their own minimal revocation notice.
- `openChat(conversation_id)` is a Frontend A module interface, not a REST route or WSS event. Frontend B owns application routing and calls it; Frontend A mounts/switches chat UI and owns the single app-scoped WSS. Chat navigation does not open a second socket.
- Frontend B exclusively owns session context and refresh cookie. After A03 succeeds it passes the new access session to Frontend A, which closes the old WSS and creates a new WSS (W01/W02), sends its first W21, and resumes from the saved cursor. No same-socket reauthentication. A04 revokes the current device session and push binding; successful logout clears local auth and tells Frontend A to stop its socket. Other devices are unaffected.
- Group mapping: A14/A16 → W11; A15/A17 → W20; A18 → W12. There is no ban operation.
- Confirmed/inherited: CC-01 durable ACK, C1→M1 idempotency, per-user commit-safe cursors, snapshot continuation, and offline recovery. Proposed pending approval: A25, W21/W22, server-issued DeviceID details, SessionContext additions, activity-lease and push audience behavior, numeric ceilings/rates/TTLs, and operational values. No candidate value is a production SLO.
- Authoritative confirmed platform placement: The HINE client is ONE responsive Web application (RWD) serving desktop, tablet, and mobile browsers from a unified codebase. Frontend A (chat/real-time) and Frontend B (auth/contacts/routing) are feature modules within this single Web app, not separate or device-specific applications. They share the same `SessionContext`, REST API client, WebSocket events, data models, and a single app-scoped WSS connection. Frontend frameworks and styling tooling (React, Vue, Tailwind, etc.) are explicitly not locked. There is no automatic native mobile app, progressive web app (PWA), installation, or offline persistence requirement in this contract baseline. For detailed responsive UI rules, viewport breakpoints, and navigation transition specifications, see [HINE-IC-0.4 role PRDs: Shared Web Responsive UI Layout](HINE-IC-0.4-role-prds.md#web-rwd).
- Explicit Web push scope decision: The A23 `platform` parameter remains strictly `"ios" | "android"` for native push tokens and is unchanged; clients must never treat a mobile browser as a native app or send synthetic `ios`/`android` tokens from Web browsers. The existing product demand for push notifications is preserved, but browser-based background push requires separate PM approval of provider, subscription model, and delivery contract; there is no automatic PWA or Web Push requirement. No new A-series endpoints or W-series event IDs are added for Web push in this specification.

## 2. Common formats, errors, IDs, and projections

### REST and WSS envelopes

REST success object: `{"data": ...}`. Success list: `{"data":{"items":[...]},"meta":{"next_cursor":string|null}}`. HTTP 204 has no response body. REST error:

```json
{"error":{"code":"FORBIDDEN","message":"Access denied","request_id":"req-1","retryable":false,"details":{}}}
```

All error fields shown are required and non-null; `details` is an object. `details.retry_after_ms` may be included for a rate limit. Error codes and status mappings: `INVALID_ARGUMENT` 400, `UNAUTHENTICATED` 401, `FORBIDDEN` 403, `NOT_FOUND` 404, `CONFLICT` 409, `IDEMPOTENCY_CONFLICT` 409, `CURSOR_INVALID` 400 (invalid REST cursor), `CURSOR_EXPIRED` 410 (expired A08/A11/A19 REST cursor only), `SYNC_RESET_REQUIRED` 410 (expired WSS user-feed cursor only), `PAYLOAD_TOO_LARGE` 413, `UNSUPPORTED_MEDIA_TYPE` 415, `UPLOAD_NOT_READY` 409, `UPLOAD_EXPIRED` 410 (proposal), `RATE_LIMITED` 429, `DEPENDENCY_UNAVAILABLE` 503, `PERSISTENCE_FAILED` 503, and `OUTCOME_UNCONFIRMED` 503. `OUTCOME_UNCONFIRMED` means a write may have committed but has no confirmed result; a known rollback is `PERSISTENCE_FAILED`. A disconnected socket need not receive an error frame. REST cursor errors are local to that REST query; only a WSS user-feed `SYNC_RESET_REQUIRED` starts W13 bootstrap.

Every WSS frame has `event:string`, `event_id:UUID`, `timestamp:Timestamp`, `payload:object`. A response to a request has `correlation_id:UUID` referencing that request's `event_id`; commands and unsolicited events omit it. Conversation events require top-level `conversation_id`; W07 also requires top-level `sender_id`. A client-supplied sender is never trusted. A message's stable server event ID is the same in live delivery and feed replay; request event IDs are per attempt, while C1 is stable for the send intent.

### Shared scalar types and privacy

- `EntityID`: opaque server-issued JSON string (candidate max 128 characters); not necessarily a UUID. IDs other than `message_id`, `client_message_id`, and `event_id` are opaque strings.
- `DeviceID`: distinct server-issued opaque identifier bound to an account and device session; it is not an `EntityID` promise or a credential. `AccessSession.device_id`, W01/W02 `device_id`, A23/A24 device path, W21/W22, and internal device arguments use this type. A02 may accept `null` only for first-install issuance; responses always contain a non-null DeviceID.
- Public `user_id` and internal `subject_id` are different identity types. Backend B maps them; `subject_id` is never a client field.
- `UUID`: UUID string; required for `message_id`, `client_message_id`, `event_id`, and response correlation IDs.
- `Timestamp`: ISO-8601 UTC string; authoritative timestamps are server generated.
- `OpaqueCursor`: server-issued opaque string bound to the user/feed generation or its REST query; cannot be decoded or used to authorize access.
- `Title`: string; proposed 1–80 Unicode characters.
- `UserSummary`: `{id:EntityID,display_name:string,avatar_attachment_id:EntityID|null}`; every field required. Avatar is null when absent or not visible. Summary has no email.
- `UserProfile`: all UserSummary fields plus required `email:string`; only the person and Backend B can see email. Password is only in A01/A02 request and never in a response, log, or WSS frame.
- `AccessSession`: `{access_token:string,expires_at:Timestamp,user_id:EntityID,device_id:DeviceID,session_generation:int}`; every field required/non-null. Refresh credential is an HTTP-only Secure/SameSite cookie, never JSON. A01 returns UserProfile only; A02/A03 return AccessSession.
- `SessionContext`: exactly one discriminant. `authenticated` has non-null `user_id,device_id,access_token,expires_at,session_generation`; `refreshing` has non-null `user_id,device_id,session_generation` and null `access_token,expires_at`; `logged_out` has all five null. Frontend B owns it. An installation-scoped DeviceStore is separate from SessionContext and may retain device_id per account across logout; logged_out SessionContext itself remains all-null. A02 reuses a stored DeviceID only for the same account. A05 `UserProfile.id` is compared only to public `user_id`, never internal `subject_id`.
- Internal JWT subject `subject_id` is mapped server-side to public `user_id`; it is never accepted from or returned to a client. DeviceID identifies a bound device, not a credential.

### User, conversation, and membership types

- `ContactView`: required `user:UserSummary`, `added_at:Timestamp`, `presence:"online"|"offline"|"unknown"`. Presence required in A08; optional in A09 response. Presence is ephemeral Backend A/Redis state, not push state.
- `ConversationSummary` (A11): required `id:EntityID`, `type:"direct"|"group"`, `title:Title|null` (direct is null), `unread_count:int>=0`. Does not require members or created_at.
- `ConversationDetail` (A12): all ConversationSummary fields plus required `members:MemberView[]`, `created_at:Timestamp`, `membership_version:int|null` (group >=1; direct null). Only currently authorized members can read it.
- `ConversationCreateResult` (A13/A14): required `id,type,title,member_ids:EntityID[],membership_version:int|null`; group creator is in member_ids, direct has null membership_version.
- `ConversationMutationResult`: required `id,type,title,membership_version:int>=1` (A15).
- `MemberView`: required `user_id:EntityID`, `role:"admin"|"member"`. `MemberMutationResult` adds required `membership_version:int>=1`.
- `BootstrapConversation` (W14): required `id,type,title,unread_count,my_role:"admin"|"member"|null,recent_messages:MessageSnapshot[]`; direct has null title and my_role. Recent messages are full message snapshots, not IDs only; complete member list comes from A12.

### Messages, receipts, attachments, and sync

- `MessageView` (A19): required non-null `id:UUID,event_id:UUID,conversation_id:EntityID,sender_id:EntityID,created_at:Timestamp,order_key:string,type:"text"|"image"|"file",receipt:ReceiptProjection|null`. For text, `text:string` is required (candidate 1–4096 Unicode chars) and `attachment_id` is omitted. For image/file, `attachment_id:EntityID` is required and `text` omitted. Optional `client_message_id:UUID` is visible only to the original sender. `order_key` is not a sync cursor.
- `MessageSnapshot` has the same fields and visibility as MessageView and represents full recent content. W07/W16 map top-level event_id→MessageView.event_id, timestamp→created_at, conversation_id and sender_id to corresponding fields, and payload.message_id→MessageView.id. W07's C1 is sender-only.
- `ReceiptProjection` is either direct `{kind:"direct",message_id:UUID,recipient_id:EntityID,status:"delivered"|"read",updated_at:Timestamp}` or proposed group summary `{kind:"group",message_id:UUID,read_count:int>=0,member_count:int>=1,updated_at:Timestamp}`. The backend stores per-recipient status; pending is a client UI state, not a stored receipt value. Group read-count policy remains a product decision.
- `AttachmentView` (A21): required non-null `id:EntityID,scope:"avatar"|"conversation",uploader_id:EntityID,kind:"image"|"file",filename:string,content_type:string,size_bytes:int>0,sha256:string` (64 hex), `state:"pending"|"ready",created_at:Timestamp,conversation_id:EntityID|null`. `scope=avatar` requires null conversation, image kind, and owner uploader. Conversation scope requires non-null conversation and checks membership at creation/download. Candidate file max 20 MiB and candidate MIME allowlist `image/jpeg,image/png,image/webp,application/pdf,text/plain` are pending approval. GCS object key is not exposed.
- `UploadGrant` (A20/A25): required `attachment_id,upload_attempt_id:EntityID,upload_url:string` (short-lived HTTPS signed URL), `expires_at:Timestamp`, `required_headers:object<string,string>`. Only attachment owner receives it; never log or place URL in a message/event.
- `DownloadGrant` (A22): required `download_url:string,expires_at:Timestamp,content_type:string`.
- `DeviceTokenStatus` (A23): required `device_id:DeviceID,platform:"ios"|"android",registered:boolean`; raw push token is accepted/stored only under control and never returned.
- `SyncBootstrapPage` (W14): required `snapshot_id:EntityID,start_cursor:OpaqueCursor,conversations:BootstrapConversation[],next_page_token:OpaqueCursor|null,has_more:boolean`. Candidate page maximum 50 logical items counting each conversation, nested recent message, and status separately. Install start_cursor only after all pages for the same snapshot are staged and projection switches atomically.
- `SyncBatch` (W16): required `snapshot_boundary:OpaqueCursor,events:WsEnvelope[],next_cursor:OpaqueCursor,has_more:boolean`. Candidate scan ceiling 50 feed positions including hidden filtered positions. Empty visible events may still advance a safe candidate cursor; a truly empty scan does not.
- `HealthResponse`: required `status:"ok"|"unready",service:"api"|"realtime",timestamp:Timestamp,dependencies:{postgresql:"ok"|"fail"|"not_checked",redis:"ok"|"fail"|"not_checked"}`; optional `reason:string` (omitted unless a public-safe readiness reason applies; if present, non-null). Internal only; live is 200 and does not check dependencies; ready is 200 when required dependencies are ready, otherwise 503. `CONFIG_MISSING` may identify missing configuration without naming or exposing its value.

## 3. REST API registry A01–A25

Every path below is relative to the single base URL `https://hine.run.place`; joining it with the displayed `/api/v1/...` path forms the complete public path. All operations are provided by Backend B. Unless stated public/cookie-only, use a valid Bearer access JWT. Fields in the table are required unless marked optional/nullable. GETs are safe to retry; 204 has no body. List responses use the common list envelope. REST cursor errors remain local to the relevant list/history query and never reset the WSS feed.

| ID / operationId | Method and path | Request → response; status | Authorization, errors, and retry/key behavior |
|---|---|---|---|
| A01 `registerUser` | POST `/api/v1/auth/register` | `{email,password,display_name}` → UserProfile; 201 | Public. INVALID_ARGUMENT, CONFLICT, RATE_LIMITED; duplicate email is 409 and is not bypassed with a new email after uncertain response. No session response. |
| A02 `login` | POST `/api/v1/auth/login` | `{email,password,device_id:DeviceID|null}` → AccessSession; 200 + refresh cookie | Public; null only for first-install DeviceID issuance. UNAUTHENTICATED, RATE_LIMITED; unknown outcome resolves by login, not a second session store. |
| A03 `refreshSession` | POST `/api/v1/auth/refresh` | No JSON body; refresh cookie → AccessSession; 200 + rotated cookie | Valid refresh cookie. UNAUTHENTICATED, RATE_LIMITED; old cookie is not indefinitely reusable. |
| A04 `logout` | POST `/api/v1/auth/logout` | No body → no body; 204 | Current session cookie; idempotent. UNAUTHENTICATED; proposed revocation of current device push binding. |
| A05 `getMe` | GET `/api/v1/users/me` | No body → UserProfile; 200 | Own profile. UNAUTHENTICATED; safe retry. |
| A06 `updateMe` | PATCH `/api/v1/users/me` | At least one `{display_name:string,avatar_attachment_id:EntityID|null}` → UserProfile; 200 | Own profile. INVALID_ARGUMENT, UNAUTHENTICATED, FORBIDDEN, UPLOAD_NOT_READY; avatar must be own ready avatar-scope attachment; null removes it. |
| A07 `getUserSummary` | GET `/api/v1/users/{user_id}` | No body → UserSummary; 200 | Authenticated. UNAUTHENTICATED, NOT_FOUND, RATE_LIMITED; hidden avatar is null, email never returned. |
| A08 `listContacts` | GET `/api/v1/contacts?cursor={cursor}&limit={limit}` | No body → ContactView[] + meta.next_cursor; 200 | Own contacts. UNAUTHENTICATED, CURSOR_INVALID, CURSOR_EXPIRED; either cursor error affects only this REST query. Presence unknown is reported as unknown. |
| A09 `addContact` | POST `/api/v1/contacts` | `{user_id}` → ContactView; 201 new / 200 existing | Own list. INVALID_ARGUMENT, UNAUTHENTICATED, NOT_FOUND; duplicate owner/user is not duplicated. |
| A10 `removeContact` | DELETE `/api/v1/contacts/{user_id}` | No body → no body; 204 | Own list. UNAUTHENTICATED; repeated deletion is 204 and does not remove conversation history. |
| A11 `listConversations` | GET `/api/v1/conversations?cursor={cursor}&limit={limit}` | No body → ConversationSummary[] + meta.next_cursor; 200 | Own authorized list. UNAUTHENTICATED, CURSOR_INVALID, CURSOR_EXPIRED; local recovery only, not WSS feed. |
| A12 `getConversation` | GET `/api/v1/conversations/{conversation_id}` | No body → ConversationDetail; 200 | Current authorized member. UNAUTHENTICATED, NOT_FOUND; version gap is reconciled by refetching A12. |
| A13 `getOrCreateDirectConversation` | POST `/api/v1/conversations/direct` | `{peer_user_id}` → ConversationCreateResult; 201 new / 200 existing | Authenticated. INVALID_ARGUMENT, UNAUTHENTICATED, NOT_FOUND, CONFLICT; unordered two-user pair is unique. |
| A14 `createGroup` | POST `/api/v1/conversations/groups` | `{title,member_ids:EntityID[]}` → ConversationCreateResult; 201 | Authenticated; Idempotency-Key required. INVALID_ARGUMENT, UNAUTHENTICATED, CONFLICT, IDEMPOTENCY_CONFLICT; same key/different content is 409. Creator is admin; post-commit W11. |
| A15 `renameGroup` | PATCH `/api/v1/conversations/{conversation_id}` | `{title}` → ConversationMutationResult; 200 | Admin. INVALID_ARGUMENT, UNAUTHENTICATED, FORBIDDEN, NOT_FOUND; same title retry is idempotent; post-commit W20 title change. |
| A16 `addGroupMember` | POST `/api/v1/conversations/{conversation_id}/members` | `{user_id}` → MemberMutationResult; 201 new / 200 existing | Admin. INVALID_ARGUMENT, UNAUTHENTICATED, FORBIDDEN, NOT_FOUND, CONFLICT; post-commit W11, never W12. |
| A17 `changeGroupMemberRole` | PATCH `/api/v1/conversations/{conversation_id}/members/{user_id}` | `{role:"admin"|"member"}` → MemberMutationResult; 200 | Admin. INVALID_ARGUMENT, UNAUTHENTICATED, FORBIDDEN, NOT_FOUND, CONFLICT; last admin cannot be removed; post-commit W20 role change. |
| A18 `removeGroupMember` | DELETE `/api/v1/conversations/{conversation_id}/members/{user_id}` | No body → no body; 204 | Admin or self-leave. UNAUTHENTICATED, FORBIDDEN, NOT_FOUND, CONFLICT; repeated valid deletion is idempotent; post-commit W12, no ban. |
| A19 `listMessages` | GET `/api/v1/conversations/{conversation_id}/messages?before={history_cursor}&limit={limit}` | No body → MessageView[] + meta.next_cursor; 200 | Authorized history reader. UNAUTHENTICATED, NOT_FOUND, CURSOR_INVALID, CURSOR_EXPIRED; newest to oldest by order_key/message_id; history cursor is not SyncCursor. |
| A20 `createUpload` | POST `/api/v1/uploads` | `{scope:"avatar"|"conversation",conversation_id:EntityID|null,filename,content_type,size_bytes,sha256}` → UploadGrant; 201 | Idempotency-Key required. INVALID_ARGUMENT, UNAUTHENTICATED, FORBIDDEN, PAYLOAD_TOO_LARGE, UNSUPPORTED_MEDIA_TYPE, IDEMPOTENCY_CONFLICT. Avatar requires null conversation; conversation scope requires current authorization. |
| A21 `completeUpload` | POST `/api/v1/uploads/{attachment_id}/complete` | `{upload_attempt_id,sha256}` → AttachmentView(state="ready"); 200 | Owner. UNAUTHENTICATED, FORBIDDEN, UPLOAD_NOT_READY, CONFLICT; verify actual GCS type/size/hash; only current attempt accepted, same completed attempt returns original ready result. |
| A22 `getAttachmentDownload` | GET `/api/v1/attachments/{attachment_id}/download` | No body/query → DownloadGrant; 200 | Owner or authorized viewer. UNAUTHENTICATED, FORBIDDEN, NOT_FOUND, UPLOAD_NOT_READY, DEPENDENCY_UNAVAILABLE; recheck conversation membership each time; permitted avatar viewers may obtain new short-lived URL. |
| A23 `upsertPushToken` | PUT `/api/v1/devices/{device_id}/push-token` | `{platform:"ios"|"android",token}` → DeviceTokenStatus; 200 | Own bound DeviceID. INVALID_ARGUMENT, UNAUTHENTICATED; PUT replaces token; raw token never returned. |
| A24 `deletePushToken` | DELETE `/api/v1/devices/{device_id}/push-token` | No body → no body; 204 | Own bound DeviceID. UNAUTHENTICATED, FORBIDDEN; repeated deletion is 204. |
| A25 `renewUploadGrant` (proposal) | POST `/api/v1/uploads/{attachment_id}/renew` | No JSON body → UploadGrant; 200 | Pending upload owner; reauthorize conversation membership. UNAUTHENTICATED, FORBIDDEN, NOT_FOUND, CONFLICT, UPLOAD_EXPIRED, IDEMPOTENCY_CONFLICT. Each renewal uses a NEW Idempotency-Key. Same-key retry returns same attempt/URL even if expired; new key keeps attachment_id and issues a new upload_attempt_id/URL; A21 rejects old attempt. |

A20/A21/A22 avatar flows work without any conversation. Candidate attachment filename is 1–255 chars, maximum file 20 MiB, MIME types as listed above; values are not approved. A25 has proposed `UPLOAD_EXPIRED` error. A08/A11/A19 REST cursor errors (including expired/invalid) restart only their local query; only the WSS feed's `SYNC_RESET_REQUIRED` begins W13 bootstrap.
### Complete REST request/response sample registry

`request:null` means there is no HTTP request body (not a literal JSON null); query/path/header inputs are identified in the registry table. Responses use the contract projection and common REST envelope. All examples are synthetic.

```json
{
  "A01":{"request":{"email":"a@example.test","password":"example-password-123","display_name":"A"},"status":201,"response":{"data":{"id":"u1","display_name":"A","avatar_attachment_id":null,"email":"a@example.test"}}},
  "A02":{"request":{"email":"a@example.test","password":"example-password-123","device_id":null},"status":200,"response":{"data":{"access_token":"<jwt>","expires_at":"2026-10-01T08:15:00Z","user_id":"u1","device_id":"d1","session_generation":1}},"set_cookie":"<HttpOnly refresh cookie>"},
  "A03":{"request":null,"status":200,"response":{"data":{"access_token":"<jwt>","expires_at":"2026-10-01T08:30:00Z","user_id":"u1","device_id":"d1","session_generation":2}},"set_cookie":"<rotated HttpOnly refresh cookie>"},
  "A04":{"request":null,"status":204,"response":null},
  "A05":{"request":null,"status":200,"response":{"data":{"id":"u1","display_name":"A","avatar_attachment_id":null,"email":"a@example.test"}}},
  "A06":{"request":{"avatar_attachment_id":"a-avatar-1"},"status":200,"response":{"data":{"id":"u1","display_name":"A","avatar_attachment_id":"a-avatar-1","email":"a@example.test"}}},
  "A07":{"request":null,"status":200,"response":{"data":{"id":"u2","display_name":"B","avatar_attachment_id":"a-avatar-2"}}},
  "A08":{"request":null,"status":200,"response":{"data":{"items":[{"user":{"id":"u2","display_name":"B","avatar_attachment_id":"a-avatar-2"},"added_at":"2026-10-01T07:00:00Z","presence":"unknown"}]},"meta":{"next_cursor":null}}},
  "A09":{"request":{"user_id":"u2"},"status":201,"response":{"data":{"user":{"id":"u2","display_name":"B","avatar_attachment_id":"a-avatar-2"},"added_at":"2026-10-01T07:00:00Z"}}},
  "A10":{"request":null,"status":204,"response":null},
  "A11":{"request":null,"status":200,"response":{"data":{"items":[{"id":"c1","type":"direct","title":null,"unread_count":0}]},"meta":{"next_cursor":null}}},
  "A12":{"request":null,"status":200,"response":{"data":{"id":"c1","type":"direct","title":null,"unread_count":0,"members":[{"user_id":"u1","role":"member"},{"user_id":"u2","role":"member"}],"created_at":"2026-10-01T07:00:00Z","membership_version":null}}},
  "A13":{"request":{"peer_user_id":"u2"},"status":201,"response":{"data":{"id":"c1","type":"direct","title":null,"member_ids":["u1","u2"],"membership_version":null}}},
  "A14":{"request":{"title":"Team","member_ids":["u2","u3"]},"status":201,"response":{"data":{"id":"g1","type":"group","title":"Team","member_ids":["u1","u2","u3"],"membership_version":1}}},
  "A15":{"request":{"title":"Team 2"},"status":200,"response":{"data":{"id":"g1","type":"group","title":"Team 2","membership_version":2}}},
  "A16":{"request":{"user_id":"u4"},"status":201,"response":{"data":{"user_id":"u4","role":"member","membership_version":3}}},
  "A17":{"request":{"role":"admin"},"status":200,"response":{"data":{"user_id":"u4","role":"admin","membership_version":4}}},
  "A18":{"request":null,"status":204,"response":null},
  "A19":{"request":null,"status":200,"response":{"data":{"items":[{"id":"22222222-2222-4222-8222-222222222222","event_id":"00000000-0000-4000-8000-000000000007","conversation_id":"c1","sender_id":"u1","created_at":"2026-10-01T08:00:04Z","order_key":"c1-41","type":"text","text":"Hello","receipt":{"kind":"direct","message_id":"22222222-2222-4222-8222-222222222222","recipient_id":"u2","status":"read","updated_at":"2026-10-01T08:00:07Z"},"client_message_id":"11111111-1111-4111-8111-111111111111"}]},"meta":{"next_cursor":null}}},
  "A20":{"request":{"scope":"avatar","conversation_id":null,"filename":"avatar.png","content_type":"image/png","size_bytes":1024,"sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},"status":201,"response":{"data":{"attachment_id":"a-avatar-1","upload_attempt_id":"attempt-1","upload_url":"https://storage.googleapis.com/example-private/avatar?sig=example1","expires_at":"2026-10-01T08:05:00Z","required_headers":{"Content-Type":"image/png"}}}},
  "A21":{"request":{"upload_attempt_id":"attempt-1","sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},"status":200,"response":{"data":{"id":"a-avatar-1","scope":"avatar","conversation_id":null,"uploader_id":"u1","kind":"image","filename":"avatar.png","content_type":"image/png","size_bytes":1024,"sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","state":"ready","created_at":"2026-10-01T08:00:00Z"}}},
  "A22":{"request":null,"status":200,"response":{"data":{"download_url":"https://storage.googleapis.com/example-private/avatar?sig=download1","expires_at":"2026-10-01T08:01:00Z","content_type":"image/png"}}},
  "A23":{"request":{"platform":"android","token":"example-device-token"},"status":200,"response":{"data":{"device_id":"d1","platform":"android","registered":true}}},
  "A24":{"request":null,"status":204,"response":null},
  "A25":{"request":null,"status":200,"response":{"data":{"attachment_id":"a-avatar-1","upload_attempt_id":"attempt-2","upload_url":"https://storage.googleapis.com/example-private/avatar-attempt-2?sig=example2","expires_at":"2026-10-01T08:10:00Z","required_headers":{"Content-Type":"image/png"}}}}
}
```

A20 conversation-upload request variant:
```json
{"scope":"conversation","conversation_id":"c1","filename":"report.pdf","content_type":"application/pdf","size_bytes":4096,"sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}
```

## 4. WebSocket registry W01–W22

All events are frames in the common envelope. Directions are client→server (C→S) or server→client (S→C). Except W01, business frames require successful authentication. The exact required fields, direction, and transitions are:

| ID / event | Direction; payload and top-level fields | Behavior |
|---|---|---|
| W01 `auth.authenticate` | C→S `{access_token:string,device_id:DeviceID}` | First business frame. Validates token and bound device; success W02; invalid may W17 then close or close directly. |
| W02 `auth.accepted` | S→C, correlated to W01: `{user_id:EntityID,device_id:DeviceID,expires_at:Timestamp,session_generation:int,heartbeat_interval_seconds:int,heartbeat_timeout_seconds:int}` | Public identity and session generation; heartbeat values are candidate runtime config. No cursor effect. |
| W03 `heartbeat.ping` | C→S `{nonce}` | Connection liveness only; does not extend JWT. |
| W04 `heartbeat.pong` | S→C, correlated to W03 `{nonce}` | Echo nonce; timeout closes this connection only. |
| W05 `message.send` | C→S, top-level `conversation_id`; `{client_message_id,type:"text"|"image"|"file",text? | attachment_id?}` | Text requires text only; image/file require attachment_id only. Same C1/same payload idempotent; different payload conflict. |
| W06 `message.ack` | S→C, correlated to current W05, top-level `conversation_id`; `{client_message_id,message_id,status:"persisted"}` | Only after complete atomic persistence; may be lost to disconnect. |
| W07 `message.created` | S→C, top-level `conversation_id,sender_id`; `{message_id,client_message_id?,type,text? | attachment_id?,order_key}` | Authorized recipients; C1 only sender. Stable event_id on feed replay. Live event never advances cursor. |
| W08 `message.received` | C→S, top-level `conversation_id`; `{message_id}` | Sent after durable local receipt; response W19; idempotent. |
| W09 `message.read` | C→S, top-level `conversation_id`; `{message_id}` | Sent after actual reading; read is monotonic and implies delivered. |
| W10 `message.status` | S→C, top-level `conversation_id`; ReceiptProjection | Backend B committed receipt projection; direct projection or proposed group aggregate. Also recoverable by sync. |
| W11 `conversation.member_added` | S→C, top-level `conversation_id`; `{member_id,role:"admin"|"member",actor_id,membership_version}` | A14/A16 post-commit. New member obtains detail with A12; live loss is recoverable through feed. |
| W12 `conversation.member_removed` | S→C, top-level `conversation_id`; self `{member_id,change:"removed",membership_version}`; peers may also include `actor_id` | A18 post-commit. Removed member gets only minimal self-notice, not unauthorized future content. |
| W13 `sync.bootstrap.request` | C→S `{reason:"first_login"|"cursor_reset",snapshot_id?,page_token?}` | Initial or continuation page; continuation binds snapshot_id and page_token. |
| W14 `sync.bootstrap.page` | S→C, correlated; SyncBootstrapPage | Full authorized conversation snapshot with recent message bodies/status. Apply all pages under one snapshot before installing start_cursor. |
| W15 `sync.request` | C→S `{cursor,snapshot_boundary?}` | First request uses saved cursor; continuation uses same round's boundary. Trigger on reconnect/foreground/periodic reconciliation. |
| W16 `sync.batch` | S→C, correlated; SyncBatch | Candidate next_cursor; apply events and projection atomically before saving. Hidden rows can advance; expired feed cursor causes W17 SYNC_RESET_REQUIRED. |
| W17 `error` | S→C, correlated when replying: `{code,message,retryable,retry_after_ms?}` | Shared error code semantics; disconnected socket need not receive it. |
| W18 `presence.changed` | S→C `{user_id,presence:"online"|"offline"|"unknown"}` | Ephemeral authorized presence; unknown when backend cannot confirm Redis state. |
| W19 `receipt.ack` | S→C, correlated to W08/W09, top-level `conversation_id`; `{message_id,status:"delivered"|"read",changed}` | Receipt request result; repeated no-op may return changed=false. |
| W20 `conversation.updated` | S→C, top-level `conversation_id`; `{changes:{kind:"title",title:Title}|{kind:"role",member_id,role:"admin"|"member"},actor_id,membership_version}` | A15/A17 post-commit to currently authorized members; version gap corrected with A12. |
| W21 `device.activity` (proposal) | C→S `{device_id:DeviceID,state:"foreground"|"background"}` | First after W02 and on state change/renewal. Device must match authenticated session; expired/missing state is unknown. |
| W22 `device.activity.ack` (proposal) | S→C, correlated to W21 `{device_id:DeviceID,state:"foreground"|"background",valid_until}` | Confirms recorded lease only, not push delivery or message receipt. |

In nested W16, each event preserves its own event_id and conversation_id; C1 remains sender-only. W21/W22 activity is distinct from W03/W04 connection heartbeat and W18 user-level online presence.

### WSS frame examples

UUIDs below are illustrative UUIDs; timestamps are UTC. Access token and URL examples are placeholders, not credentials.

```json
{"event":"auth.authenticate","event_id":"10000000-0000-4000-8000-000000000001","timestamp":"2026-09-29T12:00:00Z","payload":{"access_token":"<jwt>","device_id":"d1"}}
```
```json
{"event":"auth.accepted","event_id":"10000000-0000-4000-8000-000000000002","timestamp":"2026-09-29T12:00:00Z","payload":{"user_id":"u1","device_id":"d1","expires_at":"2026-09-29T13:00:00Z","session_generation":1,"heartbeat_interval_seconds":25,"heartbeat_timeout_seconds":60},"correlation_id":"10000000-0000-4000-8000-000000000001"}
```
```json
{"event":"message.send","event_id":"10000000-0000-4000-8000-000000000005","timestamp":"2026-09-29T12:01:00Z","conversation_id":"c1","payload":{"client_message_id":"10000000-0000-4000-8000-000000000006","type":"text","text":"hello"}}
```
```json
{"event":"message.ack","event_id":"10000000-0000-4000-8000-000000000007","timestamp":"2026-09-29T12:01:00Z","conversation_id":"c1","payload":{"client_message_id":"10000000-0000-4000-8000-000000000006","message_id":"10000000-0000-4000-8000-000000000008","status":"persisted"},"correlation_id":"10000000-0000-4000-8000-000000000005"}
```
```json
{"event":"message.created","event_id":"10000000-0000-4000-8000-000000000009","timestamp":"2026-09-29T12:01:00Z","conversation_id":"c1","sender_id":"u1","payload":{"message_id":"10000000-0000-4000-8000-000000000008","client_message_id":"10000000-0000-4000-8000-000000000006","type":"text","text":"hello","order_key":"k1"}}
```
```json
{"event":"heartbeat.ping","event_id":"10000000-0000-4000-8000-000000000003","timestamp":"2026-09-29T12:00:30Z","payload":{"nonce":"n1"}}
```
```json
{"event":"heartbeat.pong","event_id":"10000000-0000-4000-8000-000000000004","timestamp":"2026-09-29T12:00:30Z","payload":{"nonce":"n1"},"correlation_id":"10000000-0000-4000-8000-000000000003"}
```
```json
{"event":"message.received","event_id":"10000000-0000-4000-8000-000000000010","timestamp":"2026-09-29T12:02:00Z","conversation_id":"c1","payload":{"message_id":"10000000-0000-4000-8000-000000000008"}}
```
```json
{"event":"message.read","event_id":"10000000-0000-4000-8000-000000000011","timestamp":"2026-09-29T12:03:00Z","conversation_id":"c1","payload":{"message_id":"10000000-0000-4000-8000-000000000008"}}
```
```json
{"event":"message.status","event_id":"10000000-0000-4000-8000-000000000012","timestamp":"2026-09-29T12:03:01Z","conversation_id":"c1","payload":{"kind":"direct","message_id":"10000000-0000-4000-8000-000000000008","recipient_id":"u2","status":"read","updated_at":"2026-09-29T12:03:01Z"}}
```
```json
{"event":"conversation.member_added","event_id":"10000000-0000-4000-8000-000000000013","timestamp":"2026-09-29T12:04:00Z","conversation_id":"g1","payload":{"member_id":"u2","role":"member","actor_id":"u1","membership_version":2}}
```
```json
{"event":"conversation.member_removed","event_id":"10000000-0000-4000-8000-000000000014","timestamp":"2026-09-29T12:05:00Z","conversation_id":"g1","payload":{"member_id":"u2","change":"removed","membership_version":3}}
```
```json
{"event":"sync.bootstrap.request","event_id":"10000000-0000-4000-8000-000000000015","timestamp":"2026-09-29T12:06:00Z","payload":{"reason":"first_login"}}
```
```json
{"event":"sync.bootstrap.page","event_id":"10000000-0000-4000-8000-000000000016","timestamp":"2026-09-29T12:06:01Z","correlation_id":"10000000-0000-4000-8000-000000000015","payload":{"snapshot_id":"s1","start_cursor":"opaque-user1-40","conversations":[{"id":"c1","type":"direct","title":null,"unread_count":0,"my_role":null,"recent_messages":[{"id":"33333333-3333-4333-8333-333333333333","event_id":"44444444-4444-4444-8444-444444444444","conversation_id":"c1","sender_id":"u2","created_at":"2026-09-29T11:59:00Z","order_key":"c1-40","type":"text","text":"Earlier message","receipt":null}]}],"next_page_token":null,"has_more":false}}
```
```json
{"event":"sync.request","event_id":"10000000-0000-4000-8000-000000000017","timestamp":"2026-09-29T12:07:00Z","payload":{"cursor":"opaque-user1-40"}}
```
```json
{"event":"sync.batch","event_id":"10000000-0000-4000-8000-000000000018","timestamp":"2026-09-29T12:07:01Z","correlation_id":"10000000-0000-4000-8000-000000000017","payload":{"snapshot_boundary":"opaque-user1-41","events":[{"event":"message.created","event_id":"10000000-0000-4000-8000-000000000009","timestamp":"2026-09-29T12:01:00Z","conversation_id":"c1","sender_id":"u1","payload":{"message_id":"10000000-0000-4000-8000-000000000008","client_message_id":"10000000-0000-4000-8000-000000000006","type":"text","text":"hello","order_key":"k1"}}],"next_cursor":"opaque-user1-41","has_more":false}}
```
```json
{"event":"error","event_id":"10000000-0000-4000-8000-000000000019","timestamp":"2026-09-29T12:07:02Z","correlation_id":"10000000-0000-4000-8000-000000000017","payload":{"code":"SYNC_RESET_REQUIRED","message":"Cursor expired","retryable":false}}
```
```json
{"event":"presence.changed","event_id":"10000000-0000-4000-8000-000000000020","timestamp":"2026-09-29T12:08:00Z","payload":{"user_id":"u2","presence":"offline"}}
```
```json
{"event":"receipt.ack","event_id":"10000000-0000-4000-8000-000000000021","timestamp":"2026-09-29T12:03:01Z","conversation_id":"c1","correlation_id":"10000000-0000-4000-8000-000000000010","payload":{"message_id":"10000000-0000-4000-8000-000000000008","status":"delivered","changed":true}}
```
```json
{"event":"conversation.updated","event_id":"10000000-0000-4000-8000-000000000022","timestamp":"2026-09-29T12:09:00Z","conversation_id":"g1","payload":{"changes":{"kind":"title","title":"Team 2"},"actor_id":"u1","membership_version":4}}
```
```json
{"event":"conversation.updated","event_id":"10000000-0000-4000-8000-000000000023","timestamp":"2026-09-29T12:09:01Z","conversation_id":"g1","payload":{"changes":{"kind":"role","member_id":"u4","role":"admin"},"actor_id":"u1","membership_version":5}}
```
```json
{"event":"device.activity","event_id":"10000000-0000-4000-8000-000000000024","timestamp":"2026-09-29T12:10:00Z","payload":{"device_id":"d1","state":"background"}}
```
```json
{"event":"device.activity.ack","event_id":"10000000-0000-4000-8000-000000000025","timestamp":"2026-09-29T12:10:01Z","correlation_id":"10000000-0000-4000-8000-000000000024","payload":{"device_id":"d1","state":"background","valid_until":"2026-09-29T12:11:01Z"}}
```
```json
{"event":"message.send","event_id":"10000000-0000-4000-8000-000000000026","timestamp":"2026-09-29T12:11:00Z","conversation_id":"c1","payload":{"client_message_id":"10000000-0000-4000-8000-000000000027","type":"image","attachment_id":"a2"}}
```
## 5. Backend A ↔ Backend B internal contracts

These are module contracts, not public endpoints or mandated microservices. Backend A passes authenticated subject/device and request correlation; Backend B rechecks authorization inside each mutating transaction. Map internal failures to shared public codes without exposing table names/private fields.

1. `validateAccess(access_token:string,device_id:DeviceID)` → `{subject_id:EntityID,session_id:EntityID,session_generation:int,expires_at:Timestamp,session_valid:boolean}`. Errors: UNAUTHENTICATED, DEPENDENCY_UNAVAILABLE. Checks signature, issuer/audience, device binding, and revocation.
2. `authorize(subject_id:EntityID,action:"send"|"receive"|"read"|"history"|"attachment"|"manage_group",resource_type:"conversation"|"message"|"attachment",resource_id:EntityID,device_id:DeviceID)` → `{allowed:boolean,authorization_version:EntityID}`. Errors: UNAUTHENTICATED, FORBIDDEN, NOT_FOUND, DEPENDENCY_UNAVAILABLE. Precheck only; mutation transaction must recheck.
3. `persistIfAbsent(subject_id:EntityID,conversation_id:EntityID,client_message_id:UUID,type:"text"|"image"|"file",payload:{text:string}|{attachment_id:EntityID},request_event_id:UUID)` → exactly one of `created|existing_same`, with `{message_id:UUID,event_id:UUID,order_key:string,created_at:Timestamp,recipient_ids:EntityID[],status:"persisted"}`. Errors: UNAUTHENTICATED, FORBIDDEN, IDEMPOTENCY_CONFLICT, PERSISTENCE_FAILED, OUTCOME_UNCONFIRMED, DEPENDENCY_UNAVAILABLE. Same C1/different body is IDEMPOTENCY_CONFLICT. Message, C1 mapping, every required recipient feed row, and proposed eligible-device push intents commit atomically before W06.
4. `persistReceipt(subject_id:EntityID,device_id:DeviceID,conversation_id:EntityID,message_id:UUID,kind:"delivered"|"read",request_event_id:UUID)` → `{message_id:UUID,status:"delivered"|"read",changed:boolean,updated_at:Timestamp,status_event_id:UUID|null}`. Errors: UNAUTHENTICATED, FORBIDDEN, NOT_FOUND, PERSISTENCE_FAILED, OUTCOME_UNCONFIRMED, DEPENDENCY_UNAVAILABLE. Status is monotonic; unchanged duplicate creates no new status event.
5. `readBootstrap(subject_id:EntityID,reason:"first_login"|"cursor_reset",snapshot_id?:EntityID,page_token?:OpaqueCursor)` → SyncBootstrapPage. Errors: UNAUTHENTICATED, FORBIDDEN, CURSOR_INVALID, SYNC_RESET_REQUIRED, DEPENDENCY_UNAVAILABLE. Snapshot state/head are read consistently under short REPEATABLE READ; do not hold a transaction across network pagination. Validate authorization before each page; expired snapshot restarts rather than mixing snapshots.
6. `readFeed(subject_id:EntityID,cursor:OpaqueCursor,snapshot_boundary?:OpaqueCursor,limit:int)` → SyncBatch. Errors: UNAUTHENTICATED, FORBIDDEN, CURSOR_INVALID, SYNC_RESET_REQUIRED, DEPENDENCY_UNAVAILABLE. Pin continuation boundary; scan hidden positions as well as visible; return authorized content and minimal self-revocation notices; never let one revoked conversation block other feed positions.
7. `getDevicePresence(subject_id:EntityID,device_id:DeviceID)` returns `{online:"online"|"offline"|"unknown",activity:"foreground"|"background"|"unknown",valid_until:Timestamp|null}`. `recordActivity(subject_id:EntityID,device_id:DeviceID,session_generation:int,state:"foreground"|"background")` returns `{state:"foreground"|"background",valid_until:Timestamp}`. Errors: UNAUTHENTICATED, FORBIDDEN, DEPENDENCY_UNAVAILABLE. They are distinct read/query and mutation operations. Redis failure yields unknown, never false foreground.
8. `dispatchPushIntent(message_id:UUID,recipient_user_id:EntityID,device_id:DeviceID)` → `sent|suppressed|retryable_failure|permanent_token_failure`. Errors: FORBIDDEN, DEPENDENCY_UNAVAILABLE; provider failures are represented by the result, not a receipt mutation. Durable intent is created transactionally with eligible recipient message/feed data. Suppress fresh foreground device; background/unknown may receive generic body-free hint. Provider retries do not change receipts; `(message_id,device_id)` supports deduplication but provider exactly-once is not guaranteed.

### Group event mapping and client application

A14 create emits W11 projections for creator/initial members. A15 rename emits W20 `kind=title`; A16 add emits W11 (not W12); A17 role change emits W20 `kind=role`; A18 removal emits W12 (not W13). The REST caller updates its own view from the REST result without waiting for Pub/Sub. Other devices apply events; new members fetch A12; version gaps fetch A12. The removed user leaves the route after the minimal W12 or successful A18, and gets no new unauthorized body. Membership change and each required user feed entry commit together; Pub/Sub only accelerates post-commit delivery.

### Presence, activity, and push (proposal)

W21 reports app foreground/background for the authenticated device; W22 grants a short lease. A lost background frame, expired lease, or missing socket means unknown, not foreground. Backend B stores a durable generic push intent for eligible registered non-sender devices. Fresh foreground device suppresses a push; known background or unknown may receive a generic notification without message body. Provider acceptance/failure is not a delivered/read receipt. Tapping a notification restores auth and obtains content through authorized W13–W16/A19 sync. Per-user online and per-device foreground are different state.

## 6. Deployment and operational policy

The following environment registry is proposed configuration, not a statement that settings are currently deployed. `Required` means required when the named capability is enabled; push-provider credentials are conditional on that provider/platform being enabled.

| Name | Type / required | Consumer | Setter / source | Secret? | Missing/invalid behavior |
|---|---|---|---|---|---|
| `HINE_ENV` | enum/string; required | BA, BB, DO | DevOps deployment config | no | refuse startup/readiness |
| `PUBLIC_ORIGIN` | HTTPS URL; required | BB, DO | DevOps ingress config | no | refuse readiness; do not construct public links |
| `API_BASE_URL` | HTTPS URL; required | FB, FA config; DO ingress | DevOps frontend/release config | no | frontend deployment invalid |
| `WS_URL` | WSS URL; required | FA config; DO ingress | DevOps frontend/release config | no | realtime client not ready |
| `DATABASE_URL` | PostgreSQL connection URI; required | BB | DevOps Secret Manager reference | yes | BB fails startup/readiness |
| `REDIS_URL` | Redis connection URI; required for ephemeral realtime/presence | BA | DevOps Secret Manager reference | yes | BA not ready; report unknown rather than false presence |
| `GCS_BUCKET` | bucket name; required for uploads | BB | DevOps deployment config | no | attachment capability not ready |
| `JWT_ISSUER` | string; required | BB issues, BA validates | Backend B auth owner + DevOps | no | auth startup/readiness fails closed |
| `JWT_AUDIENCE` | string; required | BB issues, BA validates | Backend B auth owner + DevOps | no | auth startup/readiness fails closed |
| `JWT_SIGNING_KEY_SECRET_REF` | secret reference; required | BB only | DevOps Secret Manager binding; BB owns key rotation | reference sensitive; value secret | BB auth unavailable/not ready; never accept a fake key |
| `FCM_CREDENTIAL_SECRET_REF` | secret reference; conditional if Android push enabled | BB push worker | DevOps Secret Manager binding; BB owns provider use | reference sensitive; value secret | push remains disabled or deployment not ready per approved policy; never use fake credential |
| `APNS_KEY_SECRET_REF` | secret reference; conditional if iOS push enabled | BB push worker | DevOps Secret Manager binding; BB owns provider use | reference sensitive; value secret | push remains disabled or deployment not ready per approved policy; never use fake credential |
| `SYNC_PAGE_LIMIT` | positive integer; required | BB readBootstrap/readFeed, BA | PM approves value; DevOps injects; BA/BB validate | no | reject invalid config; no unbounded page |
| `UPLOAD_MAX_BYTES` | positive integer; required when upload enabled | BB | PM approves value; DevOps injects; BB validates | no | reject invalid config; uploads unavailable |
| `HEARTBEAT_TIMEOUT_SECONDS` | positive integer; required | BA; advertised via W02 policy | PM approves value; DevOps injects; BA validates | no | reject invalid config/readiness; do not silently invent runtime value |
| `HEARTBEAT_INTERVAL_SECONDS` | positive integer; required | BA sets/enforces heartbeat cadence; W02 advertises to FA | PM approves candidate; DevOps injects; BA validates | no | reject invalid config/readiness; do not silently invent W02 value |
| `ACTIVITY_LEASE_SECONDS` | positive integer; required when W21/W22 enabled | BA recordActivity/W22; BB device push eligibility | PM approves candidate; DevOps injects; BA validates | no | reject invalid config/readiness; activity becomes unknown rather than presumed foreground |
| `SYNC_RECONCILE_SECONDS` | positive integer; required for periodic foreground sync | FA schedules W15/W16; BA/BB handle requests | PM approves candidate; DevOps injects; FA/BA validate | no | reject invalid client/runtime config; do not silently invent a sync cadence |

Every environment also records which team sets the value and the reference/version used, without recording secret contents. Missing push credentials have a policy choice between disabling that provider and failing readiness; PM/DevOps must approve it before deployment.

Internal `/health/live` reports process liveness (200; dependencies may be `not_checked`). `/health/ready` reports required dependency readiness (200 or 503). Response follows HealthResponse and contains no credentials. Candidate values—not approval—include sync logical page ceiling 50, upload maximum 20 MiB, heartbeat interval 25 seconds and timeout 60 seconds, activity lease 60 seconds with W22-based renewal before `valid_until`, and foreground sync reconciliation every 10 seconds. Candidate rate limits include message 60/minute with burst 10 and login 5/minute/source; these are pending PM/QA approval. Sync continuation must not be blocked by generic periodic-request throttling. A01–A25/W01–W22 registry and this document are specification only; no deployment or runtime test is asserted.
Complete health response samples:
```json
{"status":"ok","service":"realtime","timestamp":"2026-10-01T08:00:00Z","dependencies":{"postgresql":"not_checked","redis":"not_checked"}}
```
```json
{"status":"unready","service":"api","timestamp":"2026-10-01T08:00:01Z","dependencies":{"postgresql":"fail","redis":"ok"}}
```
```json
{"status":"unready","service":"api","timestamp":"2026-10-01T08:00:02Z","dependencies":{"postgresql":"not_checked","redis":"not_checked"},"reason":"CONFIG_MISSING"}
```
This readiness response identifies configuration failure without disclosing the setting name or value.
The first is `/health/live` 200; the second is `/health/ready` 503. Monitoring separately measures ACK, live delivery, sync recovery, and push failures. Public metric labels exclude user IDs/tokens/message bodies; logs exclude full tokens and private message bodies.

## 7. Pending product decisions and change ledger

Pending decisions: DeviceID issuance/reuse across reinstall/account switch; foreground/activity lease and push behavior for unknown state; production page/file/heartbeat/rate values; group role and size policy; group receipt visibility; history before joining/after leaving; attachment types/size; and which historical performance/reconnect objectives remain current. Proposed A25, W21, W22, SessionContext fields, and activity/push projections are not presented as approved existing production behavior. A01–A25 and W01–W22 names and IDs are preserved; A18 removes membership, not bans. Document cross-reference/integrity review is not runtime API verification. HINE-IC-0.4 incorporates confirmed platform placement (single Web RWD application across desktop/tablet/mobile, shared SessionContext and WSS) and explicit Web push boundaries (A23 platform ios/android unchanged, browser background push requires separate PM approval).
