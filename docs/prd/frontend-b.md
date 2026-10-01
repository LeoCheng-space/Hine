<a id="hine-ic-04--frontend-b-角色-prd"></a>
# HINE-IC-0.4 — 前端 B 角色 PRD

**版本：** HINE-IC-0.4  
**狀態：** 現行角色 PRD（2026-10-01 PM 決議）
**來源：** [歷史來源：HINE-IC-0.4 角色 PRD](../HINE-IC-0.4-role-prds.md)；唯一現行介面規格依據為[共同介面契約](../contracts/interface-contract.md)。  
**角色目的：** 負責唯一的 SessionContext 與 AccessSession、A02／A03／A04 認證流程（不讀取更新憑證 Cookie 值）、個人檔案／聯絡人／群組入口與頂層路由。本 PRD 規定未來行為與驗收要求，不代表已實作或已完成測試。  
**必讀／串接時查閱：** [系統架構](../architecture/README.md)；[共同介面契約](../contracts/interface-contract.md)；[驗收矩陣](../testing/acceptance-matrix.md)；[Web/RWD 規格](../ui/web-rwd.md#web-rwd)；[決策：Web Push](../decisions.md#decision-web-push)；[文件導覽](../README.md)。

## 範圍

- **範圍內：** SessionContext 與 AccessSession、A02／A03／A04 認證流程、個人檔案／聯絡人／群組入口與頂層路由負責權；以及下列角色專屬功能卡。
- **範圍外：** 其他角色所負責的範圍；不得單方變更共用 API／事件 ID、正式資料、ACK、游標或同步語意。介面可以依[共同變更流程](../../CONTRIBUTING.md#interface-changes)與受影響成員一起修改；模組內實作由負責人決定。先對齊[近期串接基線](../contracts/interface-contract.md#integration-baseline)，不要求一次鎖死整份規格。
- **共用 Web 行為：** 遵循 [Web / RWD 規格](../ui/web-rwd.md#web-rwd)；不得另訂斷點或重複定義版面規則。

## 功能索引

- [FB-01 — 註冊、登入與裝置綁定](#fb-01)
- [FB-02 — 更新與登出](#fb-02)
- [FB-03 — 個人檔案與頭像（含無對話帳戶）](#fb-03)
- [FB-04 — 聯絡人、已知 ID 查詢與本機游標復原](#fb-04)
- [FB-05 — 對話導覽與群組管理](#fb-05)
- [FB-06 — 推播權杖註冊與清理（本版範圍外）](#fb-06)
- [FB-07 — 響應式 Web 外框、非聊天頁面與路由返回](#fb-07)

## 角色目的與責任界線

為前端唯一的 SessionContext 與 AccessSession、A02／A03／A04 認證流程、個人檔案／聯絡人／群組入口與頂層路由負責者；呼叫 FA 的 `openChat`。不負責 `subject_id`、不讀取或保存更新憑證 Cookie 值（由後端 B 以 `Set-Cookie` 設定、瀏覽器保存並自動附帶，見[分工](../contracts/interface-contract.md#refresh-cookie-roles)）、不建立額外 WSS，也不重新定義傳輸格式。

<a id="fb-01"></a>
<a id="fb-01-registration-login-and-device-binding"></a>
<a id="fb-01--registration-login-and-device-binding"></a>
### FB-01 — 註冊、登入與裝置綁定
**追溯：** [REQ-01 帳戶驗證與登入身分](../testing/acceptance-matrix.md#req-01); [A01](../contracts/interface-contract.md#api-a01), [A02](../contracts/interface-contract.md#api-a02), [A05](../contracts/interface-contract.md#api-a05), [W01](../contracts/interface-contract.md#event-w01), [W02](../contracts/interface-contract.md#event-w02); [validateAccess](../contracts/interface-contract.md#internal-validate-access)。
- **前置條件：** 已登出；DeviceStore 可能已有該帳戶 DeviceID，新安裝則可能沒有；認證操作前取得同來源獨占 Web Lock `hine-session`。
- **正常流程：** A01 註冊並僅回傳 UserProfile。A02 在同帳號、同瀏覽器且 DeviceStore 尚存時送出該 DeviceID；首次或資料清除／遺失／重裝後送 `device_id:null`，由伺服器核發不透明 DeviceID。DeviceID 僅作裝置／本機資料分區識別，不是認證憑證；同帳號重用既存值並存回該帳戶 DeviceStore。將 AccessSession 保存在 FB 工作階段狀態（更新憑證 Cookie 由 BB 以 `Set-Cookie` 設定、瀏覽器保存，FB 不讀值），再交給 FA。登出清除 SessionContext，不清除 DeviceStore。
- **失敗流程：** 儲存 ID 遺失或伺服器拒絕重用時採用伺服器回傳的 DeviceID。切換帳號須重新驗證並使用該帳號自身的綁定與儲存分區，不得沿用前帳號內容；不做指紋辨識、裝置找回、遠端抹除或多帳號快速切換。未取得鎖的分頁不登入、不刷新、不建立 WSS，顯示「聊天已在另一個分頁開啟」；不搶鎖亦無無鎖退路。
- **驗收條件：** A02／W02 的 user_id 與 A05 UserProfile.id 一致；DeviceID／工作階段世代與 W02 相符。`logged_out` SessionContext 的 `state` 為 `"logged_out"`、五個工作階段資料欄位為 null，DeviceStore 獨立保存。內部 subject_id 絕不進入 SessionContext；同一瀏覽器設定檔同時一帳號、一個可操作聊天分頁。C5 同帳號同裝置 A02 取代舊工作階段照常適用（2026-10-01 PM 決議）。
**交接：** [FA-02](../prd/frontend-a.md#fa-02) 世代／拆除；[BA-01](../prd/backend-a.md#ba-01) 連線替換；[BB-01](../prd/backend-b.md#bb-01) 工作階段結果。

<a id="fb-02"></a>
<a id="fb-02-refresh-and-logout"></a>
<a id="fb-02--refresh-and-logout"></a>
### FB-02 — 更新與登出
**追溯：** [REQ-02 憑證更新與登出轉換](../testing/acceptance-matrix.md#req-02); [A03](../contracts/interface-contract.md#api-a03), [A04](../contracts/interface-contract.md#api-a04), [W01](../contracts/interface-contract.md#event-w01), [W02](../contracts/interface-contract.md#event-w02)。
- **前置條件：** 目前已驗證的 SessionContext；A02／A03／A04 等任何認證操作前取得同來源獨占 Web Lock `hine-session`。
- **正常流程：** 呼叫 A03（瀏覽器自動附帶更新憑證 Cookie，BB 在回應中輪替），向 FA 發布新 AccessSession／世代。A04 完成後清除目前裝置認證並通知 FA 停止 WSS。鎖由操作分頁持有至其結束；未取得鎖的分頁顯示「聊天已在另一個分頁開啟」，不作登入／刷新／聊天連線；不強制搶鎖或採無鎖退路。鎖釋放後下一分頁才可取得並重新驗證工作階段。
- **失敗流程：** 依 M3：正常 A03 自動刷新一次；等待 10 秒仍無法確認結果、收到 401 或刷新失敗，停止 WSS／自動刷新、清除本機可用認證狀態並提示重新登入。舊 Cookie 寬限 0 秒，不重播舊請求、無跨分頁接班或不明結果後額外復原。`RATE_LIMITED` 有效 `retry_after_ms` 時等待到期後最多再自動嘗試一次；省略／無效即停止自動刷新，由使用者手動操作，絕不無限重試。伺服器錯誤／網路問題不得顯示為密碼錯誤。
- **驗收條件：** 更新一律替換舊連線並使用已儲存游標；登出撤銷目前裝置，不登出無關裝置。一般服務故障不得套用認證重登流程。
- **交接：** [FA-02](../prd/frontend-a.md#fa-02) 連線替換；[BA-01](../prd/backend-a.md#ba-01) 連線替換；[BB-01](../prd/backend-b.md#bb-01) 工作階段結果。

<a id="fb-03"></a>
<a id="fb-03-profile-and-avatar-including-zero-conversation-account"></a>
<a id="fb-03--profile-and-avatar-including-zero-conversation-account"></a>
### FB-03 — 個人檔案與頭像（含無對話帳戶）
**追溯：** [REQ-03 個人檔案、頭像與聯絡人](../testing/acceptance-matrix.md#req-03); [A05](../contracts/interface-contract.md#api-a05), [A06](../contracts/interface-contract.md#api-a06), [A20](../contracts/interface-contract.md#api-a20), [A21](../contracts/interface-contract.md#api-a21), [A22](../contracts/interface-contract.md#api-a22); [authorize](../contracts/interface-contract.md#internal-authorize)。
- **前置條件：** 已登入的擁有者；不要求有對話。
- **正常流程：** 讀取／更新個人檔案；以 A20 `scope=avatar,conversation_id:null` 上傳頭像，使用單次原始位元組簽署網址 PUT，完成 A21 後透過 A06 指派就緒附件，以 A22 取回。
- **失敗流程：** 頭像與對話附件使用相同 C9／C10 核驗與版本綁定；PUT 回覆遺失／412 先用同嘗試 A21 核驗，不無條件覆寫。A21 就緒前不 A06 指派。A22 已核驗版本失敗時不移除世代或改取最新版本；頭像移除以 `avatar_attachment_id:null` 表示。上傳授權過期時不做 A25，依新 Idempotency-Key 重新 A20 建立新嘗試／附件。
- **驗收條件：** 無聊天帳戶也能上傳及顯示頭像；私人電子郵件僅本人可見；附件網址為短效網址。頭像與對話附件共用[就緒不變條件](../contracts/interface-contract.md#attachment-ready-invariant)，不同嘗試分別存放，舊簽署網址／延遲 PUT 不得改寫已指派的就緒附件；參見 [AC-R04](../testing/acceptance-matrix.md#ac-r04)。
- **交接：** [BB-02](../prd/backend-b.md#bb-02) 個人檔案授權；[BB-07](../prd/backend-b.md#bb-07) 附件生命週期；[DO-02](../prd/devops.md#do-02) 傳輸設定。

<a id="fb-04"></a>
<a id="fb-04-contacts-known-id-lookup-and-local-cursor-recovery"></a>
<a id="fb-04--contacts-known-id-lookup-and-local-cursor-recovery"></a>
### FB-04 — 聯絡人、已知 ID 查詢與本機游標復原
**追溯：** [REQ-03 個人檔案、頭像與聯絡人](../testing/acceptance-matrix.md#req-03); [A07](../contracts/interface-contract.md#api-a07), [A08](../contracts/interface-contract.md#api-a08), [A09](../contracts/interface-contract.md#api-a09), [A10](../contracts/interface-contract.md#api-a10); [getDevicePresence](../contracts/interface-contract.md#internal-get-device-presence)。
- **前置條件：** 已驗證使用者。
- **正常流程：** [A07](../contracts/interface-contract.md#api-a07) 僅使用已知公開 user_id 查詢摘要。使用者可輸入／貼上對方分享的公開 ID（對方從自己的 A02／A03／A05 取得），或選取自己有權讀取的 A08 UserSummary.id／A12 成員 user_id；先核對摘要再確認 A09。A08 是聯絡人摘要，不是對話摘要。依[已知 ID 流程](../contracts/interface-contract.md#contact-id-lookup)分頁、加入／移除聯絡人及顯示線上狀態；不提供名稱／電子郵件搜尋或新查詢 API。聯絡人頁的「搜尋／篩選」只是[本機清單篩選](../ui/web-rwd.md#rwd-local-filter)，不呼叫 A07。
- **失敗流程：** [A08](../contracts/interface-contract.md#api-a08) REST 游標錯誤僅重新取得聯絡人第一頁；不請求 [W13](../contracts/interface-contract.md#event-w13)，也不清除 FA 事件流。線上狀態未知時顯示為未知。
- **驗收條件：** 摘要不得揭露電子郵件；查詢須有已知 ID，且不新增關鍵字搜尋行為；重複加入不會建立重複聯絡人；移除聯絡人不會刪除對話歷史。響應式聯絡人／目錄版面遵循集中管理的 Web/RWD 章節。參見 [AC-R07](../testing/acceptance-matrix.md#ac-r07)。
**交接：** [BB-02](../prd/backend-b.md#bb-02) 聯絡人投影；[BA-02](../prd/backend-a.md#ba-02) 在線狀態；[FA-01](../prd/frontend-a.md#fa-01) 經唯一 WSS 接收 W18。

<a id="fb-05"></a>
<a id="fb-05-conversation-navigation-and-group-management"></a>
<a id="fb-05--conversation-navigation-and-group-management"></a>
### FB-05 — 對話導覽與群組管理
**追溯：** [REQ-04 一對一聊天導覽與建立](../testing/acceptance-matrix.md#req-04), [REQ-05 群組管理、權限與成員變更](../testing/acceptance-matrix.md#req-05), [REQ-11 撤銷篩選、自身通知與多群組同步](../testing/acceptance-matrix.md#req-11); [A11](../contracts/interface-contract.md#api-a11), [A12](../contracts/interface-contract.md#api-a12), [A13](../contracts/interface-contract.md#api-a13), [A14](../contracts/interface-contract.md#api-a14), [A15](../contracts/interface-contract.md#api-a15), [A16](../contracts/interface-contract.md#api-a16), [A17](../contracts/interface-contract.md#api-a17), [A18](../contracts/interface-contract.md#api-a18), [W11](../contracts/interface-contract.md#event-w11), [W12](../contracts/interface-contract.md#event-w12), [W20](../contracts/interface-contract.md#event-w20)。
- **前置條件：** 已驗證使用者；僅管理員可執行的操作須具備目前管理員授權。
- **正常流程：** 透過 REST 列表／建立一對一對話／建立群組／更新成員。聊天清單未讀徽章只顯示最近一次伺服器查詢值（C14-S），不在前端加一／減一；進入／返回清單以 A11 查詢，開啟對話以 A12 查詢，首次登入／游標重設由 W14 收斂。只計他人所發、目前可讀且尚未 read 的訊息；本機或其他裝置讀過要等下一次成功查詢才反映，允許短暫舊值。對話串新訊息提示可留作本機提示，不得冒充 `unread_count`。清單搜尋只篩選本機已載入項目。群組上限 50 人（含管理員）、僅 `admin`／`member`；建立者為 admin，管理員依既有 API 加入／移除／調整角色，禁止移除／降級／退出最後一位 admin，且無自訂權限、封鎖、審核入群、公開邀請連結或解散群組 API。新成員只看加入界線之後訊息；退出後重加入採新界線。開啟聊天時更新路由並呼叫 FA `openChat`；REST 呼叫端更新自身成功操作結果，其他裝置接收提交後事件。
- **失敗流程：** A11 游標錯誤僅重啟清單查詢。成員版本缺口由 A12 調和。自行遭移除時，於 A18 成功／收到最小 W12 後清除群組路由；離開後停止顯示不可存取內容，不新增唯讀歷史頁、不承諾遠端抹除。撤權後新歷史／同步／附件查詢均不得取回群組內容；已在途內容依 E1 規則。
- **驗收條件：** A14/A16→W11、A15/A17→W20、A18→W12。A14 `member_ids`（含建立者）超過 50 回 `INVALID_ARGUMENT`；A16 群組已滿回 `CONFLICT`。不提供封鎖端點或行為；未授權成員不得取得詳細資料／歷史／內容。A19、W14、W16、A22 附件授權及 C14-S 未讀計算使用相同加入界線，不得只在 UI 隱藏；[加入界線](../contracts/interface-contract.md#join-boundary)。群組不顯示已讀人數／名單彙總，但個別 W08/W09/W19 狀態仍保留。群組其他細節見[撤權政策](../contracts/interface-contract.md#group-revocation-policy)。
**交接：** [BB-03](../prd/backend-b.md#bb-03) REST 群組操作；[FA-05](../prd/frontend-a.md#fa-05) 群組事件分派／聊天路由。

<a id="fb-06"></a>
<a id="fb-06-push-token-registration-and-cleanup"></a>
<a id="fb-06--push-token-registration-and-cleanup"></a>
### FB-06 — 推播權杖註冊與清理
**追溯：** REQ-14／22、A23／A24、`dispatchPushIntent`（保留追溯 ID）。
- **前置條件：** 本版不適用。
- **正常流程：** 本版範圍外（2026-10-01 PM 決議）：Web Push 與 iOS／Android 原生推播均不納入；不註冊／清理供應商權杖，不要求推播意圖或 worker。保留 FB-06、REQ-14／22、A23／A24 及 `dispatchPushIntent` ID。
- **失敗流程：** 不適用；關閉網頁後不保證通知。
- **驗收條件：** 不實作或驗收推播；開啟網頁仍有 WSS 即時訊息、聊天內提示及查詢後更新未讀徽章。
- **交接：** 無推播交接；通知範圍外，核心 Web 聊天仍由 FA-01／FB-05 負責。

<a id="fb-07"></a>
<a id="fb-07-responsive-web-shell-non-chat-pages-and-route-return"></a>
<a id="fb-07--responsive-web-shell-non-chat-pages-and-route-return"></a>
### FB-07 — 響應式 Web 外框、非聊天頁面與路由返回
**追溯：** [REQ-19 共用響應式 Web 頁面](../testing/acceptance-matrix.md#req-19), [REQ-21 Web 深層連結與已授權路由返回](../testing/acceptance-matrix.md#req-21); [Web/RWD](../ui/web-rwd.md#web-rwd), [A01](../contracts/interface-contract.md#api-a01), [A02](../contracts/interface-contract.md#api-a02), [A03](../contracts/interface-contract.md#api-a03), [A04](../contracts/interface-contract.md#api-a04), [A05](../contracts/interface-contract.md#api-a05), [A06](../contracts/interface-contract.md#api-a06), [A07](../contracts/interface-contract.md#api-a07), [A08](../contracts/interface-contract.md#api-a08), [A09](../contracts/interface-contract.md#api-a09), [A10](../contracts/interface-contract.md#api-a10), [A11](../contracts/interface-contract.md#api-a11), [A12](../contracts/interface-contract.md#api-a12)。
- **前置條件：** FA 與 FB 共用單一 Web 建置版本；路由與既有認證狀態可用。
- **正常流程：** 共用外框套用於註冊／登入、聯絡人／目錄、個人檔案／頭像及群組管理。管理瀏覽器歷史、受保護路由守衛、深層連結進入與登入後返回，並為聊天呼叫 FA `openChat`。`/` 先顯示初始化，再以 replace 導向 `/login` 或 `/chats`；不新增後端 API。
- **失敗流程：** 未驗證／未授權深層連結不得呈現受保護資料；登入後僅返回已授權路由。重新排版不建立另一工作階段或 WSS。RWD 僅有 768 CSS px 斷點：窄版清單／聊天室切換，寬版雙欄；群組資訊採同一抽屜／對話框。
- **驗收條件：** 共用一套 SessionContext／路由政策；FA 負責聊天 UI。清單搜尋只篩選本機已載入項目，A07 指定 ID 查找照常。採單一 Web 體驗，不做原生 App／PWA 安裝或完整離線產品（2026-10-01 PM 決議）。
**交接：** [FA-08](../prd/frontend-a.md#fa-08) 路由／聊天行為；[BB-03](../prd/backend-b.md#bb-03) 授權；[DO-06](../prd/devops.md#do-06) 瀏覽器路由／頁面路由回退；[QA-06](../prd/qa.md#qa-06) 矩陣案例。

<a id="候選多分頁工作階段交接fb-提案待批准"></a>
<a id="fb-multi-tab"></a>
<a id="候選多分頁-session-交接fb-提案待批准"></a>
## 多分頁工作階段政策（M1；2026-10-01 PM 決議）

同一瀏覽器設定檔只允許一個可操作的聊天分頁。分頁在 A02／A03／A04 等認證操作前，必須取得並持有同來源獨占 Web Lock `hine-session`；不使用 `steal`，不設無鎖退路。未取得鎖的分頁顯示「聊天已在另一個分頁開啟」，不登入、不刷新、不建立 WSS。持有分頁結束釋放鎖後，另一分頁才可取得鎖並重新驗證工作階段（A03 以瀏覽器附帶的更新憑證 Cookie 取得新 AccessSession，或要求登入）。不同瀏覽器／裝置仍可登入；C5 同帳號同裝置 A02 取代舊工作階段照常適用。

不實作多分頁同步刷新、BroadcastChannel、`auth_epoch`、`auth.request`／`auth.session`／`auth.logout` 訊息、共享 `refresh_phase` 或每分頁 WSS。存取權杖不寫入持久儲存。參見 [AC-N19](../testing/acceptance-matrix.md#ac-n19)～[AC-N24](../testing/acceptance-matrix.md#ac-n24)。

<a id="n23唯一刷新復原流程與-bb-共用-c6待批准"></a>
<a id="fb-refresh-recovery"></a>
<a id="fb-refresh-recovery-unique-flow"></a>
<a id="n23唯一刷新恢復流程與-bb-共用-c6待批准"></a>
### N23：唯一刷新復原流程（M3；2026-10-01 PM 決議）

正常需要時 A03 自動刷新一次。若等待 10 秒仍無法確認結果、收到 401 或刷新失敗，停止 WSS／自動刷新、清除本機可用認證狀態並提示重新登入。舊 Cookie 寬限 0 秒；不重播舊刷新請求、不做跨分頁接班或結果不明後額外恢復流程。A03 回 `RATE_LIMITED` 且含有效 `retry_after_ms` 時，等待至期限後最多再自動嘗試一次；省略／無效時停止自動刷新，由使用者手動操作，絕不無限重試。伺服器錯誤／網路問題不得冒充密碼錯誤；一般服務故障不得套用此認證處理（C13）。參見 [AC-R02](../testing/acceptance-matrix.md#ac-r02)。

<a id="瀏覽器支援前提與缺少能力政策待批准"></a>
<a id="fb-browser-support"></a>
<a id="fb-browser-support-prerequisites-and-missing-capability-policy"></a>
### 瀏覽器支援前提與缺少能力政策（B1；2026-10-01 PM 決議）

驗收對象為 Chrome／Edge 桌面版與 Android Chrome；QA 記錄實際版本，未測瀏覽器不保證支援。這是支援政策，非已通過相容性測試。

| 必要能力／環境 | 用途 | 缺少或被停用時 |
|---|---|---|
| HTTPS、同來源 Web 應用程式 | 安全傳輸與來源邊界 | 顯示不支援，不啟用聊天 |
| Cookie、本機儲存 | 認證 Cookie 與同步投影保存 | 顯示不支援，不啟用聊天 |
| WebSocket、Page Visibility | 聊天即時連線與前景可見判定 | 顯示不支援，不啟用聊天 |
| Web Locks | M1 單操作分頁的 `hine-session` 獨占鎖 | 顯示不支援，不啟用聊天；不走無鎖退路 |

缺少必要能力時不得啟用登入／聊天；不要求 BroadcastChannel 或跨分頁紀元交接。無舊瀏覽器相容層、原生 App、PWA 或 SharedWorker 替代方案。QA 驗收案例 [AC-N19](../testing/acceptance-matrix.md#ac-n19)～[AC-N24](../testing/acceptance-matrix.md#ac-n24)、[AC-N27](../testing/acceptance-matrix.md#ac-n27)、[AC-N28](../testing/acceptance-matrix.md#ac-n28)，未執行。


## 決策與共用參照

- [響應式 Web 行為](../ui/web-rwd.md#web-rwd)
- [決策：Web Push 範圍](../decisions.md#decision-web-push)
- [決策：響應式 Web 版面](../decisions.md#decision-rwd)
- [返回文件導覽](../README.md)
