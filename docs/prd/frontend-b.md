# HINE-IC-0.4 — Frontend B 角色 PRD

**版本：** HINE-IC-0.4  
**狀態：** 待產品核准  
**來源：** [歷史來源：HINE-IC-0.4 role PRDs](../HINE-IC-0.4-role-prds.md); 唯一現行介面規格依據為 [共同介面契約](../contracts/interface-contract.md).  
**角色目的：** 負責唯一的 SessionContext、auth-cookie、個人檔案／聯絡人／群組入口、push-token 與頂層路由。本 PRD 規定未來行為與驗收要求，不代表已實作或已完成測試。
**必讀／串接時查閱：** [共同介面契約](../contracts/interface-contract.md); [驗收矩陣](../testing/acceptance-matrix.md); [Web/RWD 規格](../ui/web-rwd.md#web-rwd); [決策：Web Push](../decisions.md#decision-web-push); [文件導覽](../README.md)。

## 範圍

- **範圍內：** SessionContext, auth-cookie, profile/contact/group-entry, push-token, and top-level route ownership; the role-specific feature cards below.
- **範圍外：** 其他角色所負責的範圍；亦不得變更共用 API／event IDs、正式資料、ACK、Cursor 或同步語意。共用欄位型別、envelope、錯誤與限制均以共同介面契約為準。
- **共用 Web 行為：** 遵循 [Web / RWD specification](../ui/web-rwd.md#web-rwd); 不得另訂 breakpoint 或重複定義版面規則。

## 功能索引

- [FB-01 — 註冊、登入與裝置綁定](#fb-01)
- [FB-02 — 更新與登出](#fb-02)
- [FB-03 — 個人檔案與頭像（含無對話帳戶）](#fb-03)
- [FB-04 — 聯絡人、目錄與本機 cursor 復原](#fb-04)
- [FB-05 — 對話導覽與群組管理](#fb-05)
- [FB-06 — Push-token 註冊與清理](#fb-06)
- [FB-07 — 響應式 Web 外框、非聊天頁面與路由返回](#fb-07)

## 角色目的與責任界線

為前端唯一的 SessionContext、auth-cookie、個人檔案／聯絡人／群組入口、push-token 與頂層路由負責者；呼叫 FA 的 `openChat`。不負責 `subject_id`、不建立額外 WSS，也不重新定義 wire format。

<a id="fb-01"></a>
### FB-01 — Registration, login, and device binding
**Trace:** [REQ-01 Account verification and login identity](../testing/acceptance-matrix.md#req-01); [A01](../contracts/interface-contract.md#api-a01), [A02](../contracts/interface-contract.md#api-a02), [A05](../contracts/interface-contract.md#api-a05), [W01](../contracts/interface-contract.md#event-w01), [W02](../contracts/interface-contract.md#event-w02); [validateAccess](../contracts/interface-contract.md#internal-validate-access).
- **Precondition:** Logged out; DeviceStore may have a DeviceID for this same account or none on a new install.
- **Normal flow:** [A01](../contracts/interface-contract.md#api-a01) registers and returns UserProfile only. [A02](../contracts/interface-contract.md#api-a02) sends the same-account DeviceStore DeviceID when present, or `device_id:null` for first-install issuance; save the returned DeviceID back to that account's DeviceStore and keep the returned AccessSession/refresh cookie in FB-owned session state, then give FA the authenticated context. Logout clears SessionContext, not the separate installation-scoped DeviceStore.
- **Failure flow:** If the stored ID is lost or the server refuses reuse, adopt returned server DeviceID. DeviceID is not authentication; errors and login throttling are surfaced without account enumeration.
- **Acceptance:** [A02](../contracts/interface-contract.md#api-a02) user_id, [W02](../contracts/interface-contract.md#event-w02) user_id, and [A05](../contracts/interface-contract.md#api-a05) UserProfile.id agree as the public identity; [A02](../contracts/interface-contract.md#api-a02) AccessSession device_id/generation match [W02](../contracts/interface-contract.md#event-w02). The logged_out SessionContext remains all-null while DeviceStore is separate. Internal subject_id never enters SessionContext.
**Handoff:** [FA-01](../prd/frontend-a.md#fa-01) AccessSession; [BB-01](../prd/backend-b.md#bb-01)/[BA-01](../prd/backend-a.md#ba-01) account/session/device binding.

<a id="fb-02"></a>
### FB-02 — Refresh and logout
**Trace:** [REQ-02 Credential refresh and logout transition](../testing/acceptance-matrix.md#req-02); [A03](../contracts/interface-contract.md#api-a03), [A04](../contracts/interface-contract.md#api-a04), [W01](../contracts/interface-contract.md#event-w01), [W02](../contracts/interface-contract.md#event-w02), [W21](../contracts/interface-contract.md#event-w21); [validateAccess](../contracts/interface-contract.md#internal-validate-access).
- **Precondition:** Current authenticated SessionContext.
- **Normal flow:** [A03](../contracts/interface-contract.md#api-a03) refreshes cookie and publishes new access session/generation to FA; [A04](../contracts/interface-contract.md#api-a04) completes, clears current device auth, and tells FA to stop WSS.
- **Failure flow:** If refresh fails, require re-login and do not let FA use stale credentials. Resolve [A03](../contracts/interface-contract.md#api-a03)/[A04](../contracts/interface-contract.md#api-a04) race according to Backend B session result.
- **Acceptance:** Refresh always replaces old socket and uses saved cursor; logout revokes current device and push binding under proposal and does not log out unrelated devices.
**Handoff:** [FA-02](../prd/frontend-a.md#fa-02) generation/teardown; [BA-01](../prd/backend-a.md#ba-01) socket replacement; [BB-01](../prd/backend-b.md#bb-01) session outcome.

<a id="fb-03"></a>
### FB-03 — Profile and avatar, including zero-conversation account
**Trace:** [REQ-03 Profile, avatar, and contacts](../testing/acceptance-matrix.md#req-03); [A05](../contracts/interface-contract.md#api-a05), [A06](../contracts/interface-contract.md#api-a06), [A20](../contracts/interface-contract.md#api-a20), [A21](../contracts/interface-contract.md#api-a21), [A22](../contracts/interface-contract.md#api-a22), [A25](../contracts/interface-contract.md#api-a25); [authorize](../contracts/interface-contract.md#internal-authorize).
- **Precondition:** Logged-in owner; no conversation is required.
- **Normal flow:** Read/update profile; upload avatar with [A20](../contracts/interface-contract.md#api-a20) `scope=avatar,conversation_id:null`, transfer, complete [A21](../contracts/interface-contract.md#api-a21), assign ready attachment through [A06](../contracts/interface-contract.md#api-a06); retrieve with [A22](../contracts/interface-contract.md#api-a22).
- **Failure flow:** Renew an expired grant through [A25](../contracts/interface-contract.md#api-a25)/new key. Do not assign an unready or non-owned attachment. Null avatar assignment removes it.
- **Acceptance:** Avatar upload and display work for an account with no chats; private email stays self-only; attachment URL is short-lived. The responsive profile/avatar surface follows the central Web/RWD chapter.
**Handoff:** [BB-02](../prd/backend-b.md#bb-02) profile authorization; [BB-07](../prd/backend-b.md#bb-07) attachment lifecycle; [DO-02](../prd/devops.md#do-02) transfer setup.

<a id="fb-04"></a>
### FB-04 — Contacts, directory, and local cursor recovery
**Trace:** [REQ-03 Profile, avatar, and contacts](../testing/acceptance-matrix.md#req-03); [A07](../contracts/interface-contract.md#api-a07), [A08](../contracts/interface-contract.md#api-a08), [A09](../contracts/interface-contract.md#api-a09), [A10](../contracts/interface-contract.md#api-a10); [getDevicePresence](../contracts/interface-contract.md#internal-get-device-presence).
- **Precondition:** Authenticated user.
- **Normal flow:** Find authorized summaries, page contacts, add/remove contact, display explicit online/offline/unknown presence.
- **Failure flow:** [A08](../contracts/interface-contract.md#api-a08) REST cursor error refetches only first contacts page; it does not request [W13](../contracts/interface-contract.md#event-w13) or clear FA feed. Unknown presence is shown as unknown.
- **Acceptance:** No email disclosure through summaries; duplicate add does not create duplicate contacts; removal does not delete conversation history. Responsive contacts/directory layout follows the central Web/RWD chapter.
**Handoff:** [BB-02](../prd/backend-b.md#bb-02) contact projection; [BA-02](../prd/backend-a.md#ba-02)/[FA-07](../prd/frontend-a.md#fa-07) presence display.

<a id="fb-05"></a>
### FB-05 — Conversation navigation and group management
**Trace:** [REQ-04 Direct-chat navigation and creation](../testing/acceptance-matrix.md#req-04), [REQ-05 Group management, permissions, and membership changes](../testing/acceptance-matrix.md#req-05), [REQ-11 Revocation filtering, self-notice, and multi-group sync](../testing/acceptance-matrix.md#req-11); [A11](../contracts/interface-contract.md#api-a11), [A12](../contracts/interface-contract.md#api-a12), [A13](../contracts/interface-contract.md#api-a13), [A14](../contracts/interface-contract.md#api-a14), [A15](../contracts/interface-contract.md#api-a15), [A16](../contracts/interface-contract.md#api-a16), [A17](../contracts/interface-contract.md#api-a17), [A18](../contracts/interface-contract.md#api-a18), [W11](../contracts/interface-contract.md#event-w11), [W12](../contracts/interface-contract.md#event-w12), [W20](../contracts/interface-contract.md#event-w20); [authorize](../contracts/interface-contract.md#internal-authorize).
- **Precondition:** Authenticated user; admin-only actions require current admin authorization.
- **Normal flow:** List/direct-create/group-create/update members through REST. For opening a chat, FB updates app route and calls FA-provided `openChat`. REST caller updates its own successful operation; other devices consume post-commit events.
- **Failure flow:** [A11](../contracts/interface-contract.md#api-a11) REST cursor error restarts only the conversation list. Membership version gap is reconciled by [A12](../contracts/interface-contract.md#api-a12). On own removal, clear group route after [A18](../contracts/interface-contract.md#api-a18) success/minimal [W12](../contracts/interface-contract.md#event-w12).
- **Acceptance:** [A14](../contracts/interface-contract.md#api-a14)/[A16](../contracts/interface-contract.md#api-a16)→[W11](../contracts/interface-contract.md#event-w11), [A15](../contracts/interface-contract.md#api-a15)/[A17](../contracts/interface-contract.md#api-a17)→[W20](../contracts/interface-contract.md#event-w20), [A18](../contracts/interface-contract.md#api-a18)→[W12](../contracts/interface-contract.md#event-w12). No ban endpoint or behavior. Unauthorized member cannot continue to fetch detail/history/content; responsive group controls follow the central Web/RWD chapter.
**Handoff:** [BB-03](../prd/backend-b.md#bb-03) REST group operation; [FA-05](../prd/frontend-a.md#fa-05) group event distribution/chat route.

<a id="fb-06"></a>
### FB-06 — Push-token registration and cleanup
**Trace:** [REQ-14 Device activity and background push](../testing/acceptance-matrix.md#req-14), [REQ-22 Web Push policy scope and acceptance governance](../testing/acceptance-matrix.md#req-22); [A02](../contracts/interface-contract.md#api-a02), [A04](../contracts/interface-contract.md#api-a04), [A23](../contracts/interface-contract.md#api-a23), [A24](../contracts/interface-contract.md#api-a24); [dispatchPushIntent](../contracts/interface-contract.md#internal-dispatch-push-intent).
- **Precondition:** Authenticated device and OS notification permission/provider token.
**Normal flow:** A23/A24 and `DeviceTokenStatus` define the existing native iOS/Android push-token contract. Register/update a native provider token for AccessSession.device_id with [A23](../contracts/interface-contract.md#api-a23); revoke it with [A24](../contracts/interface-contract.md#api-a24) when disabled. Web-browser push is not approved; see [Web Push decision](../decisions.md#decision-web-push). Do not call A23 with fake native tokens from a browser.
- **Failure flow:** Do not expose token in UI/logs. [A04](../contracts/interface-contract.md#api-a04) current-device logout removes its binding per proposal; other devices remain registered.
**Acceptance:** Native token registration is bound to current account/device; push is only a hint and opening it invokes normal authenticated sync. Web-browser push remains unapproved pending a separately approved scope and contract; [A23](../contracts/interface-contract.md#api-a23)/[A24](../contracts/interface-contract.md#api-a24) do not define it.
**Handoff:** [BB-08](../prd/backend-b.md#bb-08) native device/session checks and token storage; [FA-07](../prd/frontend-a.md#fa-07)/[BA-07](../prd/backend-a.md#ba-07) lifecycle/activity.

<a id="fb-07"></a>
### FB-07 — Responsive Web shell, non-chat pages, and route return
**Trace:** [REQ-19 Shared responsive Web pages](../testing/acceptance-matrix.md#req-19), [REQ-21 Web deep links and authorized route return](../testing/acceptance-matrix.md#req-21); [Web/RWD](../ui/web-rwd.md#web-rwd), [A01](../contracts/interface-contract.md#api-a01), [A02](../contracts/interface-contract.md#api-a02), [A03](../contracts/interface-contract.md#api-a03), [A04](../contracts/interface-contract.md#api-a04), [A05](../contracts/interface-contract.md#api-a05), [A06](../contracts/interface-contract.md#api-a06), [A07](../contracts/interface-contract.md#api-a07), [A08](../contracts/interface-contract.md#api-a08), [A09](../contracts/interface-contract.md#api-a09), [A10](../contracts/interface-contract.md#api-a10), [A11](../contracts/interface-contract.md#api-a11), [A12](../contracts/interface-contract.md#api-a12), [A13](../contracts/interface-contract.md#api-a13), [A14](../contracts/interface-contract.md#api-a14), [A15](../contracts/interface-contract.md#api-a15), [A16](../contracts/interface-contract.md#api-a16), [A17](../contracts/interface-contract.md#api-a17), [A18](../contracts/interface-contract.md#api-a18).
- **Precondition:** One Web build shared by FA and FB; routes and existing auth state are available.
- **Normal flow:** Apply the shared shell/layout to registration/login, contacts/directory, profile/avatar, and group management. Own browser history, protected route guard, deep-link route entry, post-login return, and call FA's `openChat` for chat content.
- **Failure flow:** Unauthenticated/unauthorized deep links do not render protected data; login returns only to the authorized requested route. Reflow does not create another session or WSS. Preserve existing API/event/model contracts across layouts.
- **Acceptance:** Browser navigation and responsive non-chat pages share one SessionContext/router policy; FA remains chat UI owner. Use the central [shared UI chapter](../ui/web-rwd.md#web-rwd) without restating its viewport bands.
**Handoff:** [FA-08](../prd/frontend-a.md#fa-08) route/chat behavior; [BB-03](../prd/backend-b.md#bb-03) authorization; [DO-06](../prd/devops.md#do-06) browser route/fallback; [QA-06](../prd/qa.md#qa-06) matrix cases.

## 決策與共用參照

- [響應式 Web 行為](../ui/web-rwd.md#web-rwd)
- [決策：Web Push 範圍](../decisions.md#decision-web-push)
- [決策：響應式 Web 版面](../decisions.md#decision-rwd)
- [返回文件導覽](../README.md)
