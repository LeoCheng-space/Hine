<a id="hine-ic-04--shared-interface-contract"></a>
# HINE-IC-0.4 — 共用介面契約
<a id="hine-ic-04-shared-interface-contract"></a>

**狀態：**整合提案，待批准。本文件是 [HINE-IC-0.4 角色 PRD](HINE-IC-0.4-role-prds.md) 的單一共用契約。本文描述規格行為，不代表已實作軟體或測試結果。除非明確標示為已確認／繼承，新增欄位與數值仍屬提案。本文不宣稱有產品程式碼、部署或產品測試。

## 1. 契約不變條件與提案狀態
<a id="1-contract-invariants-and-proposal-status"></a>

- 公開 REST：`https://hine.run.place/api/v1`；WSS：`wss://hine.run.place/ws/v1`。簽署 GCS 網址僅承載物件位元組；不是 HINE API 路由。內部 `/health/live` 與 `/health/ready` 並非公開端點。
- 後端 B 中的 PostgreSQL 是訊息、成員資格、回條、附件中繼資料及同步事件流的權威資料來源。後端 A 的 Redis/Pub/Sub 僅用於短暫即時分發，不是訊息儲存處。
- 僅在標準訊息、寄件者 C1→M1 對應，以及每位使用者所有必填事件流資料列均以原子方式提交後，才允許成功的 W06 持久化 ACK。若 ACK 遺失，透過重試相同的 `client_message_id`（C1）解決；相同 C1／相同內容回傳相同 M1，不同內容回傳 `IDEMPOTENCY_CONFLICT`。提交不保證寄件者收到 ACK。
- 即時 `message.created` 可立即顯示，但絕不會推進同步游標。W16 `next_cursor` 是候選值，僅會與已完整套用的本機投影以原子方式一併儲存。歷史 `before`、REST 清單游標與使用者 SyncCursor 各不相同，不能互換。
- 啟動快照狀態與起始游標 H 共用一致快照。同一 `snapshot_id` 的所有頁面都必須先暫存並套用，之後才能安裝 H。重新啟動或頁面失敗時，不得宣稱部分快照狀態已完成。掃描事件流時會略過未授權位置且不回傳其內容；遭移除的使用者可能收到自己的最少撤銷通知。
- `openChat(conversation_id)` 是前端 A 模組介面，不是 REST 路由或 WSS 事件。前端 B 擁有應用程式路由並呼叫它；前端 A 掛載／切換聊天 UI，並擁有單一應用程式範圍的 WSS。聊天導覽不會開啟第二個連線。
- 前端 B 專責擁有工作階段內容與更新憑證 Cookie。A03 成功後，會將新的存取工作階段傳給前端 A；前端 A 關閉舊 WSS 並建立新的 WSS（W01/W02）、傳送第一個 W21，並從已儲存的游標繼續。不會在同一連線上重新驗證。A04 撤銷目前裝置工作階段及推播綁定；成功登出會清除本機驗證資料，並通知前端 A 停止其連線。其他裝置不受影響。
- 群組對應：A14/A16 → W11；A15/A17 → W20；A18 → W12。沒有封鎖操作。
- 已確認／繼承：CC-01 持久化 ACK、C1→M1 冪等性、每使用者提交安全游標、快照續傳及離線復原。提案、待批准：A25、W21/W22、伺服器核發 DeviceID 的細節、SessionContext 新增內容、活動租約與推播受眾行為、數值上限／速率／TTL，以及作業值。沒有任何候選值是正式環境 SLO。
- 具權威性的已確認平台配置：HINE 用戶端是單一響應式 Web 應用程式（RWD），以統一程式碼庫服務桌面、平板與行動瀏覽器。前端 A（聊天／即時功能）及前端 B（驗證／聯絡人／路由）是此單一 Web 應用程式內的功能模組，不是分離或依裝置區分的應用程式。兩者共用相同的 `SessionContext`、REST API 用戶端、WebSocket 事件、資料模型及單一應用程式範圍 WSS 連線。前端框架與樣式工具（React、Vue、Tailwind 等）明確未定。此契約基準不要求自動提供原生行動應用程式、漸進式 Web 應用程式（PWA）、安裝或離線持久化。響應式 UI 規則、檢視區斷點與導覽轉換規格的詳細內容，請參閱 [HINE-IC-0.4 角色 PRD：共用 Web 響應式 UI 版面](HINE-IC-0.4-role-prds.md#web-rwd)。
- Web 推播範圍的明確決策：A23 `platform` 參數仍嚴格限定為原生推播權杖使用的 `"ios" | "android"`，且不變；用戶端不得將行動瀏覽器視為原生應用程式，也不得從 Web 瀏覽器傳送合成的 `ios`／`android` 權杖。保留產品既有的推播通知需求，但瀏覽器背景推播須另經 PM 批准供應商、訂閱模型與傳遞契約；不會自動要求 PWA 或 Web Push。本規格不新增 Web 推播用的 A 系列端點或 W 系列事件 ID。

## 2. 共用格式、錯誤、ID 與投影
<a id="2-common-formats-errors-ids-and-projections"></a>

### REST 與 WSS 封套
<a id="rest-and-wss-envelopes"></a>

REST 成功物件：`{"data": ...}`。成功清單：`{"data":{"items":[...]},"meta":{"next_cursor":string|null}}`。HTTP 204 沒有回應主體。REST 錯誤：

```json
{"error":{"code":"FORBIDDEN","message":"Access denied","request_id":"req-1","retryable":false,"details":{}}}
```

所示的所有錯誤欄位均為必填且不可為 null；`details` 是物件。速率限制時可包含 `details.retry_after_ms`。錯誤碼與狀態對應：`INVALID_ARGUMENT` 400、`UNAUTHENTICATED` 401、`FORBIDDEN` 403、`NOT_FOUND` 404、`CONFLICT` 409、`IDEMPOTENCY_CONFLICT` 409、`CURSOR_INVALID` 400（REST 游標無效）、`CURSOR_EXPIRED` 410（僅適用於過期的 A08/A11/A19 REST 游標）、`SYNC_RESET_REQUIRED` 410（僅適用於過期的 WSS 使用者事件流游標）、`PAYLOAD_TOO_LARGE` 413、`UNSUPPORTED_MEDIA_TYPE` 415、`UPLOAD_NOT_READY` 409、`UPLOAD_EXPIRED` 410（提案）、`RATE_LIMITED` 429、`DEPENDENCY_UNAVAILABLE` 503、`PERSISTENCE_FAILED` 503，以及 `OUTCOME_UNCONFIRMED` 503。`OUTCOME_UNCONFIRMED` 表示寫入可能已提交，但尚無確認結果；已知回滾則為 `PERSISTENCE_FAILED`。已中斷的連線不一定會收到錯誤訊框。REST 游標錯誤只影響該 REST 查詢；只有 WSS 使用者事件流的 `SYNC_RESET_REQUIRED` 會啟動 W13 啟動同步。

每個 WSS 訊框都有 `event:string`、`event_id:UUID`、`timestamp:Timestamp`、`payload:object`。對請求的回應會帶有 `correlation_id:UUID`，指向該請求的 `event_id`；命令與非請求事件則省略此欄位。對話事件要求頂層 `conversation_id`；W07 也要求頂層 `sender_id`。絕不信任用戶端提供的寄件者。訊息穩定的伺服器事件 ID 在即時傳遞與事件流重播中相同；請求事件 ID 每次嘗試都不同，而 C1 對同一傳送意圖保持穩定。

### 共用純量型別與隱私
<a id="shared-scalar-types-and-privacy"></a>

- `EntityID`：伺服器核發的不透明 JSON 字串（候選上限 128 個字元）；不一定是 UUID。除 `message_id`、`client_message_id` 與 `event_id` 外，ID 均為不透明字串。
- `DeviceID`：伺服器核發、綁定帳戶與裝置工作階段的獨立不透明識別碼；不保證屬於 `EntityID`，也不是憑證。`AccessSession.device_id`、W01/W02 `device_id`、A23/A24 裝置路徑、W21/W22 及內部裝置引數都使用此型別。A02 僅在首次安裝核發時可接受 `null`；回應一律包含非 null DeviceID。
- 公開 `user_id` 與內部 `subject_id` 是不同的身分型別。後端 B 會進行對應；`subject_id` 絕不是用戶端欄位。
- `UUID`：UUID 字串；`message_id`、`client_message_id`、`event_id` 與回應關聯 ID 均必填。
- `Timestamp`：ISO-8601 UTC 字串；權威時間戳記由伺服器產生。
- `OpaqueCursor`：伺服器核發的不透明字串，綁定使用者／事件流世代或其 REST 查詢；無法解碼，也不能用於授權存取。
- `Title`：字串；提案為 1–80 個 Unicode 字元。
- `UserSummary`：`{id:EntityID,display_name:string,avatar_attachment_id:EntityID|null}`；每個欄位皆必填。若頭像不存在或不可見，則為 null。摘要不含電子郵件。
- `UserProfile`：包含所有 UserSummary 欄位，並加上必填的 `email:string`；只有本人與後端 B 能看見電子郵件。密碼只會出現在 A01/A02 請求中，絕不出現在回應、日誌或 WSS 訊框中。
- `AccessSession`：`{access_token:string,expires_at:Timestamp,user_id:EntityID,device_id:DeviceID,session_generation:int}`；每個欄位都必填且不可為 null。更新憑證是 HTTP-only Secure/SameSite Cookie，絕不以 JSON 傳送。A01 僅回傳 UserProfile；A02/A03 回傳 AccessSession。
- `SessionContext`：恰有一個判別值。`authenticated` 含不可為 null 的 `user_id,device_id,access_token,expires_at,session_generation`；`refreshing` 含不可為 null 的 `user_id,device_id,session_generation`，且 `access_token,expires_at` 為 null；`logged_out` 的五個欄位全為 null。由前端 B 擁有。安裝範圍的 DeviceStore 與 SessionContext 分離，可在登出後依帳戶保留 device_id；`logged_out` 的 SessionContext 本身仍全部為 null。A02 僅對同一帳戶重用已儲存的 DeviceID。A05 `UserProfile.id` 只會與公開 `user_id` 比對，絕不與內部 `subject_id` 比對。
- 內部 JWT 主體 `subject_id` 會在伺服器端對應至公開 `user_id`；絕不從用戶端接收，也不回傳給用戶端。DeviceID 用於識別已綁定裝置，不是憑證。

### 使用者、對話與成員資格型別
<a id="user-conversation-and-membership-types"></a>

- `ContactView`：必填 `user:UserSummary`、`added_at:Timestamp`、`presence:"online"|"offline"|"unknown"`。A08 中線上狀態為必填；A09 回應中可省略。線上狀態是後端 A／Redis 的短暫狀態，不是推播狀態。
- `ConversationSummary`（A11）：必填 `id:EntityID`、`type:"direct"|"group"`、`title:Title|null`（一對一為 null）、`unread_count:int>=0`。不要求 `members` 或 `created_at`。
- `ConversationDetail`（A12）：包含所有 ConversationSummary 欄位，並加上必填的 `members:MemberView[]`、`created_at:Timestamp`、`membership_version:int|null`（群組 >=1；一對一為 null）。只有目前獲授權的成員可以讀取。
- `ConversationCreateResult`（A13/A14）：必填 `id,type,title,member_ids:EntityID[],membership_version:int|null`；群組建立者包含在 member_ids 中，一對一的 membership_version 為 null。
- `ConversationMutationResult`：必填 `id,type,title,membership_version:int>=1`（A15）。
- `MemberView`：必填 `user_id:EntityID`、`role:"admin"|"member"`。`MemberMutationResult` 另加必填 `membership_version:int>=1`。
- `BootstrapConversation`（W14）：必填 `id,type,title,unread_count,my_role:"admin"|"member"|null,recent_messages:MessageSnapshot[]`；一對一的 `title` 與 `my_role` 為 null。近期訊息是完整訊息快照，不只是 ID；完整成員清單來自 A12。

### 訊息、回條、附件與同步
<a id="messages-receipts-attachments-and-sync"></a>

- `MessageView`（A19）：必填且不可為 null 的 `id:UUID,event_id:UUID,conversation_id:EntityID,sender_id:EntityID,created_at:Timestamp,order_key:string,type:"text"|"image"|"file",receipt:ReceiptProjection|null`。若為文字訊息，必填 `text:string`（候選 1–4096 個 Unicode 字元），並省略 `attachment_id`。若為圖片／檔案訊息，必填 `attachment_id:EntityID`，並省略 `text`。可省略的 `client_message_id:UUID` 僅原寄件者可見。`order_key` 不是同步游標。
- `MessageSnapshot` 的欄位與可見性和 MessageView 相同，代表完整近期內容。W07/W16 將頂層 event_id 對應至 MessageView.event_id、`timestamp` 對應至 `created_at`、conversation_id 與 sender_id 對應至相應欄位，並將 `payload.message_id` 對應至 MessageView.id。W07 的 C1 僅寄件者可見。
- `ReceiptProjection` 可為一對一 `{kind:"direct",message_id:UUID,recipient_id:EntityID,status:"delivered"|"read",updated_at:Timestamp}`，或提案中的群組摘要 `{kind:"group",message_id:UUID,read_count:int>=0,member_count:int>=1,updated_at:Timestamp}`。後端儲存每位收件者的狀態；待處理是用戶端 UI 狀態，不是儲存的回條值。群組已讀數政策仍待產品決定。
- `AttachmentView`（A21）：必填且不可為 null 的 `id:EntityID,scope:"avatar"|"conversation",uploader_id:EntityID,kind:"image"|"file",filename:string,content_type:string,size_bytes:int>0,sha256:string`（64 位十六進位）、`state:"pending"|"ready",created_at:Timestamp,conversation_id:EntityID|null`。`scope=avatar` 要求對話為 null、`kind` 為 `image`，且上傳者為擁有者。對話範圍要求對話非 null，並在建立／下載時檢查成員資格。候選檔案上限 20 MiB，候選 MIME 允許清單 `image/jpeg,image/png,image/webp,application/pdf,text/plain` 均待批准。不公開 GCS 物件金鑰。
- `UploadGrant`（A20/A25）：必填 `attachment_id,upload_attempt_id:EntityID,upload_url:string`（短效 HTTPS 簽署網址）、`expires_at:Timestamp`、`required_headers:object<string,string>`。僅附件擁有者會收到；絕不記錄網址或將其放入訊息／事件。
- `DownloadGrant`（A22）：必填 `download_url:string,expires_at:Timestamp,content_type:string`。
- `DeviceTokenStatus`（A23）：必填 `device_id:DeviceID,platform:"ios"|"android",registered:boolean`；僅在控管下接收／儲存原始推播權杖，絕不回傳。
- `SyncBootstrapPage`（W14）：必填 `snapshot_id:EntityID,start_cursor:OpaqueCursor,conversations:BootstrapConversation[],next_page_token:OpaqueCursor|null,has_more:boolean`。候選頁面上限為 50 個邏輯項目，各對話、巢狀近期訊息及狀態分別計數。同一快照的所有頁面完成暫存且投影原子切換後，才安裝 `start_cursor`。
- `SyncBatch`（W16）：必填 `snapshot_boundary:OpaqueCursor,events:WsEnvelope[],next_cursor:OpaqueCursor,has_more:boolean`。候選掃描上限為 50 個事件流位置，包含隱藏的過濾位置。可見事件為空時，仍可能推進安全的候選游標；真正空掃描則不會。
- `HealthResponse`：必填 `status:"ok"|"unready",service:"api"|"realtime",timestamp:Timestamp,dependencies:{postgresql:"ok"|"fail"|"not_checked",redis:"ok"|"fail"|"not_checked"}`；可省略 `reason:string`（除非適用對外安全的就緒原因，否則省略；若存在則不可為 null）。僅供內部使用；存活檢查回傳 200 且不檢查依賴；必要依賴就緒時，就緒檢查回傳 200，否則回傳 503。`CONFIG_MISSING` 可指出缺少設定，但不揭露或命名其值。

## 3. REST API 登錄表 A01–A25
<a id="3-rest-api-registry-a01a25"></a>

以下各路徑均相對於單一基底網址 `https://hine.run.place`；與所示 `/api/v1/...` 路徑組合後即為完整公開路徑。所有操作均由後端 B 提供。除非標示為公開／僅 Cookie，否則使用有效的 Bearer 存取 JWT。表格欄位除標示為可省略／可為 null 外，均為必填。GET 可安全重試；204 無主體。清單回應使用共用清單封套。REST 游標錯誤僅影響相關清單／歷史查詢，不會重設 WSS 事件流。

| ID／operationId | 方法與路徑 | 請求 → 回應；狀態 | 授權、錯誤與重試／鍵行為 |
|---|---|---|---|
| A01 `registerUser` | POST `/api/v1/auth/register` | `{email,password,display_name}` → UserProfile；201 | 公開。INVALID_ARGUMENT、CONFLICT、RATE_LIMITED；重複電子郵件為 409，若回應不確定，不得改用新電子郵件繞過。無工作階段回應。 |
| A02 `login` | POST `/api/v1/auth/login` | `{email,password,device_id:DeviceID\|null}` → AccessSession；200 + 更新憑證 Cookie | 公開；僅首次安裝核發 DeviceID 時為 null。UNAUTHENTICATED、RATE_LIMITED；結果不確定時透過登入解決，而非依賴第二個工作階段儲存區。 |
| A03 `refreshSession` | POST `/api/v1/auth/refresh` | 無 JSON 主體；更新憑證 Cookie → AccessSession；200 + 輪替後的 Cookie | 有效更新憑證 Cookie。UNAUTHENTICATED、RATE_LIMITED；舊 Cookie 不可無限期重用。 |
| A04 `logout` | POST `/api/v1/auth/logout` | 無主體 → 無主體；204 | 目前工作階段 Cookie；具冪等性。UNAUTHENTICATED；提案中撤銷目前裝置的推播綁定。 |
| A05 `getMe` | GET `/api/v1/users/me` | 無主體 → UserProfile；200 | 自有個人檔案。UNAUTHENTICATED；可安全重試。 |
| A06 `updateMe` | PATCH `/api/v1/users/me` | 至少一個 `{display_name:string,avatar_attachment_id:EntityID\|null}` → UserProfile；200 | 自有個人檔案。INVALID_ARGUMENT、UNAUTHENTICATED、FORBIDDEN、UPLOAD_NOT_READY；頭像必須是本人擁有且就緒的頭像範圍附件；null 會移除頭像。 |
| A07 `getUserSummary` | GET `/api/v1/users/{user_id}` | 無主體 → UserSummary；200 | 已驗證。UNAUTHENTICATED、NOT_FOUND、RATE_LIMITED；隱藏的頭像為 null，絕不回傳電子郵件。 |
| A08 `listContacts` | GET `/api/v1/contacts?cursor={cursor}&limit={limit}` | 無主體 → ContactView[] + `meta.next_cursor`；200 | 自有聯絡人。UNAUTHENTICATED、CURSOR_INVALID、CURSOR_EXPIRED；任一游標錯誤僅影響此 REST 查詢。線上狀態未知時回報未知。 |
| A09 `addContact` | POST `/api/v1/contacts` | `{user_id}` → ContactView；新項目 201／既有項目 200 | 自有清單。INVALID_ARGUMENT、UNAUTHENTICATED、NOT_FOUND；相同擁有者／使用者不會重複新增。 |
| A10 `removeContact` | DELETE `/api/v1/contacts/{user_id}` | 無主體 → 無主體；204 | 自有清單。UNAUTHENTICATED；重複刪除仍為 204，且不會移除對話歷史。 |
| A11 `listConversations` | GET `/api/v1/conversations?cursor={cursor}&limit={limit}` | 無主體 → ConversationSummary[] + `meta.next_cursor`；200 | 自有且已授權的清單。UNAUTHENTICATED、CURSOR_INVALID、CURSOR_EXPIRED；僅供本地復原，而非透過 WSS 事件流。 |
| A12 `getConversation` | GET `/api/v1/conversations/{conversation_id}` | 無主體 → ConversationDetail；200 | 目前已授權成員。UNAUTHENTICATED、NOT_FOUND；版本落差透過重新擷取 A12 協調。 |
| A13 `getOrCreateDirectConversation` | POST `/api/v1/conversations/direct` | `{peer_user_id}` → ConversationCreateResult；新項目 201／既有項目 200 | 已驗證。INVALID_ARGUMENT、UNAUTHENTICATED、NOT_FOUND、CONFLICT；無序的雙人組合具有唯一性。 |
| A14 `createGroup` | POST `/api/v1/conversations/groups` | `{title,member_ids:EntityID[]}` → ConversationCreateResult；201 | 已驗證；必須提供 Idempotency-Key。INVALID_ARGUMENT、UNAUTHENTICATED、CONFLICT、IDEMPOTENCY_CONFLICT；相同鍵／不同內容為 409。建立者為管理員；提交後發出 W11。 |
| A15 `renameGroup` | PATCH `/api/v1/conversations/{conversation_id}` | `{title}` → ConversationMutationResult；200 | 管理員。INVALID_ARGUMENT、UNAUTHENTICATED、FORBIDDEN、NOT_FOUND；重試相同標題具冪等性；提交後發出 W20 標題變更。 |
| A16 `addGroupMember` | POST `/api/v1/conversations/{conversation_id}/members` | `{user_id}` → MemberMutationResult；新項目 201／既有項目 200 | 管理員。INVALID_ARGUMENT、UNAUTHENTICATED、FORBIDDEN、NOT_FOUND、CONFLICT；提交後發出 W11，絕不發出 W12。 |
| A17 `changeGroupMemberRole` | PATCH `/api/v1/conversations/{conversation_id}/members/{user_id}` | `{role:"admin"\|"member"}` → MemberMutationResult；200 | 管理員。INVALID_ARGUMENT、UNAUTHENTICATED、FORBIDDEN、NOT_FOUND、CONFLICT；不可移除最後一位管理員；提交後發出 W20 角色變更。 |
| A18 `removeGroupMember` | DELETE `/api/v1/conversations/{conversation_id}/members/{user_id}` | 無主體 → 無主體；204 | 管理員或自行離開。UNAUTHENTICATED、FORBIDDEN、NOT_FOUND、CONFLICT；重複的有效刪除具冪等性；提交後發出 W12，不設封鎖。 |
| A19 `listMessages` | GET `/api/v1/conversations/{conversation_id}/messages?before={history_cursor}&limit={limit}` | 無主體 → MessageView[] + `meta.next_cursor`；200 | 已授權的歷史讀取者。UNAUTHENTICATED、NOT_FOUND、CURSOR_INVALID、CURSOR_EXPIRED；依 order_key/message_id 由新至舊排序；歷史游標不是 SyncCursor。 |
| A20 `createUpload` | POST `/api/v1/uploads` | `{scope:"avatar"\|"conversation",conversation_id:EntityID\|null,filename,content_type,size_bytes,sha256}` → UploadGrant；201 | 必須提供 Idempotency-Key。INVALID_ARGUMENT、UNAUTHENTICATED、FORBIDDEN、PAYLOAD_TOO_LARGE、UNSUPPORTED_MEDIA_TYPE、IDEMPOTENCY_CONFLICT。頭像要求對話為 null；對話範圍要求目前具授權。 |
| A21 `completeUpload` | POST `/api/v1/uploads/{attachment_id}/complete` | `{upload_attempt_id,sha256}` → `AttachmentView(state="ready")`；200 | 擁有者。UNAUTHENTICATED、FORBIDDEN、UPLOAD_NOT_READY、CONFLICT；驗證實際 GCS 類型／大小／雜湊；僅接受目前嘗試，相同已完成嘗試會回傳原本的就緒結果。 |
| A22 `getAttachmentDownload` | GET `/api/v1/attachments/{attachment_id}/download` | 無主體／查詢 → DownloadGrant；200 | 擁有者或已授權檢視者。UNAUTHENTICATED、FORBIDDEN、NOT_FOUND、UPLOAD_NOT_READY、DEPENDENCY_UNAVAILABLE；每次重新檢查對話成員資格；獲准檢視頭像者可取得新的短效網址。 |
| A23 `upsertPushToken` | PUT `/api/v1/devices/{device_id}/push-token` | `{platform:"ios"\|"android",token}` → DeviceTokenStatus；200 | 自有且已綁定的 DeviceID。INVALID_ARGUMENT、UNAUTHENTICATED；PUT 會取代權杖；絕不回傳原始權杖。 |
| A24 `deletePushToken` | DELETE `/api/v1/devices/{device_id}/push-token` | 無主體 → 無主體；204 | 自有且已綁定的 DeviceID。UNAUTHENTICATED、FORBIDDEN；重複刪除仍為 204。 |
| A25 `renewUploadGrant`（提案） | POST `/api/v1/uploads/{attachment_id}/renew` | 無 JSON 主體 → UploadGrant；200 | 待處理上傳的擁有者；重新授權對話成員資格。UNAUTHENTICATED、FORBIDDEN、NOT_FOUND、CONFLICT、UPLOAD_EXPIRED、IDEMPOTENCY_CONFLICT。每次續期使用新的 Idempotency-Key。相同鍵的重試會回傳相同嘗試／網址，即使已過期；新鍵保留 `attachment_id` 並核發新的 upload_attempt_id／網址；A21 會拒絕舊嘗試。 |

A20/A21/A22 頭像流程不需要任何對話。候選附件檔名長度為 1–255 字元，檔案上限 20 MiB，MIME 類型如上所列；這些值尚未批准。A25 提案包含 `UPLOAD_EXPIRED` 錯誤。A08/A11/A19 REST 游標錯誤（包含過期／無效）只會重新啟動各自的本地查詢；只有 WSS 事件流的 `SYNC_RESET_REQUIRED` 才會開始 W13 啟動同步。
### 完整 REST 請求／回應範例登錄表
<a id="complete-rest-requestresponse-sample-registry"></a>

`request:null` 表示沒有 HTTP 請求主體（不是字面上的 JSON null）；查詢／路徑／標頭輸入已在登錄表中標明。回應使用契約投影與共用 REST 封套。所有範例均為合成資料。

```json
{
  "A01":{"request":{"email":"a@example.test","password":"example-password-123","display_name":"A"},"status":201,"response":{"data":{"id":"u1","display_name":"A","avatar_attachment_id":null,"email":"a@example.test"}}},
  "A02":{"request":{"email":"a@example.test","password":"example-password-123","device_id":null},"status":200,"response":{"data":{"access_token":"<jwt>","expires_at":"2026-10-01T08:15:00Z","user_id":"u1","device_id":"d1","session_generation":1}},"set_cookie":"<HttpOnly refresh cookie>"},
  "A03":{"request":null,"status":200,"response":{"data":{"access_token":"<jwt>","expires_at":"2026-10-01T08:30:00Z","user_id":"u1","device_id":"d1","session_generation":2}},"set_cookie":"<rotated HttpOnly refresh cookie>"},
  "A04":{"request":null,"status":204,"response":null},
  "A05":{"request":null,"status":200,"response":{"data":{"id":"u1","display_name":"A","avatar_attachment_id":null,"email":"a@example.test"}}},
  "A06":{"request":{"avatar_attachment_id":"a-avatar-1"},"status":200,"response":{"data":{"id":"u1","display_name":"A","avatar_attachment_id":"a-avatar-1","email":"a@example.test"}}},
  "A07":{"request":null,"status":200,"response":{"data":{"id":"u2","display_name":"B","avatar_attachment_id":"a-avatar-2"}}},
  "A08":{"request":null,"status":200,"response":{"data":{"items":[{"user":{"id":"u2","display_name":"B","avatar_attachment_id":"a-avatar-2"},"added_at":"2026-10-01T07:00:00Z","presence":"unknown"}]},"meta":{"next_cursor":null}}},
  "A09":{"request":{"user_id":"u2"},"status":201,"response":{"data":{"user":{"id":"u2","display_name":"B","avatar_attachment_id":"a-avatar-2"},"added_at":"2026-10-01T07:00:00Z"}}},
  "A10":{"request":null,"status":204,"response":null},
  "A11":{"request":null,"status":200,"response":{"data":{"items":[{"id":"c1","type":"direct","title":null,"unread_count":0}]},"meta":{"next_cursor":null}}},
  "A12":{"request":null,"status":200,"response":{"data":{"id":"c1","type":"direct","title":null,"unread_count":0,"members":[{"user_id":"u1","role":"member"},{"user_id":"u2","role":"member"}],"created_at":"2026-10-01T07:00:00Z","membership_version":null}}},
  "A13":{"request":{"peer_user_id":"u2"},"status":201,"response":{"data":{"id":"c1","type":"direct","title":null,"member_ids":["u1","u2"],"membership_version":null}}},
  "A14":{"request":{"title":"Team","member_ids":["u2","u3"]},"status":201,"response":{"data":{"id":"g1","type":"group","title":"Team","member_ids":["u1","u2","u3"],"membership_version":1}}},
  "A15":{"request":{"title":"Team 2"},"status":200,"response":{"data":{"id":"g1","type":"group","title":"Team 2","membership_version":2}}},
  "A16":{"request":{"user_id":"u4"},"status":201,"response":{"data":{"user_id":"u4","role":"member","membership_version":3}}},
  "A17":{"request":{"role":"admin"},"status":200,"response":{"data":{"user_id":"u4","role":"admin","membership_version":4}}},
  "A18":{"request":null,"status":204,"response":null},
  "A19":{"request":null,"status":200,"response":{"data":{"items":[{"id":"22222222-2222-4222-8222-222222222222","event_id":"00000000-0000-4000-8000-000000000007","conversation_id":"c1","sender_id":"u1","created_at":"2026-10-01T08:00:04Z","order_key":"c1-41","type":"text","text":"Hello","receipt":{"kind":"direct","message_id":"22222222-2222-4222-8222-222222222222","recipient_id":"u2","status":"read","updated_at":"2026-10-01T08:00:07Z"},"client_message_id":"11111111-1111-4111-8111-111111111111"}]},"meta":{"next_cursor":null}}},
  "A20":{"request":{"scope":"avatar","conversation_id":null,"filename":"avatar.png","content_type":"image/png","size_bytes":1024,"sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},"status":201,"response":{"data":{"attachment_id":"a-avatar-1","upload_attempt_id":"attempt-1","upload_url":"https://storage.googleapis.com/example-private/avatar?sig=example1","expires_at":"2026-10-01T08:05:00Z","required_headers":{"Content-Type":"image/png"}}}},
  "A21":{"request":{"upload_attempt_id":"attempt-1","sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},"status":200,"response":{"data":{"id":"a-avatar-1","scope":"avatar","conversation_id":null,"uploader_id":"u1","kind":"image","filename":"avatar.png","content_type":"image/png","size_bytes":1024,"sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","state":"ready","created_at":"2026-10-01T08:00:00Z"}}},
  "A22":{"request":null,"status":200,"response":{"data":{"download_url":"https://storage.googleapis.com/example-private/avatar?sig=download1","expires_at":"2026-10-01T08:01:00Z","content_type":"image/png"}}},
  "A23":{"request":{"platform":"android","token":"example-device-token"},"status":200,"response":{"data":{"device_id":"d1","platform":"android","registered":true}}},
  "A24":{"request":null,"status":204,"response":null},
  "A25":{"request":null,"status":200,"response":{"data":{"attachment_id":"a-avatar-1","upload_attempt_id":"attempt-2","upload_url":"https://storage.googleapis.com/example-private/avatar-attempt-2?sig=example2","expires_at":"2026-10-01T08:10:00Z","required_headers":{"Content-Type":"image/png"}}}}
}
```

A20 對話附件上傳的請求變體：
```json
{"scope":"conversation","conversation_id":"c1","filename":"report.pdf","content_type":"application/pdf","size_bytes":4096,"sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}
```

## 4. WebSocket 登錄表 W01–W22
<a id="4-websocket-registry-w01w22"></a>

所有事件均為共用封套中的訊框。方向為用戶端→伺服器（C→S）或伺服器→用戶端（S→C）。除 W01 外，業務訊框均要求驗證成功。必填欄位、方向與狀態轉換如下：

| ID／事件 | 方向；承載資料與頂層欄位 | 行為 |
|---|---|---|
| W01 `auth.authenticate` | C→S `{access_token:string,device_id:DeviceID}` | 第一個業務訊框。驗證權杖及綁定裝置；成功後發出 W02；無效時可能先發出 W17 再關閉，或直接關閉。 |
| W02 `auth.accepted` | S→C，與 W01 關聯：`{user_id:EntityID,device_id:DeviceID,expires_at:Timestamp,session_generation:int,heartbeat_interval_seconds:int,heartbeat_timeout_seconds:int}` | 公開身分與工作階段世代；心跳值為候選執行期設定。不影響游標。 |
| W03 `heartbeat.ping` | C→S `{nonce}` | 僅確認連線存活；不延長 JWT。 |
| W04 `heartbeat.pong` | S→C，與 W03 關聯 `{nonce}` | 回傳 `nonce`；逾時只會關閉此連線。 |
| W05 `message.send` | C→S，頂層 `conversation_id`；`{client_message_id,type:"text"\|"image"\|"file",text? \| attachment_id?}` | 文字訊息僅要求 `text`；圖片／檔案訊息僅要求 `attachment_id`。相同 C1／相同承載資料具冪等性；不同承載資料則衝突。 |
| W06 `message.ack` | S→C，與目前 W05 關聯，頂層 `conversation_id`；`{client_message_id,message_id,status:"persisted"}` | 僅在完整原子持久化後發出；可能因斷線而遺失。 |
| W07 `message.created` | S→C，頂層 `conversation_id,sender_id`；`{message_id,client_message_id?,type,text? \| attachment_id?,order_key}` | 傳送給已授權的收件者；C1 僅寄件者可見。事件流重播時 event_id 穩定。即時事件絕不推進游標。 |
| W08 `message.received` | C→S，頂層 `conversation_id`；`{message_id}` | 在本機持久化接收該訊息後傳送；回應為 W19；具冪等性。 |
| W09 `message.read` | C→S，頂層 `conversation_id`；`{message_id}` | 實際讀取後傳送；已讀狀態單調遞進，且隱含已送達。 |
| W10 `message.status` | S→C，頂層 `conversation_id`；ReceiptProjection | 後端 B 已提交的回條投影；可為一對一投影或提案中的群組彙總。也可透過同步復原。 |
| W11 `conversation.member_added` | S→C，頂層 `conversation_id`；`{member_id,role:"admin"\|"member",actor_id,membership_version}` | A14/A16 提交後發出。新成員透過 A12 取得詳細資料；即時事件遺失時可由事件流復原。 |
| W12 `conversation.member_removed` | S→C，頂層 `conversation_id`；自身 `{member_id,change:"removed",membership_version}`；對等成員也可能包含 `actor_id` | A18 提交後發出。遭移除的成員只收到最少的自身通知，不會收到未授權的後續內容。 |
| W13 `sync.bootstrap.request` | C→S `{reason:"first_login"\|"cursor_reset",snapshot_id?,page_token?}` | 初始或續傳頁面；續傳會綁定 snapshot_id 與 page_token。 |
| W14 `sync.bootstrap.page` | S→C，帶關聯；SyncBootstrapPage | 完整且已授權的對話快照，含近期訊息本文／狀態。同一快照的所有頁面都須先套用，才能安裝 start_cursor。 |
| W15 `sync.request` | C→S `{cursor,snapshot_boundary?}` | 第一個請求使用已儲存的游標；續傳使用同一輪的快照邊界。於重新連線／回到前景／定期協調時觸發。 |
| W16 `sync.batch` | S→C，帶關聯；SyncBatch | 候選 next_cursor；先原子套用事件與投影，再儲存游標。隱藏資料列也可能推進游標；事件流游標過期會導致 W17 `SYNC_RESET_REQUIRED`。 |
| W17 `error` | S→C，回應時帶關聯：`{code,message,retryable,retry_after_ms?}` | 共用錯誤碼語意；已斷線的連線不一定能收到。 |
| W18 `presence.changed` | S→C `{user_id,presence:"online"\|"offline"\|"unknown"}` | 短暫的已授權線上狀態；後端無法確認 Redis 狀態時為未知。 |
| W19 `receipt.ack` | S→C，與 W08/W09 關聯，頂層 `conversation_id`；`{message_id,status:"delivered"\|"read",changed}` | 回條請求結果；重複無操作時可能回傳 `changed=false`。 |
| W20 `conversation.updated` | S→C，頂層 `conversation_id`；`{changes:{kind:"title",title:Title}\|{kind:"role",member_id,role:"admin"\|"member"},actor_id,membership_version}` | A15/A17 提交後傳送給目前已授權成員；版本落差透過 A12 修正。 |
| W21 `device.activity`（提案） | C→S `{device_id:DeviceID,state:"foreground"\|"background"}` | W02 後首次傳送，並於狀態變更／續期時傳送。裝置必須符合已驗證工作階段；狀態過期／缺漏時視為未知。 |
| W22 `device.activity.ack`（提案） | S→C，與 W21 關聯 `{device_id:DeviceID,state:"foreground"\|"background",valid_until}` | 僅確認已記錄租約，不代表推播送達或訊息回條。 |

在巢狀 W16 中，每個事件都保留自己的 event_id 與 conversation_id；C1 仍僅寄件者可見。W21/W22 活動與 W03/W04 連線心跳、W18 使用者層級線上狀態彼此不同。
### WSS 訊框範例
<a id="wss-frame-examples"></a>

以下 UUID 僅為示意；時間戳記為 UTC。存取權杖與網址範例皆為佔位值，不是憑證。

```json
{"event":"auth.authenticate","event_id":"10000000-0000-4000-8000-000000000001","timestamp":"2026-09-29T12:00:00Z","payload":{"access_token":"<jwt>","device_id":"d1"}}
```
```json
{"event":"auth.accepted","event_id":"10000000-0000-4000-8000-000000000002","timestamp":"2026-09-29T12:00:00Z","payload":{"user_id":"u1","device_id":"d1","expires_at":"2026-09-29T13:00:00Z","session_generation":1,"heartbeat_interval_seconds":25,"heartbeat_timeout_seconds":60},"correlation_id":"10000000-0000-4000-8000-000000000001"}
```
```json
{"event":"message.send","event_id":"10000000-0000-4000-8000-000000000005","timestamp":"2026-09-29T12:01:00Z","conversation_id":"c1","payload":{"client_message_id":"10000000-0000-4000-8000-000000000006","type":"text","text":"hello"}}
```
```json
{"event":"message.ack","event_id":"10000000-0000-4000-8000-000000000007","timestamp":"2026-09-29T12:01:00Z","conversation_id":"c1","payload":{"client_message_id":"10000000-0000-4000-8000-000000000006","message_id":"10000000-0000-4000-8000-000000000008","status":"persisted"},"correlation_id":"10000000-0000-4000-8000-000000000005"}
```
```json
{"event":"message.created","event_id":"10000000-0000-4000-8000-000000000009","timestamp":"2026-09-29T12:01:00Z","conversation_id":"c1","sender_id":"u1","payload":{"message_id":"10000000-0000-4000-8000-000000000008","client_message_id":"10000000-0000-4000-8000-000000000006","type":"text","text":"hello","order_key":"k1"}}
```
```json
{"event":"heartbeat.ping","event_id":"10000000-0000-4000-8000-000000000003","timestamp":"2026-09-29T12:00:30Z","payload":{"nonce":"n1"}}
```
```json
{"event":"heartbeat.pong","event_id":"10000000-0000-4000-8000-000000000004","timestamp":"2026-09-29T12:00:30Z","payload":{"nonce":"n1"},"correlation_id":"10000000-0000-4000-8000-000000000003"}
```
```json
{"event":"message.received","event_id":"10000000-0000-4000-8000-000000000010","timestamp":"2026-09-29T12:02:00Z","conversation_id":"c1","payload":{"message_id":"10000000-0000-4000-8000-000000000008"}}
```
```json
{"event":"message.read","event_id":"10000000-0000-4000-8000-000000000011","timestamp":"2026-09-29T12:03:00Z","conversation_id":"c1","payload":{"message_id":"10000000-0000-4000-8000-000000000008"}}
```
```json
{"event":"message.status","event_id":"10000000-0000-4000-8000-000000000012","timestamp":"2026-09-29T12:03:01Z","conversation_id":"c1","payload":{"kind":"direct","message_id":"10000000-0000-4000-8000-000000000008","recipient_id":"u2","status":"read","updated_at":"2026-09-29T12:03:01Z"}}
```
```json
{"event":"conversation.member_added","event_id":"10000000-0000-4000-8000-000000000013","timestamp":"2026-09-29T12:04:00Z","conversation_id":"g1","payload":{"member_id":"u2","role":"member","actor_id":"u1","membership_version":2}}
```
```json
{"event":"conversation.member_removed","event_id":"10000000-0000-4000-8000-000000000014","timestamp":"2026-09-29T12:05:00Z","conversation_id":"g1","payload":{"member_id":"u2","change":"removed","membership_version":3}}
```
```json
{"event":"sync.bootstrap.request","event_id":"10000000-0000-4000-8000-000000000015","timestamp":"2026-09-29T12:06:00Z","payload":{"reason":"first_login"}}
```
```json
{"event":"sync.bootstrap.page","event_id":"10000000-0000-4000-8000-000000000016","timestamp":"2026-09-29T12:06:01Z","correlation_id":"10000000-0000-4000-8000-000000000015","payload":{"snapshot_id":"s1","start_cursor":"opaque-user1-40","conversations":[{"id":"c1","type":"direct","title":null,"unread_count":0,"my_role":null,"recent_messages":[{"id":"33333333-3333-4333-8333-333333333333","event_id":"44444444-4444-4444-8444-444444444444","conversation_id":"c1","sender_id":"u2","created_at":"2026-09-29T11:59:00Z","order_key":"c1-40","type":"text","text":"Earlier message","receipt":null}]}],"next_page_token":null,"has_more":false}}
```
```json
{"event":"sync.request","event_id":"10000000-0000-4000-8000-000000000017","timestamp":"2026-09-29T12:07:00Z","payload":{"cursor":"opaque-user1-40"}}
```
```json
{"event":"sync.batch","event_id":"10000000-0000-4000-8000-000000000018","timestamp":"2026-09-29T12:07:01Z","correlation_id":"10000000-0000-4000-8000-000000000017","payload":{"snapshot_boundary":"opaque-user1-41","events":[{"event":"message.created","event_id":"10000000-0000-4000-8000-000000000009","timestamp":"2026-09-29T12:01:00Z","conversation_id":"c1","sender_id":"u1","payload":{"message_id":"10000000-0000-4000-8000-000000000008","client_message_id":"10000000-0000-4000-8000-000000000006","type":"text","text":"hello","order_key":"k1"}}],"next_cursor":"opaque-user1-41","has_more":false}}
```
```json
{"event":"error","event_id":"10000000-0000-4000-8000-000000000019","timestamp":"2026-09-29T12:07:02Z","correlation_id":"10000000-0000-4000-8000-000000000017","payload":{"code":"SYNC_RESET_REQUIRED","message":"Cursor expired","retryable":false}}
```
```json
{"event":"presence.changed","event_id":"10000000-0000-4000-8000-000000000020","timestamp":"2026-09-29T12:08:00Z","payload":{"user_id":"u2","presence":"offline"}}
```
```json
{"event":"receipt.ack","event_id":"10000000-0000-4000-8000-000000000021","timestamp":"2026-09-29T12:03:01Z","conversation_id":"c1","correlation_id":"10000000-0000-4000-8000-000000000010","payload":{"message_id":"10000000-0000-4000-8000-000000000008","status":"delivered","changed":true}}
```
```json
{"event":"conversation.updated","event_id":"10000000-0000-4000-8000-000000000022","timestamp":"2026-09-29T12:09:00Z","conversation_id":"g1","payload":{"changes":{"kind":"title","title":"Team 2"},"actor_id":"u1","membership_version":4}}
```
```json
{"event":"conversation.updated","event_id":"10000000-0000-4000-8000-000000000023","timestamp":"2026-09-29T12:09:01Z","conversation_id":"g1","payload":{"changes":{"kind":"role","member_id":"u4","role":"admin"},"actor_id":"u1","membership_version":5}}
```
```json
{"event":"device.activity","event_id":"10000000-0000-4000-8000-000000000024","timestamp":"2026-09-29T12:10:00Z","payload":{"device_id":"d1","state":"background"}}
```
```json
{"event":"device.activity.ack","event_id":"10000000-0000-4000-8000-000000000025","timestamp":"2026-09-29T12:10:01Z","correlation_id":"10000000-0000-4000-8000-000000000024","payload":{"device_id":"d1","state":"background","valid_until":"2026-09-29T12:11:01Z"}}
```
```json
{"event":"message.send","event_id":"10000000-0000-4000-8000-000000000026","timestamp":"2026-09-29T12:11:00Z","conversation_id":"c1","payload":{"client_message_id":"10000000-0000-4000-8000-000000000027","type":"image","attachment_id":"a2"}}
```

<a id="5-backend-a--backend-b-internal-contracts"></a>
## 5. 後端 A ↔ 後端 B 內部契約
<a id="5-backend-a-backend-b-internal-contracts"></a>

這些是模組契約，不是公開端點或強制採用的微服務。後端 A 傳遞已驗證的主體／裝置與請求關聯；後端 B 會在每個變更交易中重新檢查授權。將內部失敗對應至共用公開錯誤碼，不揭露資料表名稱／私有欄位。

1. `validateAccess(access_token:string,device_id:DeviceID)` → `{subject_id:EntityID,session_id:EntityID,session_generation:int,expires_at:Timestamp,session_valid:boolean}`。錯誤：UNAUTHENTICATED、DEPENDENCY_UNAVAILABLE。檢查簽章、簽發者／受眾、裝置綁定及撤銷狀態。
2. `authorize(subject_id:EntityID,action:"send"|"receive"|"read"|"history"|"attachment"|"manage_group",resource_type:"conversation"|"message"|"attachment",resource_id:EntityID,device_id:DeviceID)` → `{allowed:boolean,authorization_version:EntityID}`。錯誤：UNAUTHENTICATED、FORBIDDEN、NOT_FOUND、DEPENDENCY_UNAVAILABLE。僅為預先檢查；變更交易必須重新檢查。
3. `persistIfAbsent(subject_id:EntityID,conversation_id:EntityID,client_message_id:UUID,type:"text"|"image"|"file",payload:{text:string}|{attachment_id:EntityID},request_event_id:UUID)` → 僅可能為 `created|existing_same` 之一，並包含 `{message_id:UUID,event_id:UUID,order_key:string,created_at:Timestamp,recipient_ids:EntityID[],status:"persisted"}`。錯誤：UNAUTHENTICATED、FORBIDDEN、IDEMPOTENCY_CONFLICT、PERSISTENCE_FAILED、OUTCOME_UNCONFIRMED、DEPENDENCY_UNAVAILABLE。相同 C1／不同本文為 IDEMPOTENCY_CONFLICT。訊息、C1 對應、每筆必要收件者事件流資料列及提案中符合條件裝置的推播意圖，均須在 W06 前原子提交。
4. `persistReceipt(subject_id:EntityID,device_id:DeviceID,conversation_id:EntityID,message_id:UUID,kind:"delivered"|"read",request_event_id:UUID)` → `{message_id:UUID,status:"delivered"|"read",changed:boolean,updated_at:Timestamp,status_event_id:UUID|null}`。錯誤：UNAUTHENTICATED、FORBIDDEN、NOT_FOUND、PERSISTENCE_FAILED、OUTCOME_UNCONFIRMED、DEPENDENCY_UNAVAILABLE。狀態單調遞進；未變更的重複請求不會建立新狀態事件。
5. `readBootstrap(subject_id:EntityID,reason:"first_login"|"cursor_reset",snapshot_id?:EntityID,page_token?:OpaqueCursor)` → SyncBootstrapPage。錯誤：UNAUTHENTICATED、FORBIDDEN、CURSOR_INVALID、SYNC_RESET_REQUIRED、DEPENDENCY_UNAVAILABLE。在簡短的 REPEATABLE READ 下，以一致方式讀取快照狀態／最新位置；網路分頁期間不得持有交易。每頁前驗證授權；快照過期時重新開始，不混用快照。
6. `readFeed(subject_id:EntityID,cursor:OpaqueCursor,snapshot_boundary?:OpaqueCursor,limit:int)` → SyncBatch。錯誤：UNAUTHENTICATED、FORBIDDEN、CURSOR_INVALID、SYNC_RESET_REQUIRED、DEPENDENCY_UNAVAILABLE。固定續傳快照邊界；掃描隱藏與可見位置；回傳已授權內容及最少的自身撤銷通知；不得讓單一遭撤銷的對話阻塞其他事件流位置。
7. `getDevicePresence(subject_id:EntityID,device_id:DeviceID)` 回傳 `{online:"online"|"offline"|"unknown",activity:"foreground"|"background"|"unknown",valid_until:Timestamp|null}`。`recordActivity(subject_id:EntityID,device_id:DeviceID,session_generation:int,state:"foreground"|"background")` 回傳 `{state:"foreground"|"background",valid_until:Timestamp}`。錯誤：UNAUTHENTICATED、FORBIDDEN、DEPENDENCY_UNAVAILABLE。兩者分別為讀取／查詢與變更操作。Redis 失敗時回傳未知，絕不回傳錯誤的前景狀態。
8. `dispatchPushIntent(message_id:UUID,recipient_user_id:EntityID,device_id:DeviceID)` → `sent|suppressed|retryable_failure|permanent_token_failure`。錯誤：FORBIDDEN、DEPENDENCY_UNAVAILABLE；供應商失敗由結果表示，不會變更回條。符合條件收件者的訊息／事件流資料建立時，會在交易中建立持久推播意圖。抑制近期處於前景的裝置；背景／未知裝置可能收到不含本文的一般提示。供應商重試不會變更回條；`(message_id,device_id)` 可供去重，但不保證供應商端恰好一次。

### 群組事件對應與用戶端套用
<a id="group-event-mapping-and-client-application"></a>

A14 建立時會為建立者／初始成員發出 W11 投影。A15 重新命名會發出 `kind=title` 的 W20；A16 新增成員會發出 W11（不是 W12）；A17 角色變更會發出 `kind=role` 的 W20；A18 移除成員會發出 W12（不是 W13）。REST 呼叫端依 REST 結果更新自己的檢視，不等待 Pub/Sub。其他裝置套用事件；新成員擷取 A12；版本落差時擷取 A12。遭移除使用者收到最少的 W12 或 A18 成功後即離開路由，不會取得新的未授權本文。成員資格變更與每筆必要使用者事件流項目一併提交；Pub/Sub 僅加速提交後的傳遞。
### 線上狀態、活動與推播（提案）
<a id="presence-activity-and-push-proposal"></a>

W21 回報已驗證裝置的應用程式前景／背景狀態；W22 核發短效租約。背景訊框遺失、租約過期或連線缺漏時，狀態為未知，而非前景。後端 B 為符合條件且已註冊的非寄件者裝置儲存一般推播意圖。近期處於前景的裝置會抑制推播；已知為背景或狀態未知的裝置可能收到不含訊息本文的一般通知。供應商接受／失敗不等於已送達／已讀回條。點選通知後會恢復驗證，並透過已授權的 W13–W16/A19 同步取得內容。每位使用者的線上狀態與每台裝置的前景狀態不同。
## 6. 部署與作業政策
<a id="6-deployment-and-operational-policy"></a>

以下環境登錄表是提案設定，不代表目前已部署這些設定。`Required`（必填）表示啟用具名功能時必須設定；推播供應商憑證則視該供應商／平台是否啟用而定。

| 名稱 | 型別／必填 | 使用端 | 設定者／來源 | 機密？ | 缺漏／無效時的行為 |
|---|---|---|---|---|---|
| `HINE_ENV` | 列舉／字串；必填 | BA、BB、DO | 維運部署設定 | 否 | 拒絕啟動／就緒 |
| `PUBLIC_ORIGIN` | HTTPS URL；必填 | BB、DO | 維運入口設定 | 否 | 拒絕就緒；不建立公開連結 |
| `API_BASE_URL` | HTTPS URL；必填 | FB、FA 設定；DO 入口 | 維運前端／發佈設定 | 否 | 前端部署無效 |
| `WS_URL` | WSS URL；必填 | FA 設定；DO 入口 | 維運前端／發佈設定 | 否 | 即時用戶端未就緒 |
| `DATABASE_URL` | PostgreSQL 連線 URI；必填 | BB | 維運 Secret Manager 參照 | 是 | BB 啟動／就緒失敗 |
| `REDIS_URL` | Redis 連線 URI；即時／線上狀態短暫狀態功能必填 | BA | 維運 Secret Manager 參照 | 是 | BA 未就緒；回報未知，不回報錯誤的線上狀態 |
| `GCS_BUCKET` | 儲存桶名稱；上傳功能必填 | BB | 維運部署設定 | 否 | 附件功能未就緒 |
| `JWT_ISSUER` | 字串；必填 | BB 核發、BA 驗證 | 後端 B 驗證負責人＋維運 | 否 | 驗證啟動／就緒失敗並採拒絕預設 |
| `JWT_AUDIENCE` | 字串；必填 | BB 核發、BA 驗證 | 後端 B 驗證負責人＋維運 | 否 | 驗證啟動／就緒失敗並採拒絕預設 |
| `JWT_SIGNING_KEY_SECRET_REF` | 密鑰參照；必填 | 僅 BB | 維運 Secret Manager 綁定；BB 負責金鑰輪替 | 參照資訊敏感；值為機密 | BB 驗證服務不可用／未就緒；絕不接受假金鑰 |
| `FCM_CREDENTIAL_SECRET_REF` | 密鑰參照；啟用 Android 推播時必填 | BB 推播工作程序 | 維運 Secret Manager 綁定；BB 負責供應商使用 | 參照資訊敏感；值為機密 | 依批准政策停用推播或判定部署未就緒；絕不使用假憑證 |
| `APNS_KEY_SECRET_REF` | 密鑰參照；啟用 iOS 推播時必填 | BB 推播工作程序 | 維運 Secret Manager 綁定；BB 負責供應商使用 | 參照資訊敏感；值為機密 | 依批准政策停用推播或判定部署未就緒；絕不使用假憑證 |
| `SYNC_PAGE_LIMIT` | 正整數；必填 | BB readBootstrap/readFeed、BA | PM 批准數值；維運注入；BA/BB 驗證 | 否 | 拒絕無效設定；不可使用無上限頁數 |
| `UPLOAD_MAX_BYTES` | 正整數；啟用上傳時必填 | BB | PM 批准數值；維運注入；BB 驗證 | 否 | 拒絕無效設定；上傳不可用 |
| `HEARTBEAT_TIMEOUT_SECONDS` | 正整數；必填 | BA；透過 W02 公告政策 | PM 批准數值；維運注入；BA 驗證 | 否 | 拒絕無效設定／判定未就緒；不得暗中自行設定執行期數值 |
| `HEARTBEAT_INTERVAL_SECONDS` | 正整數；必填 | BA 設定／執行心跳頻率；W02 向 FA 公告 | PM 批准候選值；維運注入；BA 驗證 | 否 | 拒絕無效設定／判定未就緒；不得暗中自行設定 W02 數值 |
| `ACTIVITY_LEASE_SECONDS` | 正整數；啟用 W21/W22 時必填 | BA recordActivity/W22；BB 裝置推播資格 | PM 批准候選值；維運注入；BA 驗證 | 否 | 拒絕無效設定／判定未就緒；活動狀態應為未知，不可推定為前景 |
| `SYNC_RECONCILE_SECONDS` | 正整數；定期前景同步時必填 | FA 排程 W15/W16；BA/BB 處理請求 | PM 批准候選值；維運注入；FA/BA 驗證 | 否 | 拒絕無效用戶端／執行期設定；不得暗中自行設定同步頻率 |

每個環境也會記錄設定值的團隊及所用參照／版本，但不記錄機密內容。推播憑證缺漏時，可選擇停用該供應商或使就緒檢查失敗；部署前必須由 PM／維運批准。

內部 `/health/live` 回報程序存活狀態（200；依賴可能為 `not_checked`）。`/health/ready` 回報必要依賴的就緒狀態（200 或 503）。回應遵循 HealthResponse，且不含憑證。候選值（並非批准值）包括：同步邏輯頁面上限 50、上傳上限 20 MiB、心跳間隔 25 秒及逾時 60 秒、活動租約 60 秒並依據 W22 在 `valid_until` 前續期，以及每 10 秒進行一次前景同步協調。候選速率限制包括訊息每分鐘 60 次、突發上限 10 次，以及登入每來源每分鐘 5 次；這些數值仍待 PM／QA 批准。同步續傳不得被一般定期請求節流阻擋。A01–A25/W01–W22 登錄表與本文件僅為規格；不宣稱已完成任何部署或執行期測試。
完整健康檢查回應範例：
```json
{"status":"ok","service":"realtime","timestamp":"2026-10-01T08:00:00Z","dependencies":{"postgresql":"not_checked","redis":"not_checked"}}
```
```json
{"status":"unready","service":"api","timestamp":"2026-10-01T08:00:01Z","dependencies":{"postgresql":"fail","redis":"ok"}}
```
```json
{"status":"unready","service":"api","timestamp":"2026-10-01T08:00:02Z","dependencies":{"postgresql":"not_checked","redis":"not_checked"},"reason":"CONFIG_MISSING"}
```
此就緒回應指出設定失敗，但不揭露設定名稱或值。
第一個範例是 `/health/live` 200；第二個是 `/health/ready` 503。監控會分別量測 ACK、即時傳遞、同步復原與推播失敗。公開指標標籤不含使用者 ID／權杖／訊息本文；日誌不含完整權杖及私人訊息本文。

## 7. 待決產品事項與變更紀錄
<a id="7-pending-product-decisions-and-change-ledger"></a>

待決事項：重新安裝／切換帳戶時 DeviceID 的核發／重用；未知狀態下的前景／活動租約與推播行為；正式環境頁數／檔案／心跳／速率數值；群組角色與人數政策；群組回條可見性；加入／離開前後的歷史紀錄；附件類型／大小；以及哪些歷史效能／重新連線目標仍有效。A25、W21、W22、SessionContext 欄位與活動／推播投影仍屬提案，不代表已批准的既有正式環境行為。保留 A01–A25 與 W01–W22 名稱及 ID；A18 是移除成員資格，不是封鎖。文件交叉參照／完整性檢閱不等於執行期 API 驗證。HINE-IC-0.4 納入已確認的平台配置（桌面／平板／行動裝置共用單一 Web RWD 應用程式，並共用 SessionContext 與 WSS），以及明確的 Web 推播界線（A23 `platform` 的 `ios`／`android` 維持不變；瀏覽器背景推播需另行取得 PM 批准）。
