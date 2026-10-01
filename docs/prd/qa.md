<a id="hine-ic-04--qa-角色-prd"></a>
# HINE-IC-0.4 — 品質驗證（QA）角色 PRD

**版本：** HINE-IC-0.4  
**狀態：** 現行規格（2026-10-01 PM 決議）
**來源：** [歷史來源：HINE-IC-0.4 角色 PRD](../HINE-IC-0.4-role-prds.md); 唯一現行介面規格依據為 [共同介面契約](../contracts/interface-contract.md).  
**角色目的：** 負責行為、結構描述、隱私、復原與效能驗收。本 PRD 規定未來行為與驗收要求，不代表已實作或已完成測試。
**必讀／串接時查閱：** [系統架構](../architecture/README.md)、[共同介面契約](../contracts/interface-contract.md)、[驗收矩陣](../testing/acceptance-matrix.md)；各功能串接見下方追溯／交接。 [返回文件導覽](../README.md)。

## 範圍

- **範圍內：** 行為、結構描述、隱私、復原與效能驗收；以及下方角色專屬功能卡。
- **範圍外：** 其他角色所負責的範圍；不得單方變更共用 API／事件 ID、正式資料、ACK、游標或同步語意。介面可以依[共同變更流程](../../CONTRIBUTING.md#interface-changes)與受影響成員一起修改；測試工具與內部實作由負責人決定。先對齊[近期串接基線](../contracts/interface-contract.md#integration-baseline)及其驗收，不要求一次鎖死整份規格。
- **共用 Web 行為：** 遵循 [Web／RWD 規格](../ui/web-rwd.md#web-rwd)；不得另訂斷點或重複定義版面規則。

## 功能索引

- [QA-01 — 介面契約與結構描述符合性](#qa-01)
- [QA-02 — 工作階段、刷新與單操作分頁行為](#qa-02)
- [QA-03 — 快照／事件流復原與游標隔離](#qa-03)
- [QA-04 — 跨模組行為與故障注入](#qa-04)
- [QA-05 — 隱私、設定與課程效能驗收](#qa-05)
- [QA-06 — Web 響應式、輸入、路由與瀏覽器支援驗收](#qa-06)

## 角色目的與責任界線

定義行為、結構描述、隱私、復原與效能驗收。僅於已有實作與核准測試環境後執行產品測試；本 PRD 未記錄任何測試執行結果。跨語言以介面文件／Schema／測試樣例驗證契約，不要求共用程式碼型別。

<a id="qa-01"></a>
<a id="qa-01--interface-contract-and-schema-compliance"></a>
### QA-01 — 介面契約與結構描述符合性
**追溯：** [REQ-01 帳戶驗證與登入識別](../testing/acceptance-matrix.md#req-01), [REQ-02 憑證更新與登出轉換](../testing/acceptance-matrix.md#req-02), [REQ-03 個人檔案、頭像與聯絡人](../testing/acceptance-matrix.md#req-03), [REQ-04 一對一聊天導覽與建立](../testing/acceptance-matrix.md#req-04), [REQ-05 群組管理、權限與成員變更](../testing/acceptance-matrix.md#req-05), [REQ-06 文字訊息與持久 ACK](../testing/acceptance-matrix.md#req-06); [介面定位](../contracts/interface-contract.md#rest-api), [REST API A01–A25](../contracts/interface-contract.md#rest-api), [WebSocket W01–W22](../contracts/interface-contract.md#websocket-events)。
**REST 條目：** [A01](../contracts/interface-contract.md#api-a01), [A02](../contracts/interface-contract.md#api-a02), [A03](../contracts/interface-contract.md#api-a03), [A04](../contracts/interface-contract.md#api-a04), [A05](../contracts/interface-contract.md#api-a05), [A06](../contracts/interface-contract.md#api-a06), [A07](../contracts/interface-contract.md#api-a07), [A08](../contracts/interface-contract.md#api-a08), [A09](../contracts/interface-contract.md#api-a09), [A10](../contracts/interface-contract.md#api-a10), [A11](../contracts/interface-contract.md#api-a11), [A12](../contracts/interface-contract.md#api-a12), [A13](../contracts/interface-contract.md#api-a13).
**REST 條目（續）：** [A14](../contracts/interface-contract.md#api-a14), [A15](../contracts/interface-contract.md#api-a15), [A16](../contracts/interface-contract.md#api-a16), [A17](../contracts/interface-contract.md#api-a17), [A18](../contracts/interface-contract.md#api-a18), [A19](../contracts/interface-contract.md#api-a19), [A20](../contracts/interface-contract.md#api-a20), [A21](../contracts/interface-contract.md#api-a21), [A22](../contracts/interface-contract.md#api-a22), [A23](../contracts/interface-contract.md#api-a23)（本版範圍外）, [A24](../contracts/interface-contract.md#api-a24)（本版範圍外）, [A25](../contracts/interface-contract.md#api-a25)（本版範圍外）。
**WebSocket 條目：** [W01](../contracts/interface-contract.md#event-w01), [W02](../contracts/interface-contract.md#event-w02), [W03](../contracts/interface-contract.md#event-w03), [W04](../contracts/interface-contract.md#event-w04), [W05](../contracts/interface-contract.md#event-w05), [W06](../contracts/interface-contract.md#event-w06), [W07](../contracts/interface-contract.md#event-w07), [W08](../contracts/interface-contract.md#event-w08), [W09](../contracts/interface-contract.md#event-w09), [W10](../contracts/interface-contract.md#event-w10), [W11](../contracts/interface-contract.md#event-w11)。
**WebSocket 條目（續）：** [W12](../contracts/interface-contract.md#event-w12), [W13](../contracts/interface-contract.md#event-w13), [W14](../contracts/interface-contract.md#event-w14), [W15](../contracts/interface-contract.md#event-w15), [W16](../contracts/interface-contract.md#event-w16), [W17](../contracts/interface-contract.md#event-w17), [W18](../contracts/interface-contract.md#event-w18), [W19](../contracts/interface-contract.md#event-w19), [W20](../contracts/interface-contract.md#event-w20), [W21](../contracts/interface-contract.md#event-w21)（本版範圍外）, [W22](../contracts/interface-contract.md#event-w22)（本版範圍外）。
- **前置條件：** 各語言的契約 Schema／測試樣例及共用字典。
- **正常流程：** 驗證欄位存在性、null／省略、方法／路徑、status、關聯、授權、排序分頁及事件對應。C8–C14 使用跨語言 Schema／測試樣例驗收：C8 `validateAccess` 可信 `user_id` 用於 W02；C9/C10 已核驗附件版本及對話授權；C11/C12 排序與 REST 分頁；C13 內部身分錯誤分層；C14-S 伺服器權威未讀查詢。A23–A25、W21／W22 本版範圍外，僅保留 ID，不做 Schema／樣例驗收。
- **失敗流程：** 欄位不符、事件錯配、以摘要代詳細資料或洩漏 subject_id 均為契約失敗。
- **驗收條件：** 每個消費端參照同一契約並通過對應 Schema／測試樣例；不要求跨語言共用程式碼型別。
- **首輪長度驗收：** PM 已確認 EntityID 上限 128、text 非空且有效範圍 1～4096；用 ASCII 資料驗收 text 空、1、4096／4097 與 EntityID 128／129。核對 BB 持久化前的最終判定、拒絕時不寫訊息／C1 對應／事件流，以及 BA 映射既有 W17 INVALID_ARGUMENT、不回成功 W06；前端提示僅屬 UX，不驗收跨語言一致計數算法。原訊息不自動 trim／normalization 或轉換。依[首輪條件](../testing/acceptance-matrix.md#first-integration-cases)記錄實際證據；只有文件檢查時明列「尚未產品驗證」。
- **交接：** 結構描述／報告發現交給 [FA-01](frontend-a.md#fa-01)、[FB-01](frontend-b.md#fb-01)、[BA-01](backend-a.md#ba-01)、[BB-01](backend-b.md#bb-01)。

<a id="qa-02--工作階段更新活動與多裝置行為"></a>
<a id="qa-02"></a>
<a id="qa-02--session-refresh-activity-and-multi-device-behavior"></a>
### QA-02 — 工作階段、刷新與單操作分頁行為
**追溯：** A02／A03／A04 與 W01–W04、W18；REQ-01／REQ-02／REQ-14／REQ-15。
- **前置條件：** 有效帳戶及可控制連線生命週期的瀏覽器。
- **正常流程：** 驗證工作階段綁定、刷新／登出撤銷與恢復游標。同一瀏覽器設定檔僅一個可操作聊天分頁；同來源獨占 Web Lock `hine-session` 必須在任何認證操作前取得並持有至分頁結束。未取得鎖的分頁顯示「聊天已在另一個分頁開啟」，不得登入、刷新或建立 WSS；持有分頁結束後，另一分頁取得鎖並重新取得／驗證工作階段。不同瀏覽器／裝置仍可登入。
- **失敗流程：** 正常 A03 最多自動刷新一次；結果 10 秒仍不明、401 或刷新失敗時，停止 WSS／自動刷新、清除本機可用認證狀態並提示重新登入。舊 Cookie 寬限 0 秒、不重播舊刷新請求、不做跨分頁接班；RATE_LIMITED 僅依有效 `retry_after_ms` 等待後最多再試一次，否則停止自動刷新。服務錯誤不得誤報帳密錯誤。M2 活動租約、W21／W22 本版範圍外；保留 WSS 心跳、斷線重連及 Page Visibility 已讀判斷。
- **驗收條件：** 驗收單操作分頁限制、刷新／登出撤銷及錯誤分流；不測活動租約或多分頁同步刷新。
- **補充案例：** AC-N19–N24 改驗單操作分頁限制；AC-N23 依簡化 C6 流程；AC-N28 驗必要瀏覽器能力不足時拒絕啟用聊天。
- **交接：** 狀態轉換案例交給 FB-02、FA-01／FA-02、BA-01／BA-02、BB-01；FA-07、BB-08 本版範圍外，不交接。

<a id="qa-03"></a>
<a id="qa-03--snapshotfeed-recovery-and-cursor-isolation"></a>
### QA-03 — 快照／事件流復原與游標隔離
**追溯：** REQ-09–REQ-11；A08／A11／A19、W13–W17；readBootstrap／readFeed。
- **前置條件：** 獨立 REST 游標與使用者事件流游標，以及可驗證加入界線的群組資料。
- **正常流程：** 快照多頁完成並原子切換後安裝 H、續讀事件流；保存義務依本機持久化界線。新成員只讀加入界線後的群組內容；退出重加以新界線起算。撤權後新發起的歷史／同步／附件查詢逐頁授權，依 G3 拒絕。
- **失敗流程：** 分別使 REST 游標與事件流游標過期；確認未授權內容不傳送。
- **驗收條件：** 各查詢失敗只重取自身查詢；WSS 重設才觸發 W13；同步每頁最多 100 個事件、每請求最多掃描 1000 個紀錄，未掃完須依游標續傳。A19／W14／W16／附件及 C14-S 未讀使用同一可讀範圍。
- **補充案例：** AC-R03 驗 C8 公開 user_id 映射；AC-N25／N26 分驗本機既有副本及 E1 待送／同步；AC-R06 驗持久化界線。
- **交接：** 游標邊界交給 FA-05、FB-04、BA-06、BB-06。

<a id="qa-04"></a>
<a id="qa-04--cross-module-behavior-and-failure-injection"></a>
### QA-04 — 跨模組行為與故障注入
**追溯：** REQ-03–REQ-08、REQ-12、REQ-13；A05/A06/A14–A18/A20–A22；A25 本版範圍外；C1–C14（C8–C14 見 QA-01）；附件與群組政策。
- **內部操作：** authorize、persistIfAbsent、persistReceipt、readBootstrap、readFeed；dispatchPushIntent 本版範圍外。
- **前置條件：** 隔離使用者、對話、附件儲存測試設定；不需推播供應商。
- **正常流程：** 驗證 ACK 復原、回條復原、附件上傳／下載與群組操作；附件限 JPEG／PNG／PDF、每檔最多 10 MiB，群組最多 50 人。附件授權逾期以新 A20 嘗試；不做 A25、分塊續傳或群組已讀彙總。
- **失敗流程：** 注入提交／ACK／發布中斷、過期上傳、錯誤 MIME、撤權；推播供應商故障不屬本版驗收。
- **補充案例：** AC-R02 驗 W17 復原路由；AC-R04 驗 C9/C10 版本一致性；AC-R08 驗一對一回條及群組個別狀態；AC-N01/N02/N09/N12/N18/N26 驗核准後的 E1 行為。
- **驗收條件：** 完整提交先於 ACK；A14/A16→W11、A15/A17→W20、A18→W12。
- **交接：** 故障檢查點交給 FA-03、BA-03、BB-04、BB-05、BB-07、BB-08。

<a id="qa-05"></a>
<a id="qa-05--privacy-configuration-and-performance-acceptance"></a>
### QA-05 — 隱私、設定與效能驗收
- **追溯：** REQ-16／REQ-17／REQ-18；W17、HealthResponse 與部署設定。
- **前置條件：** 本版設定與課程基線、隔離憑證。
- **正常流程：** 驗設定缺漏／就緒、隱私安全日誌，分別量測協定負載與真實瀏覽器 E2E。課程基線為 50 測試使用者／50 WSS、25 個一對一聊天室、每使用者平均每 5 秒一則 ≤1 KiB 文字訊息，持續 10 分鐘；另驗收一個 50 人群組，不混入基線。記錄 VM、資料集、網路、工具及版本；量成功率、p95、CPU／RAM。目標：送出至收件端呈現 p95 ≤2 秒；有效登入、網路恢復、待補 ≤100 則時同步 ≤5 秒。
- **失敗流程：** 拒絕機密／本文洩漏、虛假健康狀態或未測規模宣稱；1k／5k／10k 連線僅未來壓測。
- **驗收條件：** 協定負載報告不得以收到訊框代替瀏覽器已保存／呈現，也不得把 ACK 當收件顯示；E2E 另行記錄實際瀏覽器結果。未達目標揭露原因，不宣稱高可用。
- **交接：** 發現交給 PM、DO-04、DO-05、BA-08、BB-04。

<a id="qa-06--web-響應式輸入路由與推播政策驗收"></a>
<a id="qa-06"></a>
<a id="qa-06--web-responsive-input-route-and-push-policy-acceptance"></a>
### QA-06 — Web 響應式、輸入、路由與瀏覽器支援驗收
**追溯：** REQ-19–REQ-22；Web/RWD、A12、A19、W08、W09。A23／A24 與 Web Push 本版範圍外。
- **前置條件：** 單一共用 Web 建置；Chrome／Edge 桌面版及 Android Chrome，記錄實測版本。
- **正常流程：** 僅一個 768 CSS px 斷點：窄版清單／聊天室切換，寬版雙欄；驗證 320、375、767、768、1024、1199、1200、1440 CSS px 視窗、方向、200% 縮放、鍵盤／觸控／中文 IME、焦點、捲動及頁面路由。未測瀏覽器不保證支援；缺 HTTPS、同來源、Cookie、本機儲存、WebSocket、Page Visibility 或 Web Locks 時顯示不支援且不啟用聊天，無無鎖退路。
- **失敗流程：** 不得因 IME 誤送、強制捲動或實際不可見而送 W09；授權前不得暴露內容；API/WSS 不套用頁面路由回退。Web Push 本版範圍外，關閉網頁不保證通知。
- **驗收條件：** 依 V3（50% 可見連續 500 ms）與 V4（鍵盤判別、根路徑、已載入清單篩選）驗收；記錄瀏覽器／版本、尺寸、方向、縮放與觀察結果。協定負載與瀏覽器 E2E 分開。
- **交接：** 發現交給 FA-08、FB-05、FB-06、FB-07、DO-06、BA-04、BB-05、BB-08 與 PM。

## 決策與共用參照

- [響應式 Web 行為](../ui/web-rwd.md#web-rwd)
- [決策：Web Push 範圍](../decisions.md#decision-web-push)
- [決策：響應式 Web 版面](../decisions.md#decision-rwd)
- [返回文件導覽](../README.md)
