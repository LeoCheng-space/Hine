<a id="hine-ic-04--frontend-a-角色-prd"></a>
# HINE-IC-0.4 — 前端 A 角色 PRD

**版本：** HINE-IC-0.4  
**狀態：** 現行角色 PRD（2026-10-01 PM 決議）
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
**追溯：** [REQ-01 帳戶驗證與登入身分](../testing/acceptance-matrix.md#req-01), [REQ-02 憑證更新與登出轉換](../testing/acceptance-matrix.md#req-02), [REQ-15 在線狀態與多裝置存活狀態](../testing/acceptance-matrix.md#req-15); [W01](../contracts/interface-contract.md#event-w01), [W02](../contracts/interface-contract.md#event-w02), [W03](../contracts/interface-contract.md#event-w03), [W04](../contracts/interface-contract.md#event-w04), [W17](../contracts/interface-contract.md#event-w17)。
- **前置條件：** FB 提供目前已驗證的 SessionContext（公開 user_id、device_id、存取權杖與工作階段世代）；FB 已在認證前取得 `hine-session` Web Lock。
- **正常流程：** 建立唯一的應用程式範圍 WSS；將 [W01](../contracts/interface-contract.md#event-w01) 作為第一個業務訊框送出；驗證 [W02](../contracts/interface-contract.md#event-w02) 的身分／裝置／世代；依 `heartbeat_interval_seconds` 安排 [W03](../contracts/interface-contract.md#event-w03)，依 `heartbeat_timeout_seconds` 偵測缺少的 [W04](../contracts/interface-contract.md#event-w04)。不回報 W21 活動租約。
- **失敗流程：** 依共享的[錯誤復原契約](../contracts/interface-contract.md#error-recovery)，按錯誤碼與操作範圍處理 [W17](../contracts/interface-contract.md#event-w17)。僅 UNAUTHENTICATED／已知權杖過期使用 [FB-02](frontend-b.md#fb-02) 認證流程；有效權杖的斷線則經 W01/W02 重新連線後再送 W15，不得盲目執行 A03。FORBIDDEN、NOT_FOUND、驗證、衝突及相依項目失敗僅使受影響操作失敗。事件流 SYNC_RESET_REQUIRED 使用 W13；REST 游標失敗僅重設該查詢。未確認結果時保留相同的 C1。
- **驗收條件：** 路由變更不會建立另一個連線。[A03](../contracts/interface-contract.md#api-a03) 成功交接時建立新連線，而非在同一連線重新認證；A03 結果不明且逾時、401 或刷新失敗時，停止 WSS／自動刷新並清除本機可用認證狀態、提示重新登入。其他分頁未取得 Web Lock 時不建立 WSS。
**交接：** [FB-01](../prd/frontend-b.md#fb-01) SessionContext／認證轉換；[BA-01](../prd/backend-a.md#ba-01)/[BB-01](../prd/backend-b.md#bb-01) 工作階段驗證。

<a id="fa-02"></a>
<a id="fa-02-token-refresh-and-logout-teardown"></a>
<a id="fa-02--token-refresh-and-logout-teardown"></a>
### FA-02 — 權杖更新與登出拆除
**追溯：** [REQ-02 憑證更新與登出轉換](../testing/acceptance-matrix.md#req-02); [A03](../contracts/interface-contract.md#api-a03), [A04](../contracts/interface-contract.md#api-a04), [W01](../contracts/interface-contract.md#event-w01), [W02](../contracts/interface-contract.md#event-w02), [W13](../contracts/interface-contract.md#event-w13), [W14](../contracts/interface-contract.md#event-w14), [W15](../contracts/interface-contract.md#event-w15), [W16](../contracts/interface-contract.md#event-w16), [W17](../contracts/interface-contract.md#event-w17)。
- **前置條件：** 現有 WSS 與已儲存的使用者事件流游標；此分頁持有 `hine-session` Web Lock。
- **正常流程：** FB 發布 [A03](../contracts/interface-contract.md#api-a03) 的新 AccessSession 後，停止舊連線業務訊框、關閉舊連線、開啟新連線、送出 W01／接收 W02，並從已儲存游標繼續。A04 執行時關閉連線並清除目前帳戶的作用中投影。鎖持有至分頁結束；另一分頁僅在鎖釋放後取得鎖並重新驗證工作階段。
- **失敗流程：** 依 M3 簡化規則：正常需要時 A03 自動刷新一次；等待 10 秒仍無法確認結果、收到 401 或刷新失敗，即停止 WSS／自動刷新、清除本機可用認證狀態並提示重新登入；舊 Cookie 寬限 0 秒，不重播舊刷新請求，不進行跨分頁接班。有效 retry_after_ms 可等待到期後最多再自動嘗試一次；缺少／無效則停止自動刷新，交由使用者手動操作。服務端錯誤／網路問題不得冒充密碼錯誤。
- **驗收條件：** 不存在同一連線重新認證路徑；成功更新使用新連線與已儲存游標，登出拆除目前帳戶即時狀態；本機清除不宣稱已完成 A04。
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
- **正常流程：** 已收訊息及其識別資訊完成本機持久保存後才送出 [W08](../contracts/interface-contract.md#event-w08)，實際閱讀後才送出 [W09](../contracts/interface-contract.md#event-w09)；使用 [W19](../contracts/interface-contract.md#event-w19)／[W10](../contracts/interface-contract.md#event-w10) 調和狀態。W08 不需先取得伺服器回條。群組不提供已讀人數／名單彙總，但保留個別回條狀態。
- **失敗流程：** 重複回條具冪等性；較舊的延遲狀態不會讓已讀狀態倒退。重新連線時，同步會還原狀態。
- **驗收條件：** 用戶端絕不僅因訊息抵達就回報已讀；已收訊息的本機持久保存先於 W08；`read` 單調遞增且代表已送達。即使沒有新訊息送出，回條狀態仍可復原。未讀徽章只顯示伺服器最近一次查詢值（C14-S），不做本機加減；群組不顯示彙總回條。
- **未讀數：** 依 [C14-S](../contracts/interface-contract.md#unread-count)，只採伺服器最近一次查詢值，不做本機加／減；本機新訊息提示不得冒充 `unread_count`。開啟對話 A12 與首次登入／游標重設 W14 依契約更新查詢值。見[未讀政策](../contracts/interface-contract.md#unread-merge)。
**交接：** [BA-04](../prd/backend-a.md#ba-04) W08/W09 轉換；[BB-05](../prd/backend-b.md#bb-05) 標準回條與 `unread_count`；[FB-05](../prd/frontend-b.md#fb-05) 聊天清單未讀數。

<a id="fa-05"></a>
<a id="fa-05-chat-navigation-history-bootstrap-and-synchronization"></a>
<a id="fa-05--chat-navigation-history-bootstrap-and-synchronization"></a>
### FA-05 — 聊天導覽、歷史紀錄、初始化與同步
**追溯：** [REQ-04 一對一聊天導覽與建立](../testing/acceptance-matrix.md#req-04), [REQ-08 跨節點即時廣播與漏送復原](../testing/acceptance-matrix.md#req-08), [REQ-09 首次登入、已授權快照與歷史分離](../testing/acceptance-matrix.md#req-09), [REQ-10 快照切換與即時投影合併](../testing/acceptance-matrix.md#req-10), [REQ-11 撤銷篩選、自身通知與多群組同步](../testing/acceptance-matrix.md#req-11); [A12](../contracts/interface-contract.md#api-a12), [A19](../contracts/interface-contract.md#api-a19), [W07](../contracts/interface-contract.md#event-w07), [W11](../contracts/interface-contract.md#event-w11), [W12](../contracts/interface-contract.md#event-w12), [W13](../contracts/interface-contract.md#event-w13), [W14](../contracts/interface-contract.md#event-w14), [W15](../contracts/interface-contract.md#event-w15), [W16](../contracts/interface-contract.md#event-w16), [W17](../contracts/interface-contract.md#event-w17)。
- **前置條件：** FB 將已授權的對話 ID 路由至 FA，或已驗證用戶端具有已儲存事件流游標／首次登入狀態。
- **正常流程：** 提供 `openChat(conversation_id)` 供 FB 呼叫；掛載／切換聊天 UI，使用 A12 取得詳細資料、A19 由新到舊載入歷史，並以 W13/W14 取得快照。對單一 snapshot_id 暫存所有頁面，合併期間接收的即時項目，原子切換本機投影，最後安裝 start_cursor。W14 每頁最多 100 個邏輯項目；W16 每批最多 100 個事件、每次請求最多掃描 1000 個事件流位置，到上限依游標續傳，未掃完不得當同步完成。原子儲存投影與游標；保留核心本機持久性義務，不代表完整離線產品。重新連線、回到前景及協調時使用 W15/W16；較舊歷史使用 A19。C14-S 未讀數以伺服器最近查詢值為準，不本機合併。
- **失敗流程：** A12 拒絕時移除無法存取的檢視。A19 游標失敗僅重啟該歷史查詢，不呼叫 W13。頁面不完整時不儲存 start_cursor；快照切換時保留已觀察到的即時 E41/C1；僅在原子套用投影時前移 W16 游標。WSS 事件流重設時請求新的 W13；撤權內容持續過濾，不阻擋其他事件流資料列。
- **驗收條件：** FB 負責路由並呼叫 FA 的 `openChat`；FA 使用單一應用程式範圍連線。歷史／清單游標維持於本機；快照（截至 H）與 H 之後增量事件流銜接無缺口，合併無重複，不宣稱 H 以前全部歷史已下載；不顯示撤權後未授權內文。新成員僅能讀加入界線之後的訊息；A19、W14、W16、附件授權與 C14-S 未讀計算共用伺服器判定的可讀範圍，不得只在 UI 隱藏。[加入界線](../contracts/interface-contract.md#join-boundary)。版面遵循[集中管理的 Web/RWD 章節](../ui/web-rwd.md#web-rwd)。
**交接：** [FB-05](../prd/frontend-b.md#fb-05) `openChat` 與路由；[BB-03](../prd/backend-b.md#bb-03) 對話詳細資料與授權；[BB-05](../prd/backend-b.md#bb-05) A19 訊息歷史；[BA-06](../prd/backend-a.md#ba-06)/[BB-06](../prd/backend-b.md#bb-06) 事件流掃描／投影；[QA-03](../prd/qa.md#qa-03) 游標復原。

<a id="fa-06--對話附件更新與下載"></a>
<a id="fa-06"></a>
<a id="fa-06-conversation-attachments-renewal-and-downloads"></a>
<a id="fa-06--conversation-attachments-renewal-and-downloads"></a>
### FA-06 — 對話附件與下載
**追溯：** [REQ-13 圖片、檔案與上傳更新](../testing/acceptance-matrix.md#req-13); [A20](../contracts/interface-contract.md#api-a20), [A21](../contracts/interface-contract.md#api-a21), [A22](../contracts/interface-contract.md#api-a22), [W05](../contracts/interface-contract.md#event-w05), [W07](../contracts/interface-contract.md#event-w07); [authorize](../contracts/interface-contract.md#internal-authorize)。
- **前置條件：** 對話目前已授權，且已選取支援的 JPEG、PNG 或 PDF 檔案，單檔不超過 10 MiB。
- **正常流程：** 使用 `scope=conversation` 呼叫 A20，以單次簽署網址 PUT 原始位元組（非 multipart、JSON 或 base64；不得附帶 HINE 憑證），等待 A21 狀態為就緒才送附件 W05。使用 A22 取得接收端中繼資料與短效網址；只用已核驗版本，收件端不得以僅限擁有者的 A21 查詢取資料。PDF 以下載附件呈現，不內嵌預覽。
- **失敗流程：** PUT 回覆遺失時先以原嘗試 A21 核驗；重送保留簽章中的僅建立條件。GCS 412 不得視為成功、移除前置條件或刪除目標後重送；A21 確認就緒前不得送 W05。上傳授權過期時，A25 本版範圍外，使用新 Idempotency-Key 重新 A20 建立新嘗試／attachment_id；舊嘗試遲到不得完成新附件。A22 無法取得固定版本時顯示失敗並重新取得 A22，不改送最新版本。
- **驗收條件：** 二進位位元組不經 WSS 傳送；訊息具備與文字相同 C1/ACK/同步保證；訊息或記錄不得放簽署網址；下載時重新檢查目前對話權限。僅 JPEG、PNG、PDF、每檔 ≤10 MiB；PDF 僅下載。響應式圖片／檔案呈現遵循 Web/RWD；參見 [AC-R04](../testing/acceptance-matrix.md#ac-r04)。
- **內容一致性：** 依 `UploadGrant.required_headers` 原值送出 `Content-Type`、`x-goog-if-generation-match:0`、`Cache-Control:no-transform`；簽署網址不是一次性的。A21 就緒狀態與 A22 中繼資料／位元組指向同一已核驗版本，前端不得自行選擇世代或以檔名／大小相同視為版本一致。參見 [AC-R04 四項交錯](../testing/acceptance-matrix.md#ac-r04-version-cases)。
**交接：** [BB-07](../prd/backend-b.md#bb-07) 授權憑證／中繼資料；[DO-02](../prd/devops.md#do-02) 傳輸／執行環境設定。

<a id="fa-07"></a>
<a id="fa-07-app-activity-and-lease-renewal"></a>
<a id="fa-07--app-activity-and-lease-renewal"></a>
### FA-07 — 應用程式活動與租約更新
**追溯：** [REQ-14 裝置活動與背景推播](../testing/acceptance-matrix.md#req-14), [REQ-15 在線狀態與多裝置存活狀態](../testing/acceptance-matrix.md#req-15); [W21](../contracts/interface-contract.md#event-w21), [W22](../contracts/interface-contract.md#event-w22); [recordActivity](../contracts/interface-contract.md#internal-record-activity)。
- **前置條件：** 本版不適用；保留此卡與相關追溯 ID。
- **正常流程：** 本版範圍外（2026-10-01 PM 決議）：應用程式活動租約、W21／W22 活動上報與 unknown 推播對象判斷（M2／C7）。保留 ID FA-07、REQ-14／15、W21／W22、`recordActivity`。
- **失敗流程：** 不適用；不實作活動租約。
- **驗收條件：** 不驗收活動租約／W21／W22。WSS 心跳、斷線重連及 Page Visibility 已讀判斷仍依其他功能卡保留且互不混用。
- **交接：** 相關已批准交付改由 FA-01／FA-02 的 WSS 心跳與重連及 FA-08 的可見性已讀判斷負責；保留 BA-07／BB-08 參照僅供 ID 追溯，不代表本版活動租約工作。

<a id="fa-08"></a>
<a id="fa-08-responsive-web-chat-interaction"></a>
<a id="fa-08--responsive-web-chat-interaction"></a>
### FA-08 — 響應式 Web 聊天互動
**追溯：** [REQ-19 共用響應式 Web 頁面](../testing/acceptance-matrix.md#req-19), [REQ-20 響應式聊天互動與已讀狀態](../testing/acceptance-matrix.md#req-20); [Web/RWD](../ui/web-rwd.md#web-rwd), [A12](../contracts/interface-contract.md#api-a12), [A19](../contracts/interface-contract.md#api-a19), [W08](../contracts/interface-contract.md#event-w08), [W09](../contracts/interface-contract.md#event-w09); [authorize](../contracts/interface-contract.md#internal-authorize)。
- **前置條件：** 已驗證 Web 工作階段、可用聊天路由與單一應用程式範圍 WSS。
- **正常流程：** 套用共用 Web/RWD 行為：單一 768 CSS px 斷點，窄版清單／聊天室切換，寬版清單與聊天室雙欄；重排時保留草稿、待處理 C1 與閱讀位置。撰寫區配合虛擬鍵盤；中文 IME 組字中 Enter 不送出。只有無法確定鍵盤能力時採 Enter 換行、送出按鈕送出並支援 Ctrl／⌘+Enter。只依[已讀判定規則](../ui/web-rwd.md#rwd-read-rule)送 W09；不以寬度推定鍵盤來源。
- **失敗流程：** 版面變更不重新登入、另開 WSS 或變更／重設 SyncCursor。W08 在已收訊息本機持久保存後送出，不必送 W09；可見性不確定時不推定已讀。
- **驗收條件：** 互動遵循單一[共用 UI 規格](../ui/web-rwd.md#web-rwd)，重排後保留 C1 狀態與閱讀位置，W08/W09 區分。已讀門檻為他人訊息最大可能交集 50%、連續 500 ms；頁面隱藏、模態覆蓋或條件中斷即停止歸零，表示可見而非讀完全文（2026-10-01 PM 決議，尚未完成瀏覽器驗證）。
**交接：** [FB-07](../prd/frontend-b.md#fb-07) 共用 UI／`openChat`；[BA-04](../prd/backend-a.md#ba-04)/[BB-05](../prd/backend-b.md#bb-05) 已讀模型；[QA-06](../prd/qa.md#qa-06) 瀏覽器輸入／可見性。

## 決策與共用參照

- [響應式 Web 行為](../ui/web-rwd.md#web-rwd)
- [決策：Web Push 範圍](../decisions.md#decision-web-push)
- [決策：響應式 Web 版面](../decisions.md#decision-rwd)
- [返回文件導覽](../README.md)
