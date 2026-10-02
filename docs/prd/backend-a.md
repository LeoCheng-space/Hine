<a id="hine-ic-04--backend-a-角色-prd"></a>
# HINE-IC-0.4 — 後端 A 角色 PRD

**版本：** HINE-IC-0.4  
**狀態：** 現行規格（2026-10-01 PM 決議）
**來源：** [歷史來源：HINE-IC-0.4 角色 PRD](../HINE-IC-0.4-role-prds.md); 唯一現行介面規格依據為 [共同介面契約](../contracts/interface-contract.md).  
**角色目的：** 負責 WSS 交握、連線／心跳、短暫性 Redis／在線狀態、事件路由與同步入口。本 PRD 規定行為與驗收要求，不代表已實作或已完成測試。
**必讀／串接時查閱：** [系統架構](../architecture/README.md)、[共同介面契約](../contracts/interface-contract.md)、[驗收矩陣](../testing/acceptance-matrix.md)；各功能串接見下方追溯／交接。 [返回文件導覽](../README.md)。

## 範圍

- **範圍內：** WSS 交握、連線／心跳、單一 Redis Pub/Sub 通知／在線狀態、事件路由與同步入口；以及下方角色專屬功能卡。
- **範圍外：** 活動租約與 W21／W22（本版範圍外，2026-10-01 PM 決議）；其他角色所負責的範圍；不得單方變更共用 API／事件 ID、正式資料、ACK、游標或同步語意。介面依[共同變更流程](../../CONTRIBUTING.md#interface-changes)與受影響成員一起修改，先對齊[近期串接基線](../contracts/interface-contract.md#integration-baseline)。各後端負責人自選語言及內部實作，以內部 HTTP＋JSON 對接；不要求共用後端原始碼／型別／ORM或一次鎖死整份規格。PostgreSQL 為主資料庫，Redis 僅供通知與在線狀態。
- **共用 Web 行為：** 遵循 [Web／RWD 規格](../ui/web-rwd.md#web-rwd)；不得另訂斷點或重複定義版面規則。

## 功能索引

- [BA-01 — WSS 驗證與工作階段終止](#ba-01)
- [BA-02 — 心跳與使用者層級在線狀態](#ba-02)
- [BA-03 — 訊息入口與持久化 ACK](#ba-03)
- [BA-04 — 送達／已讀回條轉送](#ba-04)
- [BA-05 — 即時散佈（單一 realtime 實例）與群組事件路由](#ba-05)
- [BA-06 — 初始化與事件流同步入口](#ba-06)
- [BA-07 — 裝置活動租約（本版範圍外）](#ba-07)
- [BA-08 — 速率限制、訊框防護與 WSS 錯誤](#ba-08)

## 角色目的與責任界線

負責 WSS 交握、連線／心跳、短暫性 Redis／在線狀態、事件路由與同步入口。後端 B 負責工作階段權威、授權決策、持久化狀態與 PostgreSQL 結構描述；兩者可使用不同語言，以內部 HTTP＋JSON 對接，無須共用 backend/common 原始碼或 ORM。Redis 僅用於通知與在線狀態。瀏覽器版面不得衍生另一套即時 API、事件模型、連線或游標。

<a id="ba-01"></a>
<a id="ba-01--wss-authentication-and-session-termination"></a>
### BA-01 — WSS 驗證與工作階段終止
**追溯：** [REQ-01 帳戶驗證與登入識別](../testing/acceptance-matrix.md#req-01), [REQ-02 憑證更新與登出轉換](../testing/acceptance-matrix.md#req-02); [W01](../contracts/interface-contract.md#event-w01), [W02](../contracts/interface-contract.md#event-w02), [W17](../contracts/interface-contract.md#event-w17); [validateAccess](../contracts/interface-contract.md#internal-validate-access)。
- **前置條件：** 新的 WSS 連線。
**正常流程：** 一律先要求 [W01](../contracts/interface-contract.md#event-w01)；由 BB 驗證權杖與裝置綁定，並在同一次驗證結果中取得 BB 依已驗證主體／工作階段映射的公開 `user_id`（[C8，現行規格（2026-10-01 PM 決議）](../contracts/interface-contract.md#public-identity-handoff)）；以該公開身分／裝置／工作階段世代及心跳設定回覆 W02。不得退回使用 `subject_id`，也不得假設 JWT 含 `user_id` 宣告。
- **失敗流程：** 拒絕已過期、已撤銷、裝置錯誤或世代過期的工作階段；A03/A04 撤銷生效時停止新操作並關閉舊連線。關閉前可傳送 W17，但不保證送達。
- **驗收條件：** 絕不信任用戶端提供的 subject_id；更新憑證後須使用新連線完成驗證；單一裝置失效不撤銷其他裝置。缺少公開使用者映射時不得成功回覆 W02。
- **現行失效處理（C1–C4、E1、S1、S2；2026-10-01 PM 決議）：** 經 BB 的操作一律帶該連線工作階段綁定（C2）。只有可信 BB 回應明確為 `UNAUTHENTICATED` 且 `details.auth_layer:"user_session"` 才關閉該使用者連線；服務身分失敗、缺少分層或非 HINE 回覆均視為 `DEPENDENCY_UNAVAILABLE`，顯示服務暫時不可用並記錄，不登出／刷新使用者（C13）。新 W01 無可信驗證結果時不回 W02，回 W17 `DEPENDENCY_UNAVAILABLE` 後關閉未驗證連線；已驗證連線依[狀態表](../contracts/interface-contract.md#delivery-state-table)處理。
- A03、A04 與 A02 取代同帳號同裝置工作階段依 T1 同一交易寫入失效紀錄；提供 `readSessionInvalidations`。所有帶工作階段綁定操作依 T2／T4 在交易或快照內檢查工作階段；A03 只關舊世代，A04／A02 取代只關該工作階段。失效紀錄由通知、每 5 秒輪詢或遞送閘門補齊。
- **交付界線（E1／S1）：** `INVALIDATION_STALE_SECONDS=15`。套用撤權／工作階段撤銷即停止相符舊授權內容開始交付；最遲提交後 15 秒不得再開始交付，權杖先到期則更早停止。這是開始交付界線，不是網路抵達期限；單一 realtime 實例亦須符合，不宣稱跨區高可用。60 秒移除紀錄保留窗不是交付上限。W01 最後檢查與註冊須和套用失效互斥，涵蓋所有已知且位置較新的紀錄；連線最遲在權杖到期關閉。
- **補齊中斷（S2）：** 超過最近完整補齊開始後 15 秒即暫停資料交付，可保留連線及 W04／W17，最遲權杖到期關閉；恢復後先補齊權威狀態再恢復交付。單事件補齊等待 1000 毫秒，逾時放棄該次即時遞送、交既有同步補回。服務故障不得誤當帳密錯誤；不增加多實例容錯。
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
**正常流程：** W03/W04 用於追蹤連線存活。`HEARTBEAT_INTERVAL_SECONDS=30`、`HEARTBEAT_TIMEOUT_SECONDS=90`。`nonce` 必須是非空字串；W04 必須原樣回顯，且 correlation_id 必須對應同一連線上同一筆待回覆 W03。不得轉型；重複或過期 W04 不延長存活時間。
- **失敗流程：** 心跳逾時只清除該連線。Redis 無法使用時，在線狀態視為未知，不得斷定離線或在線。
**驗收條件：** 在線狀態描述彙總連線情形，絕不代表應用程式在前景或訊息已送達；本版設定未量測。
- **交接：** [BB-02](backend-b.md#bb-02) 在線狀態查詢；[FA-01](frontend-a.md#fa-01) 經唯一 WSS 接收 W18、[FB-04](frontend-b.md#fb-04) 顯示。

<a id="ba-03"></a>
<a id="ba-03--message-ingress-and-persisted-ack"></a>
### BA-03 — 訊息入口與持久化 ACK
**追溯：** [REQ-06 文字訊息與持久 ACK](../testing/acceptance-matrix.md#req-06), [REQ-07 ACK 遺失、重試與去重](../testing/acceptance-matrix.md#req-07); [W05](../contracts/interface-contract.md#event-w05), [W06](../contracts/interface-contract.md#event-w06), [W07](../contracts/interface-contract.md#event-w07), [W17](../contracts/interface-contract.md#event-w17); [authorize](../contracts/interface-contract.md#internal-authorize), [persistIfAbsent](../contracts/interface-contract.md#internal-persist-if-absent)。
- **前置條件：** 已驗證的主體、已授權的對話、有效訊息 C1。
**正常流程：** BA 驗 WSS envelope／required／基本型別及既有 connection/frame defense，再交 BB 依[六階段](../contracts/interface-contract.md#validation-precedence)做 canonical、認證／授權、C1、僅新合法 intent 的 5/s burst10 產品 quota、持久化；BA 不先判此產品 quota 或以 authorize 跳過 BB validation，不重現 canonical 計數。完整結果才回 W06，W07 路由至已授權收件者。
- **失敗流程：** BB 的 INVALID_ARGUMENT／IDEMPOTENCY_CONFLICT／RATE_LIMITED 由 BA 映射既有 W17、關聯原 W05；拒絕不回成功 W06。產品 quota 拒絕不持久化或建立 C1→M1，安全 retry_after_ms 依既有規則。回滾／結果不明／ACK 遺失與 Redis 發布復原規則不變。
- **驗收條件：** ACK 先有完整提交。quota exhausted 時，非法 payload（含同 C1）先 INVALID_ARGUMENT；不同合法 C1 payload 先 IDEMPOTENCY_CONFLICT；同 C1 相同合法 payload 回 existing_same／原 M1，不進 quota；只有新合法 intent 由 BB 可能回 RATE_LIMITED。
- **長度交接：** [JSON 解碼後 Unicode code points](../contracts/interface-contract.md#string-length-counting)是 BB canonical 單位，不是 BA 重現算法義務；BB 的 EntityID 前置拒絕及 text 拒絕均沿用 INVALID_ARGUMENT 映射。不 trim／normalization 或轉換原內容。
- **正式通知交接：** [publishCommitted](../contracts/interface-contract.md#committed-notice-validation) 只接受已驗服務身分的 BB；BB 發送前負責 canonical EntityID，BA 驗結構／required／null／型別／enum／UUID／source，結構錯誤仍 INVALID_ARGUMENT。合法結構通知不由 BA 重算 Unicode 長度，不因巢狀 EntityID >128 自行補判。
- **交接：** [BB-04](backend-b.md#bb-04) 持久化／收件者；[FA-03](frontend-a.md#fa-03) 重試／合併；[QA-04](qa.md#qa-04) 故障案例。

<a id="ba-04"></a>
<a id="ba-04--deliveryread-receipt-forwarding"></a>
### BA-04 — 送達／已讀回條轉送
**追溯：** [REQ-12 已送達／已讀回條狀態機](../testing/acceptance-matrix.md#req-12); [W08](../contracts/interface-contract.md#event-w08), [W09](../contracts/interface-contract.md#event-w09), [W10](../contracts/interface-contract.md#event-w10), [W19](../contracts/interface-contract.md#event-w19); [persistReceipt](../contracts/interface-contract.md#internal-persist-receipt)。
- **前置條件：** 已驗證的裝置與已授權的訊息收件者。
**正常流程：** 透過 BB 持久化單調回條；將 W19 與其 W08/W09 請求關聯；向允許的觀察者轉送一對一 W10，並支援事件流復原。一對一訊息的 W10 依 BB `persistReceipt` 回傳的正式訊息／`status`／`updated_at` 建構；recipient_id 取自 C8 信任的公開操作者身分、event_id 取自 `status_event_id`、收件者取自 C4 `observer_ids`。群組不發出 W10，不提供群組回條彙總；群組回條投影為 null，保留個別 W08／W09／W19 狀態。
- **失敗流程：** 拒絕偽造／不相關回條；重複回報不執行操作；`read` 不得倒退。
- **驗收條件：** W19 請求結果有別於 W10 投影；BB 為正式狀態的權威來源。
- **交接：** [BB-05](backend-b.md#bb-05) 權威回條；[FA-04](frontend-a.md#fa-04) 回條投影。

<a id="ba-05"></a>
<a id="ba-05--cross-node-fanout-and-group-event-routing"></a>
<a id="ba-05--跨節點散佈與群組事件路由"></a>
### BA-05 — 即時散佈（單一 realtime 實例）與群組事件路由
**追溯：** [REQ-05 群組管理、權限與成員變更](../testing/acceptance-matrix.md#req-05), [REQ-08 即時廣播與漏送復原（單一 realtime 實例）](../testing/acceptance-matrix.md#req-08), [REQ-11 撤權過濾、自身通知與多群組同步](../testing/acceptance-matrix.md#req-11); [A14](../contracts/interface-contract.md#api-a14), [A15](../contracts/interface-contract.md#api-a15), [A16](../contracts/interface-contract.md#api-a16), [A17](../contracts/interface-contract.md#api-a17), [A18](../contracts/interface-contract.md#api-a18); [W07](../contracts/interface-contract.md#event-w07), [W11](../contracts/interface-contract.md#event-w11), [W12](../contracts/interface-contract.md#event-w12), [W15](../contracts/interface-contract.md#event-w15), [W16](../contracts/interface-contract.md#event-w16), [W20](../contracts/interface-contract.md#event-w20)。
- **前置條件：** BB 已提交訊息或成員變更交易。
- **正常流程：** Redis Pub/Sub 加速將事件送至目前已授權的連線；保留各收件者專屬的事件識別。
- **失敗流程：** 發布遺失時透過 [W16](../contracts/interface-contract.md#event-w16) 修復。遞送時重新檢查授權；已撤權成員僅收到自己的最小化 [W12](../contracts/interface-contract.md#event-w12)，不得收到後續本文。
- **驗收條件：** 群組變更事件對應精確；不得將訊息代理中的暫態資料視為持久化成功。
**現行規格（C1–C4、E1；2026-10-01 PM 決議）：**
  - 收件者一律採用 BB 在提交交易內決定的清單（`persistIfAbsent` 的 `recipient_ids`、`persistReceipt` 的 `observer_ids`、BB 通知的 `deliveries`），不得以快取成員名單或 `authorize` 結果決定。
  - 遞送前若 `invalidation_position` 大於已套用位置，先補齊失效紀錄；無法補齊就放棄即時遞送，由同步補回。
  - 每個訊框開始交付時，再檢查連線狀態與節點新鮮狀態；套用工作階段撤銷時，丟棄連線佇列中尚未開始交付的訊框。群組撤權不清空整條連線佇列。
  - 單一 Redis Pub/Sub 由 BB 提交後經內部 HTTP／JSON 呼叫 `publishCommitted`，以 `notice_id` 去重；PostgreSQL 為準，Pub/Sub 遺失由 W15／W16 與失效紀錄輪詢補齊。不得提交前發事件。不採多實例／多節點廣播拓樸。
  - 群組舊授權內容採 E1 有界停止交付：套用撤權即停止開始交付，最遲撤權提交後 15 秒不得再開始；這不是抵達期限，且只驗收單一 realtime 實例。不得以 60 秒移除紀錄保留窗冒充交付上限（[AC-N26](../testing/acceptance-matrix.md#ac-n26)）。
  - 見[驗收 AC-N01、AC-N02、AC-N09、AC-N12～AC-N18](../testing/acceptance-matrix.md#ac-n01)。
- **交接：** [BB-03](backend-b.md#bb-03) 已提交的成員／事件流資料列；[FA-05](frontend-a.md#fa-05) 即時遞送與漏送復原（W15／W16）；[DO-01](devops.md#do-01) 路由。

<a id="ba-06"></a>
<a id="ba-06--bootstrap-and-feed-sync-ingress"></a>
### BA-06 — 初始化與事件流同步入口
**追溯：** [REQ-09 首次登入、已授權快照與歷史分離](../testing/acceptance-matrix.md#req-09), [REQ-10 快照切換與即時投影合併](../testing/acceptance-matrix.md#req-10), [REQ-11 撤權過濾、自身通知與多群組同步](../testing/acceptance-matrix.md#req-11); [W13](../contracts/interface-contract.md#event-w13), [W14](../contracts/interface-contract.md#event-w14), [W15](../contracts/interface-contract.md#event-w15), [W16](../contracts/interface-contract.md#event-w16), [W17](../contracts/interface-contract.md#event-w17); [readBootstrap](../contracts/interface-contract.md#internal-read-bootstrap), [readFeed](../contracts/interface-contract.md#internal-read-feed)。
- **前置條件：** 有效且已驗證的主體。
**正常流程：** [W13](../contracts/interface-contract.md#event-w13)/[W14](../contracts/interface-contract.md#event-w14) 代理一致性快照頁面；[W15](../contracts/interface-contract.md#event-w15)/[W16](../contracts/interface-contract.md#event-w16) 代理已固定安全邊界的事件流批次。W14 每頁最多 100 個邏輯項目；W16 每批最多回傳 100 個事件、每次請求最多掃描 1000 個事件流位置，到上限依游標續傳，不得把未掃完當同步完成。A19／W14／W16 每頁均須授權並套用同一加入界線。
- **失敗流程：** 使用者 SyncCursor 過期時回傳 [W17](../contracts/interface-contract.md#event-w17) SYNC_RESET_REQUIRED。[A08](../contracts/interface-contract.md#api-a08)/[A11](../contracts/interface-contract.md#api-a11)/[A19](../contracts/interface-contract.md#api-a19) 的 REST 游標錯誤不得觸發重設。快照未完整時，頁面序列不得宣稱起始游標已安裝。
- **驗收條件：** 隱藏位置可安全前進；未授權內容會被過濾；單一撤權對話不得阻塞其餘事件流。新成員只可讀本次加入之後訊息；加入界線依 A14／A16 加入交易記錄的當時最新 `order_key`（與 C11 排序一致），退出後重加入重新記錄。W14／W16 依同一界線過濾。
- **撤權與加入政策（2026-10-01 PM 決議）：** A19／W14／W16 每頁授權；撤權後新查詢不得取回該群組內容，W16 仍可保留最小自身 W12。套用 E1 撤權後不開始交付相符舊授權內容，不代用戶端推進游標，沿用授權過濾／重新讀取與錯誤恢復路徑，其他對話繼續同步（[AC-N26](../testing/acceptance-matrix.md#ac-n26)）。
- **交接：** [BB-06](backend-b.md#bb-06) 讀取／授權過濾資料列；[FA-05](frontend-a.md#fa-05) 游標提交／投影；[QA-03](qa.md#qa-03) 復原。

<a id="ba-07"></a>
<a id="ba-07--device-activity-leases"></a>
### BA-07 — 裝置活動租約
**追溯：** 本版範圍外（2026-10-01 PM 決議）；保留 REQ-14、W21／W22 與 `recordActivity`／`getDevicePresence` 介面識別以供追溯。
- **前置條件：** 本版範圍外（2026-10-01 PM 決議）。
- **正常流程：** 本版範圍外（2026-10-01 PM 決議）。不實作裝置活動租約、W21／W22 上報或 unknown 推播判斷；WSS 心跳、斷線重連及前端 Page Visibility 已讀判斷仍保留且互不混用。
- **失敗流程：** 本版範圍外（2026-10-01 PM 決議）。
- **驗收條件：** 本版範圍外（2026-10-01 PM 決議）。保留 BA-07 卡片及錨點。
- **交接：** 本版範圍外，無交接；連線生命週期與心跳由 [BA-01](#ba-01)／[BA-02](#ba-02) 及 [FA-01](frontend-a.md#fa-01) 負責，活動租約不交接至 FA-07／BB-08。

<a id="ba-08"></a>
<a id="ba-08--rate-limiting-frame-defense-and-wss-errors"></a>
### BA-08 — 速率限制、訊框防護與 WSS 錯誤
**追溯：** [REQ-16 統一錯誤與隱私保護](../testing/acceptance-matrix.md#req-16); [W17](../contracts/interface-contract.md#event-w17) 與本版限制（2026-10-01 PM 決議）。
- **前置條件：** 任意未驗證／已驗證訊框。
**正常流程（BA 服務端責任）：** 保留 WSS connection/frame abuse defense、envelope／required fields／基本型別、transport 與 W17 mapping。**transport/frame defense ≠ product W05 message-send quota**；原每使用者 5/s、burst 10 的產品 quota 唯一權威是 BB，BA 不在 BB canonical validation 前執行，也不另維護一套產品 quota。BA 將 BB RATE_LIMITED 映射 W17；可重試且有安全延遲才提供既有非負 retry_after_ms，否則省略、不猜 0。C13 user_session／service_identity 分層及原新連線／已驗證連線處理不變，BA 不替前端決定刷新／登出／重試。
- **前端消費規則（FA／FB 執行，BA 只確保錯誤可辨識）：** 依[共用錯誤復原規則](../contracts/interface-contract.md#error-recovery)：僅 UNAUTHENTICATED／已知權杖過期進入既有驗證更新流程；有效權杖斷線應重連並執行 W01/W02、再送 W15，不得盲目呼叫 A03。RATE_LIMITED 只限制失敗動作，依 retry_after_ms 規則；一般服務故障不套用認證重試。
- **失敗流程：** 為慢速消費者限制每個連線的輸出；連線中斷時不得宣稱錯誤已送達；絕不記錄權杖或本文。
- **驗收條件：** 不得捏造成功結果；速率限制為本版設定，未量測。
- **交接：** [FA-01](frontend-a.md#fa-01)／[FB-02](frontend-b.md#fb-02) 前端錯誤消費規則；[BB-01](backend-b.md#bb-01) 內部驗證錯誤分層；[QA-05](qa.md#qa-05) 錯誤／隱私驗收；[DO-04](devops.md#do-04) 維運設定與服務身分失敗告警。

## 決策與共用參照

- [響應式 Web 行為](../ui/web-rwd.md#web-rwd)
- [決策：Web Push 範圍](../decisions.md#decision-web-push)
- [決策：響應式 Web 版面](../decisions.md#decision-rwd)
- [返回文件導覽](../README.md)
