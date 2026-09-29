# HINE-IC-0.4 — Backend B 角色 PRD

**版本：** HINE-IC-0.4  
**狀態：** 待產品核准  
**來源：** [歷史來源：HINE-IC-0.4 role PRDs](../HINE-IC-0.4-role-prds.md); 唯一現行介面規格依據為 [共同介面契約](../contracts/interface-contract.md).  
**角色目的：** 負責 REST API、帳戶／session 權威、PostgreSQL 正式狀態、物件 metadata／GCS 授權、持久化 feed 與 push 意圖。本 PRD 規定未來行為與驗收要求，不代表已實作或已完成測試。
**必讀／串接時查閱：** [共同介面契約](../contracts/interface-contract.md)、[驗收矩陣](../testing/acceptance-matrix.md)；各功能串接見下方 Trace／Handoff。 [返回文件導覽](../README.md)。

## 範圍

- **範圍內：** REST API, account/session authority, PostgreSQL canonical state, object metadata/GCS grants, durable feed and push intents; the role-specific feature cards below.
- **範圍外：** 其他角色所負責的範圍；亦不得變更共用 API／event IDs、正式資料、ACK、Cursor 或同步語意。共用欄位型別、envelope、錯誤與限制均以共同介面契約為準。
- **共用 Web 行為：** 遵循 [Web / RWD specification](../ui/web-rwd.md#web-rwd); 不得另訂 breakpoint 或重複定義版面規則。

## 功能索引

- [BB-01 — 帳戶、工作階段與裝置識別](#bb-01)
- [BB-02 — 個人檔案與聯絡人](#bb-02)
- [BB-03 — 對話、群組與授權](#bb-03)
- [BB-04 — 交易式訊息、冪等性與持久化 push 意圖](#bb-04)
- [BB-05 — 歷史紀錄與回條權威](#bb-05)
- [BB-06 — 快照與持久化使用者 feed](#bb-06)
- [BB-07 — 附件、頭像與簽署傳輸](#bb-07)
- [BB-08 — Push token 儲存與背景派送](#bb-08)

## 角色目的與責任界線

[A01](../contracts/interface-contract.md#api-a01)–[A25](../contracts/interface-contract.md#api-a25), account/session authority, PostgreSQL canonical state, object metadata/GCS grants, durable feed and push intents. Does not own client sockets and does not use Redis as message storage. All browser layouts use the same REST contracts, models, authorization, and durable feeds; do not duplicate business APIs by device form factor.

<a id="bb-01"></a>
### BB-01 — Accounts, session, and device identity
**Trace:** [REQ-01 Account verification and login identity](../testing/acceptance-matrix.md#req-01), [REQ-02 Credential refresh and logout transition](../testing/acceptance-matrix.md#req-02); [A01](../contracts/interface-contract.md#api-a01), [A02](../contracts/interface-contract.md#api-a02), [A03](../contracts/interface-contract.md#api-a03), [A04](../contracts/interface-contract.md#api-a04); [validateAccess](../contracts/interface-contract.md#internal-validate-access).
- **Precondition:** Registration/login/refresh/logout request.
- **Normal flow:** Persist account credentials safely; authenticate [A02](../contracts/interface-contract.md#api-a02); bind or issue device_id; issue AccessSession; advance session generation on [A03](../contracts/interface-contract.md#api-a03); revoke current device/session on [A04](../contracts/interface-contract.md#api-a04).
- **Failure flow:** Serialize refresh/logout race; stale/revoked cookie cannot issue a still-valid socket session. Device ID alone cannot authenticate or cross-bind another user.
- **Acceptance:** [A05](../contracts/interface-contract.md#api-a05) `UserProfile.id` equals only the public `user_id` in the current [A02](../contracts/interface-contract.md#api-a02)/[A03](../contracts/interface-contract.md#api-a03) AccessSession and [W02](../contracts/interface-contract.md#event-w02). Compare `device_id` and `session_generation` strictly between the matching [A02](../contracts/interface-contract.md#api-a02)/[A03](../contracts/interface-contract.md#api-a03) AccessSession and [W02](../contracts/interface-contract.md#event-w02); [A05](../contracts/interface-contract.md#api-a05) has neither field. Never expose `subject_id`.
- **Handoff:** [FB-01](frontend-b.md#fb-01) AccessSession; [BA-01](backend-a.md#ba-01) session validation.

<a id="bb-02"></a>
### BB-02 — Profiles and contacts
**Trace:** [REQ-03 Profile, avatar, and contacts](../testing/acceptance-matrix.md#req-03); [A05](../contracts/interface-contract.md#api-a05), [A06](../contracts/interface-contract.md#api-a06), [A07](../contracts/interface-contract.md#api-a07), [A08](../contracts/interface-contract.md#api-a08), [A09](../contracts/interface-contract.md#api-a09), [A10](../contracts/interface-contract.md#api-a10).
- **Precondition:** Authenticated caller and relevant user/contact authorization.
- **Normal flow:** Maintain own profile/contacts, return distinct self Profile vs public Summary, require ready own avatar on [A06](../contracts/interface-contract.md#api-a06).
- **Failure flow:** Prevent email or hidden avatar disclosure; report unknown transient presence as unknown; invalid list cursor affects only its REST query.
- **Acceptance:** Required projection fields/nullability match common dictionary; contact duplicate does not duplicate row; removal does not erase conversation data.
- **Handoff:** [FB-03](frontend-b.md#fb-03)/[FB-04](frontend-b.md#fb-04) profile/contact; [FA-06](frontend-a.md#fa-06) summaries; [BA-02](backend-a.md#ba-02) ephemeral presence.

<a id="bb-03"></a>
### BB-03 — Conversations, groups, and authorization
**Trace:** [REQ-04 Direct-chat navigation and creation](../testing/acceptance-matrix.md#req-04), [REQ-05 Group management, permissions, and membership changes](../testing/acceptance-matrix.md#req-05), [REQ-11 Revocation filtering, self-notice, and multi-group sync](../testing/acceptance-matrix.md#req-11); [A11](../contracts/interface-contract.md#api-a11), [A12](../contracts/interface-contract.md#api-a12), [A13](../contracts/interface-contract.md#api-a13), [A14](../contracts/interface-contract.md#api-a14), [A15](../contracts/interface-contract.md#api-a15), [A16](../contracts/interface-contract.md#api-a16), [A17](../contracts/interface-contract.md#api-a17), [A18](../contracts/interface-contract.md#api-a18); [W11](../contracts/interface-contract.md#event-w11), [W12](../contracts/interface-contract.md#event-w12), [W20](../contracts/interface-contract.md#event-w20); [authorize](../contracts/interface-contract.md#internal-authorize).
- **Precondition:** Current member/admin/self-leave policy for requested operation.
- **Normal flow:** Read direct/group projections; create unique direct conversation; transact membership/title/role and required feed updates.
- **Failure flow:** Reject unauthorized operation, protect last-admin invariant, enforce post-removal authorization on history/download and future feed. No ban state/operation.
- **Acceptance:** [A14](../contracts/interface-contract.md#api-a14)/[A16](../contracts/interface-contract.md#api-a16) emit [W11](../contracts/interface-contract.md#event-w11), [A15](../contracts/interface-contract.md#api-a15)/[A17](../contracts/interface-contract.md#api-a17) [W20](../contracts/interface-contract.md#event-w20), [A18](../contracts/interface-contract.md#api-a18) [W12](../contracts/interface-contract.md#event-w12). Membership version and REST response correspond to committed state; feed mutation is committed before Pub/Sub.
- **Handoff:** [FB-05](frontend-b.md#fb-05) REST projection; [BA-05](backend-a.md#ba-05)/[FA-05](frontend-a.md#fa-05) committed events; policy decisions with PM.

<a id="bb-04"></a>
### BB-04 — Transactional messages, idempotency, and durable push intent
**Trace:** [REQ-06 Text messaging and durable ACK](../testing/acceptance-matrix.md#req-06), [REQ-07 Lost ACK, retry, and deduplication](../testing/acceptance-matrix.md#req-07), [REQ-08 Cross-node live broadcast and missed-delivery recovery](../testing/acceptance-matrix.md#req-08), [REQ-14 Device activity and background push](../testing/acceptance-matrix.md#req-14); [W05](../contracts/interface-contract.md#event-w05), [W06](../contracts/interface-contract.md#event-w06), [W07](../contracts/interface-contract.md#event-w07); [authorize](../contracts/interface-contract.md#internal-authorize), [persistIfAbsent](../contracts/interface-contract.md#internal-persist-if-absent), [dispatchPushIntent](../contracts/interface-contract.md#internal-dispatch-push-intent).
- **Precondition:** Authorized sender, message shape, stable C1.
- **Normal flow:** Transactionally write canonical message, C1 mapping, every required per-user feed row, and eligible per-device push intent. Return `created` or `existing_same` with persisted result.
- **Failure flow:** Different payload under same C1 is conflict; distinguish known rollback from uncertain outcome; never write successful ACK evidence before required rows commit.
- **Acceptance:** Retried send produces same M1 and stable event ID; push provider failure cannot alter message/receipt state.
- **Handoff:** [BA-03](backend-a.md#ba-03) transaction result; [FA-03](frontend-a.md#fa-03) C1 merge; [QA-04](qa.md#qa-04) fault outcomes.

<a id="bb-05"></a>
### BB-05 — History and receipt authority
**Trace:** [REQ-09 First login, authorized snapshot, and history separation](../testing/acceptance-matrix.md#req-09), [REQ-12 Delivered/read receipt state machine](../testing/acceptance-matrix.md#req-12); [A19](../contracts/interface-contract.md#api-a19); [W08](../contracts/interface-contract.md#event-w08), [W09](../contracts/interface-contract.md#event-w09), [W10](../contracts/interface-contract.md#event-w10), [W19](../contracts/interface-contract.md#event-w19); [persistReceipt](../contracts/interface-contract.md#internal-persist-receipt).
- **Precondition:** Current permission to read message/history or report receipt.
- **Normal flow:** Query history by separate history cursor; persist delivery/read monotonically; include old-message status corrections in feed/bootstrap projection.
- **Failure flow:** [A19](../contracts/interface-contract.md#api-a19) cursor error affects only that history view; authorization loss blocks further content. Duplicate receipt does not create redundant status event.
- **Acceptance:** Same canonical message ID appears in live, history, and sync; [A19](../contracts/interface-contract.md#api-a19) order is independent of user feed cursor.
- **Handoff:** [FA-04](frontend-a.md#fa-04) message/receipt projection; [BA-04](backend-a.md#ba-04) forwarding.

<a id="bb-06"></a>
### BB-06 — Snapshot and durable user feed
**Trace:** [REQ-09 First login, authorized snapshot, and history separation](../testing/acceptance-matrix.md#req-09), [REQ-10 Snapshot switch and live projection merge](../testing/acceptance-matrix.md#req-10), [REQ-11 Revocation filtering, self-notice, and multi-group sync](../testing/acceptance-matrix.md#req-11); [W13](../contracts/interface-contract.md#event-w13), [W14](../contracts/interface-contract.md#event-w14), [W15](../contracts/interface-contract.md#event-w15), [W16](../contracts/interface-contract.md#event-w16); [readBootstrap](../contracts/interface-contract.md#internal-read-bootstrap), [readFeed](../contracts/interface-contract.md#internal-read-feed).
- **Precondition:** Authenticated subject and supported snapshot/feed cursor.
- **Normal flow:** Read authorized snapshot content and H from one consistent view; paginate by same snapshot id; scan per-user feed in safe committed order with pinned continuation boundary.
- **Failure flow:** Snapshot expiry creates a fresh consistent snapshot; do not install H before all pages and local switch. Filter revoked body while allowing safe advancement and other conversation rows.
- **Acceptance:** The agreed bounded bootstrap scope and current state at H are represented by the completed snapshot; later durable feed positions remain accessible through [W16](../contracts/interface-contract.md#event-w16), and older authorized history remains available through [A19](../contracts/interface-contract.md#api-a19). REST cursor errors do not reset the feed.
- **Handoff:** [BA-06](backend-a.md#ba-06) sync reads; [FA-05](frontend-a.md#fa-05) cursor application; [QA-03](qa.md#qa-03) recovery.

<a id="bb-07"></a>
### BB-07 — Attachments, avatars, and signed transfer
**Trace:** [REQ-03 Profile, avatar, and contacts](../testing/acceptance-matrix.md#req-03), [REQ-13 Images, files, and upload renewal](../testing/acceptance-matrix.md#req-13); [A06](../contracts/interface-contract.md#api-a06), [A20](../contracts/interface-contract.md#api-a20), [A21](../contracts/interface-contract.md#api-a21), [A22](../contracts/interface-contract.md#api-a22), [A25](../contracts/interface-contract.md#api-a25).
- **Precondition:** Owner and valid scope; conversation authorization where applicable.
- **Normal flow:** Store metadata, create short-lived GCS upload/download grant, verify bytes and hash on completion, permit ready attachment use; renewal preserves attachment ID and creates current attempt.
- **Failure flow:** Reject old attempts, wrong metadata/type/size and unauthorized downloads. Avatar scope must have null conversation_id and work without a chat.
- **Acceptance:** [A22](../contracts/interface-contract.md#api-a22) reauthorizes each retrieval; signed URL and GCS object key remain private; failed upload does not become ready.
- **Handoff:** [FA-06](frontend-a.md#fa-06)/[FB-03](frontend-b.md#fb-03) transfer and metadata; [DO-02](devops.md#do-02) bucket/secrets.

<a id="bb-08"></a>
### BB-08 — Push token store and background dispatch
**Trace:** [REQ-14 Device activity and background push](../testing/acceptance-matrix.md#req-14); [A23](../contracts/interface-contract.md#api-a23), [A24](../contracts/interface-contract.md#api-a24); [W21](../contracts/interface-contract.md#event-w21), [W22](../contracts/interface-contract.md#event-w22); [getDevicePresence](../contracts/interface-contract.md#internal-get-device-presence), [dispatchPushIntent](../contracts/interface-contract.md#internal-dispatch-push-intent).
- **Precondition:** Valid bound device token and committed eligible message.
- **Normal flow:** Store token securely; after durable commit evaluate each recipient device activity; suppress fresh foreground, send generic hint for background/unknown.
- **Failure flow:** Provider failure retries durable intent; permanent invalid token retires binding. [A04](../contracts/interface-contract.md#api-a04) current-device logout revokes binding per proposal. No message body in push; no receipt mutation.
- **Acceptance:** Push is a hint, not delivery/read evidence; opening notification gets authorized content through sync. [A23](../contracts/interface-contract.md#api-a23)/[A24](../contracts/interface-contract.md#api-a24) remain the iOS/android token contract; browser push has no subscription/provider schema here and is pending the Web-push policy/contract decision, not an implied implementation.
- **Handoff:** [FA-07](frontend-a.md#fa-07)/[BA-07](backend-a.md#ba-07) activity; [FB-06](frontend-b.md#fb-06) token workflow; [DO-02](devops.md#do-02)/[DO-04](devops.md#do-04) credentials/monitoring.

## 決策與共用參照

- [響應式 Web 行為](../ui/web-rwd.md#web-rwd)
- [決策：Web Push 範圍](../decisions.md#decision-web-push)；A23/A24 僅定義 iOS／Android 原生推播 token，瀏覽器推播未定義且待另行核准。
- [決策：響應式 Web 版面](../decisions.md#decision-rwd)
- [返回文件導覽](../README.md)
