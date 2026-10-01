<a id="hine-ic-04--frontend-b-角色-prd"></a>
# HINE-IC-0.4 — 前端 B 角色 PRD

**版本：** HINE-IC-0.4  
**狀態：** 待產品核准  
**來源：** [歷史來源：HINE-IC-0.4 角色 PRD](../HINE-IC-0.4-role-prds.md)；唯一現行介面規格依據為[共同介面契約](../contracts/interface-contract.md)。  
**角色目的：** 負責唯一的 SessionContext 與 AccessSession、A02／A03／A04 認證流程（不讀取更新憑證 Cookie 值）、個人檔案／聯絡人／群組入口、推播權杖與頂層路由。本 PRD 規定未來行為與驗收要求，不代表已實作或已完成測試。  
**必讀／串接時查閱：** [系統架構](../architecture/README.md)；[共同介面契約](../contracts/interface-contract.md)；[驗收矩陣](../testing/acceptance-matrix.md)；[Web/RWD 規格](../ui/web-rwd.md#web-rwd)；[決策：Web Push](../decisions.md#decision-web-push)；[文件導覽](../README.md)。

## 範圍

- **範圍內：** SessionContext 與 AccessSession、A02／A03／A04 認證流程、個人檔案／聯絡人／群組入口、推播權杖與頂層路由負責權；以及下列角色專屬功能卡。
- **範圍外：** 其他角色所負責的範圍；亦不得變更共用 API／事件 ID、正式資料、ACK、游標或同步語意。共用欄位型別、封套、錯誤與限制均以共同介面契約為準。
- **共用 Web 行為：** 遵循 [Web / RWD 規格](../ui/web-rwd.md#web-rwd)；不得另訂斷點或重複定義版面規則。

## 功能索引

- [FB-01 — 註冊、登入與裝置綁定](#fb-01)
- [FB-02 — 更新與登出](#fb-02)
- [FB-03 — 個人檔案與頭像（含無對話帳戶）](#fb-03)
- [FB-04 — 聯絡人、已知 ID 查詢與本機游標復原](#fb-04)
- [FB-05 — 對話導覽與群組管理](#fb-05)
- [FB-06 — 推播權杖註冊與清理](#fb-06)
- [FB-07 — 響應式 Web 外框、非聊天頁面與路由返回](#fb-07)

## 角色目的與責任界線

為前端唯一的 SessionContext 與 AccessSession、A02／A03／A04 認證流程、個人檔案／聯絡人／群組入口、推播權杖與頂層路由負責者；呼叫 FA 的 `openChat`。不負責 `subject_id`、不讀取或保存更新憑證 Cookie 值（由後端 B 以 `Set-Cookie` 設定、瀏覽器保存並自動附帶，見[分工](../contracts/interface-contract.md#refresh-cookie-roles)）、不建立額外 WSS，也不重新定義傳輸格式。

<a id="fb-01"></a>
<a id="fb-01-registration-login-and-device-binding"></a>
<a id="fb-01--registration-login-and-device-binding"></a>
### FB-01 — 註冊、登入與裝置綁定
**追溯：** [REQ-01 帳戶驗證與登入身分](../testing/acceptance-matrix.md#req-01); [A01](../contracts/interface-contract.md#api-a01), [A02](../contracts/interface-contract.md#api-a02), [A05](../contracts/interface-contract.md#api-a05), [W01](../contracts/interface-contract.md#event-w01), [W02](../contracts/interface-contract.md#event-w02); [validateAccess](../contracts/interface-contract.md#internal-validate-access)。
- **前置條件：** 已登出；DeviceStore 可能已有此帳戶的 DeviceID，新安裝則可能沒有。
- **正常流程：** [A01](../contracts/interface-contract.md#api-a01) 註冊並僅回傳 UserProfile。[A02](../contracts/interface-contract.md#api-a02) 在同帳戶 DeviceStore 有 DeviceID 時送出該 ID，首次安裝核發時則送出 `device_id:null`；將回傳的 DeviceID 存回該帳戶的 DeviceStore，並將回傳的 AccessSession 保存在 FB 負責的工作階段狀態（更新憑證 Cookie 由 BB 以 `Set-Cookie` 設定、瀏覽器保存，FB 不讀取其值），再將已驗證的工作階段資訊交給 FA。登出時清除 SessionContext，而非獨立的安裝層級 DeviceStore。
- **失敗流程：** 若儲存的 ID 遺失或伺服器拒絕重用，採用伺服器回傳的 DeviceID。DeviceID 不等同認證；呈現錯誤與登入限流資訊，但不得洩漏帳戶是否存在。
- **驗收條件：** [A02](../contracts/interface-contract.md#api-a02) 的 user_id、[W02](../contracts/interface-contract.md#event-w02) 的 user_id 與 [A05](../contracts/interface-contract.md#api-a05) 的 UserProfile.id 一致，作為公開身分；[A02](../contracts/interface-contract.md#api-a02) AccessSession 的 device_id／世代與 [W02](../contracts/interface-contract.md#event-w02) 相符。`logged_out` SessionContext 的 `state` 為 `"logged_out"`、五個工作階段資料欄位為 null，DeviceStore 則另行獨立。內部 subject_id 絕不進入 SessionContext。
**交接：** [FA-01](../prd/frontend-a.md#fa-01) AccessSession；[BB-01](../prd/backend-b.md#bb-01)/[BA-01](../prd/backend-a.md#ba-01) 帳戶／工作階段／裝置綁定。

<a id="fb-02"></a>
<a id="fb-02-refresh-and-logout"></a>
<a id="fb-02--refresh-and-logout"></a>
### FB-02 — 更新與登出
**追溯：** [REQ-02 憑證更新與登出轉換](../testing/acceptance-matrix.md#req-02); [A03](../contracts/interface-contract.md#api-a03), [A04](../contracts/interface-contract.md#api-a04), [W01](../contracts/interface-contract.md#event-w01), [W02](../contracts/interface-contract.md#event-w02), [W21](../contracts/interface-contract.md#event-w21); [validateAccess](../contracts/interface-contract.md#internal-validate-access)。
- **前置條件：** 目前已驗證的 SessionContext。
- **正常流程：** 呼叫 [A03](../contracts/interface-contract.md#api-a03)（瀏覽器自動附帶更新憑證 Cookie，BB 在回應中輪替），並向 FA 發布新的 AccessSession／世代；[A04](../contracts/interface-contract.md#api-a04) 完成後清除目前裝置認證，並通知 FA 停止 WSS。
- **失敗流程：** 更新失敗時要求重新登入，不得讓 FA 使用過期憑證。依後端 B 工作階段結果處理 [A03](../contracts/interface-contract.md#api-a03)/[A04](../contracts/interface-contract.md#api-a04) 競態。
- **驗收條件：** 更新一律替換舊連線並使用已儲存游標；登出會撤銷目前裝置及（提案中、待批准的）推播綁定，而不登出無關裝置。
- **候選（待批准）：** 同瀏覽器多分頁依[既有交接](#fb-multi-tab)共用更新憑證 Cookie 與工作階段、各有一條 WSS；A02 仍依 [C5](../contracts/interface-contract.md#internal-change-requests) 取代同裝置舊工作階段。刷新結果不明一律採 [C6／唯一復原流程](#fb-refresh-recovery)：舊 Cookie 無寬限，最多一次復原，失敗進入重新登入；不再由 FB／BB 各自選有無寬限。瀏覽器缺少[必要能力](#fb-browser-support)時不啟用登入／聊天，A／W 公開格式與 Web 範圍不變。
**交接：** [FA-02](../prd/frontend-a.md#fa-02) 世代／拆除；[BA-01](../prd/backend-a.md#ba-01) 連線替換；[BB-01](../prd/backend-b.md#bb-01) 工作階段結果。

<a id="fb-03"></a>
<a id="fb-03-profile-and-avatar-including-zero-conversation-account"></a>
<a id="fb-03--profile-and-avatar-including-zero-conversation-account"></a>
### FB-03 — 個人檔案與頭像（含無對話帳戶）
**追溯：** [REQ-03 個人檔案、頭像與聯絡人](../testing/acceptance-matrix.md#req-03); [A05](../contracts/interface-contract.md#api-a05), [A06](../contracts/interface-contract.md#api-a06), [A20](../contracts/interface-contract.md#api-a20), [A21](../contracts/interface-contract.md#api-a21), [A22](../contracts/interface-contract.md#api-a22), [A25](../contracts/interface-contract.md#api-a25); [authorize](../contracts/interface-contract.md#internal-authorize)。
- **前置條件：** 已登入的擁有者；不要求有對話。
- **正常流程：** 讀取／更新個人檔案；以 [A20](../contracts/interface-contract.md#api-a20) `scope=avatar,conversation_id:null` 上傳頭像，依待批准 [C10](../contracts/interface-contract.md#signed-upload-contract) 以單次原始位元組簽署網址 PUT 傳輸，完成 [A21](../contracts/interface-contract.md#api-a21)，透過 [A06](../contracts/interface-contract.md#api-a06) 指派就緒附件；以 [A22](../contracts/interface-contract.md#api-a22) 取回。
- **失敗流程：** 頭像沿待批准 [C10](../contracts/interface-contract.md#signed-upload-contract) 的僅建立標頭與版本綁定；PUT 回覆遺失／412 先用同嘗試 A21 核驗，不無條件覆寫。待處理授權憑證續期仍依 A25 新鍵值／新嘗試；A21 就緒前不 A06 指派。A22 已核驗版本失敗時不移除世代或改取最新版本；頭像移除仍以 avatar_attachment_id:null 表示。
- **驗收條件：** 無聊天的帳戶也能上傳及顯示頭像；私人電子郵件僅本人可見；附件網址為短效網址。響應式個人檔案／頭像介面遵循集中管理的 Web/RWD 章節。參見 [AC-R04](../testing/acceptance-matrix.md#ac-r04)。
- **C10 內容一致性補充（待批准）：** 頭像與對話附件使用同一[就緒不變條件](../contracts/interface-contract.md#attachment-ready-invariant)，不同嘗試分別存放；舊簽署網址／延遲 PUT 不得改寫已指派的就緒附件。新頭像內容須經新的附件／核驗流程，不重開既有就緒 `attachment_id`；不新增公開 API。
**交接：** [BB-02](../prd/backend-b.md#bb-02) 個人檔案授權；[BB-07](../prd/backend-b.md#bb-07) 附件生命週期；[DO-02](../prd/devops.md#do-02) 傳輸設定。

<a id="fb-04"></a>
<a id="fb-04-contacts-known-id-lookup-and-local-cursor-recovery"></a>
<a id="fb-04--contacts-known-id-lookup-and-local-cursor-recovery"></a>
### FB-04 — 聯絡人、已知 ID 查詢與本機游標復原
**追溯：** [REQ-03 個人檔案、頭像與聯絡人](../testing/acceptance-matrix.md#req-03); [A07](../contracts/interface-contract.md#api-a07), [A08](../contracts/interface-contract.md#api-a08), [A09](../contracts/interface-contract.md#api-a09), [A10](../contracts/interface-contract.md#api-a10); [getDevicePresence](../contracts/interface-contract.md#internal-get-device-presence)。
- **前置條件：** 已驗證使用者。
- **正常流程：** [A07](../contracts/interface-contract.md#api-a07) 僅使用已知公開 user_id 查詢摘要。使用者可輸入／貼上對方分享的公開 ID（對方從自己的 A02／A03／A05 取得），或選取自己有權讀取的 A08 UserSummary.id／A12 成員 user_id；先核對摘要再確認 A09。A08 是聯絡人摘要，不是對話摘要。依[已知 ID 流程](../contracts/interface-contract.md#contact-id-lookup)分頁、加入／移除聯絡人及顯示線上狀態；不提供名稱／電子郵件搜尋或新查詢 API。聯絡人頁的「搜尋／篩選」只是[本機清單篩選](../ui/web-rwd.md#rwd-local-filter)，不呼叫 A07。
- **失敗流程：** [A08](../contracts/interface-contract.md#api-a08) REST 游標錯誤僅重新取得聯絡人第一頁；不請求 [W13](../contracts/interface-contract.md#event-w13)，也不清除 FA 事件流。線上狀態未知時顯示為未知。
- **驗收條件：** 摘要不得揭露電子郵件；查詢須有已知 ID，且不新增關鍵字搜尋行為；重複加入不會建立重複聯絡人；移除聯絡人不會刪除對話歷史。響應式聯絡人／目錄版面遵循集中管理的 Web/RWD 章節。參見 [AC-R07](../testing/acceptance-matrix.md#ac-r07)。
**交接：** [BB-02](../prd/backend-b.md#bb-02) 聯絡人投影；[BA-02](../prd/backend-a.md#ba-02)/[FA-07](../prd/frontend-a.md#fa-07) 在線狀態顯示。

<a id="fb-05"></a>
<a id="fb-05-conversation-navigation-and-group-management"></a>
<a id="fb-05--conversation-navigation-and-group-management"></a>
### FB-05 — 對話導覽與群組管理
**追溯：** [REQ-04 一對一聊天導覽與建立](../testing/acceptance-matrix.md#req-04), [REQ-05 群組管理、權限與成員變更](../testing/acceptance-matrix.md#req-05), [REQ-11 撤銷篩選、自身通知與多群組同步](../testing/acceptance-matrix.md#req-11); [A11](../contracts/interface-contract.md#api-a11), [A12](../contracts/interface-contract.md#api-a12), [A13](../contracts/interface-contract.md#api-a13), [A14](../contracts/interface-contract.md#api-a14), [A15](../contracts/interface-contract.md#api-a15), [A16](../contracts/interface-contract.md#api-a16), [A17](../contracts/interface-contract.md#api-a17), [A18](../contracts/interface-contract.md#api-a18), [W11](../contracts/interface-contract.md#event-w11), [W12](../contracts/interface-contract.md#event-w12), [W20](../contracts/interface-contract.md#event-w20); [authorize](../contracts/interface-contract.md#internal-authorize)。
- **前置條件：** 已驗證使用者；僅管理員可執行的操作須具備目前的管理員授權。
- **正常流程：** 透過 REST 列表／建立一對一對話／建立群組／更新成員。聊天清單顯示 A11 的 `unread_count`（語義依待批准 [C14](../contracts/interface-contract.md#unread-count)），進入或返回聊天清單時以 A11 讀取，該頁列出的對話以伺服器值作為新基準並覆蓋本機值；之後的本機加減依 PM 尚未選定的 C14-M（[合併規則](../contracts/interface-contract.md#unread-merge)：以 A11 為基準時新訊息不加一，本裝置已讀只在可證明未含於基準時減一）或 C14-S（只顯示最近查詢值），下一次查詢前允許偏高或偏低，不自行猜測修正；清單搜尋只做[本機篩選](../ui/web-rwd.md#rwd-local-filter)。開啟聊天時，FB 更新應用程式路由並呼叫 FA 提供的 `openChat`。REST 呼叫端更新自身成功操作的結果；其他裝置則接收提交後事件。
- **失敗流程：** [A11](../contracts/interface-contract.md#api-a11) REST 游標錯誤僅重新啟動對話清單。成員版本缺口由 [A12](../contracts/interface-contract.md#api-a12) 調和。自行遭移除時，於 [A18](../contracts/interface-contract.md#api-a18) 成功／收到最小 [W12](../contracts/interface-contract.md#event-w12) 後清除群組路由。
- **驗收條件：** [A14](../contracts/interface-contract.md#api-a14)/[A16](../contracts/interface-contract.md#api-a16)→[W11](../contracts/interface-contract.md#event-w11)、[A15](../contracts/interface-contract.md#api-a15)/[A17](../contracts/interface-contract.md#api-a17)→[W20](../contracts/interface-contract.md#event-w20)、[A18](../contracts/interface-contract.md#api-a18)→[W12](../contracts/interface-contract.md#event-w12)。不提供封鎖端點或行為。未授權成員不得繼續取得詳細資料／歷史／內容；響應式群組控制項遵循集中管理的 Web/RWD 章節。
- **候選（待批准）：** [群組三項政策](../contracts/interface-contract.md#group-revocation-policy)分開批准。已取得內容沿用本卡 A18／W12 後離開路由，不新增退出後歷史頁，也不把離開路由宣稱為已抹除裝置副本；待送內容採否 E1 與新歷史查詢權限分開決定（[AC-N25](../testing/acceptance-matrix.md#ac-n25)）。
**交接：** [BB-03](../prd/backend-b.md#bb-03) REST 群組操作；[FA-05](../prd/frontend-a.md#fa-05) 群組事件分派／聊天路由。

<a id="fb-06"></a>
<a id="fb-06-push-token-registration-and-cleanup"></a>
<a id="fb-06--push-token-registration-and-cleanup"></a>
### FB-06 — 推播權杖註冊與清理
**追溯：** [REQ-14 裝置活動與背景推播](../testing/acceptance-matrix.md#req-14), [REQ-22 Web Push 政策範圍與驗收治理](../testing/acceptance-matrix.md#req-22); [A02](../contracts/interface-contract.md#api-a02), [A04](../contracts/interface-contract.md#api-a04), [A23](../contracts/interface-contract.md#api-a23), [A24](../contracts/interface-contract.md#api-a24); [dispatchPushIntent](../contracts/interface-contract.md#internal-dispatch-push-intent)。
- **前置條件：** 已驗證裝置及 OS 通知權限／供應商權杖。
- **正常流程：** A23/A24 與 `DeviceTokenStatus` 定義既有原生 iOS/Android 推播權杖契約。使用 [A23](../contracts/interface-contract.md#api-a23) 為 AccessSession.device_id 註冊／更新原生供應商權杖；停用時以 [A24](../contracts/interface-contract.md#api-a24) 撤銷。瀏覽器 Web 推播尚未核准；參見 [Web Push 決策](../decisions.md#decision-web-push)。不得從瀏覽器呼叫 A23 並提供虛構的原生權杖。
- **失敗流程：** 不得在 UI／記錄中揭露權杖。[A04](../contracts/interface-contract.md#api-a04) 目前裝置登出時，依提案移除其綁定；其他裝置維持註冊。
- **驗收條件：** 原生權杖註冊綁定目前帳戶／裝置；推播僅是提示，開啟後會執行一般已驗證同步。瀏覽器 Web 推播仍未批准，須待另行批准範圍與契約；[A23](../contracts/interface-contract.md#api-a23)/[A24](../contracts/interface-contract.md#api-a24) 未定義此功能。
**交接：** [BB-08](../prd/backend-b.md#bb-08) 原生裝置／工作階段檢查與權杖儲存；[FA-07](../prd/frontend-a.md#fa-07)/[BA-07](../prd/backend-a.md#ba-07) 生命週期／活動。

<a id="fb-07"></a>
<a id="fb-07-responsive-web-shell-non-chat-pages-and-route-return"></a>
<a id="fb-07--responsive-web-shell-non-chat-pages-and-route-return"></a>
### FB-07 — 響應式 Web 外框、非聊天頁面與路由返回
**追溯：** [REQ-19 共用響應式 Web 頁面](../testing/acceptance-matrix.md#req-19), [REQ-21 Web 深層連結與已授權路由返回](../testing/acceptance-matrix.md#req-21); [Web/RWD](../ui/web-rwd.md#web-rwd), [A01](../contracts/interface-contract.md#api-a01), [A02](../contracts/interface-contract.md#api-a02), [A03](../contracts/interface-contract.md#api-a03), [A04](../contracts/interface-contract.md#api-a04), [A05](../contracts/interface-contract.md#api-a05), [A06](../contracts/interface-contract.md#api-a06), [A07](../contracts/interface-contract.md#api-a07), [A08](../contracts/interface-contract.md#api-a08), [A09](../contracts/interface-contract.md#api-a09), [A10](../contracts/interface-contract.md#api-a10), [A11](../contracts/interface-contract.md#api-a11), [A12](../contracts/interface-contract.md#api-a12), [A13](../contracts/interface-contract.md#api-a13), [A14](../contracts/interface-contract.md#api-a14), [A15](../contracts/interface-contract.md#api-a15), [A16](../contracts/interface-contract.md#api-a16), [A17](../contracts/interface-contract.md#api-a17), [A18](../contracts/interface-contract.md#api-a18)。
- **前置條件：** FA 與 FB 共用一個 Web 建置版本；路由與既有認證狀態可用。
- **正常流程：** 將共用外框／版面套用於註冊／登入、聯絡人／目錄、個人檔案／頭像及群組管理。負責瀏覽器歷史、受保護路由守衛、深層連結路由進入、登入後返回，並為聊天內容呼叫 FA 的 `openChat`。根路徑 `/` 依[根路徑規則](../ui/web-rwd.md#rwd-root-route)處理初始化中、未登入與已登入三種狀態，不新增後端 API。
- **失敗流程：** 未驗證／未授權的深層連結不得呈現受保護資料；登入後僅返回已授權的請求路由。重新排版不會建立另一個工作階段或 WSS。不同版面間維持既有 API／事件／模型契約。
- **驗收條件：** 瀏覽器導覽與響應式非聊天頁面共用一套 SessionContext／路由器政策；FA 仍是聊天 UI 負責者。使用集中管理的[共用 UI 章節](../ui/web-rwd.md#web-rwd)，不重述其視窗寬度區間。
**交接：** [FA-08](../prd/frontend-a.md#fa-08) 路由／聊天行為；[BB-03](../prd/backend-b.md#bb-03) 授權；[DO-06](../prd/devops.md#do-06) 瀏覽器路由／頁面路由回退；[QA-06](../prd/qa.md#qa-06) 矩陣案例。

<a id="fb-multi-tab"></a>
<a id="候選多分頁-session-交接fb-提案待批准"></a>
## 候選：多分頁工作階段交接（FB 提案，待批准）

**範圍：** 同一瀏覽器設定檔、同一來源（`https://hine.run.place`）的多個分頁。
- 每個分頁是一個獨立的應用程式實例，各自持有 SessionContext、一條應用程式範圍的 WSS（FA 擁有）、SyncCursor 與本機投影。
- 多分頁支援**不是**讓整個瀏覽器共用單一連線；不使用 SharedWorker 或其他跨分頁共用連線的機制。
- 分頁之間共用的是瀏覽器 Cookie（更新憑證）與安裝層級的 DeviceStore，因此它們共用同一個工作階段與世代。
- 本方案不新增公開 API 或 W 事件；下列訊息與儲存鍵都是 FB 的內部約定。

**機制：**
- **認證鎖：** Web Locks API 的獨占鎖 `hine-auth`。分頁在鎖內發起 A02、A03、A04；關頁後已送出的 HTTP 請求仍可能在 BB 執行，鎖不代表伺服器請求已結束。等待鎖不能繞過鎖另送請求；持有者凍結時顯示等待，不以 `steal` 強行接管。
- **非機密共享狀態：** `localStorage` 的 `hine-auth-state`：`{state:"authenticated"|"logged_out", user_id, device_id, auth_epoch, expires_at, refresh_phase:"idle"|"sent"|"recovery_sent", retry_not_before:Timestamp|null, retry_requires_user_action:boolean}`。`refresh_phase` 記錄同一紀元的嘗試進度，不是公開 SessionContext 新狀態；`retry_not_before` 是已知限速截止；缺少有效等待值時以 `retry_requires_user_action` 記錄停止自動重試，跨分頁／重新載入都不能遺失此條件。
  - `auth_epoch` 是本瀏覽器遞增序號：持鎖分頁每次 A02、A03、A04 成功或決定清除本地認證時加一，釋放鎖前寫入，並把 `refresh_phase` 重設為 `idle`。
  - 分頁以 `auth_epoch`、而不是 `session_generation` 判斷新舊，因為 A02 會建立新工作階段，世代不能跨工作階段比較。
  - 存取權杖不寫入任何儲存空間。
- **分頁間訊息：** BroadcastChannel `hine-auth` 傳送三種訊息：
  - `auth.session`：`{auth_epoch, access_session}`，其中 `access_session` 是 A02／A03 回傳的 AccessSession，只在記憶體傳遞；
  - `auth.request`：請求目前的 `auth.session`；
  - `auth.logout`：`{auth_epoch, user_id}`。
- **依據：** Web Locks 與 BroadcastChannel 都只在同一來源內作用，Web Locks 需要 HTTPS（[Web Locks](https://developer.mozilla.org/en-US/docs/Web/API/Web_Locks_API)、[BroadcastChannel](https://developer.mozilla.org/en-US/docs/Web/API/Broadcast_Channel_API)）。

**行為：**
1. **同時刷新：** 需要更新的分頁先記下觸發更新時自己持有的 `auth_epoch`（記為 `e0`），再取得認證鎖。
   - 取得鎖後先重讀共享狀態；`logged_out` 就清除本分頁認證，不再 A03。若等鎖期間已採用比 `e0` 新、與共享帳號／裝置及紀元相符、未到期的 AccessSession，直接釋放鎖。
   - 若共享狀態是 `authenticated`／`idle` 且紀元大於 `e0`，以 `auth.request` 取得同一紀元的未到期 AccessSession，候選等 1 秒。沒有可用回覆才更新；不得使用 `refreshing`／結果不明分頁的舊權杖。
   - 需要呼叫 A03 時，先依第 6 點判斷 `refresh_phase` 與是否尚有恢復額度；正常首次請求先寫 `sent`。成功後依序更新自身 SessionContext、共享狀態、廣播 `auth.session`，再釋放鎖。
2. **刷新結果共享：** 只接受與共享 `authenticated`／`idle` 的紀元、user_id、device_id 相符且未到期的 `auth.session`；採用較新紀元時更新 SessionContext，FA 依 [FA-02](frontend-a.md#fa-02) 換線與續傳。回覆 `auth.request` 的分頁也必須滿足這些條件。
3. **遲到的刷新結果：** 舊於／等於自己持有紀元，或不符共享狀態的 `auth.session` 一律忽略。在舊連線收到 W17、但已持有較新 AccessSession 時不再刷新。結果不明／重登後的舊 HTTP 回覆不得復活認證；取消請求不代表伺服器取消輪替，遲到 Cookie 仍須經 BB 當下有效性檢查。
4. **登出傳播：**
   - 任一分頁 A04 成功後，增加紀元、寫 `logged_out`，再廣播 `auth.logout`。接收端先重讀共享狀態，只在仍是該通知的 `logged_out` 紀元／帳號、且本地沒有較新認證時，清除相符帳號 SessionContext 並停 WSS；舊登出通知不能清掉後來 A02 建立的新工作階段。
   - 沒收到廣播的分頁仍依伺服器撤銷與共享狀態恢復；若已重新登入，先採用較新的共享認證，不因舊連線關閉或舊登出事件復原成登出。
   - `localStorage` 的 `storage` 事件只作「重新讀共享狀態」的提示，不直接套用事件攜帶的舊值。C6 本地放棄恢復也使用同一紀元檢查；共享 `logged_out` 的 user_id 是供通知比對的非機密帳號標記，SessionContext 的五個工作階段資料欄位仍為 null。
5. **新分頁：** 載入時讀共享狀態。
   - 若為 `authenticated`／`idle`，送 `auth.request` 等可用回覆（候選 1 秒）；收到就採用，不 A03。
   - 無回覆或發現 `sent`／`recovery_sent` 時，在認證鎖內依第 1、6 點接手；不能把新分頁當作新的一次恢復額度。`logged_out` 不自動刷新。
6. **協調分頁消失／刷新結果不明：** 統一依[下方唯一恢復流程](#fb-refresh-recovery)；不以分頁關閉在 COMMIT 前後推定成功或回滾。關頁可釋放 Web Lock，凍結不一定釋放；等待分頁不可並行送認證請求。
7. **重新登入與其他帳號：**
   - 同一瀏覽器設定檔同時只支援一個登入帳號，因為更新憑證 Cookie 由所有分頁共用。
   - 任一分頁 A02 成功後，依第 1 點廣播新的 `auth.session`。同帳號時，C5 已撤銷原工作階段，其他分頁經第 2 點換到新工作階段。不同帳號時，其他分頁收到不同的 `user_id`，視為登出並回到登入頁。
8. **同裝置 W21：** 每個分頁各自回報 `visible`→前景、`hidden`→背景；不代其他分頁送最後一筆背景。[C7](../contracts/interface-contract.md#activity-merge) 在伺服器合併：任一有效前景租期優先，其次背景，皆無才未知。關閉／失效只移除該連線，租期過期也不再計入；W22 不是整個瀏覽器的狀態回覆。

<a id="fb-refresh-recovery"></a>
<a id="fb-refresh-recovery-unique-flow"></a>
<a id="n23唯一刷新恢復流程與-bb-共用-c6待批准"></a>
### N23：唯一刷新復原流程（與 BB 共用 C6，待批准）

1. 正常 A03 送出前，在認證鎖內把該紀元的 `refresh_phase` 寫為 `sent`。當前分頁的 SessionContext 轉 `refreshing`、停止用舊憑證開始新操作；成功才把新 AccessSession 給 FA。單次 A03 的候選等待上限 10 秒，不代表伺服器交易截止。
2. 若失去可用成功結果（網路錯誤、逾時、頁面消失），持鎖者或下一個取得鎖者先重讀狀態。已完成的新紀元優先依第 1 點共享結果；`logged_out` 結束。`sent` 表示不明，即使分頁在「寫 `sent`／真正送出」之間消失，也保守按不明處理。
3. `sent` 且無可用新結果時，先檢查共享 `retry_requires_user_action` 與 `retry_not_before`。需要使用者動作時，不因新分頁或重載自動嘗試；手動觸發仍須等已知期限，取得鎖並重讀狀態後才消耗剩餘額度。可嘗試時，**先寫 `recovery_sent`，再用瀏覽器當下 Cookie 呼叫 A03 一次**。BB 按原 C6 候選不給舊 Cookie 寬限；不因這個缺欄位處理變更寬限、次數或重登終點。
4. 成功：確認仍是本次嘗試所屬紀元，更新自身與共享狀態、增加紀元、改 `idle`、廣播，FA 換線並按原游標同步。`auth.request` 不回覆結果不明的舊權杖。
5. 初次已明確 `UNAUTHENTICATED`、唯一復原未成功（含再次逾時／斷網），或接手時看見 `recovery_sent` 且未有新紀元：不做第三次 A03。在鎖內增加紀元、寫 `logged_out`／`idle`、廣播 `auth.logout`；各分頁清除 SessionContext 並停止 WSS，提示重新登入。下一次只能由使用者發起 A02，遲到結果不得撤銷這個決定。這是本地放棄復原，不宣稱已完成 A04。
6. `RATE_LIMITED` 依[共用錯誤分流](../contracts/interface-contract.md#error-recovery)：只有可重試且有效 retry_after_ms 才算收到時點＋延遲，與已有截止取較晚者。省略／無效或 `retryable:false` 時，寫 `retry_requires_user_action:true`，不造出 0／未定義的截止，也不由接手分頁自動重試。初次限速保留 `sent` 與剩餘額度；手動操作可在鎖內解除本次等待標記，但不能跳過既有截止或增加恢復次數。恢復仍失敗依原第 5 點重登；已知期限／手動等待標記在接手及重登提示中保留，成功採用新認證後才結束該次恢復。參見 [AC-R02](../testing/acceptance-matrix.md#ac-r02)。

**取捨：** 不引入舊更新憑證 Cookie 可重播期間；代價是回應遺失或短暫斷網可能要求使用者重登。整個瀏覽器以共享階段計次，不是每個分頁各重試一次。此為單一主要推薦，PM 若要求寬限，須連同 BB／C6／N23 一起改寫批准，不保留執行期任選分支。

<a id="fb-browser-support"></a>
<a id="fb-browser-support-prerequisites-and-missing-capability-policy"></a>
### 瀏覽器支援前提與缺少能力政策（待批准）

| 必要能力／環境 | 用途 | 缺少或被停用時 |
|---|---|---|
| 同來源頂層 HTTPS Web 應用程式、Web Locks | 共用認證鎖 | 不支援登入／聊天 |
| BroadcastChannel、可讀寫的 localStorage／`storage` 事件通知 | 記憶體工作階段交接、共享紀元／嘗試狀態 | 不支援登入／聊天；不能退化成每分頁自行刷新 |
| 可用的同站 Cookie、既有 WebSocket 與本機同步儲存能力 | A02／A03 憑證、每分頁 WSS、游標／投影保存 | 顯示阻擋原因，不宣稱已登入或已完成同步 |
| Page Visibility API | 各分頁獨立 W21 | 不支援登入／聊天，不猜前景 |

FB 在登入前檢查能力與共享儲存可用性；執行中能力喪失時停止自動刷新與該分頁 WSS，顯示不支援／需恢復瀏覽器設定。**不提供無鎖的「單分頁降級」**，因為不能可靠排除其他分頁；不靠原生應用程式、PWA、SharedWorker 補缺。跨來源嵌入／不同儲存分割不列入本方案。

支援前提是上述能力全部可用；具體瀏覽器／版本清單仍由 PM／QA 在[響應式 Web 決策](../decisions.md#decision-rwd)登錄，尚無版本相容性實測。依據：[Web Locks](https://developer.mozilla.org/en-US/docs/Web/API/Web_Locks_API)、[BroadcastChannel](https://developer.mozilla.org/en-US/docs/Web/API/Broadcast_Channel_API)、[Page Visibility](https://developer.mozilla.org/en-US/docs/Web/API/Page_Visibility_API)。背景排程或關頁通知不保證即時，C7 靠租期到期兜底。

**候選驗收：** [AC-N19](../testing/acceptance-matrix.md#ac-n19)～[AC-N24](../testing/acceptance-matrix.md#ac-n24)、[AC-N27](../testing/acceptance-matrix.md#ac-n27)、[AC-N28](../testing/acceptance-matrix.md#ac-n28)，均未執行。

## 決策與共用參照

- [響應式 Web 行為](../ui/web-rwd.md#web-rwd)
- [決策：Web Push 範圍](../decisions.md#decision-web-push)
- [決策：響應式 Web 版面](../decisions.md#decision-rwd)
- [返回文件導覽](../README.md)
