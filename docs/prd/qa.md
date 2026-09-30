# HINE-IC-0.4 — QA 角色 PRD

**版本：** HINE-IC-0.4  
**狀態：** 待產品核准  
**來源：** [歷史來源：HINE-IC-0.4 role PRDs](../HINE-IC-0.4-role-prds.md); 唯一現行介面規格依據為 [共同介面契約](../contracts/interface-contract.md).  
**角色目的：** 負責行為、schema、隱私、復原與效能驗收。本 PRD 規定未來行為與驗收要求，不代表已實作或已完成測試。
**必讀／串接時查閱：** [系統架構](../architecture/README.md)、[共同介面契約](../contracts/interface-contract.md)、[驗收矩陣](../testing/acceptance-matrix.md)；各功能串接見下方 Trace／Handoff。 [返回文件導覽](../README.md)。

## 範圍

- **範圍內：** behavior, schema, privacy, recovery, and performance acceptance; the role-specific feature cards below.
- **範圍外：** 其他角色所負責的範圍；亦不得變更共用 API／event IDs、正式資料、ACK、Cursor 或同步語意。共用欄位型別、envelope、錯誤與限制均以共同介面契約為準。
- **共用 Web 行為：** 遵循 [Web / RWD specification](../ui/web-rwd.md#web-rwd); 不得另訂 breakpoint 或重複定義版面規則。

## 功能索引

- [QA-01 — 介面契約與 schema 符合性](#qa-01)
- [QA-02 — 工作階段、更新、活動與多裝置行為](#qa-02)
- [QA-03 — 快照／feed 復原與 cursor 隔離](#qa-03)
- [QA-04 — 跨模組行為與故障注入](#qa-04)
- [QA-05 — 隱私、設定與效能驗收](#qa-05)
- [QA-06 — Web 響應式、輸入、路由與 push 政策驗收](#qa-06)

## 角色目的與責任界線

定義行為、schema、隱私、復原與效能驗收。僅於已有實作與核准測試環境後執行產品測試；本 PRD 未記錄任何測試執行結果。

<a id="qa-01"></a>
### QA-01 — Interface contract and schema compliance
**Trace:** [REQ-01 Account verification and login identity](../testing/acceptance-matrix.md#req-01), [REQ-02 Credential refresh and logout transition](../testing/acceptance-matrix.md#req-02), [REQ-03 Profile, avatar, and contacts](../testing/acceptance-matrix.md#req-03), [REQ-04 Direct-chat navigation and creation](../testing/acceptance-matrix.md#req-04), [REQ-05 Group management, permissions, and membership changes](../testing/acceptance-matrix.md#req-05), [REQ-06 Text messaging and durable ACK](../testing/acceptance-matrix.md#req-06); [介面定位](../contracts/interface-contract.md#rest-api), [REST API A01–A25](../contracts/interface-contract.md#rest-api), [WebSocket W01–W22](../contracts/interface-contract.md#websocket-events).
**REST 條目：** [A01](../contracts/interface-contract.md#api-a01), [A02](../contracts/interface-contract.md#api-a02), [A03](../contracts/interface-contract.md#api-a03), [A04](../contracts/interface-contract.md#api-a04), [A05](../contracts/interface-contract.md#api-a05), [A06](../contracts/interface-contract.md#api-a06), [A07](../contracts/interface-contract.md#api-a07), [A08](../contracts/interface-contract.md#api-a08), [A09](../contracts/interface-contract.md#api-a09), [A10](../contracts/interface-contract.md#api-a10), [A11](../contracts/interface-contract.md#api-a11), [A12](../contracts/interface-contract.md#api-a12), [A13](../contracts/interface-contract.md#api-a13).
**REST 條目（續）：** [A14](../contracts/interface-contract.md#api-a14), [A15](../contracts/interface-contract.md#api-a15), [A16](../contracts/interface-contract.md#api-a16), [A17](../contracts/interface-contract.md#api-a17), [A18](../contracts/interface-contract.md#api-a18), [A19](../contracts/interface-contract.md#api-a19), [A20](../contracts/interface-contract.md#api-a20), [A21](../contracts/interface-contract.md#api-a21), [A22](../contracts/interface-contract.md#api-a22), [A23](../contracts/interface-contract.md#api-a23), [A24](../contracts/interface-contract.md#api-a24), [A25](../contracts/interface-contract.md#api-a25).
**WebSocket 條目：** [W01](../contracts/interface-contract.md#event-w01), [W02](../contracts/interface-contract.md#event-w02), [W03](../contracts/interface-contract.md#event-w03), [W04](../contracts/interface-contract.md#event-w04), [W05](../contracts/interface-contract.md#event-w05), [W06](../contracts/interface-contract.md#event-w06), [W07](../contracts/interface-contract.md#event-w07), [W08](../contracts/interface-contract.md#event-w08), [W09](../contracts/interface-contract.md#event-w09), [W10](../contracts/interface-contract.md#event-w10), [W11](../contracts/interface-contract.md#event-w11).
**WebSocket 條目（續）：** [W12](../contracts/interface-contract.md#event-w12), [W13](../contracts/interface-contract.md#event-w13), [W14](../contracts/interface-contract.md#event-w14), [W15](../contracts/interface-contract.md#event-w15), [W16](../contracts/interface-contract.md#event-w16), [W17](../contracts/interface-contract.md#event-w17), [W18](../contracts/interface-contract.md#event-w18), [W19](../contracts/interface-contract.md#event-w19), [W20](../contracts/interface-contract.md#event-w20), [W21](../contracts/interface-contract.md#event-w21), [W22](../contracts/interface-contract.md#event-w22).
- **Precondition:** One version of common dictionary, endpoint/event registry, and sample payloads.
- **Normal flow:** Validate required fields, nullability, method/path, response status, correlation, authorization, and event mapping.
- **Failure flow:** Missing/extra wrong-state fields, wrong event mapping, summary used in place of detail, or leaked subject_id are contract failures.
- **Acceptance:** Every consumer references the shared contract and the central Web/RWD chapter; no role duplicates its layout bands or creates platform-specific business schemas.
- **Handoff:** Schema/report findings to [FA-01](frontend-a.md#fa-01), [FB-01](frontend-b.md#fb-01), [BA-01](backend-a.md#ba-01), [BB-01](backend-b.md#bb-01).

<a id="qa-02"></a>
### QA-02 — Session, refresh, activity, and multi-device behavior
**Trace:** [REQ-01 Account verification and login identity](../testing/acceptance-matrix.md#req-01), [REQ-02 Credential refresh and logout transition](../testing/acceptance-matrix.md#req-02), [REQ-14 Device activity and background push](../testing/acceptance-matrix.md#req-14), [REQ-15 Presence and multi-device liveness](../testing/acceptance-matrix.md#req-15); [A02](../contracts/interface-contract.md#api-a02), [A03](../contracts/interface-contract.md#api-a03), [A04](../contracts/interface-contract.md#api-a04); [W01](../contracts/interface-contract.md#event-w01), [W02](../contracts/interface-contract.md#event-w02), [W03](../contracts/interface-contract.md#event-w03), [W04](../contracts/interface-contract.md#event-w04), [W18](../contracts/interface-contract.md#event-w18), [W21](../contracts/interface-contract.md#event-w21), [W22](../contracts/interface-contract.md#event-w22); [validateAccess](../contracts/interface-contract.md#internal-validate-access), [getDevicePresence](../contracts/interface-contract.md#internal-get-device-presence), [recordActivity](../contracts/interface-contract.md#internal-record-activity).
- **Precondition:** Valid account, two device sessions, controllable socket lifecycle.
- **Normal flow:** Verify login/session binding; refresh, close old socket, create new [W01](../contracts/interface-contract.md#event-w01)/[W02](../contracts/interface-contract.md#event-w02), send first [W21](../contracts/interface-contract.md#event-w21), and resume saved cursor; exercise background/foreground and lease renewal.
- **Failure flow:** Exercise refresh/logout race, old-generation late activity, missed background frame, lease expiry, and Redis uncertainty.
- **Acceptance:** No same-socket reauthentication; stale session cannot resume; lease expiry becomes unknown; failure of one device does not log out another.
- **Handoff:** State-transition cases to [FB-02](frontend-b.md#fb-02), [FA-07](frontend-a.md#fa-07), [BA-01](backend-a.md#ba-01), [BB-08](backend-b.md#bb-08).

<a id="qa-03"></a>
### QA-03 — Snapshot/feed recovery and cursor isolation
**Trace:** [REQ-09 First login, authorized snapshot, and history separation](../testing/acceptance-matrix.md#req-09), [REQ-10 Snapshot switch and live projection merge](../testing/acceptance-matrix.md#req-10), [REQ-11 Revocation filtering, self-notice, and multi-group sync](../testing/acceptance-matrix.md#req-11); [A08](../contracts/interface-contract.md#api-a08), [A11](../contracts/interface-contract.md#api-a11), [A19](../contracts/interface-contract.md#api-a19); [W13](../contracts/interface-contract.md#event-w13), [W14](../contracts/interface-contract.md#event-w14), [W15](../contracts/interface-contract.md#event-w15), [W16](../contracts/interface-contract.md#event-w16), [W17](../contracts/interface-contract.md#event-w17); [readBootstrap](../contracts/interface-contract.md#internal-read-bootstrap), [readFeed](../contracts/interface-contract.md#internal-read-feed).
- **Precondition:** Multi-page snapshot with one snapshot_id and independent REST list/history cursors.
- **Normal flow:** Ensure intermediate page does not install H; after all staged pages and atomic local switch, install H and continue feed. Exercise hidden filtered positions.
- **Failure flow:** Expire each REST cursor independently, then expire user feed cursor.
- **Acceptance:** Each [A08](../contracts/interface-contract.md#api-a08)/[A11](../contracts/interface-contract.md#api-a11)/[A19](../contracts/interface-contract.md#api-a19) failure refetches only its own query; only WSS feed reset triggers [W13](../contracts/interface-contract.md#event-w13). No missed authorized event or unauthorized body; a revoked conversation does not block another.
- **Handoff:** Cursor boundaries/expected local state to [FA-05](frontend-a.md#fa-05), [FB-04](frontend-b.md#fb-04), [BA-06](backend-a.md#ba-06), [BB-06](backend-b.md#bb-06).

<a id="qa-04"></a>
### QA-04 — Cross-module behavior and failure injection
**Trace:** [REQ-03 Profile, avatar, and contacts](../testing/acceptance-matrix.md#req-03), [REQ-04 Direct-chat navigation and creation](../testing/acceptance-matrix.md#req-04), [REQ-05 Group management, permissions, and membership changes](../testing/acceptance-matrix.md#req-05), [REQ-06 Text messaging and durable ACK](../testing/acceptance-matrix.md#req-06), [REQ-07 Lost ACK, retry, and deduplication](../testing/acceptance-matrix.md#req-07), [REQ-08 Cross-node live broadcast and missed-delivery recovery](../testing/acceptance-matrix.md#req-08), [REQ-12 Delivered/read receipt state machine](../testing/acceptance-matrix.md#req-12), [REQ-13 Images, files, and upload renewal](../testing/acceptance-matrix.md#req-13), [REQ-14 Device activity and background push](../testing/acceptance-matrix.md#req-14).
**介面定位：** [A05](../contracts/interface-contract.md#api-a05), [A06](../contracts/interface-contract.md#api-a06), [A14](../contracts/interface-contract.md#api-a14), [A15](../contracts/interface-contract.md#api-a15), [A16](../contracts/interface-contract.md#api-a16), [A17](../contracts/interface-contract.md#api-a17), [A18](../contracts/interface-contract.md#api-a18), [A20](../contracts/interface-contract.md#api-a20), [A21](../contracts/interface-contract.md#api-a21), [A22](../contracts/interface-contract.md#api-a22), [A23](../contracts/interface-contract.md#api-a23), [A24](../contracts/interface-contract.md#api-a24), [A25](../contracts/interface-contract.md#api-a25); [W05](../contracts/interface-contract.md#event-w05), [W06](../contracts/interface-contract.md#event-w06), [W07](../contracts/interface-contract.md#event-w07), [W08](../contracts/interface-contract.md#event-w08), [W09](../contracts/interface-contract.md#event-w09), [W10](../contracts/interface-contract.md#event-w10), [W11](../contracts/interface-contract.md#event-w11), [W12](../contracts/interface-contract.md#event-w12), [W13](../contracts/interface-contract.md#event-w13), [W14](../contracts/interface-contract.md#event-w14), [W15](../contracts/interface-contract.md#event-w15), [W16](../contracts/interface-contract.md#event-w16), [W19](../contracts/interface-contract.md#event-w19), [W20](../contracts/interface-contract.md#event-w20).
**內部操作：** [authorize](../contracts/interface-contract.md#internal-authorize), [persistIfAbsent](../contracts/interface-contract.md#internal-persist-if-absent), [persistReceipt](../contracts/interface-contract.md#internal-persist-receipt), [readBootstrap](../contracts/interface-contract.md#internal-read-bootstrap), [readFeed](../contracts/interface-contract.md#internal-read-feed), [dispatchPushIntent](../contracts/interface-contract.md#internal-dispatch-push-intent).
- **Precondition:** Isolated users, conversations, attachment storage, and push provider test setup.
- **Normal flow:** Exercise zero-conversation avatar, A25 renewal, group A14–A18 mappings, ACK recovery, receipt recovery, background hint, and return-to-app sync.
- **Failure flow:** Inject known rollback, commit-before-ACK loss, ACK-before-publication interruption, stale upload attempt, wrong MIME, revoked membership, and provider failure.
- **Acceptance:** Original C1 recovers one M1; complete commit precedes ACK; A14/A16→W11, A15/A17→W20, A18→W12; provider errors do not alter receipts.
- **Handoff:** Reproducible failure checkpoints to [FA-03](frontend-a.md#fa-03), [BA-03](backend-a.md#ba-03), [BB-04](backend-b.md#bb-04), [BB-05](backend-b.md#bb-05), [BB-07](backend-b.md#bb-07), [BB-08](backend-b.md#bb-08).

<a id="qa-05"></a>
### QA-05 — Privacy, configuration, and performance acceptance
**Trace:** [REQ-16 Unified errors and privacy protection](../testing/acceptance-matrix.md#req-16), [REQ-17 Infrastructure, health probes, and CI delivery](../testing/acceptance-matrix.md#req-17), [REQ-18 Performance validation and capacity boundaries](../testing/acceptance-matrix.md#req-18).
**介面定位：** [W17](../contracts/interface-contract.md#event-w17), [HealthResponse](../contracts/interface-contract.md#data-dictionary), [deployment settings](../contracts/interface-contract.md#deployment-config).
- **Precondition:** PM-approved operating values/workload and isolated credentials.
- **Normal flow:** Validate missing-config/readiness response, privacy-safe logs, and independently measured ACK, end-to-end delivery, reconnect, sync recovery, and feed contention.
- **Failure flow:** Reject secret/body leakage, false healthy state, and untested scale claims. Keep unapproved historical SLOs out of pass/fail criteria.
- **Acceptance:** Results state exact environment/workload; no capacity claim without measurement. No product test or performance result is asserted by these PRDs.
- **Handoff:** Findings to PM, [DO-04](devops.md#do-04), [DO-05](devops.md#do-05), [BA-08](backend-a.md#ba-08), [BB-04](backend-b.md#bb-04).

<a id="qa-06"></a>
### QA-06 — Web responsive, input, route, and push-policy acceptance
**Trace:** [REQ-19 Shared responsive Web pages](../testing/acceptance-matrix.md#req-19), [REQ-20 Responsive chat interaction and read state](../testing/acceptance-matrix.md#req-20), [REQ-21 Web deep links and authorized route return](../testing/acceptance-matrix.md#req-21), [REQ-22 Web Push policy scope and acceptance governance](../testing/acceptance-matrix.md#req-22); [Web/RWD](../ui/web-rwd.md#web-rwd), [A12](../contracts/interface-contract.md#api-a12), [A19](../contracts/interface-contract.md#api-a19), [A23](../contracts/interface-contract.md#api-a23), [A24](../contracts/interface-contract.md#api-a24); [W08](../contracts/interface-contract.md#event-w08), [W09](../contracts/interface-contract.md#event-w09).
- **Precondition:** One shared Web build, candidate-supported browsers, controllable viewport/input/orientation, test accounts, and proposed acceptance criteria.
- **Normal flow:** Run browser/version × sample viewport × orientation × zoom cases, using mouse/touch and physical/virtual keyboard plus Chinese IME on applicable controls. Sample viewports are 320, 375, 767, 768, 1024, 1199, 1200, and 1440 CSS px (test sizes, not breakpoint definitions); include portrait/landscape, 200% zoom, all page families and candidate UI deep links/auth return. Exercise composer visibility, anchor preservation through orientation/history prepend, candidate auto-follow/read visibility thresholds, and browser-push scope as governance only. Browser/version selections are candidates pending product/QA approval and must be recorded.
- **Failure flow:** Verify no second WSS/session/cursor on reflow, no IME accidental send, no forced history scroll, no [W09](../contracts/interface-contract.md#event-w09) without the candidate actual-visibility conditions, no protected data before authorization, and no API/WSS path handled by Web-shell fallback. Do not infer browser push from [A23](../contracts/interface-contract.md#api-a23)/[A24](../contracts/interface-contract.md#api-a24) or native App/PWA behavior.
- **Acceptance:** Record browser/version, viewport/orientation/zoom, input modality, route, and observed layout/state per case. Distinguish proposed layout and interaction thresholds from approved behavior; [W08](../contracts/interface-contract.md#event-w08) remains independent of [W09](../contracts/interface-contract.md#event-w09), and [REQ-22](../testing/acceptance-matrix.md#req-22) remains a browser-push approval/contract prerequisite. No product test result is asserted here.
- **Handoff:** Browser/width/input/state findings and policy prerequisites to [FA-08](frontend-a.md#fa-08), [FB-06](frontend-b.md#fb-06), [FB-07](frontend-b.md#fb-07), [DO-06](devops.md#do-06), [BA-04](backend-a.md#ba-04), [BB-08](backend-b.md#bb-08), and PM.

## 決策與共用參照

- [響應式 Web 行為](../ui/web-rwd.md#web-rwd)
- [決策：Web Push 範圍](../decisions.md#decision-web-push)
- [決策：響應式 Web 版面](../decisions.md#decision-rwd)
- [返回文件導覽](../README.md)
