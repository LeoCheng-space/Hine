<a id="hine-ic-04--frontend-a-角色-prd"></a>
# HINE-IC-0.4 — 前端 A 角色 PRD

**版本：** HINE-IC-0.4  
**狀態：** 待產品核准  
**來源：** [歷史來源：HINE-IC-0.4 角色 PRD](../HINE-IC-0.4-role-prds.md)；唯一現行介面規格依據為[共同介面契約](../contracts/interface-contract.md)。  
**角色目的：** 負責聊天 UI、應用程式範圍的 WSS、訊息狀態與本機同步投影。本 PRD 規定未來行為與驗收要求，不代表已實作或已完成測試。  
**必讀／串接時查閱：** [系統架構](../architecture/README.md)；[共同介面契約](../contracts/interface-contract.md)；[驗收矩陣](../testing/acceptance-matrix.md)；[Web/RWD 規格](../ui/web-rwd.md#web-rwd)；[決策：Web Push](../decisions.md#decision-web-push)；[文件導覽](../README.md)。

## 範圍

- **範圍內：** 聊天 UI、應用程式範圍的 WSS、訊息狀態與本機同步投影；以及下列角色專屬功能卡。
- **範圍外：** 其他角色所負責的範圍；亦不得變更共用 API／事件 ID、正式資料、ACK、游標或同步語意。共用欄位型別、封套、錯誤與限制均以共同介面契約為準。
- **共用 Web 行為：** 遵循 [Web / RWD 規格](../ui/web-rwd.md#web-rwd)；不得另訂斷點或重複定義版面規則。

## 功能索引

- [FA-01 — 建立 WSS 工作階段與狀態](#fa-01)
- [FA-02 — 權杖更新與登出清理](#fa-02)
- [FA-03 — 即時傳送與持久化 ACK](#fa-03)
- [FA-04 — 送達與已讀回條](#fa-04)
- [FA-05 — 聊天導覽、歷史紀錄、初始化與同步](#fa-05)
- [FA-06 — 對話附件、更新與下載](#fa-06)
- [FA-07 — 應用程式活動與租約更新](#fa-07)
- [FA-08 — 響應式 Web 聊天互動](#fa-08)

## 角色目的與責任界線

負責聊天 UI、應用程式範圍的 WSS、訊息狀態與本機同步投影，並提供 `openChat(conversation_id)`。不讀取或管理更新憑證 Cookie（只消費 FB 交付的 AccessSession）、簽發 JWT、簽署 GCS URL 或傳送推播通知。

<a id="fa-01"></a>
<a id="fa-01-wss-session-establishment-and-state"></a>
<a id="fa-01--wss-session-establishment-and-state"></a>
### FA-01 — 建立 WSS 工作階段與狀態
**追溯：** [REQ-01 帳戶驗證與登入身分](../testing/acceptance-matrix.md#req-01), [REQ-02 憑證更新與登出轉換](../testing/acceptance-matrix.md#req-02), [REQ-15 在線狀態與多裝置存活狀態](../testing/acceptance-matrix.md#req-15); [W01](../contracts/interface-contract.md#event-w01), [W02](../contracts/interface-contract.md#event-w02), [W03](../contracts/interface-contract.md#event-w03), [W04](../contracts/interface-contract.md#event-w04), [W17](../contracts/interface-contract.md#event-w17), [W21](../contracts/interface-contract.md#event-w21)。
- **前置條件：** FB 提供目前已驗證的 SessionContext（公開 user_id、device_id、存取權杖、世代）。
- **正常流程：** 建立唯一的 WSS；將 [W01](../contracts/interface-contract.md#event-w01) 作為第一個業務訊框送出；驗證 [W02](../contracts/interface-contract.md#event-w02) 的身分／裝置／世代；使用 [W02](../contracts/interface-contract.md#event-w02) 的 `heartbeat_interval_seconds` 安排 [W03](../contracts/interface-contract.md#event-w03)，並使用 `heartbeat_timeout_seconds` 偵測缺少的 [W04](../contracts/interface-contract.md#event-w04)；驗證成功後回報初始 [W21](../contracts/interface-contract.md#event-w21)。
- **失敗流程：** 依共享的[錯誤復原契約](../contracts/interface-contract.md#error-recovery)，按錯誤碼與操作範圍處理 [W17](../contracts/interface-contract.md#event-w17)。僅 UNAUTHENTICATED／已知權杖過期使用 [FB-02](frontend-b.md#fb-02) 唯一既有的認證流程；有效權杖的斷線則經 W01/W02 重新連線後再送 W15，不得盲目執行 A03。FORBIDDEN、NOT_FOUND、驗證、衝突及相依項目失敗僅使受影響操作失敗。事件流 SYNC_RESET_REQUIRED 使用 W13；REST 游標失敗僅重設該查詢。未確認結果時保留相同的 C1。
- **驗收條件：** 路由變更不會建立另一個連線。[A03](../contracts/interface-contract.md#api-a03) 交接會建立新連線，而非在同一連線上重新認證。[A04](../contracts/interface-contract.md#api-a04) 會迅速拆除目前連線並清除帳戶本機認證狀態。
**交接：** [FB-01](../prd/frontend-b.md#fb-01) SessionContext／認證轉換；[BA-01](../prd/backend-a.md#ba-01)/[BB-01](../prd/backend-b.md#bb-01) 工作階段驗證。

<a id="fa-02"></a>
<a id="fa-02-token-refresh-and-logout-teardown"></a>
<a id="fa-02--token-refresh-and-logout-teardown"></a>
### FA-02 — 權杖更新與登出拆除
**追溯：** [REQ-02 憑證更新與登出轉換](../testing/acceptance-matrix.md#req-02); [A03](../contracts/interface-contract.md#api-a03), [A04](../contracts/interface-contract.md#api-a04), [W01](../contracts/interface-contract.md#event-w01), [W02](../contracts/interface-contract.md#event-w02), [W13](../contracts/interface-contract.md#event-w13), [W14](../contracts/interface-contract.md#event-w14), [W15](../contracts/interface-contract.md#event-w15), [W16](../contracts/interface-contract.md#event-w16), [W17](../contracts/interface-contract.md#event-w17)。
- **前置條件：** 現有 WSS 與已儲存的使用者事件流游標。
- **正常流程：** FB 發布 [A03](../contracts/interface-contract.md#api-a03) 的新 AccessSession 後，停止在舊連線上送出業務訊框、關閉該連線、開啟新連線、送出 [W01](../contracts/interface-contract.md#event-w01)/接收 [W02](../contracts/interface-contract.md#event-w02)、送出 [W21](../contracts/interface-contract.md#event-w21)，並從已儲存游標繼續。[A04](../contracts/interface-contract.md#api-a04) 執行時，關閉連線並清除目前帳戶的作用中投影。
- **失敗流程：** 更新失敗不會觸發在同一連線上送出 [W01](../contracts/interface-contract.md#event-w01)；斷線時保留任何未確認傳送的原始 C1。
- **驗收條件：** 不存在同一連線重新認證路徑；更新使用新連線與已儲存游標，登出則拆除目前帳戶的即時狀態。
- **候選（待批准）：**
  - 每個分頁各有一條應用程式範圍的 WSS，不跨分頁共用；另一分頁完成 A03 或 A02 後，FB 依[多分頁工作階段交接](frontend-b.md#fb-multi-tab)送來新的 AccessSession，FA 依本卡流程換線。
  - A03 提交後，仍在舊連線上的業務訊框可能收到 W17 `UNAUTHENTICATED`。若 SessionContext 已持有較新的 AccessSession（依 FB 的 `auth_epoch` 判斷），FA 不再觸發更新，改在新連線以同一 C1 重送。
  - 伺服器也可能先關閉舊連線。
  - 見[驗收 AC-N06](../testing/acceptance-matrix.md#ac-n06)、[AC-N19](../testing/acceptance-matrix.md#ac-n19)～[AC-N24](../testing/acceptance-matrix.md#ac-n24)。
**交接：** [FB-02](../prd/frontend-b.md#fb-02) 連線取代；[BA-01](../prd/backend-a.md#ba-01)/[BB-01](../prd/backend-b.md#bb-01) 工作階段強制執行；[QA-02](../prd/qa.md#qa-02) 生命週期案例。

<a id="fa-03"></a>
<a id="fa-03-realtime-send-and-persisted-ack"></a>
<a id="fa-03--realtime-send-and-persisted-ack"></a>
### FA-03 — 即時傳送與持久化 ACK
**追溯：** [REQ-06 文字訊息與持久 ACK](../testing/acceptance-matrix.md#req-06), [REQ-07 ACK 遺失、重試與去重](../testing/acceptance-matrix.md#req-07); [W05](../contracts/interface-contract.md#event-w05), [W06](../contracts/interface-contract.md#event-w06), [W07](../contracts/interface-contract.md#event-w07), [W17](../contracts/interface-contract.md#event-w17); [authorize](../contracts/interface-contract.md#internal-authorize), [persistIfAbsent](../contracts/interface-contract.md#internal-persist-if-absent)。
- **前置條件：** 對話已授權且連線已驗證。
- **正常流程：** 傳送前持久保存原始 C1／承載資料與待處理狀態，送出 [W05](../contracts/interface-contract.md#event-w05)，將 [W06](../contracts/interface-contract.md#event-w06) 與傳送端 [W07](../contracts/interface-contract.md#event-w07) 合併為同一筆 M1；未確認前保留原意圖，以便重啟／重連時復原。[本機持久化](../contracts/interface-contract.md#local-persistence-boundary)是既有義務，不等同完整離線應用程式／PWA。
- **失敗流程：** ACK 遺失、斷線或 OUTCOME_UNCONFIRMED 時，保留並重試原始 C1 與承載資料。相同 C1 搭配不同承載資料時呈現衝突；同一意圖絕不可悄悄產生替代 C1。
- **驗收條件：** 相同 C1 只產生一筆可見／持久化的 M1；不得將 `persisted` 呈現為已送達／已讀。ACK 可在 [W07](../contracts/interface-contract.md#event-w07) 前後抵達而不重複。已知的回滾不得顯示為成功。
**交接：** [BA-03](../prd/backend-a.md#ba-03) W05–W07 順序；[BB-04](../prd/backend-b.md#bb-04) 原子持久化；[QA-04](../prd/qa.md#qa-04) 失敗情境。

<a id="fa-04"></a>
<a id="fa-04-delivery-and-read-receipts"></a>
<a id="fa-04--delivery-and-read-receipts"></a>
### FA-04 — 送達與已讀回條
**追溯：** [REQ-12 已送達／已讀回條狀態機](../testing/acceptance-matrix.md#req-12); [W08](../contracts/interface-contract.md#event-w08), [W09](../contracts/interface-contract.md#event-w09), [W10](../contracts/interface-contract.md#event-w10), [W16](../contracts/interface-contract.md#event-w16), [W19](../contracts/interface-contract.md#event-w19); [persistReceipt](../contracts/interface-contract.md#internal-persist-receipt)。
- **前置條件：** 已授權訊息已持久儲存於本機；標記已讀前必須實際閱讀。
- **正常流程：** 已收訊息及其識別資訊完成本機持久保存後才送出 [W08](../contracts/interface-contract.md#event-w08)，實際閱讀後才送出 [W09](../contracts/interface-contract.md#event-w09)；使用 [W19](../contracts/interface-contract.md#event-w19)／[W10](../contracts/interface-contract.md#event-w10) 調和狀態。W08 不需先取得伺服器回條。群組彙總仍是[條件功能](../contracts/interface-contract.md#receipt-projection-handoff)，不阻擋一對一。
- **失敗流程：** 重複回條具冪等性；較舊的延遲狀態不會讓已讀狀態倒退。重新連線時，同步會還原狀態。
- **驗收條件：** 用戶端絕不僅因訊息抵達就回報已讀；已收訊息的本機持久保存先於 W08；`read` 單調遞增且代表已送達。即使沒有新訊息送出，回條狀態仍可復原。
- **候選（待批准）：** 依 [C14](../contracts/interface-contract.md#unread-count)，開啟對話的 A12 或 W13／W14 回應作為該對話的新基準並覆蓋本機值；本機加減依 PM 尚未選定的方案：若採 C14-M，依[合併規則](../contracts/interface-contract.md#unread-merge)——由基準計入的訊息，只有在基準回應到達後才送出的 W09，其 W19 為 `status:"read"` 且 `changed:true` 時才減一；本機依規則加過一的訊息，收到 W19 `status:"read"` 即減一；每則最多一次，重複 W19 與重播不改變計數；以 A11／A12 為基準時，W07／W16 新訊息不加一；已確認已讀（W19 `status:"read"`）的訊息，之後取得的建立事件也不加一。若採簡化候選 C14-S，則不做本機加減，只顯示最近查詢值；對話串內的新訊息提示是本機計數，不寫回 `unread_count`。自己的訊息不送 W09。
**交接：** [BA-04](../prd/backend-a.md#ba-04) W08/W09 轉換；[BB-05](../prd/backend-b.md#bb-05) 標準回條與 `unread_count`；[FB-05](../prd/frontend-b.md#fb-05) 聊天清單未讀數。

<a id="fa-05"></a>
<a id="fa-05-chat-navigation-history-bootstrap-and-synchronization"></a>
<a id="fa-05--chat-navigation-history-bootstrap-and-synchronization"></a>
### FA-05 — 聊天導覽、歷史紀錄、初始化與同步
**追溯：** [REQ-04 一對一聊天導覽與建立](../testing/acceptance-matrix.md#req-04), [REQ-08 跨節點即時廣播與漏送復原](../testing/acceptance-matrix.md#req-08), [REQ-09 首次登入、已授權快照與歷史分離](../testing/acceptance-matrix.md#req-09), [REQ-10 快照切換與即時投影合併](../testing/acceptance-matrix.md#req-10), [REQ-11 撤銷篩選、自身通知與多群組同步](../testing/acceptance-matrix.md#req-11); [A12](../contracts/interface-contract.md#api-a12), [A19](../contracts/interface-contract.md#api-a19), [W07](../contracts/interface-contract.md#event-w07), [W11](../contracts/interface-contract.md#event-w11), [W12](../contracts/interface-contract.md#event-w12), [W13](../contracts/interface-contract.md#event-w13), [W14](../contracts/interface-contract.md#event-w14), [W15](../contracts/interface-contract.md#event-w15), [W16](../contracts/interface-contract.md#event-w16), [W17](../contracts/interface-contract.md#event-w17)。
- **前置條件：** FB 將已授權的對話 ID 路由至 FA，或已驗證用戶端具有已儲存的事件流游標／首次登入狀態。
- **正常流程：** 提供 `openChat(conversation_id)` 供 FB 呼叫；掛載／切換聊天 UI，使用 [A12](../contracts/interface-contract.md#api-a12) 取得詳細資料，並使用 [A19](../contracts/interface-contract.md#api-a19) 由新到舊載入歷史。另行請求 [W13](../contracts/interface-contract.md#event-w13)/[W14](../contracts/interface-contract.md#event-w14) 快照，為單一 snapshot_id 暫存所有頁面，合併期間接收的即時項目，原子切換本機投影，最後才安裝 start_cursor。原子儲存投影與游標；即使完整離線應用程式/PWA 不在範圍內，本機持久性仍屬必須。重新連線、回到前景及協調時使用 [W15](../contracts/interface-contract.md#event-w15)/[W16](../contracts/interface-contract.md#event-w16)；較舊歷史使用 [A19](../contracts/interface-contract.md#api-a19)。
- **失敗流程：** [A12](../contracts/interface-contract.md#api-a12) 拒絕時移除無法存取的檢視。[A19](../contracts/interface-contract.md#api-a19) 游標失敗僅重新啟動其歷史查詢，絕不呼叫 [W13](../contracts/interface-contract.md#event-w13)。頁面不完整時絕不儲存 start_cursor；快照切換時保留已觀察到的即時 E41/C1；僅在原子套用投影時前移 [W16](../contracts/interface-contract.md#event-w16) 游標。WSS 事件流重設時請求新的 [W13](../contracts/interface-contract.md#event-w13)；撤權內容持續過濾，不阻擋其他事件流資料列。
- **驗收條件：** FB 負責路由並呼叫 FA 的 `openChat`；FA 負責聊天顯示並使用單一應用程式範圍的連線。歷史／清單游標維持於本機；快照（截至 H）與 H 之後的增量事件流銜接無缺口，合併即時與快照資料後不重複（不宣稱 H 以前的全部歷史已下載，較早歷史依需要經 A19 載入），也不顯示撤權後未授權內文。響應式聊天版面遵循[集中管理的 Web/RWD 章節](../ui/web-rwd.md#web-rwd)。
- **候選（待批准）：** [G1](../decisions.md#group-device-content) 區分已在裝置的副本與伺服器待送資料：得知自己被移除後沿用本卡移除不可存取畫面，不新增退出後唯讀頁、不承諾遠端安全抹除；未得知撤權的離線裝置可能仍顯示舊副本。[G3](../decisions.md#group-new-queries) 的新查詢不得取回該對話；E1 交付停止不等於追回已入網路內容（[AC-N25](../testing/acceptance-matrix.md#ac-n25)、[AC-N26](../testing/acceptance-matrix.md#ac-n26)）。
**交接：** [FB-05](../prd/frontend-b.md#fb-05) `openChat` 與路由；[BB-03](../prd/backend-b.md#bb-03) 對話詳細資料與授權；[BB-05](../prd/backend-b.md#bb-05) A19 訊息歷史；[BA-06](../prd/backend-a.md#ba-06)/[BB-06](../prd/backend-b.md#bb-06) 事件流掃描／投影；[QA-03](../prd/qa.md#qa-03) 游標復原。

<a id="fa-06"></a>
<a id="fa-06-conversation-attachments-renewal-and-downloads"></a>
<a id="fa-06--conversation-attachments-renewal-and-downloads"></a>
### FA-06 — 對話附件、更新與下載
**追溯：** [REQ-13 圖片、檔案與上傳更新](../testing/acceptance-matrix.md#req-13); [A20](../contracts/interface-contract.md#api-a20), [A21](../contracts/interface-contract.md#api-a21), [A22](../contracts/interface-contract.md#api-a22), [A25](../contracts/interface-contract.md#api-a25), [W05](../contracts/interface-contract.md#event-w05), [W07](../contracts/interface-contract.md#event-w07); [authorize](../contracts/interface-contract.md#internal-authorize)。
- **前置條件：** 對話目前已授權，且已選取支援的檔案。
- **正常流程：** 使用 `scope=conversation` 呼叫 [A20](../contracts/interface-contract.md#api-a20)，依待批准的 [C10](../contracts/interface-contract.md#signed-upload-contract)，以單次簽署網址 PUT 上傳原始檔案位元組（非 multipart、JSON 或 base64；不得附帶 HINE 憑證），接著須等 [A21](../contracts/interface-contract.md#api-a21) 狀態為就緒才送出附件 [W05](../contracts/interface-contract.md#event-w05)。透過已授權的 [A22](../contracts/interface-contract.md#api-a22) 取得接收端中繼資料與短效網址，遵循待批准的 [C9](../contracts/interface-contract.md#attachment-handoff)；絕不以僅限擁有者使用的 A21 查詢接收端資料。
- **失敗流程：** 依待批准 [C10](../contracts/interface-contract.md#signed-upload-contract)，若 PUT 回覆遺失，先以原嘗試呼叫 A21 核驗；若重送，保留簽章中的僅建立條件。遇到 GCS 412 不得視為上傳成功、移除前置條件或刪除目標後重送；A21 確認就緒前不得送 W05。待處理且有權限的失效／衝突恢復須經 A25 使用新鍵值、新嘗試；舊嘗試遲到不得完成目前附件。若 A22 無法取得固定版本，顯示失敗／重新取得 A22，不移除網址中的世代，也不改送最新版本。
- **驗收條件：** 二進位位元組不經 WSS 傳送。訊息具備與文字相同的 C1/ACK/同步保證。訊息或記錄中不得放入簽署網址；下載時重新檢查目前的對話權限。接收端依待批准 C9 經由 A22 取得必填檔名與大小中繼資料。響應式圖片／檔案預覽遵循集中管理的 Web/RWD 章節。參見 [AC-R04](../testing/acceptance-matrix.md#ac-r04)。
- **C10 內容一致性補充（待批准）：** 依 `UploadGrant.required_headers` 原值送出 `Content-Type`、`x-goog-if-generation-match:0`、`Cache-Control:no-transform`；簽署網址不是一次性的。A21 就緒狀態與 A22 中繼資料／位元組指向同一個已核驗版本，前端不得自行選擇物件世代，也不得把「檔名／大小相同」視為版本一致。參見 [AC-R04 四項交錯](../testing/acceptance-matrix.md#ac-r04-version-cases)。
**交接：** [BB-07](../prd/backend-b.md#bb-07) 授權憑證／中繼資料；[DO-02](../prd/devops.md#do-02) 傳輸／執行環境設定。

<a id="fa-07"></a>
<a id="fa-07-app-activity-and-lease-renewal"></a>
<a id="fa-07--app-activity-and-lease-renewal"></a>
### FA-07 — 應用程式活動與租約更新
**追溯：** [REQ-14 裝置活動與背景推播](../testing/acceptance-matrix.md#req-14), [REQ-15 在線狀態與多裝置存活狀態](../testing/acceptance-matrix.md#req-15); [W02](../contracts/interface-contract.md#event-w02), [W15](../contracts/interface-contract.md#event-w15), [W16](../contracts/interface-contract.md#event-w16), [W18](../contracts/interface-contract.md#event-w18), [W21](../contracts/interface-contract.md#event-w21), [W22](../contracts/interface-contract.md#event-w22); [getDevicePresence](../contracts/interface-contract.md#internal-get-device-presence), [recordActivity](../contracts/interface-contract.md#internal-record-activity)。
- **前置條件：** [W02](../contracts/interface-contract.md#event-w02) 已接受作用中裝置／工作階段世代。
- **正常流程：** 在 [W02](../contracts/interface-contract.md#event-w02) 後回報初始 [W21](../contracts/interface-contract.md#event-w21)；回報前景／背景轉換；在 [W22](../contracts/interface-contract.md#event-w22) valid_until 到期前更新；返回前景時調和事件流。
- **失敗流程：** 背景訊框遺失、租約過期或 Redis 狀態不確定時顯示未知，而非前景。忽略較舊工作階段世代的遲到活動確認。
- **驗收條件：** 後端可按裝置判定推播資格；心跳不代表前景狀態；開啟應用程式會觸發一般授權同步。
- **候選（待批准）：** 每分頁按自己的 Page Visibility 送 W21，W22 只確認本連線租期；裝置狀態由 [C7](../contracts/interface-contract.md#activity-merge) 跨節點合併，任一有效前景優先。背景分頁不能覆蓋其他前景；關閉／失效／租期到期只移除該連線回報，偵測前可保留到原租期截止，不聲稱關頁瞬間已全域更新（[AC-N27](../testing/acceptance-matrix.md#ac-n27)）。
- **交接：** [BA-07](../prd/backend-a.md#ba-07) 活動租約；[FB-01](../prd/frontend-b.md#fb-01)/[FB-02](../prd/frontend-b.md#fb-02) 已驗證工作階段／存取工作階段更新；僅在需要推播權杖綁定時涉及 [FB-06](../prd/frontend-b.md#fb-06)；[BB-08](../prd/backend-b.md#bb-08) 裝置狀態／推播。

<a id="fa-08"></a>
<a id="fa-08-responsive-web-chat-interaction"></a>
<a id="fa-08--responsive-web-chat-interaction"></a>
### FA-08 — 響應式 Web 聊天互動
**追溯：** [REQ-19 共用響應式 Web 頁面](../testing/acceptance-matrix.md#req-19), [REQ-20 響應式聊天互動與已讀狀態](../testing/acceptance-matrix.md#req-20); [Web/RWD](../ui/web-rwd.md#web-rwd), [A12](../contracts/interface-contract.md#api-a12), [A19](../contracts/interface-contract.md#api-a19), [W08](../contracts/interface-contract.md#event-w08), [W09](../contracts/interface-contract.md#event-w09); [authorize](../contracts/interface-contract.md#internal-authorize)。
- **前置條件：** 已驗證的 Web 工作階段、可用聊天路由與單一應用程式範圍的 WSS。
- **正常流程：** 套用共用 Web/RWD 聊天行為。窄版時，選取對話清單項目會開啟對話串並提供返回操作。調整大小／方向時保留各對話草稿、待處理 C1 與閱讀位置。確保撰寫區能配合虛擬鍵盤使用並遵循[集中管理的 Web/RWD 輸入與 IME 規則](../ui/web-rwd.md#web-rwd)；組字期間的 Enter 絕不可送出。瀏覽歷史時保留位置、限制長內容／媒體／檔名，且只依[已讀判定規則](../ui/web-rwd.md#rwd-read-rule)送出 [W09](../contracts/interface-contract.md#event-w09)。實體／軟體鍵盤無法判別時採[候選輸入行為](../ui/web-rwd.md#rwd-keyboard)，不以視窗寬度推定。
- **失敗流程：** 版面變更絕不重新登入、開啟另一個 WSS 或變更／重設 SyncCursor。[W08](../contracts/interface-contract.md#event-w08) 在已收訊息完成本機持久保存後即可送出，不必送出 [W09](../contracts/interface-contract.md#event-w09)。可見性狀態不確定時，不推定訊息已讀。
- **驗收條件：** 互動遵循單一[共用 UI 章節](../ui/web-rwd.md#web-rwd)；重排後保留 C1 待處理狀態與閱讀位置；[W08](../contracts/interface-contract.md#event-w08) 與 [W09](../contracts/interface-contract.md#event-w09) 仍明確區分。[W09](../contracts/interface-contract.md#event-w09) 的可見性門檻／停留時間仍是提案，須經產品／品質驗證核准。
**交接：** [FB-07](../prd/frontend-b.md#fb-07) 共用 UI／`openChat`；[BA-04](../prd/backend-a.md#ba-04)/[BB-05](../prd/backend-b.md#bb-05) 已讀模型；[QA-06](../prd/qa.md#qa-06) 瀏覽器輸入／可見性。

## 決策與共用參照

- [響應式 Web 行為](../ui/web-rwd.md#web-rwd)
- [決策：Web Push 範圍](../decisions.md#decision-web-push)
- [決策：響應式 Web 版面](../decisions.md#decision-rwd)
- [返回文件導覽](../README.md)
