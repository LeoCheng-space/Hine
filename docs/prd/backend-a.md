<a id="hine-ic-04--backend-a-角色-prd"></a>
# HINE-IC-0.4 — 後端 A 角色 PRD

**版本：** HINE-IC-0.4  
**狀態：** 待產品核准  
**來源：** [歷史來源：HINE-IC-0.4 角色 PRD](../HINE-IC-0.4-role-prds.md); 唯一現行介面規格依據為 [共同介面契約](../contracts/interface-contract.md).  
**角色目的：** 負責 WSS 交握、連線／心跳、短暫性 Redis／線上狀態、活動租約、事件路由與同步入口。本 PRD 規定未來行為與驗收要求，不代表已實作或已完成測試。
**必讀／串接時查閱：** [系統架構](../architecture/README.md)、[共同介面契約](../contracts/interface-contract.md)、[驗收矩陣](../testing/acceptance-matrix.md)；各功能串接見下方追溯／交接。 [返回文件導覽](../README.md)。

## 範圍

- **範圍內：** WSS 交握、連線／心跳、短暫性 Redis／在線狀態、活動租約、事件路由與同步入口；以及下方角色專屬功能卡。
- **範圍外：** 其他角色所負責的範圍；亦不得變更共用 API／事件 ID、正式資料、ACK、游標或同步語意。共用欄位型別、封套、錯誤與限制均以共同介面契約為準。
- **共用 Web 行為：** 遵循 [Web／RWD 規格](../ui/web-rwd.md#web-rwd)；不得另訂斷點或重複定義版面規則。

## 功能索引

- [BA-01 — WSS 驗證與工作階段終止](#ba-01)
- [BA-02 — 心跳與使用者層級在線狀態](#ba-02)
- [BA-03 — 訊息入口與持久化 ACK](#ba-03)
- [BA-04 — 送達／已讀回條轉送](#ba-04)
- [BA-05 — 跨節點散佈與群組事件路由](#ba-05)
- [BA-06 — 初始化與事件流同步入口](#ba-06)
- [BA-07 — 裝置活動租約](#ba-07)
- [BA-08 — 速率限制、訊框防護與 WSS 錯誤](#ba-08)

## 角色目的與責任界線

負責 WSS 交握、連線／心跳、短暫性 Redis／在線狀態、活動租約、事件路由與同步入口。後端 B 負責 JWT／工作階段權威、授權決策、持久化狀態與 PostgreSQL 結構描述。瀏覽器版面不得衍生另一套即時 API、事件模型、連線或游標。

<a id="ba-01"></a>
<a id="ba-01--wss-authentication-and-session-termination"></a>
### BA-01 — WSS 驗證與工作階段終止
**追溯：** [REQ-01 帳戶驗證與登入識別](../testing/acceptance-matrix.md#req-01), [REQ-02 憑證更新與登出轉換](../testing/acceptance-matrix.md#req-02); [W01](../contracts/interface-contract.md#event-w01), [W02](../contracts/interface-contract.md#event-w02), [W17](../contracts/interface-contract.md#event-w17); [validateAccess](../contracts/interface-contract.md#internal-validate-access)。
- **前置條件：** 新的 WSS 連線。
**正常流程：** 一律先要求 [W01](../contracts/interface-contract.md#event-w01)；由 BB 驗證權杖與裝置綁定，並在同一次驗證結果中取得 BB 依已驗證主體／工作階段映射的公開 `user_id`（[C8，待批准](../contracts/interface-contract.md#public-identity-handoff)）；以該公開身分／裝置／工作階段世代及設定的心跳值回覆 W02。不得退回使用 `subject_id`，也不得假設 JWT 含 `user_id` 宣告。
- **失敗流程：** 拒絕已過期、已撤銷、裝置錯誤或世代過期的工作階段；A03/A04 撤銷生效時停止新操作並關閉舊連線。關閉前可傳送 W17，但不保證送達。
- **驗收條件：** 絕不信任用戶端提供的 subject_id；更新憑證後須使用新連線完成驗證；單一裝置失效不撤銷其他裝置。缺少公開使用者映射時不得成功回覆 W02。
- **候選（待批准）：**
  - 經 BB 的操作一律帶該連線的工作階段綁定（[C2](../contracts/interface-contract.md#internal-change-requests)）；BB 以可信回應回使用者工作階段層的 `UNAUTHENTICATED`（[C13](../contracts/interface-contract.md#internal-auth-layer)：`details.auth_layer:"user_session"`，待批准）時，立即標記該連線失效並關閉；服務身分層、缺少分層或非可信回應回 W17 `DEPENDENCY_UNAVAILABLE`：**已驗證連線**不因這個錯誤關線、不撤銷登入，交付與關閉仍依[狀態表](../contracts/interface-contract.md#delivery-state-table)與生命週期；**新連線的 W01** 無法取得可信驗證結果時不回 W02，回 W17 `DEPENDENCY_UNAVAILABLE` 後關閉該未驗證連線（與 [AC-N10](../testing/acceptance-matrix.md#ac-n10) 相同），不宣稱工作階段已撤銷。其他錯誤碼照共用錯誤分流，不因此關線。
  - 節點依 [SessionInvalidation](../contracts/interface-contract.md#internal-session-invalidation) 只關閉 `session_id` 與世代相符的連線：A03 只關舊世代；A04 與 A02 取代只關該工作階段。紀錄經通知、每 `INVALIDATION_POLL_SECONDS` 輪詢或遞送閘門補齊取得。
  - 節點狀態不新鮮時拒絕 W01，連線保留但只送 W04 與 W17（[狀態表](../contracts/interface-contract.md#delivery-state-table)）。
  - W01 的最後檢查與註冊須與套用失效紀錄互斥，並涵蓋所有已知、位置大於 `validateAccess` 回傳位置的紀錄。
  - 連線最遲在存取權杖到期時關閉。
  - 見[授權判定界線](../contracts/interface-contract.md#authorization-boundary)與[驗收 AC-N03～AC-N08、AC-N11](../testing/acceptance-matrix.md#ac-n03)。
- **交接：** [BB-01](backend-b.md#bb-01) 工作階段狀態；[FA-01](frontend-a.md#fa-01)/[FB-02](frontend-b.md#fb-02) 工作階段替換。

<a id="ba-02"></a>
<a id="ba-02--heartbeat-and-user-level-presence"></a>
### BA-02 — 心跳與使用者層級在線狀態
**追溯：** [REQ-15 在線狀態與多裝置存活](../testing/acceptance-matrix.md#req-15); [W03](../contracts/interface-contract.md#event-w03), [W04](../contracts/interface-contract.md#event-w04), [W18](../contracts/interface-contract.md#event-w18); [getDevicePresence](../contracts/interface-contract.md#internal-get-device-presence)。
- **前置條件：** 已驗證的連線。
**正常流程：** W03/W04 用於追蹤連線存活。`nonce` 必須是非空字串；W04 必須原樣回顯，且 correlation_id 必須對應同一連線上同一筆待回覆 W03。不得轉型；重複或過期的 W04 不延長存活時間（[共用 `nonce` 規則](../contracts/interface-contract.md#heartbeat-nonce)，待批准）。
- **失敗流程：** 心跳逾時只清除該連線。Redis 無法使用時，在線狀態視為未知，不得斷定離線或在線。
- **驗收條件：** 在線狀態描述彙總連線情形，絕不代表應用程式在前景或訊息已送達。
- **交接：** [BB-02](backend-b.md#bb-02) 在線狀態查詢；[FA-07](frontend-a.md#fa-07)/[FB-04](frontend-b.md#fb-04) 顯示。

<a id="ba-03"></a>
<a id="ba-03--message-ingress-and-persisted-ack"></a>
### BA-03 — 訊息入口與持久化 ACK
**追溯：** [REQ-06 文字訊息與持久 ACK](../testing/acceptance-matrix.md#req-06), [REQ-07 ACK 遺失、重試與去重](../testing/acceptance-matrix.md#req-07); [W05](../contracts/interface-contract.md#event-w05), [W06](../contracts/interface-contract.md#event-w06), [W07](../contracts/interface-contract.md#event-w07), [W17](../contracts/interface-contract.md#event-w17); [authorize](../contracts/interface-contract.md#internal-authorize), [persistIfAbsent](../contracts/interface-contract.md#internal-persist-if-absent)。
- **前置條件：** 已驗證的主體、已授權的對話、有效訊息 C1。
- **正常流程：** 驗證類型／內容、授權並呼叫交易式持久化；完整持久化結果產生後才送出 [W06](../contracts/interface-contract.md#event-w06)；將 [W07](../contracts/interface-contract.md#event-w07) 路由至已授權的收件者。
- **失敗流程：** 已知回滾時不得產生成功 ACK；結果不明時標示 OUTCOME_UNCONFIRMED；ACK 遺失時以相同 C1 復原。Redis 發布失敗可透過 [W16](../contracts/interface-contract.md#event-w16) 復原。
- **驗收條件：** ACK 不得早於訊息、C1 對應及必要事件流提交完成。同一 C1 對應至同一 M1／事件；承載資料變更時衝突。
- **交接：** [BB-04](backend-b.md#bb-04) 持久化／收件者；[FA-03](frontend-a.md#fa-03) 重試／合併；[QA-04](qa.md#qa-04) 故障案例。

<a id="ba-04"></a>
<a id="ba-04--deliveryread-receipt-forwarding"></a>
### BA-04 — 送達／已讀回條轉送
**追溯：** [REQ-12 已送達／已讀回條狀態機](../testing/acceptance-matrix.md#req-12); [W08](../contracts/interface-contract.md#event-w08), [W09](../contracts/interface-contract.md#event-w09), [W10](../contracts/interface-contract.md#event-w10), [W19](../contracts/interface-contract.md#event-w19); [persistReceipt](../contracts/interface-contract.md#internal-persist-receipt)。
- **前置條件：** 已驗證的裝置與已授權的訊息收件者。
**正常流程：** 透過 BB 持久化單調回條；將 W19 與其 W08/W09 請求關聯；向允許的觀察者轉送 W10，並支援事件流復原。一對一訊息的 W10 依 BB `persistReceipt` 回傳的正式訊息／`status`／`updated_at` 建構；recipient_id 取自 C8 信任的公開操作者身分、event_id 取自 `status_event_id`、收件者取自 C4 `observer_ids`。群組投影仍屬條件式提案，待批准前不得捏造彙總／計數欄位（[回條投影交接](../contracts/interface-contract.md#receipt-projection-handoff)，待批准）。
- **失敗流程：** 拒絕偽造／不相關回條；重複回報不執行操作；`read` 不得倒退。
- **驗收條件：** W19 請求結果有別於 W10 投影；BB 為正式狀態的權威來源。
- **交接：** [BB-05](backend-b.md#bb-05) 權威回條；[FA-04](frontend-a.md#fa-04) 回條投影。

<a id="ba-05"></a>
<a id="ba-05--cross-node-fanout-and-group-event-routing"></a>
### BA-05 — 跨節點散佈與群組事件路由
**追溯：** [REQ-05 群組管理、權限與成員變更](../testing/acceptance-matrix.md#req-05), [REQ-08 跨節點即時廣播與漏送復原](../testing/acceptance-matrix.md#req-08), [REQ-11 撤權過濾、自身通知與多群組同步](../testing/acceptance-matrix.md#req-11); [A14](../contracts/interface-contract.md#api-a14), [A15](../contracts/interface-contract.md#api-a15), [A16](../contracts/interface-contract.md#api-a16), [A17](../contracts/interface-contract.md#api-a17), [A18](../contracts/interface-contract.md#api-a18); [W07](../contracts/interface-contract.md#event-w07), [W11](../contracts/interface-contract.md#event-w11), [W12](../contracts/interface-contract.md#event-w12), [W15](../contracts/interface-contract.md#event-w15), [W16](../contracts/interface-contract.md#event-w16), [W20](../contracts/interface-contract.md#event-w20)。
- **前置條件：** BB 已提交訊息或成員變更交易。
- **正常流程：** Redis Pub/Sub 加速將事件送至目前已授權的連線；保留各收件者專屬的事件識別。
- **失敗流程：** 發布遺失時透過 [W16](../contracts/interface-contract.md#event-w16) 修復。遞送時重新檢查授權；已撤權成員僅收到自己的最小化 [W12](../contracts/interface-contract.md#event-w12)，不得收到後續本文。
- **驗收條件：** 群組變更事件對應精確；不得將訊息代理中的暫態資料視為持久化成功。
- **候選（待批准）：**
  - 收件者一律採用 BB 在提交交易內決定的清單（`persistIfAbsent` 的 `recipient_ids`、`persistReceipt` 的 `observer_ids`、BB 通知的 `deliveries`），不得以快取的成員名單或 `authorize` 結果決定收件者。
  - 遞送前若 `invalidation_position` 大於已套用位置，先補齊失效紀錄；無法補齊就放棄即時遞送，由同步補回。
  - 每個訊框開始交付時，再檢查連線狀態與節點新鮮狀態（D2）；套用工作階段撤銷時，丟棄該連線佇列中尚未開始交付的訊框。群組撤權不清空整條連線的佇列。
  - 提供 [`publishCommitted`](../contracts/interface-contract.md#internal-publish-committed) 並發布到 Redis Pub/Sub；以 `notice_id` 去重。
  - 群組待送內容主要推薦 [E1](../contracts/interface-contract.md#group-revocation-e1) 的有界停止交付；不採 E1 的前輪候選只在移除紀錄保留窗內盡力丟棄，60 秒不是最大交付延遲。兩者由 [G2](../decisions.md#group-pending-content) 擇一批准，見 [AC-N26](../testing/acceptance-matrix.md#ac-n26)。
  - 見[驗收 AC-N01、AC-N02、AC-N09、AC-N12～AC-N18](../testing/acceptance-matrix.md#ac-n01)。
- **交接：** [BB-03](backend-b.md#bb-03) 已提交的成員／事件流資料列；[FA-05](frontend-a.md#fa-05) 節點間遞送／復原；[DO-01](devops.md#do-01) 路由。

<a id="ba-06"></a>
<a id="ba-06--bootstrap-and-feed-sync-ingress"></a>
### BA-06 — 初始化與事件流同步入口
**追溯：** [REQ-09 首次登入、已授權快照與歷史分離](../testing/acceptance-matrix.md#req-09), [REQ-10 快照切換與即時投影合併](../testing/acceptance-matrix.md#req-10), [REQ-11 撤權過濾、自身通知與多群組同步](../testing/acceptance-matrix.md#req-11); [W13](../contracts/interface-contract.md#event-w13), [W14](../contracts/interface-contract.md#event-w14), [W15](../contracts/interface-contract.md#event-w15), [W16](../contracts/interface-contract.md#event-w16), [W17](../contracts/interface-contract.md#event-w17); [readBootstrap](../contracts/interface-contract.md#internal-read-bootstrap), [readFeed](../contracts/interface-contract.md#internal-read-feed)。
- **前置條件：** 有效且已驗證的主體。
- **正常流程：** [W13](../contracts/interface-contract.md#event-w13)/[W14](../contracts/interface-contract.md#event-w14) 代理一致性快照頁面；[W15](../contracts/interface-contract.md#event-w15)/[W16](../contracts/interface-contract.md#event-w16) 代理已固定安全邊界的事件流批次。
- **失敗流程：** 使用者 SyncCursor 過期時回傳 [W17](../contracts/interface-contract.md#event-w17) SYNC_RESET_REQUIRED。[A08](../contracts/interface-contract.md#api-a08)/[A11](../contracts/interface-contract.md#api-a11)/[A19](../contracts/interface-contract.md#api-a19) 的 REST 游標錯誤不得觸發重設。快照未完整時，頁面序列不得宣稱起始游標已安裝。
- **驗收條件：** 隱藏位置可安全前進；未授權內容會被過濾；單一撤權對話不得阻塞其餘事件流。
- **候選（待批准）：** [群組三項政策](../contracts/interface-contract.md#group-revocation-policy)分開處理；採 [E1](../contracts/interface-contract.md#group-revocation-e1) 時，已套用撤權後不開始交付相符的舊授權 W14／W16 內容，不代用戶端推進游標，沿用授權過濾／重新讀取與錯誤恢復路徑，其他對話繼續同步（[AC-N26](../testing/acceptance-matrix.md#ac-n26)）。
- **交接：** [BB-06](backend-b.md#bb-06) 讀取／授權過濾資料列；[FA-05](frontend-a.md#fa-05) 游標提交／投影；[QA-03](qa.md#qa-03) 復原。

<a id="ba-07"></a>
<a id="ba-07--device-activity-leases"></a>
### BA-07 — 裝置活動租約
**追溯：** [REQ-14 裝置活動與背景推播](../testing/acceptance-matrix.md#req-14), [REQ-15 在線狀態與多裝置存活](../testing/acceptance-matrix.md#req-15); [W21](../contracts/interface-contract.md#event-w21), [W22](../contracts/interface-contract.md#event-w22); [recordActivity](../contracts/interface-contract.md#internal-record-activity), [getDevicePresence](../contracts/interface-contract.md#internal-get-device-presence)。
- **前置條件：** [W02](../contracts/interface-contract.md#event-w02) 已接受有效工作階段與裝置。
- **正常流程：** 驗證 [W21](../contracts/interface-contract.md#event-w21) 裝置與世代；記錄目前前景／背景狀態；以伺服器有效期限回覆 [W22](../contracts/interface-contract.md#event-w22)。提供裝置層級查詢給 BB。
- **失敗流程：** 拒絕過期工作階段世代；重複狀態回報具冪等性；Redis 失敗／過期時狀態為未知。
- **驗收條件：** 活動狀態不授予聊天權限、不是心跳，且可安全用於判斷各裝置的推播對象。
- **候選（待批准）：** 收到 W21 後先依 D4 完整補齊，失敗回 W17 `DEPENDENCY_UNAVAILABLE`、不記錄活動。通過後依 [C7](../contracts/interface-contract.md#activity-merge) 各連線分別計租、跨節點合併裝置狀態，不採裝置層最後寫入覆蓋；偵測關閉／套用失效時移除該連線，未偵測的關頁由原租期兜底。見 [AC-N03](../testing/acceptance-matrix.md#ac-n03)、[AC-N27](../testing/acceptance-matrix.md#ac-n27)。
- **交接：** [FA-07](frontend-a.md#fa-07) 生命週期；[BB-08](backend-b.md#bb-08) 推播資格。

<a id="ba-08"></a>
<a id="ba-08--rate-limiting-frame-defense-and-wss-errors"></a>
### BA-08 — 速率限制、訊框防護與 WSS 錯誤
**追溯：** [REQ-16 統一錯誤與隱私保護](../testing/acceptance-matrix.md#req-16); [W17](../contracts/interface-contract.md#event-w17) 與共用候選限制。
- **前置條件：** 任意未驗證／已驗證訊框。
- **正常流程（BA 服務端責任）：** 執行核准的限制及訊框防護，並依共用 W17 格式輸出 `code`／`message`／`retryable`／`correlation_id`。只有可重試的 `RATE_LIMITED` 且有已知安全延遲時才提供非負整數 `retry_after_ms`；缺少安全延遲時省略，不填 0。內部操作回的 `UNAUTHENTICATED` 依 [C13](../contracts/interface-contract.md#internal-auth-layer)（待批准）分層：只有可信回應且 `auth_layer:"user_session"` 轉為 W17 `UNAUTHENTICATED` 並關閉該連線；`service_identity`、缺少分層的 `UNAUTHENTICATED`，或非可信／非 HINE 錯誤封套的回應回 W17 `DEPENDENCY_UNAVAILABLE`，不撤銷使用者工作階段；新 W01 據此關閉未驗證連線，已驗證連線依狀態表與生命週期（見 [BA-01](#ba-01)）。`auth_layer` 只適用於 `UNAUTHENTICATED`；`FORBIDDEN`、`RATE_LIMITED`、`IDEMPOTENCY_CONFLICT`、`OUTCOME_UNCONFIRMED`、`PERSISTENCE_FAILED` 等照原錯誤碼傳遞，不因缺少 `auth_layer` 改寫。BA 不替前端決定是否刷新、登出或重試。
- **前端消費規則（FA／FB 執行，BA 只確保錯誤可辨識）：** 依[共用錯誤復原規則](../contracts/interface-contract.md#error-recovery)（待批准）：僅 UNAUTHENTICATED／已知權杖過期進入既有驗證更新流程；有效權杖的斷線應重新連線並執行 W01/W02、再送 W15，不得盲目呼叫 A03。FORBIDDEN／NOT_FOUND／驗證錯誤／衝突僅使該操作失敗；依賴項失敗不代表憑證失效。RATE_LIMITED 限於失敗動作；`retry_after_ms` 缺漏或無效時不得計算截止時間、視為零或立即自動重試，只顯示限制並允許手動重試，保留已知 `retry_not_before`，且不改變 C6 復原次數。事件流的 SYNC_RESET_REQUIRED 使用 W13；REST 游標錯誤僅重設該查詢；結果不明的寫入沿用同一 C1/Idempotency-Key；已知回滾不算成功。
- **失敗流程：** 為慢速消費者限制每個連線的輸出；連線中斷時不得宣稱錯誤已送達；絕不記錄權杖或本文。
- **驗收條件：** 不得捏造成功結果；所有最終數值限制仍須可設定，且在 PM／QA 決策前均未核准。
- **交接：** [FA-01](frontend-a.md#fa-01)／[FB-02](frontend-b.md#fb-02) 前端錯誤消費規則；[BB-01](backend-b.md#bb-01) 內部驗證錯誤分層；[QA-05](qa.md#qa-05) 錯誤／隱私驗收；[DO-04](devops.md#do-04) 維運設定與服務身分失敗告警。

## 決策與共用參照

- [響應式 Web 行為](../ui/web-rwd.md#web-rwd)
- [決策：Web Push 範圍](../decisions.md#decision-web-push)
- [決策：響應式 Web 版面](../decisions.md#decision-rwd)
- [返回文件導覽](../README.md)
