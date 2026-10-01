<a id="hine-ic-04--backend-b-角色-prd"></a>
# HINE-IC-0.4 — 後端 B 角色 PRD

**版本：** HINE-IC-0.4  
**狀態：** 現行規格（2026-10-01 PM 決議）
**來源：** [歷史來源：HINE-IC-0.4 角色 PRD](../HINE-IC-0.4-role-prds.md); 唯一現行介面規格依據為 [共同介面契約](../contracts/interface-contract.md).  
**角色目的：** 負責 REST API、帳戶／工作階段權威、PostgreSQL 正式狀態、物件中繼資料／GCS 授權及持久化事件流；推播意圖本版範圍外（BB-08 僅保留 ID）。本 PRD 規定未來行為與驗收要求，不代表已實作或已完成測試。
**必讀／串接時查閱：** [系統架構](../architecture/README.md)、[共同介面契約](../contracts/interface-contract.md)、[驗收矩陣](../testing/acceptance-matrix.md)；各功能串接見下方追溯／交接。 [返回文件導覽](../README.md)。

## 範圍

- **範圍內：** REST API、帳戶／工作階段權威、PostgreSQL 正式狀態、物件中繼資料／GCS 授權憑證及持久化事件流；以及下方角色專屬功能卡。
- **範圍外：** 推播意圖、推播權杖儲存與背景派送（本版範圍外，2026-10-01 PM 決議）；其他角色所負責的範圍。各後端負責人自選語言及內部實作，以內部 HTTP＋JSON 對接；不要求共用後端原始碼／型別／ORM。不得單方變更共同介面；依[共同變更流程](../../CONTRIBUTING.md#interface-changes)與受影響成員一起修改，先對齊[近期串接基線](../contracts/interface-contract.md#integration-baseline)，不要求一次鎖死整份規格。PostgreSQL 為主資料庫，Redis 僅供通知與在線狀態。
- **共用 Web 行為：** 遵循 [Web／RWD 規格](../ui/web-rwd.md#web-rwd)；不得另訂斷點或重複定義版面規則。

## 功能索引

- [BB-01 — 帳戶、工作階段與裝置識別](#bb-01)
- [BB-02 — 個人檔案與聯絡人](#bb-02)
- [BB-03 — 對話、群組與授權](#bb-03)
- [BB-04 — 交易式訊息、冪等性與持久化事件流](#bb-04)
- [BB-05 — 歷史紀錄與回條權威](#bb-05)
- [BB-06 — 快照與持久化使用者事件流](#bb-06)
- [BB-07 — 附件、頭像與簽署傳輸](#bb-07)
- [BB-08 — 推播權杖儲存與背景派送（本版範圍外）](#bb-08)

## 角色目的與責任界線

本版提供 [A01](../contracts/interface-contract.md#api-a01)–[A22](../contracts/interface-contract.md#api-a22)（A23–A25 僅保留 ID，本版範圍外）、帳戶／工作階段權威、PostgreSQL 正式狀態、物件中繼資料／GCS 授權憑證及持久化事件流。不負責用戶端連線，也不使用 Redis 儲存訊息；Redis 僅供通知與在線狀態。所有瀏覽器版面皆使用相同 REST 契約、模型、授權與持久化事件流；各模組可用不同語言，以內部 HTTP＋JSON 對接，不要求共用 backend/common 原始碼或 ORM。

<a id="bb-01"></a>
<a id="bb-01--accounts-session-and-device-identity"></a>
### BB-01 — 帳戶、工作階段與裝置識別
**追溯：** [REQ-01 帳戶驗證與登入識別](../testing/acceptance-matrix.md#req-01), [REQ-02 憑證更新與登出轉換](../testing/acceptance-matrix.md#req-02); [A01](../contracts/interface-contract.md#api-a01), [A02](../contracts/interface-contract.md#api-a02), [A03](../contracts/interface-contract.md#api-a03), [A04](../contracts/interface-contract.md#api-a04); [validateAccess](../contracts/interface-contract.md#internal-validate-access)。
- **前置條件：** 註冊／登入／更新憑證／登出請求。
**正常流程：** 妥善保存帳戶憑證；驗證 A02、綁定或核發伺服器核發的不透明 `device_id`，僅作裝置／本機資料分區識別、不可作登入憑證。相同帳號、同瀏覽器且本機 DeviceStore 尚在時重用；清除網站資料、遺失儲存或重新安裝後視為新裝置重新核發，不做指紋辨識／舊裝置找回。切換帳號須重新驗證並使用該帳號自己的綁定與儲存分區。每個瀏覽器設定檔同時一帳號、一個操作分頁，無裝置管理清單、遠端抹除或多帳號快速切換。A02／A03 回應以 `Set-Cookie` 設定／輪替 HttpOnly 更新憑證 Cookie；A03／A04 以瀏覽器附帶 Cookie 判定工作階段（[分工](../contracts/interface-contract.md#refresh-cookie-roles)）。`validateAccess` 同次驗證必須回傳必填且非 null 的公開 `user_id:EntityID`，由 BB 將已驗證主體／工作階段映射而得（C8，現行規格，2026-10-01 PM 決議），與 C1 `invalidation_position` 分離。BA 以公開 ID 建立 W02 及可信公開操作者／回條身分；不得退回 `subject_id` 或假設 JWT 含 `user_id` 宣告。
- **失敗流程：** 將更新憑證／登出競態序列化；過期／撤銷 Cookie 不得核發仍有效的連線工作階段。裝置 ID 本身不能用來驗證或跨綁定其他使用者。
- **驗收條件：** A05 `UserProfile.id` 僅等於目前 A02/A03 AccessSession 與 W02 的公開 `user_id`。嚴格比對相符 AccessSession 與 W02 的 `device_id`、`session_generation`；A05 無此二欄位。不得暴露 `subject_id`。DeviceID 依上述本機重用／重新核發規則；SessionContext 僅保留登入、授權、連線與同步必要欄位。C8 已是現行規格，見[公開身分交接](../contracts/interface-contract.md#public-identity-handoff)。
- **現行交易與工作階段規格（2026-10-01 PM 決議）：** A03、A04 與 A02 取代同帳號同裝置原有效工作階段（C5）依 T1 同一交易寫入 `SessionInvalidation`；提交成功後呼叫 `publishCommitted`，REST 結果只取決於提交；提供 `readSessionInvalidations`。A02 每次建立新的 `session_id`。所有帶工作階段綁定操作依 T2／T4 在交易或快照內檢查，撤銷後回 `UNAUTHENTICATED`（C2）。A03 舊 Cookie 寬限 0 秒；結果不明遵循 C6／FB 的復原流程（[AC-N23](../testing/acceptance-matrix.md#ac-n23)）：單次自動刷新、10 秒未確認／401／刷新失敗即停止 WSS 與自動刷新、清除本機可用認證並提示重新登入；不重播舊刷新、不跨分頁接班。RATE_LIMITED 依有效 `retry_after_ms` 最多再自動試一次，否則停下交由使用者手動操作。伺服器／網路錯誤不得冒充密碼錯誤。
- **內部呼叫身分（C13；2026-10-01 PM 決議）：** 內部 `UNAUTHENTICATED` 以可信 `details.auth_layer` 區分 `service_identity`／`user_session`；只有可信 user_session 失效才代表使用者工作階段無效。缺少分層或非 HINE 回覆由 BA 視為 `DEPENDENCY_UNAVAILABLE`，不新增公開錯誤碼。
- **登入速率限制（本版設定，未量測）：** 每帳號每分鐘 10 次、每來源 IP 每分鐘 60 次；拒絕依 `RATE_LIMITED`／`retry_after_ms` 契約回覆。
- **內部呼叫憑證：** Compose 私有網路內服務以維運注入、隨機產生的 bearer secret 驗證，Secret 參照 `INTERNAL_CALLER_TOKEN_SECRET_REF`，呼叫放入 `Authorization` 標頭；提供者依 `INTERNAL_ALLOWED_CALLERS` 比對呼叫者身分。憑證不得提交 Git 或記錄。
- **交接：** [FB-01](frontend-b.md#fb-01) AccessSession；[BA-01](backend-a.md#ba-01) 工作階段驗證；[QA-02](qa.md#qa-02) 工作階段、更新與登出狀態轉換案例。

<a id="bb-02"></a>
<a id="bb-02--profiles-and-contacts"></a>
### BB-02 — 個人檔案與聯絡人
**追溯：** [REQ-03 個人檔案、頭像與聯絡人](../testing/acceptance-matrix.md#req-03); [A05](../contracts/interface-contract.md#api-a05), [A06](../contracts/interface-contract.md#api-a06), [A07](../contracts/interface-contract.md#api-a07), [A08](../contracts/interface-contract.md#api-a08), [A09](../contracts/interface-contract.md#api-a09), [A10](../contracts/interface-contract.md#api-a10)。
- **前置條件：** 已驗證的呼叫者及相關使用者／聯絡人授權。
- **正常流程：** 維護自己的個人檔案／聯絡人，回傳不同的本人個人資料與公開摘要，並要求 A06 使用自己已就緒的頭像。A07 僅查詢已知 `user_id`；可用來源為使用者已知的公開 ID（含由 A02/A03/A05 取得自己的 ID）、有權讀取的 A08 摘要，或 A12 成員 ID。不得提供顯示名稱／電子郵件子字串目錄搜尋，也不得杜撰 `q` 參數（[已知 ID 查詢](../contracts/interface-contract.md#contact-id-lookup)）。
- **失敗流程：** 防止電子郵件或隱藏頭像資訊外洩；暫態在線狀態未知時回報未知；無效清單游標僅影響其 REST 查詢。
- **驗收條件：** 必填投影欄位／可為 null 性須符合共用字典；聯絡人重複不產生重複資料列；移除聯絡人不刪除對話資料。
- **交接：** [FB-03](frontend-b.md#fb-03)/[FB-04](frontend-b.md#fb-04) 個人檔案／聯絡人；[FA-06](frontend-a.md#fa-06) 摘要；[BA-02](backend-a.md#ba-02) 暫態在線狀態。

<a id="bb-03"></a>
<a id="bb-03--conversations-groups-and-authorization"></a>
### BB-03 — 對話、群組與授權
**追溯：** [REQ-04 一對一聊天導覽與建立](../testing/acceptance-matrix.md#req-04), [REQ-05 群組管理、權限與成員變更](../testing/acceptance-matrix.md#req-05), [REQ-11 撤權過濾、自身通知與多群組同步](../testing/acceptance-matrix.md#req-11); [A11](../contracts/interface-contract.md#api-a11), [A12](../contracts/interface-contract.md#api-a12), [A13](../contracts/interface-contract.md#api-a13), [A14](../contracts/interface-contract.md#api-a14), [A15](../contracts/interface-contract.md#api-a15), [A16](../contracts/interface-contract.md#api-a16), [A17](../contracts/interface-contract.md#api-a17), [A18](../contracts/interface-contract.md#api-a18); [W11](../contracts/interface-contract.md#event-w11), [W12](../contracts/interface-contract.md#event-w12), [W20](../contracts/interface-contract.md#event-w20); [authorize](../contracts/interface-contract.md#internal-authorize)。
- **前置條件：** 請求操作符合目前成員／管理員／自行離開政策；群組上限 50 人（含管理員），僅 `admin`／`member` 兩種角色，建立者為 admin。
- **正常流程：** 讀取一對一／群組投影；建立唯一一對一對話；以交易處理成員、標題、角色及必要事件流更新。管理員依既有 API 加入／移除成員及調整角色；新成員只可讀加入後訊息。A14／A16 加入交易記錄加入界線：當時最新 `order_key`，按 C11 `(order_key,message_id)` 排序判斷；退出後重加入建立新界線。
- **失敗流程：** 拒絕未授權操作；只允許 admin／member，不得自訂角色；禁止移除、降級或退出最後一位 admin，需先指定其他管理員（沿用 `CONFLICT`）。A14 `member_ids`（含建立者）超過 50 回 `INVALID_ARGUMENT`；A16 群組已滿回 `CONFLICT`。在歷史／下載及後續事件流套用移除後授權；不設封鎖狀態／操作。
- **驗收條件：** [A14](../contracts/interface-contract.md#api-a14)/[A16](../contracts/interface-contract.md#api-a16) 發出 [W11](../contracts/interface-contract.md#event-w11)，[A15](../contracts/interface-contract.md#api-a15)/[A17](../contracts/interface-contract.md#api-a17) 發出 [W20](../contracts/interface-contract.md#event-w20)，[A18](../contracts/interface-contract.md#api-a18) 發出 [W12](../contracts/interface-contract.md#event-w12)。成員版本與 REST 回應須對應已提交狀態；事件流變更須先於 Pub/Sub 提交。A19／W14／W16／A22（附件所屬訊息）及 C14 未讀計算皆使用同一加入界線。
- **現行規格（2026-10-01 PM 決議）：** A14–A18 沿用 T3 與提交後 `publishCommitted`，通知失敗不改 REST 結果。群組待送舊內容採 E1；套用撤權即停止開始交付，最遲提交後 15 秒不得再開始交付（不是抵達期限），單一 realtime 實例驗收。撤權後新查詢不得取回內容；每頁授權，W16 保留最小自身 W12。見 [AC-N02](../testing/acceptance-matrix.md#ac-n02)、[AC-N18](../testing/acceptance-matrix.md#ac-n18)、[AC-N26](../testing/acceptance-matrix.md#ac-n26)。
- **交接：** [FB-05](frontend-b.md#fb-05) REST 投影；[BA-05](backend-a.md#ba-05)/[FA-05](frontend-a.md#fa-05) 已提交事件；與 PM 討論政策決策。

<a id="bb-04--交易式訊息冪等性與持久化推播意圖"></a>
<a id="bb-04"></a>
<a id="bb-04--transactional-messages-idempotency-and-durable-push-intent"></a>
### BB-04 — 交易式訊息、冪等性與持久化事件流
**追溯：** [REQ-06 文字訊息與持久 ACK](../testing/acceptance-matrix.md#req-06), [REQ-07 ACK 遺失、重試與去重](../testing/acceptance-matrix.md#req-07), [REQ-08 即時廣播與漏送復原（單一 realtime 實例）](../testing/acceptance-matrix.md#req-08), [REQ-14 裝置活動與背景推播（本版範圍外，僅保留追溯）](../testing/acceptance-matrix.md#req-14); [W05](../contracts/interface-contract.md#event-w05), [W06](../contracts/interface-contract.md#event-w06), [W07](../contracts/interface-contract.md#event-w07); [authorize](../contracts/interface-contract.md#internal-authorize), [persistIfAbsent](../contracts/interface-contract.md#internal-persist-if-absent)。
- **前置條件：** 已授權的傳送者、訊息格式、穩定 C1。
**正常流程：** 接收 EntityID 的後端操作以固定上限 128 做權威驗證，超長依既有契約回 INVALID_ARGUMENT；EntityID 對消費端仍是 opaque string。BB 在 `persistIfAbsent` 持久化前完成 text 的最終權威長度驗證：非空且有效範圍 1～4096，不以前端 UX 或 BA 結構檢查通過作免驗證依據。合法且已授權時，以交易寫入正式訊息、C1 對應及每位使用者所有必要事件流資料列；傳回 `created` 或 `existing_same` 與持久化結果。每使用者送訊息每秒 5 則、突發 10 則（本版設定，未量測）。不建立推播意圖（本版範圍外，2026-10-01 PM 決議）。
- **失敗流程：** text 空字串或超過 4096 時回 INVALID_ARGUMENT，不持久化訊息、C1 對應或事件流，不回成功持久化結果；BA 映射 W17 INVALID_ARGUMENT，不回成功 W06。同一 C1 配上不同承載資料時為衝突；區分已知回滾與結果不明；必要資料列提交前絕不寫入成功 ACK 證據。
- **驗收條件：** 重試傳送會產生相同 M1 與穩定事件 ID；通知經提交後 publish；不含推播供應商派送。
- **責任與內容：** Canonical validation 由後端負責，不要求消費端或不同語言重現相同計數算法；首輪只以 ASCII 邊界驗收。不自動 trim、Unicode normalization 或改變原訊息內容，詳見[共同責任](../contracts/interface-contract.md#string-length-counting)。
- **現行規格（C3；2026-10-01 PM 決議）：** `persistIfAbsent` 依 T2 鎖定工作階段列與群組對話列，在交易內計算 `recipient_ids`，並回傳 `invalidation_position` 與 `membership_version`。
- **交接：** [BA-03](backend-a.md#ba-03) 交易結果；[FA-03](frontend-a.md#fa-03) C1 合併；[QA-04](qa.md#qa-04) 故障結果。

<a id="bb-05"></a>
<a id="bb-05--history-and-receipt-authority"></a>
### BB-05 — 歷史紀錄與回條權威
**追溯：** [REQ-09 首次登入、已授權快照與歷史分離](../testing/acceptance-matrix.md#req-09), [REQ-12 已送達／已讀回條狀態機](../testing/acceptance-matrix.md#req-12); [A19](../contracts/interface-contract.md#api-a19); [W08](../contracts/interface-contract.md#event-w08), [W09](../contracts/interface-contract.md#event-w09), [W10](../contracts/interface-contract.md#event-w10), [W19](../contracts/interface-contract.md#event-w19); [persistReceipt](../contracts/interface-contract.md#internal-persist-receipt)。
- **前置條件：** 目前具備讀取訊息／歷史或回報回條的權限。
**正常流程：** 以獨立歷史游標查詢歷史，單調持久化送達／已讀狀態，並將舊訊息狀態修正納入事件流／初始化投影。A19 的 `order_key` 固定 20 位 ASCII 數字字串，搭配 UUID 作次排序，按同一規則比較、不轉成浮點數；A19 依反向元組排序。REST 分頁預設 20、最大 50；首頁省略 cursor／before，後續使用伺服器回傳游標（C11／C12，現行規格，2026-10-01 PM 決議）。
- **失敗流程：** A19 游標錯誤僅影響該歷史檢視；失去授權即禁止後續內容。重複回條不產生多餘狀態事件。
- **驗收條件：** 同一正式訊息 ID 出現在即時訊息、歷史紀錄與同步中；A19 順序獨立於使用者事件流游標。`MessageView.receipt` 與 `AttachmentView.conversation_id` 均為必填且可為 null；判別欄位依共用規則。
- **現行回條規格（C4、C14-S；2026-10-01 PM 決議）：** `persistReceipt` 依 T2 檢查工作階段，回傳 W10 的 `observer_ids`、`invalidation_position` 與 `membership_version`。一對一 W10 依正式訊息／`status`／`updated_at` 建構，recipient_id 取 C8 可信公開操作者，event_id 取 `status_event_id`。群組 `MessageView.receipt`／`MessageSnapshot.receipt` 為 null，不發群組 W10，不提供群組彙總；保留逐收件者狀態與個別 W08／W09／W19。
- **未讀（C14-S）：** A11／A12／W14 `unread_count` 由 BB 計算，按使用者計他人所發、目前可讀且尚未 `read` 的訊息，含加入界線；逐訊息已讀。徽章只用伺服器最近一次查詢值，不維護本機加／減集合，不新增跨裝置未讀事件、不擴充群組 W10；本機或其他裝置讀取在下一次成功查詢反映，允許短暫舊值。
- **交接：** [FA-04](frontend-a.md#fa-04) 訊息／回條投影；[BA-04](backend-a.md#ba-04) 轉送；[FB-05](frontend-b.md#fb-05) 聊天清單 `unread_count`。

<a id="bb-06"></a>
<a id="bb-06--snapshot-and-durable-user-feed"></a>
### BB-06 — 快照與持久化使用者事件流
**追溯：** [REQ-09 首次登入、已授權快照與歷史分離](../testing/acceptance-matrix.md#req-09), [REQ-10 快照切換與即時投影合併](../testing/acceptance-matrix.md#req-10), [REQ-11 撤權過濾、自身通知與多群組同步](../testing/acceptance-matrix.md#req-11); [W13](../contracts/interface-contract.md#event-w13), [W14](../contracts/interface-contract.md#event-w14), [W15](../contracts/interface-contract.md#event-w15), [W16](../contracts/interface-contract.md#event-w16); [readBootstrap](../contracts/interface-contract.md#internal-read-bootstrap), [readFeed](../contracts/interface-contract.md#internal-read-feed)。
- **前置條件：** 已驗證的主體與支援的快照／事件流游標。
**正常流程：** 由同一一致性檢視讀取已授權快照與 H；在同一快照 id 內分頁，並依安全提交順序掃描具固定續傳邊界的每使用者事件流。REST 游標各自獨立；A08/A11 首頁省略游標，A19 首頁省略 `before`（不可傳空字串或 `"null"`）；後續請求 URL-encode 並回傳 `meta.next_cursor`，null 表示結束。`limit` 為可省略 HTTP 十進位正整數，預設 20、最大 50；無效輸入使用 INVALID_ARGUMENT。A19 使用固定排序元組比較。W14 每頁最多 100 個邏輯項目；W16 每批最多回傳 100 個事件、每次請求最多掃描 1000 個事件流位置，到上限依游標續傳，未掃完不得當同步完成。
- **失敗流程：** 快照過期時建立新的、一致的快照；所有頁面與本機切換完成前不得安裝 H。過濾已撤權本文，同時允許安全前進及其他對話資料列。A19／W14／W16 每頁檢查授權並套用加入界線；撤權後新查詢不得取回群組內容，W16 可保留最小自身 W12。加入界線由 A14／A16 加入交易記錄的當時最新 `order_key`，退出重加入重新記錄；A19、W14、W16、附件授權及 C14 未讀計算一致使用該界線。
- **驗收條件：** 完成的快照代表約定範圍及 H 時點狀態；後續持久化事件流可經 W16 取得，較舊授權歷史可經 A19 取得。REST 游標錯誤不得重設事件流；不完整掃描不得宣稱同步完成。排序與分頁為現行規格（C11／C12，2026-10-01 PM 決議）。
- **交接：** [BA-06](backend-a.md#ba-06) 同步讀取；[FA-05](frontend-a.md#fa-05) 游標套用；[QA-03](qa.md#qa-03) 復原。

<a id="bb-07"></a>
<a id="bb-07--attachments-avatars-and-signed-transfer"></a>
### BB-07 — 附件、頭像與簽署傳輸
**追溯：** [REQ-03 個人檔案、頭像與聯絡人](../testing/acceptance-matrix.md#req-03), [REQ-13 圖片、檔案與上傳更新](../testing/acceptance-matrix.md#req-13); [A06](../contracts/interface-contract.md#api-a06), [A20](../contracts/interface-contract.md#api-a20), [A21](../contracts/interface-contract.md#api-a21), [A22](../contracts/interface-contract.md#api-a22), [A25](../contracts/interface-contract.md#api-a25)。
- **前置條件：** 擁有者與有效範圍；適用時須有對話授權。
- **正常流程：** 儲存中繼資料、建立短效 GCS 上傳／下載授權，完成時驗證位元組與雜湊，僅允許就緒附件使用。僅支援 JPEG／PNG／PDF，≤10,485,760 bytes（10 MiB），檔名 1–255 Unicode 字元；伺服器產生物件鍵，副檔名與 MIME 不作唯一核驗。PDF 以下載附件呈現，不內嵌預覽；不做影片、音訊、執行檔、SVG／HTML、分塊續傳。
- **現行 C9／C10 規格（2026-10-01 PM 決議）：** A22 DownloadGrant 必填 `filename:string`、`size_bytes:int>0`；收件者取得 `attachment_id` 後仍須經對話授權檢查。每次上傳嘗試使用獨立、不重用的物件鍵及僅建立前置條件；A21 核驗並綁定已核驗世代，A22 只簽該版本，不取最新版本。上傳授權有效 10 分鐘、下載授權 5 分鐘；上傳過期以 A20 新建嘗試，不做 A25 續期（A25 本版範圍外）。下載網址到期經 A22 重新授權；已核發網址到期前可能仍可用，不宣稱撤權可立即追回。
- 單次 PUT 傳原始 File／Blob 位元組（非 multipart／JSON／base64），完整帶上應用程式設定的必填標頭（含相符 Content-Type）；Host／Content-Length 由瀏覽器管理；不得附 HINE JWT／Cookie。HTTP 200 僅代表位元組已儲存；W05／A06 前仍須 A21 回 200 就緒。回應遺失視為結果不明，以同嘗試 A21 對帳或沿既有流程重送同位元組；供應商失敗不映射成 W17 UNAUTHENTICATED。CORS 須允許 PUT／GET 及簽署所需標頭。
- **失敗流程：** 舊嘗試、核驗內容／版本不符依既有 CONFLICT 拒絕，未上傳完成用 UPLOAD_NOT_READY；查詢依賴失敗不回成功。GCS 412 只代表僅建立條件未成立，不能直接標就緒或刪物件後覆寫。已核驗版本不可取得／中繼資料版本不符時 A22 回 DEPENDENCY_UNAVAILABLE，不偷偷改綁／交付另一版。頭像仍明確 conversation_id:null。
- **驗收條件：** A22 每次讀取均重新授權；簽署網址與 GCS 物件鍵（object_key）均為私有；上傳失敗不得變成就緒。
- **交接：** [FA-06](frontend-a.md#fa-06)/[FB-03](frontend-b.md#fb-03) 傳輸與中繼資料；[DO-02](devops.md#do-02) 儲存桶／機密。

<a id="bb-08"></a>
<a id="bb-08--push-token-store-and-background-dispatch"></a>
### BB-08 — 推播權杖儲存與背景派送
**追溯：** 本版範圍外（2026-10-01 PM 決議）；保留 REQ-14、A23／A24、W21／W22、`getDevicePresence` 與 `dispatchPushIntent` 識別以供追溯。
- **前置條件：** 本版範圍外（2026-10-01 PM 決議）。
- **正常流程：** 本版範圍外（2026-10-01 PM 決議）。不儲存推播權杖、不建立推播意圖／派送程序，亦不整合 Web Push、FCM 或 APNs；缺少推播憑證不影響核心服務就緒。保留 BB-08 卡片及錨點。
- **失敗流程：** 本版範圍外（2026-10-01 PM 決議）。
- **驗收條件：** 本版範圍外（2026-10-01 PM 決議）。開啟網頁時仍保留 WSS 即時訊息、聊天內提示與查詢後更新未讀；關閉網頁後不保證通知。
- **交接：** 推播儲存／派送不交接至 FA／BA（本版範圍外）。

## 決策與共用參照

- [響應式 Web 行為](../ui/web-rwd.md#web-rwd)
- [決策：Web Push 範圍](../decisions.md#decision-web-push)；Web Push 與 iOS／Android 原生推播均為本版範圍外（2026-10-01 PM 決議），A23／A24 僅保留 ID。
- [決策：響應式 Web 版面](../decisions.md#decision-rwd)
- [返回文件導覽](../README.md)
