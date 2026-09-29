# HINE-IC-0.4 — Frontend A 角色 PRD

**版本：** HINE-IC-0.4  
**狀態：** 待產品核准  
**來源：** [歷史來源：HINE-IC-0.4 role PRDs](../HINE-IC-0.4-role-prds.md); 唯一現行介面規格依據為 [共同介面契約](../contracts/interface-contract.md).  
**角色目的：** 負責聊天 UI、應用程式範圍的 WSS、訊息狀態與本機同步投影。本 PRD 規定未來行為與驗收要求，不代表已實作或已完成測試。
**必讀／串接時查閱：** [共同介面契約](../contracts/interface-contract.md); [驗收矩陣](../testing/acceptance-matrix.md); [Web/RWD 規格](../ui/web-rwd.md#web-rwd); [決策：Web Push](../decisions.md#decision-web-push); [文件導覽](../README.md)。

## 範圍

- **範圍內：** chat UI, app-scoped WSS, message state, and local sync projection; the role-specific feature cards below.
- **範圍外：** 其他角色所負責的範圍；亦不得變更共用 API／event IDs、正式資料、ACK、Cursor 或同步語意。共用欄位型別、envelope、錯誤與限制均以共同介面契約為準。
- **共用 Web 行為：** 遵循 [Web / RWD specification](../ui/web-rwd.md#web-rwd); 不得另訂 breakpoint 或重複定義版面規則。

## 功能索引

- [FA-01 — 建立 WSS 工作階段與狀態](#fa-01)
- [FA-02 — Token 更新與登出清理](#fa-02)
- [FA-03 — 即時傳送與持久化 ACK](#fa-03)
- [FA-04 — 送達與已讀回條](#fa-04)
- [FA-05 — 聊天導覽、歷史紀錄、初始化與同步](#fa-05)
- [FA-06 — 對話附件、更新與下載](#fa-06)
- [FA-07 — App 活動與租約更新](#fa-07)
- [FA-08 — 響應式 Web 聊天互動](#fa-08)

## 角色目的與責任界線

負責聊天 UI、應用程式範圍的 WSS、訊息狀態與本機同步投影，並提供 `openChat(conversation_id)`。不負責 refresh cookies、簽發 JWT、簽署 GCS URL 或傳送 push notification。

<a id="fa-01"></a>
### FA-01 — WSS session establishment and state
**Trace:** [REQ-01 Account verification and login identity](../testing/acceptance-matrix.md#req-01), [REQ-02 Credential refresh and logout transition](../testing/acceptance-matrix.md#req-02), [REQ-15 Presence and multi-device liveness](../testing/acceptance-matrix.md#req-15); [W01](../contracts/interface-contract.md#event-w01), [W02](../contracts/interface-contract.md#event-w02), [W03](../contracts/interface-contract.md#event-w03), [W04](../contracts/interface-contract.md#event-w04), [W17](../contracts/interface-contract.md#event-w17), [W21](../contracts/interface-contract.md#event-w21).
- **Precondition:** FB supplies the current authenticated SessionContext (public user_id, device_id, access token, generation).
- **Normal flow:** Establish the unique WSS; send [W01](../contracts/interface-contract.md#event-w01) as first business frame; validate [W02](../contracts/interface-contract.md#event-w02) identity/device/generation; use [W02](../contracts/interface-contract.md#event-w02) `heartbeat_interval_seconds` to schedule [W03](../contracts/interface-contract.md#event-w03) and `heartbeat_timeout_seconds` to detect missing [W04](../contracts/interface-contract.md#event-w04); after successful auth report initial [W21](../contracts/interface-contract.md#event-w21).
- **Failure flow:** On [W17](../contracts/interface-contract.md#event-w17), disconnect, expiry, or revoked session, stop sending business commands; ask FB to refresh/re-authenticate. Do not preserve a second socket as fallback.
- **Acceptance:** Route changes do not create another socket. [A03](../contracts/interface-contract.md#api-a03) handoff causes a new socket, not same-socket authentication. [A04](../contracts/interface-contract.md#api-a04) promptly tears down the current connection and clears account-local auth state.
**Handoff:** [FB-01](../prd/frontend-b.md#fb-01) SessionContext/auth transition; [BA-01](../prd/backend-a.md#ba-01)/[BB-01](../prd/backend-b.md#bb-01) session validation.

<a id="fa-02"></a>
### FA-02 — Token refresh and logout teardown
**Trace:** [REQ-02 Credential refresh and logout transition](../testing/acceptance-matrix.md#req-02); [A03](../contracts/interface-contract.md#api-a03), [A04](../contracts/interface-contract.md#api-a04), [W01](../contracts/interface-contract.md#event-w01), [W02](../contracts/interface-contract.md#event-w02), [W13](../contracts/interface-contract.md#event-w13), [W14](../contracts/interface-contract.md#event-w14), [W15](../contracts/interface-contract.md#event-w15), [W16](../contracts/interface-contract.md#event-w16), [W17](../contracts/interface-contract.md#event-w17).
- **Precondition:** Existing WSS and saved user feed cursor.
- **Normal flow:** After FB publishes [A03](../contracts/interface-contract.md#api-a03)'s new AccessSession, stop business frames on old socket, close it, open a new socket, send [W01](../contracts/interface-contract.md#event-w01)/receive [W02](../contracts/interface-contract.md#event-w02), send [W21](../contracts/interface-contract.md#event-w21), and resume from the saved cursor. On [A04](../contracts/interface-contract.md#api-a04), close the socket and clear the current account's active projection.
- **Failure flow:** Refresh failure does not trigger same-socket [W01](../contracts/interface-contract.md#event-w01); a disconnect retains any unconfirmed send's original C1.
- **Acceptance:** No same-socket reauthentication path; refresh uses a new connection and saved cursor, while logout tears down current-account realtime state.
**Handoff:** [FB-02](../prd/frontend-b.md#fb-02) connection replacement; [BA-01](../prd/backend-a.md#ba-01)/[BB-01](../prd/backend-b.md#bb-01) session enforcement; [QA-02](../prd/qa.md#qa-02) lifecycle cases.

<a id="fa-03"></a>
### FA-03 — Realtime send and persisted ACK
**Trace:** [REQ-06 Text messaging and durable ACK](../testing/acceptance-matrix.md#req-06), [REQ-07 Lost ACK, retry, and deduplication](../testing/acceptance-matrix.md#req-07); [W05](../contracts/interface-contract.md#event-w05), [W06](../contracts/interface-contract.md#event-w06), [W07](../contracts/interface-contract.md#event-w07), [W17](../contracts/interface-contract.md#event-w17); [authorize](../contracts/interface-contract.md#internal-authorize), [persistIfAbsent](../contracts/interface-contract.md#internal-persist-if-absent).
- **Precondition:** Authorized conversation and authenticated socket.
- **Normal flow:** Persist a pending local send with stable C1; issue [W05](../contracts/interface-contract.md#event-w05); merge [W06](../contracts/interface-contract.md#event-w06) and sender [W07](../contracts/interface-contract.md#event-w07) into the same visible message M1.
- **Failure flow:** On lost ACK, disconnect, or OUTCOME_UNCONFIRMED, keep and retry the original C1 and payload. A different payload with the same C1 surfaces conflict; never silently mint a replacement C1 for the same intent.
- **Acceptance:** Same C1 yields one visible/persisted M1; `persisted` is not rendered as delivered/read. ACK can arrive before or after [W07](../contracts/interface-contract.md#event-w07) without duplication. A known rollback is not shown as success.
**Handoff:** [BA-03](../prd/backend-a.md#ba-03) W05–W07 sequencing; [BB-04](../prd/backend-b.md#bb-04) atomic persistence; [QA-04](../prd/qa.md#qa-04) failure scenarios.

<a id="fa-04"></a>
### FA-04 — Delivery and read receipts
**Trace:** [REQ-12 Delivered/read receipt state machine](../testing/acceptance-matrix.md#req-12); [W08](../contracts/interface-contract.md#event-w08), [W09](../contracts/interface-contract.md#event-w09), [W10](../contracts/interface-contract.md#event-w10), [W16](../contracts/interface-contract.md#event-w16), [W19](../contracts/interface-contract.md#event-w19); [persistReceipt](../contracts/interface-contract.md#internal-persist-receipt).
- **Precondition:** Authorized message is durably stored locally; actual read occurs before marking read.
- **Normal flow:** Send [W08](../contracts/interface-contract.md#event-w08) after durable receipt; send [W09](../contracts/interface-contract.md#event-w09) only after user views message; reconcile [W19](../contracts/interface-contract.md#event-w19) and [W10](../contracts/interface-contract.md#event-w10).
- **Failure flow:** Repeated receipt is idempotent; delayed older status does not move read backward. On reconnect, sync restores status.
- **Acceptance:** Client never reports read merely because a message arrived; `read` is monotonic and implies delivered. Receipt status can recover when no new message is sent.
**Handoff:** [BA-04](../prd/backend-a.md#ba-04) W08/W09 transition; [BB-05](../prd/backend-b.md#bb-05) canonical receipt.

<a id="fa-05"></a>
### FA-05 — Chat navigation, history, bootstrap, and synchronization
**Trace:** [REQ-04 Direct-chat navigation and creation](../testing/acceptance-matrix.md#req-04), [REQ-08 Cross-node live broadcast and missed-delivery recovery](../testing/acceptance-matrix.md#req-08), [REQ-09 First login, authorized snapshot, and history separation](../testing/acceptance-matrix.md#req-09), [REQ-10 Snapshot switch and live projection merge](../testing/acceptance-matrix.md#req-10), [REQ-11 Revocation filtering, self-notice, and multi-group sync](../testing/acceptance-matrix.md#req-11); [A12](../contracts/interface-contract.md#api-a12), [A19](../contracts/interface-contract.md#api-a19), [W07](../contracts/interface-contract.md#event-w07), [W11](../contracts/interface-contract.md#event-w11), [W12](../contracts/interface-contract.md#event-w12), [W13](../contracts/interface-contract.md#event-w13), [W14](../contracts/interface-contract.md#event-w14), [W15](../contracts/interface-contract.md#event-w15), [W16](../contracts/interface-contract.md#event-w16), [W17](../contracts/interface-contract.md#event-w17).
- **Precondition:** FB routes an authorized conversation ID to FA, or the authenticated client has a saved feed cursor/first-login state.
- **Normal flow:** Provide `openChat(conversation_id)` for FB to call; mount/switch chat UI, obtain detail with [A12](../contracts/interface-contract.md#api-a12), and load newest-to-oldest history with [A19](../contracts/interface-contract.md#api-a19). Separately request [W13](../contracts/interface-contract.md#event-w13)/[W14](../contracts/interface-contract.md#event-w14) snapshot, stage all pages for one snapshot_id, merge concurrently received live items, atomically switch the local projection, and only then install start_cursor. Use [W15](../contracts/interface-contract.md#event-w15)/[W16](../contracts/interface-contract.md#event-w16) for reconnect, foreground, and reconciliation; use [A19](../contracts/interface-contract.md#api-a19) for older history outside snapshot window.
- **Failure flow:** [A12](../contracts/interface-contract.md#api-a12) denial removes inaccessible view. [A19](../contracts/interface-contract.md#api-a19) cursor failure restarts only its history query and never invokes [W13](../contracts/interface-contract.md#event-w13). Never save start_cursor after partial pages; retain already observed live E41/C1 through snapshot switch; advance [W16](../contracts/interface-contract.md#event-w16) cursor only with atomically applied projection. A WSS feed reset requests fresh [W13](../contracts/interface-contract.md#event-w13); revoked content stays filtered without blocking other feed rows.
- **Acceptance:** FB owns routing and calls FA's `openChat`; FA owns chat display and uses one app-scoped socket. History/list cursors remain local; no gap across H, no duplicate after merging live and snapshot data, and no unauthorized post-revocation body. Responsive chat layout follows the [central Web/RWD chapter](../ui/web-rwd.md#web-rwd).
**Handoff:** [FB-05](../prd/frontend-b.md#fb-05) `openChat` and route; [BB-03](../prd/backend-b.md#bb-03) conversation detail and authorization; [BB-05](../prd/backend-b.md#bb-05) A19 message history; [BA-06](../prd/backend-a.md#ba-06)/[BB-06](../prd/backend-b.md#bb-06) feed scan/projection; [QA-03](../prd/qa.md#qa-03) cursor recovery.

<a id="fa-06"></a>
### FA-06 — Conversation attachments, renewal, and downloads
**Trace:** [REQ-13 Images, files, and upload renewal](../testing/acceptance-matrix.md#req-13); [A20](../contracts/interface-contract.md#api-a20), [A21](../contracts/interface-contract.md#api-a21), [A22](../contracts/interface-contract.md#api-a22), [A25](../contracts/interface-contract.md#api-a25), [W05](../contracts/interface-contract.md#event-w05), [W07](../contracts/interface-contract.md#event-w07); [authorize](../contracts/interface-contract.md#internal-authorize).
- **Precondition:** Current authorization for conversation and selected supported file.
- **Normal flow:** [A20](../contracts/interface-contract.md#api-a20) with `scope=conversation`, upload bytes to signed URL, [A21](../contracts/interface-contract.md#api-a21) complete, then send attachment [W05](../contracts/interface-contract.md#event-w05). Obtain a short-lived URL through [A22](../contracts/interface-contract.md#api-a22) for permitted display/download.
- **Failure flow:** An expired URL uses [A25](../contracts/interface-contract.md#api-a25) with a new idempotency key; old attempt cannot complete. Hash/type/size mismatch or lost authorization blocks use; do not send an unready attachment.
- **Acceptance:** Binary bytes do not travel over WSS. Message uses the same C1/ACK/sync guarantees as text. No signed URL is placed in messages or logs; current conversation permission is rechecked on download. Responsive image/file preview follows the central Web/RWD chapter.
**Handoff:** [BB-07](../prd/backend-b.md#bb-07) grant/metadata; [DO-02](../prd/devops.md#do-02) transfer/runtime config.

<a id="fa-07"></a>
### FA-07 — App activity and lease renewal
**Trace:** [REQ-14 Device activity and background push](../testing/acceptance-matrix.md#req-14), [REQ-15 Presence and multi-device liveness](../testing/acceptance-matrix.md#req-15); [W02](../contracts/interface-contract.md#event-w02), [W15](../contracts/interface-contract.md#event-w15), [W16](../contracts/interface-contract.md#event-w16), [W18](../contracts/interface-contract.md#event-w18), [W21](../contracts/interface-contract.md#event-w21), [W22](../contracts/interface-contract.md#event-w22); [getDevicePresence](../contracts/interface-contract.md#internal-get-device-presence), [recordActivity](../contracts/interface-contract.md#internal-record-activity).
- **Precondition:** [W02](../contracts/interface-contract.md#event-w02) accepted the active device/session generation.
- **Normal flow:** Report initial [W21](../contracts/interface-contract.md#event-w21) after [W02](../contracts/interface-contract.md#event-w02); report foreground/background transition; renew before [W22](../contracts/interface-contract.md#event-w22) valid_until; reconcile feed when returning foreground.
- **Failure flow:** Lost background frame, expired lease, or Redis uncertainty is shown as unknown, not foreground. Ignore late activity acknowledgements for an older session generation.
- **Acceptance:** Backend can decide push eligibility per device; heartbeat is not foreground state; opening app triggers normal authorized sync.
**Handoff:** [BA-07](../prd/backend-a.md#ba-07) activity lease; [FB-06](../prd/frontend-b.md#fb-06) token/session updates; [BB-08](../prd/backend-b.md#bb-08) device state/push.

<a id="fa-08"></a>
### FA-08 — Responsive Web chat interaction
**Trace:** [REQ-19 Shared responsive Web pages](../testing/acceptance-matrix.md#req-19), [REQ-20 Responsive chat interaction and read state](../testing/acceptance-matrix.md#req-20); [Web/RWD](../ui/web-rwd.md#web-rwd), [A12](../contracts/interface-contract.md#api-a12), [A19](../contracts/interface-contract.md#api-a19), [W08](../contracts/interface-contract.md#event-w08), [W09](../contracts/interface-contract.md#event-w09); [authorize](../contracts/interface-contract.md#internal-authorize).
- **Precondition:** Authenticated Web session, available chat route, and one app-scoped WSS.
- **Normal flow:** Apply the shared Web/RWD chat behavior. On a narrow layout, conversation-list selection opens a thread with a back action. Preserve per-conversation draft, pending C1, and read position through resize/orientation. Keep the composer usable with a virtual keyboard and follow the [central Web/RWD input and IME rules](../ui/web-rwd.md#web-rwd); composition Enter MUST NOT send. Keep history browsing position, constrain long content/media/file names, and send [W09](../contracts/interface-contract.md#event-w09) only for actually visible content in an active, visible browser.
- **Failure flow:** Layout changes never log in again, open another WSS, or change/reset the SyncCursor. [W08](../contracts/interface-contract.md#event-w08) may be sent after durable local receipt without sending [W09](../contracts/interface-contract.md#event-w09). If visibility state is uncertain, do not infer that a message was read.
- **Acceptance:** Interaction follows the single [shared UI chapter](../ui/web-rwd.md#web-rwd); C1 pending state and read position survive reflow; [W08](../contracts/interface-contract.md#event-w08) and [W09](../contracts/interface-contract.md#event-w09) remain distinct. Visibility threshold/dwell time for [W09](../contracts/interface-contract.md#event-w09) are proposed and require product/QA approval.
**Handoff:** [FB-07](../prd/frontend-b.md#fb-07) shared UI/`openChat`; [BA-04](../prd/backend-a.md#ba-04)/[BB-05](../prd/backend-b.md#bb-05) read model; [QA-06](../prd/qa.md#qa-06) browser input/visibility.

## 決策與共用參照

- [響應式 Web 行為](../ui/web-rwd.md#web-rwd)
- [決策：Web Push 範圍](../decisions.md#decision-web-push)
- [決策：響應式 Web 版面](../decisions.md#decision-rwd)
- [返回文件導覽](../README.md)
