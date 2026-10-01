<a id="hine-ic-04--backend-b-角色-prd"></a>
# HINE-IC-0.4 — 後端 B 角色 PRD

**版本：** HINE-IC-0.4  
**狀態：** 待產品核准  
**來源：** [歷史來源：HINE-IC-0.4 角色 PRD](../HINE-IC-0.4-role-prds.md); 唯一現行介面規格依據為 [共同介面契約](../contracts/interface-contract.md).  
**角色目的：** 負責 REST API、帳戶／工作階段權威、PostgreSQL 正式狀態、物件中繼資料／GCS 授權、持久化事件流與推播意圖。本 PRD 規定未來行為與驗收要求，不代表已實作或已完成測試。
**必讀／串接時查閱：** [系統架構](../architecture/README.md)、[共同介面契約](../contracts/interface-contract.md)、[驗收矩陣](../testing/acceptance-matrix.md)；各功能串接見下方追溯／交接。 [返回文件導覽](../README.md)。

## 範圍

- **範圍內：** REST API、帳戶／工作階段權威、PostgreSQL 正式狀態、物件中繼資料／GCS 授權憑證、持久化事件流與推播意圖；以及下方角色專屬功能卡。
- **範圍外：** 其他角色所負責的範圍；亦不得變更共用 API／事件 ID、正式資料、ACK、游標或同步語意。共用欄位型別、封套、錯誤與限制均以共同介面契約為準。
- **共用 Web 行為：** 遵循 [Web／RWD 規格](../ui/web-rwd.md#web-rwd)；不得另訂斷點或重複定義版面規則。

## 功能索引

- [BB-01 — 帳戶、工作階段與裝置識別](#bb-01)
- [BB-02 — 個人檔案與聯絡人](#bb-02)
- [BB-03 — 對話、群組與授權](#bb-03)
- [BB-04 — 交易式訊息、冪等性與持久化推播意圖](#bb-04)
- [BB-05 — 歷史紀錄與回條權威](#bb-05)
- [BB-06 — 快照與持久化使用者事件流](#bb-06)
- [BB-07 — 附件、頭像與簽署傳輸](#bb-07)
- [BB-08 — Push 權杖儲存與背景派送](#bb-08)

## 角色目的與責任界線

[A01](../contracts/interface-contract.md#api-a01)–[A25](../contracts/interface-contract.md#api-a25)、帳戶／工作階段權威、PostgreSQL 正式狀態、物件中繼資料／GCS 授權憑證、持久化事件流與推播意圖。不負責用戶端連線，也不使用 Redis 儲存訊息。所有瀏覽器版面皆使用相同 REST 契約、模型、授權與持久化事件流；不得依裝置形式重複建立業務 API。

<a id="bb-01"></a>
<a id="bb-01--accounts-session-and-device-identity"></a>
### BB-01 — 帳戶、工作階段與裝置識別
**追溯：** [REQ-01 帳戶驗證與登入識別](../testing/acceptance-matrix.md#req-01), [REQ-02 憑證更新與登出轉換](../testing/acceptance-matrix.md#req-02); [A01](../contracts/interface-contract.md#api-a01), [A02](../contracts/interface-contract.md#api-a02), [A03](../contracts/interface-contract.md#api-a03), [A04](../contracts/interface-contract.md#api-a04); [validateAccess](../contracts/interface-contract.md#internal-validate-access)。
- **前置條件：** 註冊／登入／更新憑證／登出請求。
**正常流程：** 妥善保存帳戶憑證；驗證 A02、綁定或核發 device_id，並簽發 AccessSession；A02／A03 回應以 `Set-Cookie` 設定／輪替 HttpOnly 更新憑證 Cookie，A03／A04 以瀏覽器附帶的 Cookie 判定工作階段（[分工](../contracts/interface-contract.md#refresh-cookie-roles)）。`validateAccess` 必須在同一次驗證中回傳必填且非 null 的公開 `user_id:EntityID`，由 BB 將已驗證主體／工作階段映射而得；此 C8 提案與 C1 `invalidation_position` 分離。BA 以公開 ID 建立 W02 及可信任的公開操作者／回條身分。不得退回使用 `subject_id` 或假設 JWT 含 `user_id` 宣告；缺少映射不得成功回覆 W02。A03 推進工作階段世代；A04 撤銷目前裝置／工作階段。
- **失敗流程：** 將更新憑證／登出競態序列化；過期／撤銷的 Cookie 不得核發仍有效的連線工作階段。裝置 ID 本身不能用來驗證或跨綁定其他使用者。
- **驗收條件：** A05 `UserProfile.id` 僅等於目前 A02/A03 AccessSession 與 W02 的公開 `user_id`。嚴格比對相符 AccessSession 與 W02 的 `device_id`、`session_generation`；A05 無此二欄位。不得暴露 `subject_id`。見 [C8 公開身分交接](../contracts/interface-contract.md#public-identity-handoff)，待批准。
- **候選（待批准）：** A03、A04，以及 A02 取代同帳號同裝置原有的有效工作階段（[C5](../contracts/interface-contract.md#internal-change-requests)，行為變更），都依 [T1](../contracts/interface-contract.md#internal-transaction-order) 在同一交易寫入 [SessionInvalidation](../contracts/interface-contract.md#internal-session-invalidation)。
  - 提交成功後呼叫 `publishCommitted`：回應前單次嘗試或回應後非同步，依執行環境而定。REST 結果只取決於提交。
  - 提供 [`readSessionInvalidations`](../contracts/interface-contract.md#internal-read-session-invalidations)。
  - A02 每次建立新的 `session_id`。
  - 所有帶工作階段綁定的操作都依 T2／T4，在交易或快照內檢查工作階段，撤銷後回 `UNAUTHENTICATED`（[C2](../contracts/interface-contract.md#internal-change-requests)）。
  - A03 舊 Cookie 無寬限（0 秒）；結果不明與 FB 共用 [C6](../contracts/interface-contract.md#refresh-recovery-policy)／[N23 復原流程](frontend-b.md#fb-refresh-recovery)，不另選接受舊 Cookie 的分支，見 [AC-N23](../testing/acceptance-matrix.md#ac-n23)。
- **候選（待批准）：** 內部操作回 `UNAUTHENTICATED` 時依 [C13](../contracts/interface-contract.md#internal-auth-layer) 在 `details.auth_layer` 標示 `service_identity` 或 `user_session`，不新增公開錯誤碼；其他錯誤碼不帶此欄位，語義不變。
- **交接：** [FB-01](frontend-b.md#fb-01) AccessSession；[BA-01](backend-a.md#ba-01) 工作階段驗證；[QA-02](qa.md#qa-02) 工作階段、更新與登出狀態轉換案例。

<a id="bb-02"></a>
<a id="bb-02--profiles-and-contacts"></a>
### BB-02 — 個人檔案與聯絡人
**追溯：** [REQ-03 個人檔案、頭像與聯絡人](../testing/acceptance-matrix.md#req-03); [A05](../contracts/interface-contract.md#api-a05), [A06](../contracts/interface-contract.md#api-a06), [A07](../contracts/interface-contract.md#api-a07), [A08](../contracts/interface-contract.md#api-a08), [A09](../contracts/interface-contract.md#api-a09), [A10](../contracts/interface-contract.md#api-a10)。
- **前置條件：** 已驗證的呼叫者及相關使用者／聯絡人授權。
- **正常流程：** 維護自己的個人檔案／聯絡人，回傳不同的本人個人資料與公開摘要，並要求 A06 使用自己已就緒的頭像。A07 僅查詢已知 `user_id`；可用來源為使用者已知的公開 ID（含由 A02/A03/A05 取得自己的 ID）、有權讀取的 A08 摘要，或 A12 成員 ID。不得提供顯示名稱／電子郵件子字串目錄搜尋，也不得杜撰 `q` 參數（[已知 ID 查詢](../contracts/interface-contract.md#contact-id-lookup)，待批准）。
- **失敗流程：** 防止電子郵件或隱藏頭像資訊外洩；暫態在線狀態未知時回報未知；無效清單游標僅影響其 REST 查詢。
- **驗收條件：** 必填投影欄位／可為 null 性須符合共用字典；聯絡人重複不產生重複資料列；移除聯絡人不刪除對話資料。
- **交接：** [FB-03](frontend-b.md#fb-03)/[FB-04](frontend-b.md#fb-04) 個人檔案／聯絡人；[FA-06](frontend-a.md#fa-06) 摘要；[BA-02](backend-a.md#ba-02) 暫態在線狀態。

<a id="bb-03"></a>
<a id="bb-03--conversations-groups-and-authorization"></a>
### BB-03 — 對話、群組與授權
**追溯：** [REQ-04 一對一聊天導覽與建立](../testing/acceptance-matrix.md#req-04), [REQ-05 群組管理、權限與成員變更](../testing/acceptance-matrix.md#req-05), [REQ-11 撤權過濾、自身通知與多群組同步](../testing/acceptance-matrix.md#req-11); [A11](../contracts/interface-contract.md#api-a11), [A12](../contracts/interface-contract.md#api-a12), [A13](../contracts/interface-contract.md#api-a13), [A14](../contracts/interface-contract.md#api-a14), [A15](../contracts/interface-contract.md#api-a15), [A16](../contracts/interface-contract.md#api-a16), [A17](../contracts/interface-contract.md#api-a17), [A18](../contracts/interface-contract.md#api-a18); [W11](../contracts/interface-contract.md#event-w11), [W12](../contracts/interface-contract.md#event-w12), [W20](../contracts/interface-contract.md#event-w20); [authorize](../contracts/interface-contract.md#internal-authorize)。
- **前置條件：** 請求操作符合目前成員／管理員／自行離開政策。
- **正常流程：** 讀取一對一／群組投影；建立唯一一對一對話；以交易處理成員、標題、角色及必要事件流更新。
- **失敗流程：** 拒絕未授權操作、保護最後一位管理員不變條件、在歷史／下載及後續事件流套用移除後授權。不設封鎖狀態／操作。
- **驗收條件：** [A14](../contracts/interface-contract.md#api-a14)/[A16](../contracts/interface-contract.md#api-a16) 發出 [W11](../contracts/interface-contract.md#event-w11)，[A15](../contracts/interface-contract.md#api-a15)/[A17](../contracts/interface-contract.md#api-a17) 發出 [W20](../contracts/interface-contract.md#event-w20)，[A18](../contracts/interface-contract.md#api-a18) 發出 [W12](../contracts/interface-contract.md#event-w12)。成員版本與 REST 回應須對應已提交狀態；事件流變更須先於 Pub/Sub 提交。
- **候選（待批准）：** A14–A18 沿用 [T3](../contracts/interface-contract.md#internal-transaction-order) 與提交後 [`publishCommitted`](../contracts/interface-contract.md#internal-publish-committed)，通知失敗不改 REST 結果。群組政策拆為[裝置已取得／服務端待送／撤權後新查詢](../contracts/interface-contract.md#group-revocation-policy)；待送內容主要推薦既有 [E1](../contracts/interface-contract.md#group-revocation-e1)，不把 60 秒保留窗當交付上限。見 [AC-N02](../testing/acceptance-matrix.md#ac-n02)、[AC-N18](../testing/acceptance-matrix.md#ac-n18)、[AC-N26](../testing/acceptance-matrix.md#ac-n26)。
- **交接：** [FB-05](frontend-b.md#fb-05) REST 投影；[BA-05](backend-a.md#ba-05)/[FA-05](frontend-a.md#fa-05) 已提交事件；與 PM 討論政策決策。

<a id="bb-04"></a>
<a id="bb-04--transactional-messages-idempotency-and-durable-push-intent"></a>
### BB-04 — 交易式訊息、冪等性與持久化推播意圖
**追溯：** [REQ-06 文字訊息與持久 ACK](../testing/acceptance-matrix.md#req-06), [REQ-07 ACK 遺失、重試與去重](../testing/acceptance-matrix.md#req-07), [REQ-08 跨節點即時廣播與漏送復原](../testing/acceptance-matrix.md#req-08), [REQ-14 裝置活動與背景推播](../testing/acceptance-matrix.md#req-14); [W05](../contracts/interface-contract.md#event-w05), [W06](../contracts/interface-contract.md#event-w06), [W07](../contracts/interface-contract.md#event-w07); [authorize](../contracts/interface-contract.md#internal-authorize), [persistIfAbsent](../contracts/interface-contract.md#internal-persist-if-absent), [dispatchPushIntent](../contracts/interface-contract.md#internal-dispatch-push-intent)。
- **前置條件：** 已授權的傳送者、訊息格式、穩定 C1。
- **正常流程：** 以交易寫入正式訊息、C1 對應、每位使用者所有必要事件流資料列及符合條件的各裝置推播意圖。傳回 `created` 或 `existing_same` 與持久化結果。
- **失敗流程：** 同一 C1 配上不同承載資料時為衝突；區分已知回滾與結果不明；必要資料列提交前絕不寫入成功 ACK 證據。
- **驗收條件：** 重試傳送會產生相同 M1 與穩定事件 ID；推播供應商失敗不得改變訊息／回條狀態。
- **候選（待批准）：** `persistIfAbsent` 依 [T2](../contracts/interface-contract.md#internal-transaction-order) 鎖定工作階段列與群組對話列，在交易內計算 `recipient_ids`，並回傳 `invalidation_position` 與 `membership_version`（[C3](../contracts/interface-contract.md#internal-change-requests)）。
- **交接：** [BA-03](backend-a.md#ba-03) 交易結果；[FA-03](frontend-a.md#fa-03) C1 合併；[QA-04](qa.md#qa-04) 故障結果。

<a id="bb-05"></a>
<a id="bb-05--history-and-receipt-authority"></a>
### BB-05 — 歷史紀錄與回條權威
**追溯：** [REQ-09 首次登入、已授權快照與歷史分離](../testing/acceptance-matrix.md#req-09), [REQ-12 已送達／已讀回條狀態機](../testing/acceptance-matrix.md#req-12); [A19](../contracts/interface-contract.md#api-a19); [W08](../contracts/interface-contract.md#event-w08), [W09](../contracts/interface-contract.md#event-w09), [W10](../contracts/interface-contract.md#event-w10), [W19](../contracts/interface-contract.md#event-w19); [persistReceipt](../contracts/interface-contract.md#internal-persist-receipt)。
- **前置條件：** 目前具備讀取訊息／歷史或回報回條的權限。
- **正常流程：** 以獨立歷史游標查詢歷史，單調持久化送達／已讀狀態，並將舊訊息狀態修正納入事件流／初始化投影。A19 的 `order_key` 候選格式為固定 20 位 ASCII 正十進位數（相容正 64 位元有號整數）；比較採 `(order_key, UUID hex bytes)` 遞增元組，A19 依反向元組排序。用戶端不得以 Number 或語系排序。此格式及 REST 分頁預設／上限皆為待批准選擇（[排序／分頁](../contracts/interface-contract.md#ordering-pagination)、[REST 分頁](../contracts/interface-contract.md#rest-pagination)）。
- **失敗流程：** A19 游標錯誤僅影響該歷史檢視；失去授權即禁止後續內容。重複回條不產生多餘狀態事件。
- **驗收條件：** 同一正式訊息 ID 出現在即時訊息、歷史紀錄與同步中；A19 順序獨立於使用者事件流游標。必填、可省略、可為 null 各自獨立；`MessageView.receipt` 與 `AttachmentView.conversation_id` 均為必填且可為 null，判別欄位規則不一概要求非 null（[既有矛盾修正](../contracts/interface-contract.md#field-presence)，不是新增政策批准）。
- **候選（待批准）：** `persistReceipt` 依 T2 檢查工作階段，並回傳 W10 的 `observer_ids`、`invalidation_position` 與 `membership_version`（C4）。一對一 W10 以正式訊息／`status`／`updated_at` 建構，recipient_id 取自 C8 可信任的公開操作者，event_id 取自 `status_event_id`。群組的 `MessageView.receipt` 為 null，不得捏造 W10 彙總／計數。BB 儲存逐收件者狀態；群組彙總須待批准彙總／可見性政策並完成 BB→BA 承載資料契約才能提供（[回條投影交接](../contracts/interface-contract.md#receipt-projection-handoff)，待批准）。
- **候選（待批准）：** A11／A12／W14 的 `unread_count` 依 [C14](../contracts/interface-contract.md#unread-count) 由 BB 計算：呼叫者使用者、排除自己所發、只依已提交 `read`，跨裝置共用；不影響群組彙總的待決狀態。
- **交接：** [FA-04](frontend-a.md#fa-04) 訊息／回條投影；[BA-04](backend-a.md#ba-04) 轉送；[FB-05](frontend-b.md#fb-05) 聊天清單 `unread_count`。

<a id="bb-06"></a>
<a id="bb-06--snapshot-and-durable-user-feed"></a>
### BB-06 — 快照與持久化使用者事件流
**追溯：** [REQ-09 首次登入、已授權快照與歷史分離](../testing/acceptance-matrix.md#req-09), [REQ-10 快照切換與即時投影合併](../testing/acceptance-matrix.md#req-10), [REQ-11 撤權過濾、自身通知與多群組同步](../testing/acceptance-matrix.md#req-11); [W13](../contracts/interface-contract.md#event-w13), [W14](../contracts/interface-contract.md#event-w14), [W15](../contracts/interface-contract.md#event-w15), [W16](../contracts/interface-contract.md#event-w16); [readBootstrap](../contracts/interface-contract.md#internal-read-bootstrap), [readFeed](../contracts/interface-contract.md#internal-read-feed)。
- **前置條件：** 已驗證的主體與支援的快照／事件流游標。
- **正常流程：** 由同一一致性檢視讀取已授權快照與 H；在同一快照 id 內分頁，並依安全提交順序掃描具固定續傳邊界的每使用者事件流。REST 游標各自獨立；A08/A11 首頁省略游標，A19 首頁省略 `before`（不可傳空字串或 `"null"`）；後續請求 URL-encode 並回傳 `meta.next_cursor`，null 表示結束。`limit` 為可省略 HTTP 十進位正整數；候選預設 20／上限 50，無效輸入使用 INVALID_ARGUMENT（適用範圍澄清待批准），不影響事件流分頁。A19 使用上述固定排序元組比較。
- **失敗流程：** 快照過期時建立新的、一致的快照；所有頁面與本機切換完成前不得安裝 H。過濾已撤權本文，同時允許安全前進及其他對話資料列。
- **驗收條件：** 完成的快照代表約定範圍及 H 時點狀態；後續持久化事件流可經 W16 取得，較舊授權歷史可經 A19 取得。REST 游標錯誤不得重設事件流。欄位必填性／可為 null 性遵循共用獨立存在性規則；排序與分頁選擇仍待批准（[欄位存在性](../contracts/interface-contract.md#field-presence)、[排序／分頁](../contracts/interface-contract.md#ordering-pagination)、[REST 分頁](../contracts/interface-contract.md#rest-pagination)）。
- **候選（待批准）：** 撤權後新查詢按 [G3](../decisions.md#group-new-queries) 過濾；E1 的同步回應授權點與內部位置依[既有延伸](../contracts/interface-contract.md#group-revocation-e1)，不得改 W14／W16 公開格式或游標／快照核心語義（[AC-N02](../testing/acceptance-matrix.md#ac-n02)、[AC-N26](../testing/acceptance-matrix.md#ac-n26)）。
- **交接：** [BA-06](backend-a.md#ba-06) 同步讀取；[FA-05](frontend-a.md#fa-05) 游標套用；[QA-03](qa.md#qa-03) 復原。

<a id="bb-07"></a>
<a id="bb-07--attachments-avatars-and-signed-transfer"></a>
### BB-07 — 附件、頭像與簽署傳輸
**追溯：** [REQ-03 個人檔案、頭像與聯絡人](../testing/acceptance-matrix.md#req-03), [REQ-13 圖片、檔案與上傳更新](../testing/acceptance-matrix.md#req-13); [A06](../contracts/interface-contract.md#api-a06), [A20](../contracts/interface-contract.md#api-a20), [A21](../contracts/interface-contract.md#api-a21), [A22](../contracts/interface-contract.md#api-a22), [A25](../contracts/interface-contract.md#api-a25)。
- **前置條件：** 擁有者與有效範圍；適用時須有對話授權。
- **正常流程：** 儲存中繼資料、建立短效 GCS 上傳／下載授權憑證、完成時驗證位元組與雜湊，並僅允許就緒附件使用；更新上傳時保留附件 ID 並建立目前嘗試。待批准 C9 僅為現有 A22 DownloadGrant 加上必填 `filename:string`、`size_bytes:int>0`；收件者從 W07/A19/W14/W16 得到 `attachment_id` 後，呼叫有授權檢查的 A22 讀取中繼資料與既有 content_type、URL、到期時間。A21 僅限擁有者，不能作查詢 API；不新增 API。待批准 C10 澄清 A20/A25 簽署網址傳輸：單次 PUT 原始 File/Blob 位元組（非 multipart/JSON/base64），完整帶上應用程式設定的必填標頭（含相符 Content-Type）；Host/Content-Length 由瀏覽器管理；不得附 HINE JWT／Cookie。HTTP 200 僅代表位元組已儲存；W05/A06 前仍須 A21 回 200 就緒。回應遺失視為結果不明，以同嘗試 A21 對帳或沿既有流程重送同位元組，不新增 API；供應商失敗不映射為 HINE W17 UNAUTHENTICATED。CORS 須允許 PUT/GET 及簽署所需標頭。見 [C9](../contracts/interface-contract.md#attachment-handoff) 與 [C10](../contracts/interface-contract.md#signed-upload-contract)，待批准。
- **C10 內容一致性補充（待批准）：** 沿用[同一 C10](../contracts/interface-contract.md#signed-upload-contract)：每個嘗試對應獨立且不重用的 GCS 物件鍵（object_key），上傳 URL 簽入僅建立標頭；A21 只核驗指定世代／中繼世代，提交時與 A25 的目前嘗試切換序列化，原子保存就緒綁定與中繼資料快照。同一已完成嘗試重試回原結果。A22 的中繼資料與固定世代的 URL 只取此綁定，不取最新版本；詳細不變條件與錯誤見共用契約，不新增公開欄位或 API。
- **失敗流程：** 舊嘗試、核驗內容／版本不符依既有 CONFLICT 拒絕，未上傳完成用 UPLOAD_NOT_READY；查詢依賴失敗不回成功。GCS 412 只代表僅建立條件未成立，不能直接標就緒或刪物件後覆寫。已核驗版本不可取得／中繼資料版本不符時 A22 回 DEPENDENCY_UNAVAILABLE，不偷偷改綁／交付另一版。頭像仍明確 conversation_id:null。
- **驗收條件：** A22 每次讀取均重新授權；簽署網址與 GCS 物件鍵（object_key）均為私有；上傳失敗不得變成就緒。
- **交接：** [FA-06](frontend-a.md#fa-06)/[FB-03](frontend-b.md#fb-03) 傳輸與中繼資料；[DO-02](devops.md#do-02) 儲存桶／機密。

<a id="bb-08"></a>
<a id="bb-08--push-token-store-and-background-dispatch"></a>
### BB-08 — 推播權杖儲存與背景派送
**追溯：** [REQ-14 裝置活動與背景推播](../testing/acceptance-matrix.md#req-14); [A23](../contracts/interface-contract.md#api-a23), [A24](../contracts/interface-contract.md#api-a24); [W21](../contracts/interface-contract.md#event-w21), [W22](../contracts/interface-contract.md#event-w22); [getDevicePresence](../contracts/interface-contract.md#internal-get-device-presence), [dispatchPushIntent](../contracts/interface-contract.md#internal-dispatch-push-intent)。
- **前置條件：** 有效且已綁定的裝置權杖與已提交且符合條件的訊息。
- **正常流程：** 安全儲存權杖；持久化提交後評估每位收件者裝置的活動狀態；對近期在前景的裝置抑制推播，對背景／未知狀態裝置傳送一般提示。
- **失敗流程：** 供應商失敗時重試持久化意圖；永久無效權杖時撤銷綁定。[A04](../contracts/interface-contract.md#api-a04) 目前裝置登出依提案撤銷綁定。推播不得包含訊息本文；不得變更回條。
- **驗收條件：** 推播是提示，不是送達／已讀證據；開啟通知後須透過同步取得已授權內容。[A23](../contracts/interface-contract.md#api-a23)/[A24](../contracts/interface-contract.md#api-a24) 仍是 `ios`／`android` 權杖契約；此處沒有瀏覽器推播訂閱／供應商結構描述，仍待 Web Push 政策／契約決策，並非暗示已有實作。
- **候選（待批准）：** 裝置活動使用 [C7 多連線聚合](../contracts/interface-contract.md#activity-merge)，不採最後一筆 W21 覆蓋全部分頁；沒有有效租期或來源不可判定即未知。仍只服務原本已批准範圍的受眾，這不是 Web Push／原生應用程式／PWA 的範圍批准（[AC-N27](../testing/acceptance-matrix.md#ac-n27)）。
- **交接：** [FA-07](frontend-a.md#fa-07)/[BA-07](backend-a.md#ba-07) 活動狀態；[FB-06](frontend-b.md#fb-06) 權杖流程；[DO-02](devops.md#do-02)/[DO-04](devops.md#do-04) 憑證／監控。

## 決策與共用參照

- [響應式 Web 行為](../ui/web-rwd.md#web-rwd)
- [決策：Web Push 範圍](../decisions.md#decision-web-push)；A23/A24 僅定義 iOS／Android 原生推播權杖，瀏覽器推播未定義且待另行核准。
- [決策：響應式 Web 版面](../decisions.md#decision-rwd)
- [返回文件導覽](../README.md)
