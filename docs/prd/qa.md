<a id="hine-ic-04--qa-角色-prd"></a>
# HINE-IC-0.4 — 品質驗證（QA）角色 PRD

**版本：** HINE-IC-0.4  
**狀態：** 待產品核准  
**來源：** [歷史來源：HINE-IC-0.4 角色 PRD](../HINE-IC-0.4-role-prds.md); 唯一現行介面規格依據為 [共同介面契約](../contracts/interface-contract.md).  
**角色目的：** 負責行為、結構描述、隱私、復原與效能驗收。本 PRD 規定未來行為與驗收要求，不代表已實作或已完成測試。
**必讀／串接時查閱：** [系統架構](../architecture/README.md)、[共同介面契約](../contracts/interface-contract.md)、[驗收矩陣](../testing/acceptance-matrix.md)；各功能串接見下方追溯／交接。 [返回文件導覽](../README.md)。

## 範圍

- **範圍內：** 行為、結構描述、隱私、復原與效能驗收；以及下方角色專屬功能卡。
- **範圍外：** 其他角色所負責的範圍；亦不得變更共用 API／事件 ID、正式資料、ACK、游標或同步語意。共用欄位型別、封套、錯誤與限制均以共同介面契約為準。
- **共用 Web 行為：** 遵循 [Web／RWD 規格](../ui/web-rwd.md#web-rwd)；不得另訂斷點或重複定義版面規則。

## 功能索引

- [QA-01 — 介面契約與結構描述符合性](#qa-01)
- [QA-02 — 工作階段、更新、活動與多裝置行為](#qa-02)
- [QA-03 — 快照／事件流復原與游標隔離](#qa-03)
- [QA-04 — 跨模組行為與故障注入](#qa-04)
- [QA-05 — 隱私、設定與效能驗收](#qa-05)
- [QA-06 — Web 響應式、輸入、路由與推播政策驗收](#qa-06)

## 角色目的與責任界線

定義行為、結構描述、隱私、復原與效能驗收。僅於已有實作與核准測試環境後執行產品測試；本 PRD 未記錄任何測試執行結果。

<a id="qa-01"></a>
<a id="qa-01--interface-contract-and-schema-compliance"></a>
### QA-01 — 介面契約與結構描述符合性
**追溯：** [REQ-01 帳戶驗證與登入識別](../testing/acceptance-matrix.md#req-01), [REQ-02 憑證更新與登出轉換](../testing/acceptance-matrix.md#req-02), [REQ-03 個人檔案、頭像與聯絡人](../testing/acceptance-matrix.md#req-03), [REQ-04 一對一聊天導覽與建立](../testing/acceptance-matrix.md#req-04), [REQ-05 群組管理、權限與成員變更](../testing/acceptance-matrix.md#req-05), [REQ-06 文字訊息與持久 ACK](../testing/acceptance-matrix.md#req-06); [介面定位](../contracts/interface-contract.md#rest-api), [REST API A01–A25](../contracts/interface-contract.md#rest-api), [WebSocket W01–W22](../contracts/interface-contract.md#websocket-events)。
**REST 條目：** [A01](../contracts/interface-contract.md#api-a01), [A02](../contracts/interface-contract.md#api-a02), [A03](../contracts/interface-contract.md#api-a03), [A04](../contracts/interface-contract.md#api-a04), [A05](../contracts/interface-contract.md#api-a05), [A06](../contracts/interface-contract.md#api-a06), [A07](../contracts/interface-contract.md#api-a07), [A08](../contracts/interface-contract.md#api-a08), [A09](../contracts/interface-contract.md#api-a09), [A10](../contracts/interface-contract.md#api-a10), [A11](../contracts/interface-contract.md#api-a11), [A12](../contracts/interface-contract.md#api-a12), [A13](../contracts/interface-contract.md#api-a13).
**REST 條目（續）：** [A14](../contracts/interface-contract.md#api-a14), [A15](../contracts/interface-contract.md#api-a15), [A16](../contracts/interface-contract.md#api-a16), [A17](../contracts/interface-contract.md#api-a17), [A18](../contracts/interface-contract.md#api-a18), [A19](../contracts/interface-contract.md#api-a19), [A20](../contracts/interface-contract.md#api-a20), [A21](../contracts/interface-contract.md#api-a21), [A22](../contracts/interface-contract.md#api-a22), [A23](../contracts/interface-contract.md#api-a23), [A24](../contracts/interface-contract.md#api-a24), [A25](../contracts/interface-contract.md#api-a25).
**WebSocket 條目：** [W01](../contracts/interface-contract.md#event-w01), [W02](../contracts/interface-contract.md#event-w02), [W03](../contracts/interface-contract.md#event-w03), [W04](../contracts/interface-contract.md#event-w04), [W05](../contracts/interface-contract.md#event-w05), [W06](../contracts/interface-contract.md#event-w06), [W07](../contracts/interface-contract.md#event-w07), [W08](../contracts/interface-contract.md#event-w08), [W09](../contracts/interface-contract.md#event-w09), [W10](../contracts/interface-contract.md#event-w10), [W11](../contracts/interface-contract.md#event-w11).
**WebSocket 條目（續）：** [W12](../contracts/interface-contract.md#event-w12), [W13](../contracts/interface-contract.md#event-w13), [W14](../contracts/interface-contract.md#event-w14), [W15](../contracts/interface-contract.md#event-w15), [W16](../contracts/interface-contract.md#event-w16), [W17](../contracts/interface-contract.md#event-w17), [W18](../contracts/interface-contract.md#event-w18), [W19](../contracts/interface-contract.md#event-w19), [W20](../contracts/interface-contract.md#event-w20), [W21](../contracts/interface-contract.md#event-w21), [W22](../contracts/interface-contract.md#event-w22).
- **前置條件：** 一個版本的共用字典、端點／事件登錄表及範例承載資料。
- **正常流程：** 驗證欄位、可為 null 性、方法／路徑、回應 `status`、關聯、授權與事件對應。必填、可省略、可為 null 分開判定；`MessageView.receipt` 與 `AttachmentView.conversation_id` 為必填可為 null，不把判別欄位分支一概改成非 null。驗證候選排序／分頁邊界：固定 20 位 ASCII order_key 加 UUID 十六進位元組、A19 反向排序、REST 首次請求省略欄位、續頁游標編碼、可省略正十進位 `limit`（候選預設 20／上限 50）；選擇均待批准（[欄位存在性](../contracts/interface-contract.md#field-presence)、[排序／分頁](../contracts/interface-contract.md#ordering-pagination)、[REST 分頁](../contracts/interface-contract.md#rest-pagination)）。
- **失敗流程：** 缺少／多出不符該狀態的欄位、事件對應錯誤、以摘要代替詳細資料，或 subject_id 洩漏，均屬契約失敗。
- **驗收條件：** 每個消費端皆參照共用契約及中央 Web/RWD 章節；任何角色都不得重複定義版面區段或建立平台專屬業務結構描述。
- **交接：** 結構描述／報告發現交給 [FA-01](frontend-a.md#fa-01)、[FB-01](frontend-b.md#fb-01)、[BA-01](backend-a.md#ba-01)、[BB-01](backend-b.md#bb-01)。

<a id="qa-02"></a>
<a id="qa-02--session-refresh-activity-and-multi-device-behavior"></a>
### QA-02 — 工作階段、更新、活動與多裝置行為
**追溯：** [REQ-01 帳戶驗證與登入識別](../testing/acceptance-matrix.md#req-01), [REQ-02 憑證更新與登出轉換](../testing/acceptance-matrix.md#req-02), [REQ-14 裝置活動與背景推播](../testing/acceptance-matrix.md#req-14), [REQ-15 在線狀態與多裝置存活](../testing/acceptance-matrix.md#req-15); [A02](../contracts/interface-contract.md#api-a02), [A03](../contracts/interface-contract.md#api-a03), [A04](../contracts/interface-contract.md#api-a04); [W01](../contracts/interface-contract.md#event-w01), [W02](../contracts/interface-contract.md#event-w02), [W03](../contracts/interface-contract.md#event-w03), [W04](../contracts/interface-contract.md#event-w04), [W18](../contracts/interface-contract.md#event-w18), [W21](../contracts/interface-contract.md#event-w21), [W22](../contracts/interface-contract.md#event-w22); [validateAccess](../contracts/interface-contract.md#internal-validate-access), [getDevicePresence](../contracts/interface-contract.md#internal-get-device-presence), [recordActivity](../contracts/interface-contract.md#internal-record-activity)。
- **前置條件：** 有效帳戶、兩個裝置工作階段、可控制的連線生命週期。
- **正常流程：** 驗證登入／工作階段綁定；更新憑證、關閉舊連線、建立新的 [W01](../contracts/interface-contract.md#event-w01)/[W02](../contracts/interface-contract.md#event-w02)、送出第一筆 [W21](../contracts/interface-contract.md#event-w21)，並恢復已保存的游標；測試背景／前景及租約更新。
- **失敗流程：** 測試更新憑證／登出競態、舊世代延遲活動、背景訊框漏收、租約到期及 Redis 狀態不明。
- **驗收條件：** 不在同一連線重新驗證；過期工作階段無法恢復；租約到期後狀態為未知；單一裝置失敗不得使另一裝置登出。
- **候選補充案例（待批准）：** [AC-R05](../testing/acceptance-matrix.md#ac-r05) 記錄欄位存在性、排序、REST 分頁及心跳 `nonce` 邊界；[AC-R09](../testing/acceptance-matrix.md#ac-r09) 記錄 C13 內部驗證分層，W01 與已驗證連線的 W05 分開判定，並與 [AC-N10](../testing/acceptance-matrix.md#ac-n10) 對齊；僅為文件案例，尚未執行。
- **候選補充案例（待批准）：**
  - [AC-N03](../testing/acceptance-matrix.md#ac-n03)～[AC-N08](../testing/acceptance-matrix.md#ac-n08)、[AC-N10](../testing/acceptance-matrix.md#ac-n10)、[AC-N11](../testing/acceptance-matrix.md#ac-n11)：A04 通知遺失、後端 B 不可連線、A03 延遲通知、在途傳送、註冊競態、同一工作階段多連線、權威資料不可查、同裝置重新登入。
  - [AC-N13](../testing/acceptance-matrix.md#ac-n13)～[AC-N17](../testing/acceptance-matrix.md#ac-n17)：撤銷前資料的遞送窗口、佇列丟棄、並行交易、W14／W16 回應、W18。
  - [AC-N19](../testing/acceptance-matrix.md#ac-n19)～[AC-N24](../testing/acceptance-matrix.md#ac-n24)：多分頁交接。
  - [AC-N23](../testing/acceptance-matrix.md#ac-n23) 改採 C6 無寬限、一次復原的唯一流程；[AC-N27](../testing/acceptance-matrix.md#ac-n27) 涵蓋前景／背景／關閉／失效／過期狀態合併；[AC-N28](../testing/acceptance-matrix.md#ac-n28) 涵蓋瀏覽器能力不足時的不支援政策，不得把候選描述當作實測。
  - 撤銷前資料的時間窗口案例需要能控制節點的補齊時點與時鐘，才能觀察 `INVALIDATION_STALE_SECONDS` 上限。
- **交接：** 狀態轉換案例交給 [FB-02](frontend-b.md#fb-02)、[FA-07](frontend-a.md#fa-07)、[BA-01](backend-a.md#ba-01)、[BB-01](backend-b.md#bb-01)（工作階段、更新與登出權威）、[BB-08](backend-b.md#bb-08)。

<a id="qa-03"></a>
<a id="qa-03--snapshotfeed-recovery-and-cursor-isolation"></a>
### QA-03 — 快照／事件流復原與游標隔離
**追溯：** [REQ-09 首次登入、已授權快照與歷史分離](../testing/acceptance-matrix.md#req-09), [REQ-10 快照切換與即時投影合併](../testing/acceptance-matrix.md#req-10), [REQ-11 撤權過濾、自身通知與多群組同步](../testing/acceptance-matrix.md#req-11); [A08](../contracts/interface-contract.md#api-a08), [A11](../contracts/interface-contract.md#api-a11), [A19](../contracts/interface-contract.md#api-a19); [W13](../contracts/interface-contract.md#event-w13), [W14](../contracts/interface-contract.md#event-w14), [W15](../contracts/interface-contract.md#event-w15), [W16](../contracts/interface-contract.md#event-w16), [W17](../contracts/interface-contract.md#event-w17); [readBootstrap](../contracts/interface-contract.md#internal-read-bootstrap), [readFeed](../contracts/interface-contract.md#internal-read-feed)。
- **前置條件：** 使用同一 snapshot_id 的多頁快照，且 REST 清單／歷史游標彼此獨立。
- **正常流程：** 確認中間頁不安裝 H；所有暫存頁面完成並原子切換後才安裝 H、續讀事件流，並檢查隱藏的過濾位置。即使未要求完整離線／PWA，仍須在送出前保留持久化 C1／承載資料、W08 前完成已收訊息及其識別資訊的本機持久保存（不需先有伺服器回條），且投影＋游標原子套用；儲存失敗不得送 W08 或推進游標，亦不在此選定儲存技術（[本機持久化界線](../contracts/interface-contract.md#local-persistence-boundary)，待批准）。
- **失敗流程：** 分別讓每個 REST 游標過期，再讓使用者事件流游標過期。
- **驗收條件：** 每個 A08/A11/A19 失敗都只重新取得各自查詢；只有 WSS 事件流重設會觸發 W13。不得漏掉已授權事件或傳送未授權本文；單一撤權對話不得阻塞另一對話。保留必填／可省略／可為 null 區別及待批准的分頁／排序選擇。
- **候選補充案例（待批准）：** [AC-R03](../testing/acceptance-matrix.md#ac-r03) 涵蓋 C8 必須從已驗證主體／工作階段映射公開 user_id，且與 C1 invalidation_position 分離；缺映射時 W02 失敗，不以 subject_id 代替或假設 JWT 宣告。[AC-R07](../testing/acceptance-matrix.md#ac-r07) 涵蓋 A07 已知 ID 查詢，不做顯示名稱／電子郵件目錄搜尋。
- **候選補充案例（待批准）：** [AC-N25](../testing/acceptance-matrix.md#ac-n25) 的裝置既有副本與 [AC-N26](../testing/acceptance-matrix.md#ac-n26) 的 E1 待送／同步回應分開驗收；比對 [G3](../decisions.md#group-new-queries) 撤權後新查詢與其他對話續傳，不改游標／快照安裝條件。
- **候選補充案例（待批准）：** [AC-R06](../testing/acceptance-matrix.md#ac-r06) 記錄本機持久化界線：送出前保留持久化 C1／承載資料、W08 前完成已收訊息的本機持久保存、原子套用投影＋游標，且儲存失敗時不送 W08、不推進游標。不選儲存技術；案例尚未執行。
- **交接：** 游標邊界／預期本機狀態交給 [FA-05](frontend-a.md#fa-05)、[FB-04](frontend-b.md#fb-04)、[BA-06](backend-a.md#ba-06)、[BB-06](backend-b.md#bb-06)。

<a id="qa-04"></a>
<a id="qa-04--cross-module-behavior-and-failure-injection"></a>
### QA-04 — 跨模組行為與故障注入
**追溯：** [REQ-03 個人檔案、頭像與聯絡人](../testing/acceptance-matrix.md#req-03), [REQ-04 一對一聊天導覽與建立](../testing/acceptance-matrix.md#req-04), [REQ-05 群組管理、權限與成員變更](../testing/acceptance-matrix.md#req-05), [REQ-06 文字訊息與持久 ACK](../testing/acceptance-matrix.md#req-06), [REQ-07 ACK 遺失、重試與去重](../testing/acceptance-matrix.md#req-07), [REQ-08 跨節點即時廣播與漏送復原](../testing/acceptance-matrix.md#req-08), [REQ-12 已送達／已讀回條狀態機](../testing/acceptance-matrix.md#req-12), [REQ-13 圖片、檔案與上傳更新](../testing/acceptance-matrix.md#req-13), [REQ-14 裝置活動與背景推播](../testing/acceptance-matrix.md#req-14)。
**介面定位：** [A05](../contracts/interface-contract.md#api-a05), [A06](../contracts/interface-contract.md#api-a06), [A14](../contracts/interface-contract.md#api-a14), [A15](../contracts/interface-contract.md#api-a15), [A16](../contracts/interface-contract.md#api-a16), [A17](../contracts/interface-contract.md#api-a17), [A18](../contracts/interface-contract.md#api-a18), [A20](../contracts/interface-contract.md#api-a20), [A21](../contracts/interface-contract.md#api-a21), [A22](../contracts/interface-contract.md#api-a22), [A23](../contracts/interface-contract.md#api-a23), [A24](../contracts/interface-contract.md#api-a24), [A25](../contracts/interface-contract.md#api-a25); [W05](../contracts/interface-contract.md#event-w05), [W06](../contracts/interface-contract.md#event-w06), [W07](../contracts/interface-contract.md#event-w07), [W08](../contracts/interface-contract.md#event-w08), [W09](../contracts/interface-contract.md#event-w09), [W10](../contracts/interface-contract.md#event-w10), [W11](../contracts/interface-contract.md#event-w11), [W12](../contracts/interface-contract.md#event-w12), [W13](../contracts/interface-contract.md#event-w13), [W14](../contracts/interface-contract.md#event-w14), [W15](../contracts/interface-contract.md#event-w15), [W16](../contracts/interface-contract.md#event-w16), [W19](../contracts/interface-contract.md#event-w19), [W20](../contracts/interface-contract.md#event-w20)。
**內部操作：** [authorize](../contracts/interface-contract.md#internal-authorize)、[persistIfAbsent](../contracts/interface-contract.md#internal-persist-if-absent)、[persistReceipt](../contracts/interface-contract.md#internal-persist-receipt)、[readBootstrap](../contracts/interface-contract.md#internal-read-bootstrap)、[readFeed](../contracts/interface-contract.md#internal-read-feed)、[dispatchPushIntent](../contracts/interface-contract.md#internal-dispatch-push-intent)。
- **前置條件：** 隔離的使用者、對話、附件儲存空間及推播供應商測試設定。
- **正常流程：** 測試零對話頭像、A25 更新、群組 A14–A18 對應、ACK 復原、回條復原、背景提示及返回應用程式後同步。
- **失敗流程：** 注入已知回滾、提交後 ACK 遺失、ACK 後發布中斷、過期上傳嘗試、錯誤 MIME、成員撤權及供應商失敗。
- **候選補充案例（待批准）：** [AC-R02](../testing/acceptance-matrix.md#ac-r02) 記錄 W17 代碼／操作範圍復原路由，包含 `retry_after_ms` 可省略／缺漏、無有效已知延遲時不計算截止時間或立即自動重試、僅允許手動重試，以及 C6 恢復次數不變。僅記錄案例，未執行產品測試。
- **驗收條件：** 原始 C1 恢復為單一 M1；完整提交先於 ACK；A14/A16→W11、A15/A17→W20、A18→W12；供應商錯誤不改變回條。
- **候選補充案例（待批准）：** 既有 [AC-R04](../testing/acceptance-matrix.md#ac-r04) 保留 C9 中繼資料、PUT／A21 就緒／CORS 交接，並補入同案例的[四項版本交錯](../testing/acceptance-matrix.md#ac-r04-version-cases)：就緒後舊 URL PUT 不同內容、A25 後舊 PUT 晚到、PUT 成功回覆遺失後重試 412、A21 核驗版本與 A22 交付版本不符／不可取。判定同一就緒綁定與中繼資料／位元組一致、412 不等於就緒、不退回最新版本。[AC-R08](../testing/acceptance-matrix.md#ac-r08) 的一對一回條與條件式群組範圍不變。全部是文件案例，未執行產品測試。
- **候選補充案例（待批准）：** [AC-N01](../testing/acceptance-matrix.md#ac-n01)、[AC-N02](../testing/acceptance-matrix.md#ac-n02)、[AC-N09](../testing/acceptance-matrix.md#ac-n09)、[AC-N12](../testing/acceptance-matrix.md#ac-n12) 與群組政策的 [AC-N18](../testing/acceptance-matrix.md#ac-n18)／[AC-N26](../testing/acceptance-matrix.md#ac-n26)。後兩者分別是不採／採 E1 的比較條件，批准後只驗收被選定方案；60 秒保留窗不可驗成最大遞送延遲。本輪不執行產品測試。
- **交接：** 可重現的故障檢查點交給 [FA-03](frontend-a.md#fa-03)、[BA-03](backend-a.md#ba-03)、[BB-04](backend-b.md#bb-04)、[BB-05](backend-b.md#bb-05)、[BB-07](backend-b.md#bb-07)、[BB-08](backend-b.md#bb-08)。

<a id="qa-05"></a>
<a id="qa-05--privacy-configuration-and-performance-acceptance"></a>
### QA-05 — 隱私、設定與效能驗收
**追溯：** [REQ-16 統一錯誤與隱私保護](../testing/acceptance-matrix.md#req-16), [REQ-17 基礎設施、健康探測與 CI 交付](../testing/acceptance-matrix.md#req-17), [REQ-18 效能驗證與容量界線](../testing/acceptance-matrix.md#req-18)。
**介面定位：** [W17](../contracts/interface-contract.md#event-w17), [HealthResponse](../contracts/interface-contract.md#data-dictionary), [部署設定](../contracts/interface-contract.md#deployment-config)。
- **前置條件：** PM 已核准的操作值／工作負載與隔離憑證。
- **正常流程：** 驗證缺少設定／就緒回應、隱私安全日誌，以及分別測量 ACK、端到端遞送、重新連線、同步復原與事件流競爭。
- **失敗流程：** 拒絕機密／本文洩漏、虛假的健康狀態及未測試的規模宣稱。未核准的歷史 SLO 不列入通過／失敗判準。
- **驗收條件：** 結果須列明確切環境／工作負載；未經測量不得宣稱容量。本 PRD 不宣稱執行任何產品測試或產生效能結果。
- **交接：** 將發現交給 PM、[DO-04](devops.md#do-04)、[DO-05](devops.md#do-05)、[BA-08](backend-a.md#ba-08)、[BB-04](backend-b.md#bb-04)。

<a id="qa-06"></a>
<a id="qa-06--web-responsive-input-route-and-push-policy-acceptance"></a>
### QA-06 — Web 響應式、輸入、路由與推播政策驗收
**追溯：** [REQ-19 共用響應式 Web 頁面](../testing/acceptance-matrix.md#req-19), [REQ-20 響應式聊天互動與已讀狀態](../testing/acceptance-matrix.md#req-20), [REQ-21 Web 深層連結與授權後路由返回](../testing/acceptance-matrix.md#req-21), [REQ-22 Web Push 政策範圍與驗收治理](../testing/acceptance-matrix.md#req-22); [Web/RWD](../ui/web-rwd.md#web-rwd), [A12](../contracts/interface-contract.md#api-a12), [A19](../contracts/interface-contract.md#api-a19), [A23](../contracts/interface-contract.md#api-a23), [A24](../contracts/interface-contract.md#api-a24); [W08](../contracts/interface-contract.md#event-w08), [W09](../contracts/interface-contract.md#event-w09)。
- **前置條件：** 單一共用 Web 建置、候選支援瀏覽器、可控制的視窗／輸入／方向、測試帳戶及候選驗收條件。
- **正常流程：** 執行瀏覽器／版本 × 範例視窗 × 方向 × 縮放案例；適用控制項使用滑鼠／觸控、實體／虛擬鍵盤及中文 IME。範例視窗為 320、375、767、768、1024、1199、1200 與 1440 CSS px（測試尺寸，非斷點定義）；涵蓋直向／橫向、200% 縮放、所有頁面類型及候選 UI 深層連結／授權返回。測試撰寫區可見性、方向變換／前置載入歷史期間錨點保留、候選自動跟隨／已讀可見門檻，以及僅作治理議題的瀏覽器推播範圍。瀏覽器／版本選擇均為候選，待產品／QA 核准，且必須記錄。逐一驗證 [REQ-20 詳細驗收](../testing/acceptance-matrix.md#req-20-detail) 的「應判已讀／不得判已讀」案例、鍵盤類型無法判別時的候選行為，[REQ-21 詳細驗收](../testing/acceptance-matrix.md#req-21-detail) 的根路徑 `/` 初始化中／未登入／已登入三種結果，以及 [REQ-19 詳細驗收](../testing/acceptance-matrix.md#req-19-detail) 的清單搜尋只篩選本機已載入項目。[AC-R10](../testing/acceptance-matrix.md#ac-r10) 的未讀數五個交錯（W19 晚於基準、基準已含新訊息、重複／重播、早於基準的 `changed:true`、先確認已讀後取得建立事件），依 PM 所選 C14-M 或 C14-S 判定。
- **失敗流程：** 確認重排版不會建立第二條 WSS／工作階段／游標、不會因 IME 意外送出、不會強制捲動歷史、未符合候選實際可見條件時不送出 [W09](../contracts/interface-contract.md#event-w09)、授權前不暴露受保護資料，也不會以頁面路由回退處理 API/WSS 路徑。不得從 [A23](../contracts/interface-contract.md#api-a23)/[A24](../contracts/interface-contract.md#api-a24) 或原生應用程式/PWA 行為推論瀏覽器推播。
- **驗收條件：** 每個案例記錄瀏覽器／版本、視窗／方向／縮放、輸入方式、路由及觀察到的版面／狀態。區分提議中的版面及互動門檻與已核准行為；[W08](../contracts/interface-contract.md#event-w08) 獨立於 [W09](../contracts/interface-contract.md#event-w09)，且 [REQ-22](../testing/acceptance-matrix.md#req-22) 仍是瀏覽器推播核准／契約的先決條件。此處不宣稱任何產品測試結果。
- **交接：** 將瀏覽器／寬度／輸入／狀態發現及政策先決條件交給 [FA-08](frontend-a.md#fa-08)、[FB-05](frontend-b.md#fb-05)、[FB-06](frontend-b.md#fb-06)、[FB-07](frontend-b.md#fb-07)、[DO-06](devops.md#do-06)、[BA-04](backend-a.md#ba-04)、[BB-05](backend-b.md#bb-05)、[BB-08](backend-b.md#bb-08) 與 PM。

## 決策與共用參照

- [響應式 Web 行為](../ui/web-rwd.md#web-rwd)
- [決策：Web Push 範圍](../decisions.md#decision-web-push)
- [決策：響應式 Web 版面](../decisions.md#decision-rwd)
- [返回文件導覽](../README.md)
