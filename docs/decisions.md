<a id="hine-ic-04--待決策事項"></a>
# HINE-IC-0.4 — PM 決議事項

**狀態：** 下列 32 項均由 PM 於 2026-10-01 決定，來源為 Notion 資料庫「HINE 待 PM 批准項目（HINE-IC-0.4）」([來源](https://app.notion.com/p/f325ae03c65848aba8ddfd6e029e1f95))。本登錄記錄政策核准，不代表所有實作、部署、測試或量測均已完成；現況證據與範圍分層另見[架構程式碼對應](architecture/README.md#arch-code-map)、[驗收矩陣](testing/acceptance-matrix.md)與[變更紀錄](CHANGELOG.md)。不得把政策核准當作跨角色簽核或公有容量證明。已否決及本版不做項目標示「本版範圍外（2026-10-01 PM 決議）」。

**目前實作／證據讀法：** 方案決議維持既有核准範圍；實際程式索引見[架構程式碼對應](architecture/README.md#arch-code-map)，不能以歷史「尚未實作」文字推翻現行程式碼。Backend A W18 私有聯絡人查詢、BB `readPresenceTargets` operation 11 與 23 項回歸測試已交付（父任務已驗證）。本機真 API／PG／BA fault PF01–PF08、50-WSS protocol 負載與 Chrome product proof 分別列於[故障證據](testing/evidence/product-native-faults.json)、[負載證據](testing/evidence/product-direct-load.json)及驗收紀錄；W07 protocol p95 不代表瀏覽器呈現。Edge／Android 裝置矩陣、正式 GCP VM、雲端 GCS／signed URL、遠端 CI 與公有容量仍須各自證明；本機測試沒有因此取得團隊簽核。以下歷史決議文字僅在政策範圍內解讀，不當作目前完成度清單。Title 1–80 字元仍是候選，未獲批准為全域政策。

## 2026-10-04 — main 分支保護暫緩

使用者決議：學校作業階段暫時不啟用 GitHub `main` Branch Protection／Rulesets，其他交付工作繼續。不將分支保護當作共用環境、Backend A 或首輪串接的阻塞；仍保留[一般功能分支／PR／Review／CI 協作流程](../CONTRIBUTING.md#daily-workflow)。暫緩不等於設定完成，也不取消機密保護、共同介面確認、持久化與驗收要求。

| 決策項目 | PM 決議狀態與現行定義 | 決策成本／影響 | 相關負責角色與來源 |
|---|---|---|---|
| <a id="decision-web-push"></a>Web Push 範圍與供應商 | 已否決；本版範圍外（2026-10-01 PM 決議）：不納入 Web Push 或 iOS／Android 原生推播，無須供應商、Service Worker、訂閱或 FCM／APNs；保留開啟網頁時 WSS、聊天內提示及查詢更新未讀。 | 不需推播 worker／金鑰；缺少推播金鑰不影響核心服務就緒。 | [BB](prd/backend-b.md#bb-08)、[FB](prd/frontend-b.md#fb-06)、[DO](prd/devops.md#do-02)、[QA](prd/qa.md#qa-06) |
| <a id="decision-rwd"></a>Web 響應式版面與互動 | 需修改後採用：單一 Web／RWD 網站，768 CSS px 單一斷點，窄版清單／聊天室切換，寬版雙欄；保留鍵盤、焦點、觸控、IME、捲動、已讀與本機保存。 | 不做原生 App、PWA 或完整離線產品；FA／FB 路由與產物整合為單一網站。 | [FA](prd/frontend-a.md#fa-08)、[FB](prd/frontend-b.md#fb-07)、[QA](prd/qa.md#qa-06) |
| <a id="decision-device-id"></a>DeviceID 核發、重用與重新安裝 | 需修改後採用：伺服器核發不透明 DeviceID，僅供裝置／本機資料分區，不作憑證；同帳號同瀏覽器且 DeviceStore 尚存時重用，資料清除／遺失／重裝則新核發；切帳號重新驗證並隔離儲存。 | 不做指紋、舊裝置找回、裝置管理、遠端抹除或多帳號快速切換；每設定檔一帳號、一操作分頁。 | [A02](contracts/interface-contract.md#api-a02)、[工作階段字典](contracts/interface-contract.md#data-dictionary) |
| <a id="decision-activity-push"></a>活動租期與未知狀態推播對象 | 已否決；本版範圍外（2026-10-01 PM 決議）：不建立活動租約／unknown 推播對象政策，W21／W22 活動上報停用。 | 保留 WSS 心跳、斷線重連、返回前景同步及實際可見才送已讀；不以背景狀態推論收到／已讀。 | [C7](contracts/interface-contract.md#activity-merge)、[AC-N27](testing/acceptance-matrix.md#ac-n27) |
| <a id="decision-operational-values"></a>營運上限與速率 | 需修改後採用：本版統一設定 REST 20／50、同步 100／掃描 1000、心跳 30／90 秒、前景核對 10 秒、訊息 5／秒突發 10、登入每帳號 10／分鐘及 IP 60／分鐘、群組 50 人、附件 10 MiB JPEG／PNG／PDF、撤權新鮮度 15 秒／輪詢 5 秒／補齊 1000 ms。 | 推播與活動租約停用；必要 DB／內部驗證／啟用儲存設定不完整則就緒失敗。數值為初始設定，未量測。 | [部署設定](contracts/interface-contract.md#deployment-config) |
| <a id="decision-group-policy"></a>群組角色、人數與成員政策 | 需修改後採用：上限 50 人含管理員，只保留 admin／member；建立者為 admin；禁止移除、降級或退出最後一位 admin，須先指定其他管理員。 | 不新增自訂權限、封鎖、審核入群、公開邀請連結、大群分層或解散 API；加入前歷史另依決議處理。 | [REST](contracts/interface-contract.md#rest-api)、[事件](contracts/interface-contract.md#websocket-events) |
| <a id="decision-group-receipts"></a>群組回條可見性 | 已否決；本版範圍外（2026-10-01 PM 決議）：不提供群組已讀人數／名單、read_count／member_count 彙總或群組 W10。 | 保留一對一回條與群組個別 W08／W09／W19 狀態，供同步、逐訊息已讀及 C14-S 使用。 | [回條交接](contracts/interface-contract.md#receipt-projection-handoff) |
| <a id="decision-history-membership"></a>歷史與群組撤權（分項決議） | G1、G2、G3 均已批准：裝置副本、舊授權待送內容、新查詢分別依下方具名列決議；新成員只讀加入界線之後訊息，重加入採新界線。 | 三政策互相獨立；加入界線適用 A19／W14／W16／附件授權及 C14 未讀。 | [三項政策](contracts/interface-contract.md#group-revocation-policy) |
| <a id="decision-attachment-policy"></a>附件限制與支援類型 | 需修改後採用：JPEG／PNG／PDF，≤10 MiB，檔名 1–255 Unicode 字元，伺服器產生物件鍵；上傳授權 10 分鐘、下載 5 分鐘；PDF 下載、不內嵌預覽。 | 不做影片、音訊、執行檔、SVG／HTML、分塊續傳；過期上傳重新 A20，不做 A25；保留內容核驗及 C9／C10 版本保護。 | [A20–A25](contracts/interface-contract.md#api-a20) |
| <a id="decision-historical-slos"></a>歷史效能與重連目標 | 需修改後採用：課程基線為 50 使用者／WSS、25 一對一聊天室、每人平均每 5 秒一則 ≤1 KiB 訊息、10 分鐘；另做 50 人群組功能驗收。 | 目標送出至收件端呈現 p95≤2 秒；待補≤100 時重連同步≤5 秒。已有本機一對一 protocol run 50／50 WSS、25 rooms、600 秒，6,000／6,000 成功，W07 p95 78.974 ms；獨立 50 人群組 run 50 WSS、6,000 intents、294,000／294,000 fanout、50 人 A19 history 全驗，group W07 p95 73.387 ms。皆非 browser 呈現 p95 或正式 VM 容量；1k／5k／10k 僅未來壓測。 | [REQ-18](testing/acceptance-matrix.md#req-18) |
| <a id="decision-runtime-platform"></a>GCP 執行環境與託管服務 | 需修改後採用：單台 GCP Compute Engine VM＋Docker Compose，含 Web 入口、api、realtime、PostgreSQL、單一 Redis；api／realtime 各一實例，附件用 GCS 私有桶。 | 不採 Cloud Run、Cloud SQL、Memorystore、外部 LB、執行個體群組、Kubernetes、自動擴縮；資料庫／Redis／內部 API 不公開。持久磁碟、備份還原與回滾；不承諾高可用，尚未建立資源。 | [DO-01](prd/devops.md#do-01)、[部署拓樸](architecture/README.md#arch-deployment) |
| <a id="decision-tech-stack"></a>前後端框架與程式語言 | 需修改後採用：不指定全端 TypeScript或限制語言；各模組負責人自選熟悉語言／框架，跨語言依 HTTP／JSON、WebSocket 格式及介面文件／Schema／樣例整合。 | PostgreSQL 為主資料庫；Redis 僅既有通知用途；不要求共用 backend/common 原始碼／ORM或微前端平台，Web 交付單一體驗。 | [README 技術方向](../README.md#core-technology-direction)、[架構程式碼對應](architecture/README.md#arch-code-map) |
| <a id="decision-service-topology"></a>`api`／`realtime` 部署單元與內部呼叫方式 | 需修改後採用：同一儲存庫／主機兩個獨立程序或容器，各一實例；可用不同語言，以 Compose 私有網路內 HTTP＋JSON 對接並驗證服務身分。 | 不依功能拆微服務；內部路由不得公開；本版不建立推播工作程序。 | [內部交接](contracts/interface-contract.md#internal-handoffs)、[架構元件](architecture/README.md#arch-components) |
| <a id="decision-realtime-notify"></a>REST 寫入後的即時通知與授權失效 | 已批准：BB 交易提交後以內部 HTTP／JSON `publishCommitted` 通知單一 realtime，透過單一 Redis Pub/Sub；PostgreSQL 持久資料為準。 | 不用 Kafka／RabbitMQ／多節點廣播；W15／W16 與失效紀錄輪詢補漏；通知只加速、不可提交前發事件。程式與本機 API／BA 整合已交付；正式 VM／雲端部署及公有容量另行驗收。 | [失效通知](contracts/interface-contract.md#internal-notify-invalidation)、[架構 6.6](architecture/README.md#flow-invalidation) |
| <a id="decision-load-tool"></a>負載測試工具 | 需修改後採用：QA 選用一套 Python／aiohttp HTTP＋WebSocket 工具並保留可重跑腳本與結果。 | 一對一 baseline 與獨立 50 人群組協定 run 均已執行（[一對一](testing/evidence/product-direct-load.json)、[群組](testing/evidence/product-group-load.json)）；實際結果與 W07 協定／fanout p95 見本表課程基線列。browser 呈現 p95 及正式 VM 容量另行驗收。 | [QA-05](prd/qa.md#qa-05)、[REQ-18](testing/acceptance-matrix.md#req-18)、[負載規劃](../tests/load/README.md) |

<a id="架構決策候選方案"></a>
<a id="architecture-proposals"></a>
## 架構決議

以下架構方向均已由 PM 於 2026-10-01 決定；不代表已實作、部署或量測。本節保留歷史 proposal 錨點供其他文件連結，已取代方案僅以一行標明。

<a id="pm-行為批准表全部待批准"></a>
<a id="behavior-approval"></a>
### PM 行為決議表（2026-10-01）

下表記錄 PM 決定的現行行為；「決議」欄不代表實作或測試完成。

<a id="review-resolution-status"></a>
**R1～R6 回應狀態（均已由 PM 決定；非實作狀態）：**
- **已批准／需修改後採用：** R1～R6 的文件修正、C8 公開 user_id、C9／C10 附件版本保護及 C11／C12 排序與分頁依本表所列決議；未宣稱已實作或量測。
- 所有決議依 2026-10-01 PM 原文；規格值尚未量測。

| 使用者情境 | 決議狀態與現行行為 | 受影響角色與功能 | 決議 | 原文／驗收案例連結 |
|---|---|---|---|---|
| <a id="group-device-content"></a>G1 裝置已取得歷史後被移除 | 已批准 | FA-05 本機投影；FB-05 路由；QA-03 | 得知被移除／退出後離開群組頁並停止顯示不可存取內容；不提供退出後唯讀頁，不承諾遠端抹除本機副本。離線且尚未得知撤權時可能仍顯示舊內容；截圖／下載檔無法追回。重新登入不同帳號不得讀取前帳號本機投影。 | [三項政策](contracts/interface-contract.md#group-revocation-policy)、[FB-05](prd/frontend-b.md#fb-05)、[N25](testing/acceptance-matrix.md#ac-n25) |
| <a id="group-pending-content"></a>G2 撤權前已授權、尚未開始交付的服務端內容 | 已批准（E1） | BB-03／06；BA-05／06；QA-03／04 | 採 E1，`INVALIDATION_STALE_SECONDS=15`。套用撤權即停止舊內容開始交付，最遲提交後 15 秒不得再開始；這不是網路抵達期限，不能追回已送資料。60 秒移除紀錄保留窗不是交付上限；整合所需持久化紀錄與同步中繼資料，只驗收單一 realtime 實例。 | [E1](contracts/interface-contract.md#group-revocation-e1)、[N18](testing/acceptance-matrix.md#ac-n18)、[N26](testing/acceptance-matrix.md#ac-n26) |
| <a id="group-new-queries"></a>G3 撤權後才開始歷史／同步查詢 | 已批准 | BB-03／05／06／07；FA-05；QA-03 | 撤權後新發起的歷史、同步與附件讀取不得重新取得群組內容；每頁授權。沿用 A19／A22 拒絕、W14 排除、W16 過濾正文但保留最小自身 W12；不新增離群後讀取舊歷史 API。 | [操作 5／6](contracts/interface-contract.md#internal-read-bootstrap)、[N02](testing/acceptance-matrix.md#ac-n02) |
| <a id="session-old-delivery"></a>S1 登出／刷新後舊連線仍收到舊授權資料 | 已批准 | BA-01／05／06；BB-01；FA-02；QA-02 | 採 D2／C1–C4，失效上限 15 秒；套用撤銷即停止舊內容交付，最遲提交後 15 秒不再開始交付；權杖先到期則更早停止。新授權仍直接拒絕。此為需求，尚未量測達標。 | [D1–D4](contracts/interface-contract.md#authorization-boundary)、[N13–N17](testing/acceptance-matrix.md#ac-n13) |
| <a id="stale-service-behavior"></a>S2 BB 暫時不可連線／補齊逾時 | 已批准 | BA-01／05／06；FA-01／05；BB；QA-02／04 | BB 不可用時不得無限使用舊授權；最近完整補齊開始後 15 秒暫停資料交付，可保留連線與 W04／W17，最遲權杖到期關閉。恢復先補權威狀態；失效紀錄輪詢 5 秒、單事件補齊等待 1000 毫秒，逾時交既有同步補回。UI 顯示服務異常；不做多實例容錯。數值未量測。 | [狀態表](contracts/interface-contract.md#delivery-state-table)、[N04](testing/acceptance-matrix.md#ac-n04) |
| <a id="multi-tab-session-policy"></a>M1 多分頁刷新、重登或登出 | 需修改後採用 | FB-01／02；FA-02；BB-01；QA-02 | 同一瀏覽器設定檔只允許一個可操作聊天分頁；其餘顯示「聊天已在另一個分頁開啟」，不登入、刷新或建立 WSS。認證操作前取得並持有同來源獨占 Web Lock，無搶鎖或無鎖退路；釋放後另一分頁重新驗證。不同瀏覽器／裝置登入與伺服器撤銷照常。 | [FB 交接](prd/frontend-b.md#fb-multi-tab)、[C5](contracts/interface-contract.md#internal-change-requests)、[N19–N24](testing/acceptance-matrix.md#ac-n19) |
| <a id="multi-tab-activity"></a>M2 前景／背景分頁同時在線 | 已否決；本版範圍外（2026-10-01 PM 決議） | FA-07；BA-07；BB-08；QA-02 | 不做伺服器端活動租約與合併，不採 60 秒租期；W21／W22 活動上報與 unknown 推播判斷範圍外。不保留無消費者租約子系統。WSS 心跳、斷線重連及前端 Page Visibility 已讀判斷仍保留，互不混用。 | [C7](contracts/interface-contract.md#activity-merge)、[N27](testing/acceptance-matrix.md#ac-n27) |
| <a id="refresh-uncertain-policy"></a>M3 A03 結果不明／協調分頁消失 | 需修改後採用 | FB-02；BB-01；FA-02；QA-02 | 正常 A03 可自動刷新一次；等待 10 秒仍不明、401 或刷新失敗即停止 WSS／自動刷新、清除本機可用認證並提示重登。舊 Cookie 寬限 0 秒，不重播舊請求或跨分頁接班。有效 `retry_after_ms` 依既有規則最多再試一次；網路／伺服器錯誤不顯示為密碼錯誤。 | [C6](contracts/interface-contract.md#refresh-recovery-policy)、[錯誤分流](contracts/interface-contract.md#error-recovery)、[N23](testing/acceptance-matrix.md#ac-n23) |
| <a id="browser-support-policy"></a>B1 瀏覽器支援 | 需修改後採用 | FB-02／07；FA-01／07；QA-02／06 | 驗收 Chrome／Edge 桌面及 Android Chrome，QA 記錄版本；未測瀏覽器不保證。必要能力含 HTTPS、同來源、Cookie／本機儲存、WebSocket、Page Visibility、Web Locks；缺少即不支援、不啟用聊天，無無鎖退路。無舊瀏覽器相容層、原生 App 或 PWA。 | [支援前提](prd/frontend-b.md#fb-browser-support)、[N28](testing/acceptance-matrix.md#ac-n28) |
| <a id="review-identity"></a>R3 登入後 W02 公開身分 | 已批准 | BB-01；BA-01；FA-01；QA-01 | 採 C8：BB `validateAccess` 同次回覆可信公開 `user_id`，BA 直接用於 W02；不推測、不假設 JWT 未定義宣告，不更名 W02／新增 API。 | [C8](contracts/interface-contract.md#public-identity-handoff)、[AC-R03](testing/acceptance-matrix.md#ac-r03) |
| <a id="review-attachments"></a>R4 收件者看附件／擁有者上傳 | 已批准 | FA-06；FB-03；BB-07；DO-02；QA-04 | 採 C9 與補足後 C10、沿用 GCS 私有附件流程：每次嘗試獨立物件鍵與僅建立條件；A21 綁定核驗版本，A22 僅簽該版本，失效不得取最新版本；收件者須通過對話授權。無分塊／續傳，A25 範圍外，過期由 A20 新建嘗試。 | [C9](contracts/interface-contract.md#attachment-handoff)、[C10](contracts/interface-contract.md#signed-upload-contract)、[AC-R04](testing/acceptance-matrix.md#ac-r04) |
| <a id="review-order-pagination"></a>R5 各端排序與 REST 首頁 | 已批准 | BB-05／06；FA-05；FB-04；QA-01／03 | 採 C11／C12：`order_key` 固定 20 位 ASCII 數字字串並以 UUID 次排序；REST 預設 20、最大 50；首頁省略 cursor／before，後續採服務端游標。非法值一致拒絕，不轉浮點數。效能未量測。 | [排序／分頁](contracts/interface-contract.md#ordering-pagination)、[AC-R05](testing/acceptance-matrix.md#ac-r05) |
| <a id="review-auth-layer"></a>V1 內部服務身分驗證失敗 | 已批准 | BA-08；BB-01；FA-01／FB-02；QA-02 | 採 C13：可信 `details.auth_layer` 區分 `service_identity`／`user_session`；只有明確 `user_session` 失效才關閉使用者連線並要求登入。其餘服務憑證失敗／缺分層／非 HINE 回覆視為 `DEPENDENCY_UNAVAILABLE`，顯示服務暫時不可用，不登出／刷新；不新增公開錯誤碼或完整告警平台。 | [C13](contracts/interface-contract.md#internal-auth-layer)、[AC-R09](testing/acceptance-matrix.md#ac-r09) |
| <a id="decision-unread-count"></a>V2 聊天清單未讀數 | 已批准（C14-S） | BB-05；FB-05；FA-04；QA-06 | 只顯示伺服器最近查詢值；不維護前端加減集合。以使用者計算他人所發、目前可讀且尚未 read 的訊息，保留逐訊息已讀；A11／A12／W14 查詢收斂，短暫舊值可接受。不新增跨裝置未讀事件或群組 W10；本機新訊息提示不得當權威 `unread_count`。 | [C14](contracts/interface-contract.md#unread-count)、[C14-S](contracts/interface-contract.md#unread-merge) |
| <a id="review-read-visibility"></a>V3 已讀可見判定 | 已批准 | FA-08；QA-06；BA-04／BB-05 | 採 50% 連續 500 毫秒；分母為訊息泡泡與有效可視區的最大可能交集。僅他人訊息；頁面隱藏、模態覆蓋或條件中斷即歸零。符合可見條件不代表讀完全文；保留逐訊息 W09。規格尚未瀏覽器驗證。 | [已讀判定](ui/web-rwd.md#rwd-read-rule)、[REQ-20](testing/acceptance-matrix.md#req-20-detail) |
| <a id="review-web-input-routing"></a>V4 鍵盤判別、根路徑與清單搜尋 | 已批准 | FA-08；FB-04／05／07；DO-06；QA-06 | 無法判斷鍵盤能力時 Enter 換行、送出按鈕送出，支援 Ctrl／⌘+Enter；`/` 先顯示初始化，完成後 replace 導向 `/login` 或 `/chats`；清單搜尋只篩選本機已載入項目，不擴張 A07 或新增全文搜尋。 | [鍵盤](ui/web-rwd.md#rwd-keyboard)、[根路徑](ui/web-rwd.md#rwd-root-route)、[本機篩選](ui/web-rwd.md#rwd-local-filter) |

<a id="規格目標候選配置實際量測結果"></a>
<a id="spec-config-measure"></a>
### 規格目標、決議配置、實際量測結果

下表保留政策／目標值與各項實測狀態；本機協定基線另於「負載測試工具」列明，不據此外推瀏覽器呈現、雲端、設備或公有容量達標。決議本身不代表所有實作、部署或驗收完成。

| 規格目標（2026-10-01 PM 決議） | 本版設定／政策 | 實際量測結果 |
|---|---|---|
| S1：撤銷後停止開始舊授權資料交付 | `INVALIDATION_STALE_SECONDS=15`；套用撤銷即停止，最遲提交後 15 秒 | 本機真 PG/API/BA：PF05 lost A04 notice 後 4.657 秒內關閉被撤銷連線並保留其他裝置；PF03 PG outage 過新鮮度窗口僅 control frames 並在 JWT 到期關閉。不是 VM／跨主機 SLO（[證據](testing/evidence/product-native-faults.json)） |
| G2：E1 舊授權內容交付界線 | 採 E1，與 S1 同為 15 秒；單一 realtime 驗收 | 未完成真 A18 群組撤權／舊內容開始 write 競態驗收 |
| S2：BB 中斷與補齊 | 輪詢 5 秒；單事件補齊等待 1000 毫秒；失效超過 15 秒暫停交付 | 本機真 PG outage PF03：ready 503、資料操作 fail closed、現有有效 socket 僅 control，PG 恢復後原 session/cursor 恢復；未證正式 VM／錯誤網路上的完整部署 SLO（[證據](testing/evidence/product-native-faults.json)） |
| G2 的 60 秒移除紀錄保留窗 | 不是交付上限，不作交付保證 | 未量測 |
| M2 活動租期 | 本版範圍外；`ACTIVITY_LEASE_SECONDS` 不使用 | 不適用 |
| M3 A03 結果不明 | A03 等待 10 秒、舊 Cookie 寬限 0 秒；不明／401／失敗停止刷新並提示重登 | 未量測 |
| 前景同步核對 | 每 10 秒；返回前景立即核對，背景不保證排程 | 未量測 |
| B1 瀏覽器支援 | Chrome／Edge 桌面、Android Chrome；QA 記錄實際版本 | 已有本機 Chrome product proof；Edge／Android 實機與完整版本相容性矩陣未驗，不能據單一 Chrome 場景宣稱全面支援 |
| V3 已讀 | 最大可能交集為分母，50% 連續 500 毫秒，中斷歸零 | 未量測 |
| 本版營運設定 | REST 20／50；W14 100；W16 每批 100、掃描 1000；心跳 30／90 秒；訊息每秒 5、突發 10；登入每帳號每分鐘 10、每 IP 每分鐘 60；群組 50 人；附件 JPEG／PNG／PDF ≤10 MiB；授權 10 分鐘、下載 5 分鐘 | 各項尚未量測 |

**技術方案現行定義：**
- 單一 VM＋Compose，`api`／`realtime` 各一實例；提交後通知採內部 HTTP／JSON 與單一 Redis Pub/Sub。
- G2 採 E1，現行 BA 實作失效紀錄／同步中繼資料交接；真實 PostgreSQL 提交序、撤權競態與 15 秒開始交付界線仍需正式產品 gate 驗證。
- 技術棧由模組自行選定並見目前源碼；QA 已提供一套 Python／aiohttp HTTP＋WebSocket 工具。協定基線結果與瀏覽器／VM／正式容量 gate 分開記錄。

<a id="通知路徑與-apirealtime-部署單元合併提案"></a>
<a id="proposal-notify-topology"></a>
### 通知路徑與 `api`／`realtime` 部署單元（已決議）

- **採用：** 同一主機、Compose 內 `api` 與 `realtime` 各一實例，內部 HTTP／JSON 並驗證服務身分；BB 提交後呼叫 `publishCommitted`，由單一 Redis Pub/Sub 加速通知。
- **正確性：** PostgreSQL 持久資料為準；提交前不發事件，Pub/Sub 遺失由同步與失效紀錄輪詢補齊。BA／BB 對應程式已交付，本機 API／PG／BA 測試與協定負載另有證據；真實 VM／雲端、瀏覽器呈現與公有容量未由此核准／證明。
- **已取代替代方案：** 同程序部署、任意多實例拓樸及後端 B 直接發布 Redis 均不採用。

<a id="runtime-conditions"></a>
Cloud Run 條件分析屬已取代方案，保留此錨點供舊連結使用；本版採單一 Compute Engine VM＋Docker Compose，不採 Cloud Run。

<a id="proposal-runtime-platform"></a>
### GCP 執行環境與託管服務

- **採用（2026-10-01 PM 決議）：** 單台 GCP Compute Engine VM＋Docker Compose，含 Web HTTPS／WSS 入口、`api`、`realtime`、PostgreSQL 與單一 Redis；兩服務各一實例，附件使用 GCS 私有儲存桶。
- **部署界線：** 僅 Web 入口公開；資料庫、Redis、內部 API 私有。保留持久磁碟、備份／還原演練、回滾；祕密不得提交 Git。不承諾高可用，決議不表示雲端資源已建立。
- **已取代方案：** Cloud Run、Cloud SQL、Memorystore、外部 Load Balancer、執行個體群組、Kubernetes、自動擴縮均不採用。

<a id="proposal-tech-stack"></a>
### 前後端框架與程式語言

- **現行決議（2026-10-01 PM 決議）：** 不指定全端 TypeScript或任何特定語言；各模組負責人自選熟悉的語言／框架。
- 共用介面文件／Schema／測試樣例，不要求共用原始碼型別或 ORM；共同約束為既定 HTTP／JSON、WebSocket 格式、資料格式及可重現啟動／測試方式。PostgreSQL 為主資料庫，Redis 沿用既有用途；Web 整合為單一體驗，不建微前端平台。
- **已取代候選：** 全端 TypeScript（React＋Vite／Node.js）及前端 TypeScript、後端 Python 等固定組合均不再是專案要求。

<a id="proposal-load-tool"></a>
### 負載測試工具

- **現行決議（2026-10-01 PM 決議）：** QA 自選熟悉的一套 HTTP＋WebSocket 工具或語言，第一週記錄於 `tests/load/README.md`，交付一套可重跑腳本與結果報告。
- 必測 W01 登入、W05 傳送、斷線後 W15／W16 同步與去重；負載依 50 條 WSS 課程基線。協定負載報告與真實瀏覽器端到端驗收分開標示；尚未執行壓測。
- **已取代候選：** Artillery／JavaScript 與 JMeter 外掛不再是指定工具；1,000／5,000／10,000 連線只作未來壓測，不是本版容量目標。

## 決策治理

原有 32 項 PM 決議均於 2026-10-01 作成；同日新增下方分輪共同介面政策，不冒稱原有 32 項包含本輪限制確認。本登錄記錄決策，不代表產品已實作、部署、測試或量測；契約與角色文件應以所列現行規格為準。未列入本輪工作的候選值維持原狀態，不阻擋無依賴的開發。

FB-04 僅使用[公開 ID 查詢](contracts/interface-contract.md#contact-id-lookup)，關鍵字搜尋不納入；[本地持久保存](contracts/interface-contract.md#local-persistence-boundary)仍是既有重試／回條／同步義務，不是完整離線應用程式或 PWA。

<a id="incremental-interface-governance"></a>
### 分輪共同介面政策（2026-10-01）

**使用者決議：** 有共同介面，但不一次鎖死整份規格；組員自由決定模組內「怎麼寫」，不得各自決定「怎麼跟別人溝通」。先對齊近期要串接的介面；介面可修改，但提供方與受影響的消費方須一起改。

**近期路徑：** 依 Notion 首次端到端任務，先做兩個帳號登入、一對一建立、文字送出、持久化 ACK 與另一端顯示，另以 A19 核對保存。對接清單與唯一欄位定義見[共同契約近期基線](contracts/interface-contract.md#integration-baseline)，具體修改流程見[協作指南](../CONTRIBUTING.md#interface-changes)。

**本次 PM 正式確認：** EntityID ≤128、text 非空／1～4096、BB JSON 解碼後 Unicode code points 單位不變；消費端不重現、不 trim／normalization。publishCommitted 由 BB 生成／發送前驗 IDs，BA 對 authenticated BB notice 僅結構檢查。W05 每使用者 5/s、burst 10 產品 quota 改由 BB 的 persistIfAbsent 唯一執行，順序為結構 → canonical → 認證／授權 → C1 → 僅新合法 intent 的 quota → 持久化；BA 保留 transport/frame defense，不雙重判產品 quota。不新增 API／架構，也不是組員確認或產品測試結果。


| 事項 | 本輪安排 | 已取得證據／尚缺 |
|---|---|---|
| 分輪政策與模組內自由 | 採用；不要求全文件先凍結才開始開發，不指定所有模組同一語言／框架 | 使用者本次指示；政策與對接清單已書面列明 |
| EntityID | PM 已確認上限 128；BB 以 JSON 解碼後 Unicode code points 計算。所有外部 EntityID 輸入先驗證，超長 INVALID_ARGUMENT 先於資源查詢／授權；消費端不解析格式 | 本次 PM 正式指示；實際接收 EntityID 的 REST／internal error list 同步，UUID／OpaqueCursor 不套此上限 |
| text | PM 已確認非空、有效範圍固定為 1～4096；空或超長不持久化、不回成功 W06 | 本次 PM 正式指示；由 BB 在持久化前權威判定，BA 映射既有 W17 INVALID_ARGUMENT |
| 驗證責任與模型 | BB canonical 計數單位已定；ASCII 邊界外僅以 😀＝1、e 加組合重音＝2 驗 BB，不要求消費端算法一致。BA 可做結構檢查及錯誤映射，前端提示只是 UX，不轉換原內容 | 本次 PM 正式指示；不是消費端共同計數義務，尚未產品驗證 |
| Validation／C1／產品 quota | W05 六階段；非法（含同 C1）先 INVALID_ARGUMENT；不同合法 C1 payload 先 IDEMPOTENCY_CONFLICT；相同合法 C1 即使 quota exhausted 仍 existing_same／原 M1；只有新合法 intent 超額 RATE_LIMITED | 唯一產品 quota owner 是 BB，不改 5/s burst10 或指定實作；拒絕不持久化／C1→M1／成功 W06 |
| publishCommitted 交接 | BB 發送前驗所有 canonical EntityID；BA 先驗 caller 為 authenticated BB，再驗 notice 結構，不重算 Unicode 長度 | 結構錯誤仍 INVALID_ARGUMENT；非允許 caller 依原 UNAUTHENTICATED／C13；不取消 REST／W05 外部驗證 |
| Title | 1–80 限制保留候選，群組 A14／A15 串接前共同確認 | 本輪一對一 title:null 不受影響；不作首輪阻塞 |
| 來源與修訂 | 來源提交 `17c25ec`；本次修訂透過 `docs/incremental-interface-baseline` 分支交付，以該分支提交紀錄追溯 | 來源不是已批准凍結提交；分支交付不代表已 Review／合併，不宣稱 GitHub main 已更新 |
| 首輪產品驗收 | 首輪矩陣核對全部 EntityID 接收 REST（含 A06 非 null、A10），A06 null 原義；BB／BA 通知分工、Unicode／ASCII 邊界、quota exhausted 下五個結果 | 尚未產品驗證；文件／資料檢查不是後端或瀏覽器通過 |
| 後續輪與內部部署 | 群組、附件、回條、完整同步等各輪串接前確認；`INVALIDATION_RETENTION_SECONDS` 另行協調 | 不要求一起完成，不取消現行授權／ACK／保存語意及範圍外決議 |

**任務交付狀態：** 首輪限制與後端權威驗證責任已取得 PM 正式確認；近期共同介面與共同變更流程的書面交付仍須受影響成員 Review。尚未取得 FA／FB／BA／BB 對接確認，不標示「全介面凍結完成」。PM 在原任務／PR 記錄確認者、適用介面 ID、例子／驗收結果與合併提交；每輪完成只更新該輪，不替尚未驗證的功能勾選完成。
