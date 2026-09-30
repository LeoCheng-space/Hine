# HINE-IC-0.4 — Backend A 角色 PRD

**版本：** HINE-IC-0.4  
**狀態：** 待產品核准  
**來源：** [歷史來源：HINE-IC-0.4 role PRDs](../HINE-IC-0.4-role-prds.md); 唯一現行介面規格依據為 [共同介面契約](../contracts/interface-contract.md).  
**角色目的：** 負責 WSS 交握、連線／heartbeat、短暫性 Redis／presence、活動租約、事件路由與同步入口。本 PRD 規定未來行為與驗收要求，不代表已實作或已完成測試。
**必讀／串接時查閱：** [共同介面契約](../contracts/interface-contract.md)、[驗收矩陣](../testing/acceptance-matrix.md)；各功能串接見下方 Trace／Handoff。 [返回文件導覽](../README.md)。

## 範圍

- **範圍內：** WSS handshake, connection/heartbeat, ephemeral Redis/presence, activity leases, event routing, and sync ingress; the role-specific feature cards below.
- **範圍外：** 其他角色所負責的範圍；亦不得變更共用 API／event IDs、正式資料、ACK、Cursor 或同步語意。共用欄位型別、envelope、錯誤與限制均以共同介面契約為準。
- **共用 Web 行為：** 遵循 [Web / RWD specification](../ui/web-rwd.md#web-rwd); 不得另訂 breakpoint 或重複定義版面規則。

## 功能索引

- [BA-01 — WSS 驗證與工作階段終止](#ba-01)
- [BA-02 — Heartbeat 與使用者層級在線狀態](#ba-02)
- [BA-03 — 訊息入口與持久化 ACK](#ba-03)
- [BA-04 — 送達／已讀回條轉送](#ba-04)
- [BA-05 — 跨節點散佈與群組事件路由](#ba-05)
- [BA-06 — 初始化與 feed 同步入口](#ba-06)
- [BA-07 — 裝置活動租約](#ba-07)
- [BA-08 — 速率限制、frame 防護與 WSS 錯誤](#ba-08)

## 角色目的與責任界線

負責 WSS 交握、連線／heartbeat、短暫性 Redis／presence、活動租約、事件路由與同步入口。Backend B 負責 JWT／session 權威、授權決策、持久化狀態與 PostgreSQL schema。瀏覽器版面不得衍生另一套 realtime API、event model、連線或 cursor。

<a id="ba-01"></a>
### BA-01 — WSS authentication and session termination
**Trace:** [REQ-01 Account verification and login identity](../testing/acceptance-matrix.md#req-01), [REQ-02 Credential refresh and logout transition](../testing/acceptance-matrix.md#req-02); [W01](../contracts/interface-contract.md#event-w01), [W02](../contracts/interface-contract.md#event-w02), [W17](../contracts/interface-contract.md#event-w17); [validateAccess](../contracts/interface-contract.md#internal-validate-access).
- **Precondition:** New WSS connection.
- **Normal flow:** Require [W01](../contracts/interface-contract.md#event-w01) first; validate token with BB, verify [W01](../contracts/interface-contract.md#event-w01) device binding, return [W02](../contracts/interface-contract.md#event-w02) public user/device/session generation and configured heartbeat values.
- **Failure flow:** Reject expired, revoked, wrong-device, or stale-generation session; stop new operations and close old socket when [A03](../contracts/interface-contract.md#api-a03)/[A04](../contracts/interface-contract.md#api-a04) revocation takes effect. [W17](../contracts/interface-contract.md#event-w17) may be sent before close but is not guaranteed.
- **Acceptance:** Never trust client subject_id; successful refreshed auth uses a new connection; a single device failure does not revoke other devices.
- **Handoff:** [BB-01](backend-b.md#bb-01) session state; [FA-01](frontend-a.md#fa-01)/[FB-02](frontend-b.md#fb-02) session replacement.

<a id="ba-02"></a>
### BA-02 — Heartbeat and user-level presence
**Trace:** [REQ-15 Presence and multi-device liveness](../testing/acceptance-matrix.md#req-15); [W03](../contracts/interface-contract.md#event-w03), [W04](../contracts/interface-contract.md#event-w04), [W18](../contracts/interface-contract.md#event-w18); [getDevicePresence](../contracts/interface-contract.md#internal-get-device-presence).
- **Precondition:** Authenticated socket.
- **Normal flow:** [W03](../contracts/interface-contract.md#event-w03)/[W04](../contracts/interface-contract.md#event-w04) track connection liveness. Aggregate valid user connections for [W18](../contracts/interface-contract.md#event-w18) online transitions; query device/activity separately.
- **Failure flow:** Heartbeat timeout clears that socket only. Redis unavailable means presence unknown, not offline/online certainty.
- **Acceptance:** Presence describes aggregate connectivity and never implies app foreground or message receipt.
- **Handoff:** [BB-02](backend-b.md#bb-02) presence query; [FA-07](frontend-a.md#fa-07)/[FB-04](frontend-b.md#fb-04) display.

<a id="ba-03"></a>
### BA-03 — Message ingress and persisted ACK
**Trace:** [REQ-06 Text messaging and durable ACK](../testing/acceptance-matrix.md#req-06), [REQ-07 Lost ACK, retry, and deduplication](../testing/acceptance-matrix.md#req-07); [W05](../contracts/interface-contract.md#event-w05), [W06](../contracts/interface-contract.md#event-w06), [W07](../contracts/interface-contract.md#event-w07), [W17](../contracts/interface-contract.md#event-w17); [authorize](../contracts/interface-contract.md#internal-authorize), [persistIfAbsent](../contracts/interface-contract.md#internal-persist-if-absent).
- **Precondition:** Authenticated principal, authorized conversation, valid message C1.
- **Normal flow:** Validate type/content, authorize, call transactional persistence; emit [W06](../contracts/interface-contract.md#event-w06) only after complete persisted result; route [W07](../contracts/interface-contract.md#event-w07) to authorized recipients.
- **Failure flow:** Known rollback yields no successful ACK; unknown result is OUTCOME_UNCONFIRMED; lost ACK is recovered by same C1. Redis publication failure is recoverable through [W16](../contracts/interface-contract.md#event-w16).
- **Acceptance:** The ACK never precedes message+C1 mapping+required feeds commit. Same C1 maps to same M1/event; changed payload conflicts.
- **Handoff:** [BB-04](backend-b.md#bb-04) persistence/recipients; [FA-03](frontend-a.md#fa-03) retry/merge; [QA-04](qa.md#qa-04) fault cases.

<a id="ba-04"></a>
### BA-04 — Delivery/read receipt forwarding
**Trace:** [REQ-12 Delivered/read receipt state machine](../testing/acceptance-matrix.md#req-12); [W08](../contracts/interface-contract.md#event-w08), [W09](../contracts/interface-contract.md#event-w09), [W10](../contracts/interface-contract.md#event-w10), [W19](../contracts/interface-contract.md#event-w19); [persistReceipt](../contracts/interface-contract.md#internal-persist-receipt).
- **Precondition:** Authenticated device and authorized message recipient.
- **Normal flow:** Persist monotonic receipt through BB; correlate [W19](../contracts/interface-contract.md#event-w19) to requesting [W08](../contracts/interface-contract.md#event-w08)/[W09](../contracts/interface-contract.md#event-w09); fan out [W10](../contracts/interface-contract.md#event-w10) to permitted observers and allow feed recovery.
- **Failure flow:** Reject spoofed/unrelated receipt; duplicate reports are no-ops; `read` cannot regress.
- **Acceptance:** [W19](../contracts/interface-contract.md#event-w19) request result is distinct from [W10](../contracts/interface-contract.md#event-w10) projection; canonical state is BB.
- **Handoff:** [BB-05](backend-b.md#bb-05) canonical receipt; [FA-04](frontend-a.md#fa-04) receipt projection.

<a id="ba-05"></a>
### BA-05 — Cross-node fanout and group event routing
**Trace:** [REQ-05 Group management, permissions, and membership changes](../testing/acceptance-matrix.md#req-05), [REQ-08 Cross-node live broadcast and missed-delivery recovery](../testing/acceptance-matrix.md#req-08), [REQ-11 Revocation filtering, self-notice, and multi-group sync](../testing/acceptance-matrix.md#req-11); [A14](../contracts/interface-contract.md#api-a14), [A15](../contracts/interface-contract.md#api-a15), [A16](../contracts/interface-contract.md#api-a16), [A17](../contracts/interface-contract.md#api-a17), [A18](../contracts/interface-contract.md#api-a18); [W07](../contracts/interface-contract.md#event-w07), [W11](../contracts/interface-contract.md#event-w11), [W12](../contracts/interface-contract.md#event-w12), [W15](../contracts/interface-contract.md#event-w15), [W16](../contracts/interface-contract.md#event-w16), [W20](../contracts/interface-contract.md#event-w20).
- **Precondition:** BB transaction committed message or membership change.
- **Normal flow:** Redis Pub/Sub accelerates event delivery to currently authorized sockets; preserve recipient-specific event identity.
- **Failure flow:** Lost publication is repaired through [W16](../contracts/interface-contract.md#event-w16). Recheck authorization at delivery; revoked member receives only own minimal [W12](../contracts/interface-contract.md#event-w12) and no later body.
- **Acceptance:** Group mutation event mapping is exact; ephemeral broker data is never treated as durable success.
- **Handoff:** [BB-03](backend-b.md#bb-03) committed membership/feed rows; [FA-05](frontend-a.md#fa-05) inter-node delivery/recovery; [DO-01](devops.md#do-01) routing.

<a id="ba-06"></a>
### BA-06 — Bootstrap and feed sync ingress
**Trace:** [REQ-09 First login, authorized snapshot, and history separation](../testing/acceptance-matrix.md#req-09), [REQ-10 Snapshot switch and live projection merge](../testing/acceptance-matrix.md#req-10), [REQ-11 Revocation filtering, self-notice, and multi-group sync](../testing/acceptance-matrix.md#req-11); [W13](../contracts/interface-contract.md#event-w13), [W14](../contracts/interface-contract.md#event-w14), [W15](../contracts/interface-contract.md#event-w15), [W16](../contracts/interface-contract.md#event-w16), [W17](../contracts/interface-contract.md#event-w17); [readBootstrap](../contracts/interface-contract.md#internal-read-bootstrap), [readFeed](../contracts/interface-contract.md#internal-read-feed).
- **Precondition:** Valid authenticated principal.
- **Normal flow:** [W13](../contracts/interface-contract.md#event-w13)/[W14](../contracts/interface-contract.md#event-w14) proxy consistent snapshot pages; [W15](../contracts/interface-contract.md#event-w15)/[W16](../contracts/interface-contract.md#event-w16) proxy pinned safe feed batches.
- **Failure flow:** Expired user SyncCursor returns [W17](../contracts/interface-contract.md#event-w17) SYNC_RESET_REQUIRED. Do not reset for [A08](../contracts/interface-contract.md#api-a08)/[A11](../contracts/interface-contract.md#api-a11)/[A19](../contracts/interface-contract.md#api-a19) REST cursors. A page sequence with incomplete snapshot must not claim start cursor installed.
- **Acceptance:** Hidden positions can safely advance; unauthorized content is filtered; one revoked conversation cannot stall the rest of the feed.
- **Handoff:** [BB-06](backend-b.md#bb-06) read/auth-filtered rows; [FA-05](frontend-a.md#fa-05) cursor commit/projection; [QA-03](qa.md#qa-03) recovery.

<a id="ba-07"></a>
### BA-07 — Device activity leases
**Trace:** [REQ-14 Device activity and background push](../testing/acceptance-matrix.md#req-14), [REQ-15 Presence and multi-device liveness](../testing/acceptance-matrix.md#req-15); [W21](../contracts/interface-contract.md#event-w21), [W22](../contracts/interface-contract.md#event-w22); [recordActivity](../contracts/interface-contract.md#internal-record-activity), [getDevicePresence](../contracts/interface-contract.md#internal-get-device-presence).
- **Precondition:** [W02](../contracts/interface-contract.md#event-w02) accepted active session and device.
- **Normal flow:** Verify [W21](../contracts/interface-contract.md#event-w21) device and generation; record current foreground/background state; reply [W22](../contracts/interface-contract.md#event-w22) with server validity deadline. Expose device-level query to BB.
- **Failure flow:** Reject stale session generation; duplicate state report is idempotent; Redis failure/expiry yields unknown.
- **Acceptance:** Activity never grants chat permission, is not heartbeat, and can safely inform per-device push audience.
- **Handoff:** [FA-07](frontend-a.md#fa-07) lifecycle; [BB-08](backend-b.md#bb-08) push eligibility.

<a id="ba-08"></a>
### BA-08 — Rate limiting, frame defense, and WSS errors
**Trace:** [REQ-16 Unified errors and privacy protection](../testing/acceptance-matrix.md#req-16); [W17](../contracts/interface-contract.md#event-w17) and shared candidate limits.
- **Precondition:** Any unauthenticated/authenticated frame.
- **Normal flow:** Enforce approved limits and frame constraints; emit shared [W17](../contracts/interface-contract.md#event-w17) code/message/retryable/correlation shape.
- **Failure flow:** Bound per-socket output for slow consumers; on disconnected socket do not claim error was delivered; never log token or body.
- **Acceptance:** No successful outcome is fabricated; all eventual numeric limits remain configurable and unapproved until PM/QA decision.
- **Handoff:** [QA-05](qa.md#qa-05) error/privacy acceptance; [DO-04](devops.md#do-04) operational settings.

## 決策與共用參照

- [響應式 Web 行為](../ui/web-rwd.md#web-rwd)
- [決策：Web Push 範圍](../decisions.md#decision-web-push)
- [決策：響應式 Web 版面](../decisions.md#decision-rwd)
- [返回文件導覽](../README.md)
