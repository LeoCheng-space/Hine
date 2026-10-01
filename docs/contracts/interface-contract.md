<a id="hine-ic-04-shared-interface-contract"></a>
<a id="hine-ic-04--shared-interface-contract"></a>
# HINE-IC-0.4 — 共用介面契約

**狀態：**HINE-IC-0.4 共用介面契約（2026-10-01 PM 決議與分輪對齊政策）。本文是跨模組溝通的共同依據，不是一次鎖死整份規格；先確認[近期串接基線](#integration-baseline)，其餘介面在相應串接前共同確認。模組內實作可自由選擇，跨模組變更依[共同變更流程](../../CONTRIBUTING.md#interface-changes)辦理。本輪工作值已書面列明，受影響成員確認尚未取得；不宣稱產品已實作、部署或測試。響應式介面見[獨立 Web/RWD 規格](../ui/web-rwd.md#web-rwd)。

<a id="1-契約不變條件與提案狀態"></a>
<a id="1-contract-invariants-and-proposal-status"></a>
## 1. 契約不變條件與決議狀態

- 公開 REST：`https://hine.run.place/api/v1`；WSS：`wss://hine.run.place/ws/v1`。已簽署的 GCS URL 僅承載物件位元組；它們不是 HINE API 路由。內部的 `/health/live` 和 `/health/ready` 並非公開端點。
- 後端 B 中的 PostgreSQL 是訊息、成員資格、回條、附件中繼資料及同步事件流的權威資料來源。後端 A Redis/Pub/Sub 僅用於暫時性即時扇出，絕不作為訊息儲存庫。
- 僅在標準訊息、傳送者 C1→M1 對應，以及所有必要的逐使用者事件流列均已原子提交後，才允許傳回成功的 W06 持久化 ACK。若 ACK 遺失，則以相同的 `client_message_id` (C1) 重試；相同 C1／相同內容會傳回相同 M1，不同內容則傳回 `IDEMPOTENCY_CONFLICT`。提交不保證傳送者已收到 ACK。
- 即時的 `message.created` 可立即顯示，但絕不會推進同步游標。W16 `next_cursor` 僅在本機投影完全套用後，才會與其原子儲存。歷史記錄的 `before`、REST 清單游標及使用者 SyncCursor 彼此不同，不可互換。
- 啟動同步快照狀態與起始游標 H 共用一致的快照。同一 `snapshot_id` 的所有頁面都必須完成暫存與套用後，才能安裝 H。重新啟動或頁面失敗時，不得宣稱部分快照狀態已完整。事件流掃描會略過未授權且隱藏的位置，不傳回其內容；遭移除的使用者可能會收到僅包含最低限度資訊的撤銷通知。
- `openChat(conversation_id)` 是前端 A 的模組介面，不是 REST 路由或 WSS 事件。前端 B 負責應用程式路由並呼叫它；前端 A 負責掛載／切換聊天 UI，並擁有單一應用程式範圍的 WSS。聊天導覽不會開啟第二個連線。
<a id="refresh-cookie-roles"></a>**更新憑證 Cookie 與 AccessSession 分工：** 後端 B 在 A02／A03 回應以 `Set-Cookie` 設定 HttpOnly／Secure／SameSite 更新憑證 Cookie，並負責輪替、撤銷與有效性判定；瀏覽器保存該 Cookie，並在同源 A03／A04 請求自動附帶。前端程式碼（FB、FA）無法也不得讀取、複製、保存或記錄 Cookie 值。前端 B 負責 A02／A03／A04 的呼叫時機與流程、SessionContext，以及保存 A02／A03 回傳的 AccessSession；前端 A 只消費 FB 交付的 AccessSession（存取權杖、裝置、世代）建立與替換 WSS。A03 成功後，前端 B 將新的 AccessSession 交給前端 A，後者會關閉舊 WSS 並建立新的 WSS (W01/W02)，並從已儲存的游標繼續。不得在同一連線上重新驗證。A04 會撤銷目前裝置工作階段；登出成功後會清除本機驗證資訊，並通知前端 A 停止其連線。其他裝置不受影響。同一瀏覽器設定檔只允許一個可操作聊天分頁（C5／M1）；分頁鎖政策見前端 PRD。
- 群組對應：A14/A16 → W11；A15/A17 → W20；A18 → W12。沒有封鎖操作。
- 已確認／承襲：CC-01 持久化 ACK、C1→M1 冪等性、可安全提交的逐使用者游標、快照續傳及離線復原。C1–C6（其中 C1–C4、C6 依決議改寫）、C8–C14、E1、G1–G3、S1–S2 為現行規則（2026-10-01 PM 決議）；C7、A23–A25、W21/W22、活動租約、推播及相關功能本版範圍外。EntityID／text 採下方本輪工作值；Title 留待群組串接前確認，`INVALIDATION_RETENTION_SECONDS` 另屬內部部署待決事項。分輪交付不取消既有授權、ACK、冪等及保存義務；工作值不是正式環境 SLO。
- HINE 用戶端是一個 RWD 響應式 Web 應用程式。前端 A（聊天／即時通訊）和前端 B（驗證／聯絡人／路由）是此單一 Web 應用程式中的功能模組，並非獨立或依裝置區分的應用程式。兩者共用 `SessionContext`、REST API 用戶端、WebSocket 事件、資料模型，以及單一應用程式範圍的 WSS 連線。前端框架與樣式工具由團隊共同選定；本契約不依賴特定框架。本契約不要求原生 App、PWA、安裝功能或完整離線使用；這不取消 W05／W08／W14／W16 既有的[本機保存義務](#local-persistence-boundary)。
- Web Push 與 iOS／Android 原生推播均為本版範圍外（2026-10-01 PM 決議）。保留開啟網頁時的 WebSocket 即時訊息、聊天內提示與查詢後更新的未讀徽章；關閉網頁後不保證通知。A23／A24 保留 ID，標示本版範圍外；不要求推播工作程序或推播金鑰，不影響核心服務就緒。

<a id="integration-baseline"></a>
### 近期串接基線：先對齊溝通，再自由實作

**目標：** 兩個帳號登入 → 建立一對一對話 → 送出文字 → 提交後 ACK → 另一端收到並顯示；以 A19 核對持久保存。這是第一輪交接範圍，不是全部功能的交付或驗收宣告。

| 交接 | 本輪共同介面與必須對齊的內容 | 對接角色 |
|---|---|---|
| 帳號與公開身分 | [A01／A02／A05](#api-a01)：註冊不回工作階段；登入回 AccessSession；A02.user_id＝A05.id；首次 device_id 可為 null、回覆使用伺服器核發值 | FB ↔ BB；FA／BA 消費身分 |
| 前端模組 | [SessionContext／AccessSession](#shared-scalar-types-and-privacy) 與 `openChat(conversation_id)`：FB 管認證／路由，FA 管單一 WSS／聊天室；不自行解讀 Cookie 或另開聊天連線 | FB ↔ FA |
| 一對一入口與歷史 | [A13](#api-a13) 用 peer_user_id 建立／取得唯一對話；一對一 title／membership_version 為 null；[A19](#api-a19) 用既有 REST 清單封套、歷史游標與 order_key 排序 | FB／FA ↔ BB |
| WSS 與文字 | [W01–W07](#event-w01)、[W17](#event-w17)：驗證、心跳、文字送出、ACK、接收與錯誤；封套／必填及 null／UUID／correlation_id、C1→M1、text 計數一致；W06／W07 不保證先後 | FA ↔ BA；FB 提供 AccessSession |
| 後端驗證與寫入 | [validateAccess／authorize／persistIfAbsent](#internal-handoffs)：以可信 user_id 與工作階段綁定處理；BB 原子提交訊息、C1 對應與事件流後，BA 才回 W06；同一 C1 重試得到同一 M1 | BA ↔ BB |
| 提交後傳遞 | [publishCommitted](#internal-publish-committed) 的 HTTP／JSON、服務身分與單一 Redis Pub/Sub 路徑；收件者由 BB 在提交時決定，不以快取或用戶端 sender_id 決定 | BB ↔ BA；DO 提供私有路由／設定 |

**共用格式：** 上表引用的 REST／WSS 封套、路徑、欄位、型別、可省略／null、狀態碼、錯誤分流、授權、排序與冪等語意使用本文同一份定義；不得各自另訂線上格式。內部 HTTP 亦適用，不只公開 API。

**本輪工作值：** EntityID 上限 128 個 Unicode 碼點；文字 text 為 1–4096 個 Unicode 碼點。這兩項是近期對接的共同預設值，並非不可修改；受影響成員確認或提出共同修訂後，依變更流程留下紀錄。Title 的 1–80 候選不阻擋一對一 title:null，必須在 A14／A15 群組串接前確認。

**模組內自由：** 語言、框架、內部類別／函式、資料結構、狀態管理、檔案安排與演算法由負責人決定，不需逐項請 PM 批准；仍須符合既有功能／安全要求及單一 Web 交付。若改動會讓其他模組更換輸入、解析、錯誤處理、呼叫或部署方式，就屬共同介面變更，不是內部自由。

**後續分輪：** 聯絡人、群組／Title、附件、回條及完整重連／同步驗收，在各輪串接前確認相關介面、例子、對接人與預期結果；不要求先簽核整份文件才開始模組開發。既有規則仍適用，不能以「尚未本輪驗收」推論可以自行改格式或略過安全／保存義務；A23–A25、W21／W22 的範圍外狀態不變。

**紀錄：** 政策日期為 2026-10-01；來源基準為 `main` 的 `17c25ec`，本次書面修訂透過 `docs/incremental-interface-baseline` 分支交付，以該分支提交紀錄追溯；合併前不宣稱 `main` 已更新。PM 已要求分輪共同對齊；FA／FB／BA／BB 的本輪確認尚未取得，不標示為全員凍結完成。各輪對接確認、變更 PR 與合併提交依[決策治理](../decisions.md#incremental-interface-governance)記錄；驗收見[首輪條件](../testing/acceptance-matrix.md#first-integration-cases)。

<a id="data-dictionary"></a>
<a id="2-common-formats-errors-ids-and-projections"></a>
## 2. 共用格式、錯誤、ID 與投影

<a id="error-rules"></a>
<a id="rest-and-wss-envelopes"></a>
### REST 與 WSS 封套

REST 成功物件：`{"data": ...}`。成功清單：`{"data":{"items":[...]},"meta":{"next_cursor":string|null}}`。HTTP 204 沒有回應本文。REST 錯誤：

```json
{"error":{"code":"FORBIDDEN","message":"Access denied","request_id":"req-1","retryable":false,"details":{}}}
```

REST 錯誤的 `code`、`message`、`request_id`、`retryable`、`details` 必填且非 null，`details` 是物件；W17 的必填欄位是 `code`、`message`、`retryable`，回覆請求時另有封套的 `correlation_id`。限速等待值與恢復動作統一見[錯誤分流](#error-recovery)。錯誤碼與狀態對應：`INVALID_ARGUMENT` 400、`UNAUTHENTICATED` 401、`FORBIDDEN` 403、`NOT_FOUND` 404、`CONFLICT` 409、`IDEMPOTENCY_CONFLICT` 409、`CURSOR_INVALID` 400（REST 游標無效）、`CURSOR_EXPIRED` 410（僅適用於過期的 A08/A11/A19 REST 游標）、`SYNC_RESET_REQUIRED` 410（僅適用於過期的 WSS 使用者事件流游標）、`PAYLOAD_TOO_LARGE` 413、`UNSUPPORTED_MEDIA_TYPE` 415、`UPLOAD_NOT_READY` 409、`RATE_LIMITED` 429、`DEPENDENCY_UNAVAILABLE` 503、`PERSISTENCE_FAILED` 503，以及 `OUTCOME_UNCONFIRMED` 503。`OUTCOME_UNCONFIRMED` 表示寫入可能已提交，但尚無確認結果；已知回滾則為 `PERSISTENCE_FAILED`。已中斷的連線不必收到錯誤訊框。REST 游標錯誤僅限於該 REST 查詢；只有 WSS 使用者事件流游標過期才重設同步。

每個 WSS 訊框都有 `event:string`、`event_id:UUID`、`timestamp:Timestamp`、`payload:object`。請求的回應包含 `correlation_id:UUID`，用來參照該請求的 `event_id`；命令與非請求觸發的事件則省略此欄位。對話事件需要頂層 `conversation_id`；W07 還需要頂層 `sender_id`。絕不信任用戶端提供的寄件者。訊息穩定的伺服器事件 ID 在即時傳遞與事件流重播時相同；請求事件 ID 每次嘗試都不同，而 C1 對同一傳送意圖保持穩定。

<a id="error-recovery"></a>
### 共用錯誤 → 操作範圍 → 恢復動作（既有規則對齊）

W17 是錯誤容器，不是「刷新」命令。FA／FB 先以 `correlation_id` 找原請求，再按 `code`、該操作及目前連線／SessionContext 判斷；沒有關聯的錯誤不能任意套用到其他待送操作。`retryable:true` 只表示原操作可重試，不代表可以刷新權杖、換 C1 或重設所有游標。

| 錯誤／觀察 | 操作範圍 | 恢復動作 |
|---|---|---|
| `UNAUTHENTICATED`、已知存取權杖到期／工作階段撤銷 | 使用者驗證與相符的 WSS | 停止以舊身分執行新操作，依唯一驗證流程處理；若已有較新的 AccessSession，就重新連線，不要再次刷新。A03 本身的失敗依該驗證流程處理。內部服務憑證失敗不代表使用者工作階段撤銷；BA 只在可信內部回覆明確標為使用者工作階段層時轉成此列，分層方式見 [C13](#internal-auth-layer) |
| `FORBIDDEN`、`NOT_FOUND` | 該資源／操作 | 顯示無法存取、移除失去權限的畫面，或停止該操作；不刷新、不登出整個帳號，也不影響其他對話 |
| `INVALID_ARGUMENT`、`CONFLICT`、`IDEMPOTENCY_CONFLICT`、`PAYLOAD_TOO_LARGE`、`UNSUPPORTED_MEDIA_TYPE` | 該次輸入或寫入意圖 | 修正輸入或由使用者處理衝突；不盲目自動重送相同錯誤，不為避開冪等衝突生成新 C1 |
| `RATE_LIMITED` | 被限速的請求／動作，不是所有工作階段 | 依下方等待值規則等待；重試時沿用原意圖與冪等鍵。不刷新以逃避限制；驗證操作仍受唯一驗證流程的次數限制 |
| `CURSOR_INVALID`／`CURSOR_EXPIRED`，來自 A08／A11／A19 | 該 REST 清單／歷史查詢 | 只重啟該查詢首頁；不清除使用者事件流游標、不送 W13 |
| `SYNC_RESET_REQUIRED`，來自使用者事件流／啟動同步 | W13–W16 同步範圍 | 依既有 W13／W14 完整快照恢復；未完成不安裝 H。WSS 中其他參數錯誤不等於全部重設；內部操作 9 的 CURSOR_INVALID 由節點規則處理，不挪用成用戶端 REST 游標規則 |
| `OUTCOME_UNCONFIRMED`、寫入回應／W06 遺失 | 原寫入意圖 | 不宣稱成功或回滾。W05 保留同一 C1 與承載資料；有 Idempotency-Key 的操作沿用原鍵值查回同一結果。A03 按唯一認證流程；無冪等保障的操作不能泛用盲重試 |
| `PERSISTENCE_FAILED` | 已知回滾的寫入 | 不回成功 ACK；可重試時仍保留原意圖／鍵值，不把它當憑證失效 |
| `DEPENDENCY_UNAVAILABLE`、連線中斷／心跳逾時 | 依賴／連線或該請求 | 沒有證據時不假定認證失效。權杖仍有效且未被判撤銷時重連 W01／W02，再以原游標同步；待送寫入按上一列的不明結果處理。權杖已到期才轉 FB；節點暫停／關線沿用既有狀態表 |
| `UPLOAD_NOT_READY` 或物件儲存傳輸失敗 | 該附件／上傳嘗試 | 未就緒不送 W05／A06；核對同嘗試的 A21。上傳授權過期時以新 `Idempotency-Key` 重新 A20，建立新附件嘗試；每附件只做一次上傳嘗試，不續期。GCS 的 403／網路錯誤不是 HINE W17 的 UNAUTHENTICATED，不因此刷新登入 |

**`retry_after_ms` 的唯一規則：**
- REST 位於 `error.details.retry_after_ms`；W17 位於 `payload.retry_after_ms`。保留可省略性；提供時必須是非 null、非負、安全整數的毫秒值（0 可表示不用額外等待），字串／負值／小數均無效。
- 發送端在 `RATE_LIMITED` 且 `retryable:true`、並知道安全的最早重試延遲時，必須提供該值；不知道則省略，不用 null／猜測的 0 代替。其他錯誤不要求此欄位，`retryable:false` 不因附值就變成可自動重試。
- 接收端只有在該值有效時才算「收到回應時點＋延遲」。省略／無效時顯示限速、停止該動作的**自動定時重試**，保留已知的較晚等待截止；不做未定義值的加法、不把缺少當成 0。使用者可手動再試，但不能跳過已有截止或重新取得 C6 恢復額度。
- A03 正常需要時自動刷新一次；等待 10 秒仍無法確認結果、收到 401 或刷新失敗，就停止 WSS／自動刷新、清除本機可用認證狀態並提示重新登入。舊 Cookie 寬限 0 秒，不重播舊刷新請求、不做跨分頁接班；`RATE_LIMITED` 有效 `retry_after_ms` 時最多再自動嘗試一次，省略／無效時停止自動刷新，由使用者手動操作，絕不無限自動重試。伺服器錯誤／網路問題不得顯示成密碼錯誤；一般服務故障依 C13 處理。

<a id="field-presence"></a>
### 欄位存在性、可省略與 null

`required` 表示鍵必須存在；`optional`／`?` 表示可省略；`T|null` 表示存在時允許 null，**不代表可省略**。未標可為 null 的存在欄位不得傳 null。聯集／判別欄位決定哪些欄位必填或不得出現：文字訊息必填 `text`、不帶 `attachment_id`；附件訊息相反。A06 至少出現一個修改欄位；省略代表不修改，avatar_attachment_id:null 才是移除頭像。各型別的具體規則優先於表格簡寫。

<a id="shared-scalar-types-and-privacy"></a>
### 共用純量型別與隱私

- `EntityID`：不透明的伺服器簽發 JSON 字串，本輪工作上限 128 個 Unicode 碼點（見[字元計數](#string-length-counting)與[近期基線](#integration-baseline)）；不一定是 UUID。`message_id`、`client_message_id` 和 `event_id` 以外的 ID 都是不透明字串。
- `DeviceID`：伺服器核發的不透明識別碼，僅作裝置／本機資料分區識別，不是登入憑證。同帳號、同瀏覽器且本機 DeviceStore 尚在時重用；清除網站資料、遺失儲存或重新安裝後視為新裝置重新核發；不做指紋或舊裝置找回。切換帳號須重新驗證並使用該帳號自己的綁定與儲存分區；同一瀏覽器設定檔同時一帳號、一個可操作分頁。
- 公開的 `user_id` 和內部的 `subject_id` 是不同的身分型別。後端 B 會進行對應；`subject_id` 絕不是用戶端欄位。
- `UUID`：UUID 字串；`message_id`、`client_message_id`、`event_id` 和回應關聯 ID 必填。
- `Timestamp`：ISO-8601 UTC 字串；具權威性的時間戳記由伺服器產生。
- `OpaqueCursor`：由伺服器簽發的不透明字串，與使用者／事件流世代或其 REST 查詢綁定；無法解碼，也不能用於授權存取。
- `Title`：字串；1–80 個 Unicode 碼點仍是群組串接前的候選，依[字元計數](#string-length-counting)。不阻擋本輪一對一的 title:null，不宣稱已取得群組對接確認。
- `UserSummary`：`{id:EntityID,display_name:string,avatar_attachment_id:EntityID|null}`；所有欄位皆必填。若頭像不存在或不可見，則為 null。摘要不包含電子郵件。
- `UserProfile`：包含所有 UserSummary 欄位，另加必填的 `email:string`；只有本人和後端 B 可以查看電子郵件。密碼只會出現在 A01/A02 請求中，絕不會出現在回應、記錄或 WSS 訊框中。
- `AccessSession`：`{access_token:string,expires_at:Timestamp,user_id:EntityID,device_id:DeviceID,session_generation:int}`；所有欄位皆必填／不可為 null。更新憑證是 HTTP-only Secure/SameSite Cookie，絕不會以 JSON 傳送；由後端 B 以 `Set-Cookie` 設定、瀏覽器管理，前端程式碼無法讀取（見[分工](#refresh-cookie-roles)）。A01 僅回傳 UserProfile；A02/A03 回傳 AccessSession。
- `SessionContext`：判別欄位 `state` 恰好是 `"authenticated"`、`"refreshing"` 或 `"logged_out"` 其中之一（`state` 是本輪對前端模組型別的命名補足，SessionContext 只在 FB／FA 之間使用，不傳到伺服器；不增加 AccessSession、W02 或任何公開 API／事件欄位）。`authenticated` 的 `user_id,device_id,access_token,expires_at,session_generation` 均非 null；`refreshing` 的 `user_id,device_id,session_generation` 非 null，且 `access_token,expires_at` 為 null；`logged_out` 的 `state` 仍為 `"logged_out"`，五個工作階段資料欄位 `user_id,device_id,access_token,expires_at,session_generation` 全為 null。由前端 B 負責。安裝範圍的 DeviceStore 與 SessionContext 分開，且可在登出後保留各帳戶的 device_id；`logged_out` SessionContext 的五個工作階段資料欄位仍為 null。A02 僅會為同一帳戶重用已儲存的 DeviceID。A05 `UserProfile.id` 只會與公開的 `user_id` 比較，不會與內部的 `subject_id` 比較。
- 內部 JWT 主體 `subject_id` 會在伺服器端映射為公開的 `user_id`；絕不會從用戶端接受或傳回。DeviceID 用於識別已綁定的裝置，不是憑證。

<a id="string-length-counting"></a>
#### 字元計數：跨語言共用規則

EntityID、Title、text 的長度按 JSON 解碼後的 Unicode 碼點計算，不按 UTF-8 位元組、UTF-16 碼元或畫面上的字素叢集計算；不在計數前自動 trim 或 Unicode 正規化。JavaScript 可用 `Array.from(value).length`，Python 可用 `len(value)` 計算有效 Unicode 字串；其他語言採等價計數，實作方式不強制一致。

| JSON 字串範例 | Unicode 碼點數 | 本輪文字結果 |
|---|---|---|
| `""` | 0 | 不接受：W05 回 W17 INVALID_ARGUMENT，不寫入／不回成功 ACK |
| `"A"` | 1 | 在文字長度範圍內 |
| `"\uD83D\uDE00"`（😀） | 1 | 在文字長度範圍內；不是 2 個 UTF-16 碼元 |
| `"e\u0301"`（e 加組合重音） | 2 | 在文字長度範圍內，不先正規化成單一碼點 |
| 4096 個 `"A"` 或 4096 個 `"😀"` | 4096 | 長度合法；仍須通過其他既有驗證 |
| 4097 個 `"A"` 或 4097 個 `"😀"` | 4097 | 不接受：W05 回 W17 INVALID_ARGUMENT，不寫入／不回成功 ACK |

超過 EntityID 本輪上限的輸入依各操作既有 INVALID_ARGUMENT 處理；UUID、OpaqueCursor 不套用 EntityID 上限。Title 邊界在群組輪共同確認後才列入該輪驗收。

<a id="user-conversation-and-membership-types"></a>
### 使用者、對話與成員資格型別

- `ContactView`：必填且非 null 的 `user:UserSummary`、`added_at:Timestamp`。`presence:"online"|"offline"|"unknown"` 在 A08 必填，在 A09 可省略；若存在則非 null。線上狀態是後端 A／Redis 的暫時狀態，不是推播狀態。
- `ConversationSummary`（A11）：必填 `id:EntityID`、`type:"direct"|"group"`、`title:Title|null`（一對一為 null）、`unread_count:int>=0`（計算規則見 [C14](#unread-count)）。不要求 `members` 或 `created_at`。
- `ConversationDetail`（A12）：包含所有 ConversationSummary 欄位，另加必填的 `members:MemberView[]`、`created_at:Timestamp`、`membership_version:int|null`（群組 >=1；一對一為 null）。只有目前獲授權的成員可以讀取。
- `ConversationCreateResult`（A13/A14）：必填 `id,type,title,member_ids:EntityID[],membership_version:int|null`；群組建立者包含在 member_ids 中，一對一的 membership_version 為 null。
- `ConversationMutationResult`：必填 `id,type,title,membership_version:int>=1`（A15）。
- `MemberView`：必填 `user_id:EntityID`、`role:"admin"|"member"`。`MemberMutationResult` 另加必填的 `membership_version:int>=1`。
- `BootstrapConversation`（W14）：必填 `id,type,title,unread_count,my_role:"admin"|"member"|null,recent_messages:MessageSnapshot[]`；一對一的 `title` 和 `my_role` 為 null。近期訊息是完整訊息快照，不只是 ID；完整成員清單來自 A12。

<a id="messages-receipts-attachments-and-sync"></a>
### 訊息、回條、附件與同步

- `MessageView`（A19）：必填且非 null 的 `id:UUID,event_id:UUID,conversation_id:EntityID,sender_id:EntityID,created_at:Timestamp,order_key:20 位 ASCII 數字字串,type:"text"|"image"|"file"`；必填但**可為 null** 的 `receipt:ReceiptProjection|null`（無可見一對一回條或群組回條不適用時為 null，不可省略）。若為文字訊息，必填 `text:string`（本輪工作範圍 1–4096 個 Unicode 碼點，依[字元計數](#string-length-counting)），並省略 `attachment_id`。若為圖片／檔案訊息，必填 `attachment_id:EntityID`，並省略 `text`。可省略的 `client_message_id:UUID` 僅原始寄件者可見。`order_key` 不是同步游標；編碼／比較見[排序規則](#ordering-pagination)。
- `MessageSnapshot` 具有與 MessageView 相同的欄位和可見性，並代表完整的近期內容。W07/W16 將頂層 event_id→MessageView.event_id、`timestamp`→`created_at`、conversation_id 和 sender_id 對應至相應欄位，並將 `payload.message_id`→MessageView.id。W07 的 C1 僅限寄件者。
- `ReceiptProjection` 僅為一對一回條 `{kind:"direct",message_id:UUID,recipient_id:EntityID,status:"delivered"|"read",updated_at:Timestamp}`；群組 `MessageView.receipt`／`MessageSnapshot.receipt` 為 null，本版不做群組彙總。後端會儲存每位收件者的個別狀態；待處理是用戶端 UI 狀態，不是已儲存的回條值。
- `AttachmentView` (A21)：必填且不可為 null 的 `id:EntityID,scope:"avatar"|"conversation",uploader_id:EntityID,kind:"image"|"file",filename:string,content_type:string,size_bytes:int>0,sha256:string`（64 個十六進位字元）、`state:"pending"|"ready",created_at:Timestamp`；必要但**可為 null** 的 `conversation_id:EntityID|null`。`scope=avatar` 必須明確指定 null 對話、`image` 類型及擁有者上傳者。對話範圍必須指定非 null 對話，並於建立／下載時檢查成員資格。僅支援 JPEG、PNG、PDF，最多 10,485,760 bytes，檔名 1–255 Unicode 字元；GCS 物件金鑰不會公開；A21 是擁有者完成上傳，不是收件者中繼資料查詢。
- `UploadGrant` (A20)：必填且不可為 null 的 `attachment_id:EntityID,upload_attempt_id:EntityID,upload_url:string`（短效 HTTPS 簽署 URL）、`expires_at:Timestamp`、`required_headers:object<string,string>`。只有附件擁有者會收到此項；絕不可記錄 URL 或將其放入訊息／事件；有效 10 分鐘。傳輸方式見[簽署網址上傳交接](#signed-upload-contract)。
- `DownloadGrant` (A22)：必填且不可為 null 的 `download_url:string,expires_at:Timestamp,content_type:string,filename:string,size_bytes:int>0`；有效 5 分鐘。中繼資料來自 A21 核驗快照，見[附件接收端中繼資料](#attachment-handoff)。
- `SyncBootstrapPage`（W14）：必填 `snapshot_id:EntityID,start_cursor:OpaqueCursor,conversations:BootstrapConversation[],next_page_token:OpaqueCursor|null,has_more:boolean`。每頁最多 100 個邏輯項目。只有在同一快照的所有頁面都已暫存，且投影已原子切換後，才安裝 start_cursor。
- `SyncBatch`（W16）：必填 `snapshot_boundary:OpaqueCursor,events:WsEnvelope[],next_cursor:OpaqueCursor,has_more:boolean`。每次最多回傳 100 個事件並掃描最多 1000 個事件流位置（包含隱藏的篩選位置）；到上限依游標續傳，未掃完不得當同步完成。即使沒有可見事件，也可能安全地推進游標；真正空的掃描則不會推進。
- `DeviceTokenStatus` (A23)：本版範圍外（2026-10-01 PM 決議）；保留型別識別，不提供推播權杖 API。
- `HealthResponse`：必填 `status:"ok"|"unready",service:"api"|"realtime",timestamp:Timestamp,dependencies:{postgresql:"ok"|"fail"|"not_checked",redis:"ok"|"fail"|"not_checked"}`；可省略 `reason:string`（除非適用可公開的就緒原因，否則省略；若存在則不可為 null）。僅供內部使用；存活檢查會回傳 200 且不檢查相依項目；必要相依項目皆就緒時，就緒檢查回傳 200，否則回傳 503。`CONFIG_MISSING` 可指出缺少設定，但不得指明或揭露其值。`dependencies` 各值只描述本次檢查：`ok` 表示該服務在這次就緒檢查中實際檢查且成功；`fail` 表示實際檢查失敗；`not_checked` 表示本次未檢查，或該服務不直接使用該相依項目（`api` 不直接連 Redis，`realtime` 不直接連 PostgreSQL）。未執行檢查不得回 `ok`；存活檢查一律回 `not_checked`。

<a id="rest-api"></a>
<a id="3-rest-api-registry-a01a25"></a>
## 3. REST API 登錄表 A01–A25

以下所有路徑均相對於單一基底 URL `https://hine.run.place`；將其與顯示的 `/api/v1/...` 路徑組合，即構成完整公開路徑。本版提供 A01–A22，均由後端 B 提供；A23–A25 僅保留 ID 與錨點，本版範圍外、不提供路由。除非標示為公開／僅限 Cookie，否則請使用有效的 Bearer 存取 JWT。除非明確標示為可省略，否則欄位皆為必填；可為 null 表示值可為 null，但不代表可省略（見[欄位存在性](#field-presence)）。GET 可安全重試；204 沒有本文。清單回應使用通用清單封套；A08／A11／A19 首頁與 `limit` 補足見[REST 分頁](#rest-pagination)。REST 游標錯誤僅影響相關清單／歷史查詢，絕不會重設 WSS 事件流。

| ID / operationId | 方法與路徑 | 請求 → 回應；狀態碼 | 授權、錯誤與重試／金鑰行為 |
|---|---|---|---|
| <a id="api-a01"></a>A01 `registerUser` | POST `/api/v1/auth/register` | `{email,password,display_name}` → UserProfile；201 | 公開。INVALID_ARGUMENT、CONFLICT、RATE_LIMITED；重複電子郵件會回傳 409，若回應不確定，不得改用新電子郵件繞過。無工作階段回應。 |
| <a id="api-a02"></a>A02 `login` | POST `/api/v1/auth/login` | `{email,password,device_id:DeviceID\|null}` → AccessSession；200 + 更新憑證 Cookie | 公開；僅首次安裝簽發 DeviceID 時可為 null。UNAUTHENTICATED、RATE_LIMITED；結果不確定時透過登入解決，而非建立第二個工作階段儲存區。 |
| <a id="api-a03"></a>A03 `refreshSession` | POST `/api/v1/auth/refresh` | 無 JSON 主體；更新憑證 Cookie → AccessSession；200 + 輪替後的 Cookie | 有效的更新憑證 Cookie。UNAUTHENTICATED、RATE_LIMITED；舊 Cookie 不會無限期重複使用。 |
| <a id="api-a04"></a>A04 `logout` | POST `/api/v1/auth/logout` | 無主體 → 無主體；204 | 目前的工作階段 Cookie；具冪等性。UNAUTHENTICATED；登出成功後撤銷目前裝置工作階段。 |
| <a id="api-a05"></a>A05 `getMe` | GET `/api/v1/users/me` | 無主體 → UserProfile；200 | 本人個人檔案。UNAUTHENTICATED；可安全重試。 |
| <a id="api-a06"></a>A06 `updateMe` | PATCH `/api/v1/users/me` | 至少一項 `{display_name:string,avatar_attachment_id:EntityID\|null}` → UserProfile；200 | 本人個人檔案。INVALID_ARGUMENT、UNAUTHENTICATED、FORBIDDEN、UPLOAD_NOT_READY；頭像必須是本人已就緒且屬於頭像範圍的附件；null 會移除頭像。 |
| <a id="api-a07"></a>A07 `getUserSummary` | GET `/api/v1/users/{user_id}` | 無主體 → UserSummary；200 | 已驗證。UNAUTHENTICATED、NOT_FOUND、RATE_LIMITED；隱藏的頭像會回傳 null，絕不回傳電子郵件。 |
| <a id="api-a08"></a>A08 `listContacts` | GET `/api/v1/contacts?cursor={cursor}&limit={limit}` | 無主體 → ContactView[] + `meta.next_cursor`；200 | 本人聯絡人。UNAUTHENTICATED、CURSOR_INVALID、CURSOR_EXPIRED；任一游標錯誤只影響此 REST 查詢。未知的在線狀態會回報為未知。 |
| <a id="api-a09"></a>A09 `addContact` | POST `/api/v1/contacts` | `{user_id}` → ContactView；新增時 201／已存在時 200 | 本人清單。INVALID_ARGUMENT、UNAUTHENTICATED、NOT_FOUND；不會重複新增相同擁有者／使用者。 |
| <a id="api-a10"></a>A10 `removeContact` | DELETE `/api/v1/contacts/{user_id}` | 無主體 → 無主體；204 | 本人清單。UNAUTHENTICATED；重複刪除會回傳 204，且不會移除對話記錄。 |
| <a id="api-a11"></a>A11 `listConversations` | GET `/api/v1/conversations?cursor={cursor}&limit={limit}` | 無主體 → ConversationSummary[] + `meta.next_cursor`；200 | 本人有權存取的清單。UNAUTHENTICATED、CURSOR_INVALID、CURSOR_EXPIRED；僅限本機復原，不是 WSS 事件流。 |
| <a id="api-a12"></a>A12 `getConversation` | GET `/api/v1/conversations/{conversation_id}` | 無主體 → ConversationDetail；200 | 目前有權存取的成員。UNAUTHENTICATED、NOT_FOUND；版本落差會透過重新擷取 A12 來調和。 |
| <a id="api-a13"></a>A13 `getOrCreateDirectConversation` | POST `/api/v1/conversations/direct` | `{peer_user_id}` → ConversationCreateResult；新建 201 / 已存在 200 | 已驗證。INVALID_ARGUMENT、UNAUTHENTICATED、NOT_FOUND、CONFLICT；兩位使用者組成的無序配對具有唯一性。 |
| <a id="api-a14"></a>A14 `createGroup` | POST `/api/v1/conversations/groups` | `{title,member_ids:EntityID[]}` → ConversationCreateResult；201 | 已驗證；必須提供 Idempotency-Key。INVALID_ARGUMENT（member_ids 含建立者超過 50 人）、UNAUTHENTICATED、CONFLICT、IDEMPOTENCY_CONFLICT；相同鍵值／不同內容回傳 409。上限 50 人含建立者；建立者為 admin；提交後執行 W11。加入界線見 [加入界線](#join-boundary)。 |
| <a id="api-a15"></a>A15 `renameGroup` | PATCH `/api/v1/conversations/{conversation_id}` | `{title}` → ConversationMutationResult；200 | 管理員。INVALID_ARGUMENT、UNAUTHENTICATED、FORBIDDEN、NOT_FOUND；重試相同標題具冪等性；提交後執行標題變更 W20。 |
| <a id="api-a16"></a>A16 `addGroupMember` | POST `/api/v1/conversations/{conversation_id}/members` | `{user_id}` → MemberMutationResult；新增 201 / 已存在 200 | 管理員。INVALID_ARGUMENT、UNAUTHENTICATED、FORBIDDEN、NOT_FOUND、CONFLICT（群組已滿）；最多 50 人含管理員；新增成員只可讀加入界線之後訊息；提交後執行 W11，不執行 W12。 |
| <a id="api-a17"></a>A17 `changeGroupMemberRole` | PATCH `/api/v1/conversations/{conversation_id}/members/{user_id}` | `{role:"admin"\|"member"}` → MemberMutationResult；200 | 管理員。INVALID_ARGUMENT、UNAUTHENTICATED、FORBIDDEN、NOT_FOUND、CONFLICT；僅 `admin`／`member`；不得降級最後一位 admin；提交後執行角色變更 W20。 |
| <a id="api-a18"></a>A18 `removeGroupMember` | DELETE `/api/v1/conversations/{conversation_id}/members/{user_id}` | 無本文 → 無本文；204 | 管理員或自行退出。UNAUTHENTICATED、FORBIDDEN、NOT_FOUND、CONFLICT；不得移除／退出最後一位 admin；重複的有效刪除具冪等性；提交後執行 W12，不封鎖。 |
| <a id="api-a19"></a>A19 `listMessages` | GET `/api/v1/conversations/{conversation_id}/messages?before={history_cursor}&limit={limit}` | 無本文 → MessageView[] + `meta.next_cursor`；200 | 已授權的歷史訊息讀取者。UNAUTHENTICATED、NOT_FOUND、CURSOR_INVALID、CURSOR_EXPIRED；依 order_key/message_id 由新到舊排序；歷史游標不是 SyncCursor。 |
| <a id="api-a20"></a>A20 `createUpload` | POST `/api/v1/uploads` | `{scope:"avatar"\|"conversation",conversation_id:EntityID\|null,filename,content_type,size_bytes,sha256}` → UploadGrant；201 | 必須提供 Idempotency-Key。INVALID_ARGUMENT、UNAUTHENTICATED、FORBIDDEN、PAYLOAD_TOO_LARGE（超過 10,485,760 bytes）、UNSUPPORTED_MEDIA_TYPE（非 JPEG／PNG／PDF）、IDEMPOTENCY_CONFLICT。檔名 1–255 Unicode 字元；頭像範圍要求 `conversation_id` 為 null；對話範圍需目前授權。上傳授權 10 分鐘；過期用新 Idempotency-Key 重新 A20 建新嘗試，不續期。 |
| <a id="api-a21"></a>A21 `completeUpload` | POST `/api/v1/uploads/{attachment_id}/complete` | `{upload_attempt_id,sha256}` → `AttachmentView(state="ready")`；200 | 擁有者。UNAUTHENTICATED、FORBIDDEN、UPLOAD_NOT_READY、CONFLICT；驗證實際 GCS 類型／大小／雜湊；僅接受目前嘗試，同一已完成嘗試回傳原就緒結果；每附件僅單次上傳嘗試。 |
| <a id="api-a22"></a>A22 `getAttachmentDownload` | GET `/api/v1/attachments/{attachment_id}/download` | 無本文／查詢參數 → DownloadGrant（含 `filename`,`size_bytes`）；200 | 擁有者或已授權檢視者。UNAUTHENTICATED、FORBIDDEN、NOT_FOUND、UPLOAD_NOT_READY、DEPENDENCY_UNAVAILABLE；每次重新檢查對話權限與加入界線；下載授權 5 分鐘，URL 到期後重新 A22。 |
| <a id="api-a23"></a>A23 `upsertPushToken` | PUT `/api/v1/devices/{device_id}/push-token` | 本版範圍外（2026-10-01 PM 決議） | 保留 ID／錨點；本版不提供推播權杖 API。 |
| <a id="api-a24"></a>A24 `deletePushToken` | DELETE `/api/v1/devices/{device_id}/push-token` | 本版範圍外（2026-10-01 PM 決議） | 保留 ID／錨點；本版不提供推播權杖 API。 |
| <a id="api-a25"></a>A25 `renewUploadGrant` | POST `/api/v1/uploads/{attachment_id}/renew` | 本版範圍外（2026-10-01 PM 決議） | 保留 ID／錨點；授權過期以新 Idempotency-Key 重新 A20 建立新附件嘗試，不續期。 |

<a id="join-boundary"></a>
#### 加入界線

新成員只可讀本次加入之後的群組訊息。伺服器在 A14／A16 成員加入交易中記錄加入界線：該對話當時最新的 `order_key`，以 C11 的 `(order_key,message_id)` 排序比較；只允許大於加入界線的訊息。退出後重加入以新界線重新開始。A19、W14、W16、A22（附件所屬訊息）與 C14-S 未讀計算使用同一可讀範圍；不能只在 UI 隱藏，也不回填加入前回條或未讀。G1 本機副本與 G2／G3 撤權規則分別適用。

<a id="complete-rest-requestresponse-sample-registry"></a>
### 完整 REST 請求／回應範例登錄表

`request:null` 表示沒有 HTTP 請求主體（不是字面上的 JSON null）；查詢／路徑／標頭輸入會在登錄表中標示。回應使用契約投影和通用 REST 封套。所有範例皆為合成資料。

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
  "A19":{"request":null,"status":200,"response":{"data":{"items":[{"id":"22222222-2222-4222-8222-222222222222","event_id":"00000000-0000-4000-8000-000000000007","conversation_id":"c1","sender_id":"u1","created_at":"2026-10-01T08:00:04Z","order_key":"00000000000000000041","type":"text","text":"Hello","receipt":{"kind":"direct","message_id":"22222222-2222-4222-8222-222222222222","recipient_id":"u2","status":"read","updated_at":"2026-10-01T08:00:07Z"},"client_message_id":"11111111-1111-4111-8111-111111111111"}]},"meta":{"next_cursor":null}}},
  "A20":{"request":{"scope":"avatar","conversation_id":null,"filename":"avatar.png","content_type":"image/png","size_bytes":1024,"sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},"status":201,"response":{"data":{"attachment_id":"a-avatar-1","upload_attempt_id":"attempt-1","upload_url":"https://storage.googleapis.com/example-private/avatar?sig=example1","expires_at":"2026-10-01T08:10:00Z","required_headers":{"Content-Type":"image/png","x-goog-if-generation-match":"0","Cache-Control":"no-transform"}}}},
  "A21":{"request":{"upload_attempt_id":"attempt-1","sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},"status":200,"response":{"data":{"id":"a-avatar-1","scope":"avatar","conversation_id":null,"uploader_id":"u1","kind":"image","filename":"avatar.png","content_type":"image/png","size_bytes":1024,"sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","state":"ready","created_at":"2026-10-01T08:00:00Z"}}},
  "A22":{"request":null,"status":200,"response":{"data":{"download_url":"https://storage.googleapis.com/example-private/avatar?generation=1&sig=download1","expires_at":"2026-10-01T08:05:00Z","content_type":"image/png","filename":"avatar.png","size_bytes":1024}}},
  "A23":{"status":"out_of_scope","note":"本版範圍外（2026-10-01 PM 決議）"},
  "A24":{"status":"out_of_scope","note":"本版範圍外（2026-10-01 PM 決議）"},
  "A25":{"status":"out_of_scope","note":"本版範圍外（2026-10-01 PM 決議）；過期以新 Idempotency-Key 建立新 A20 嘗試"}
}
```

A20 對話上傳請求變體：
```json
{"scope":"conversation","conversation_id":"c1","filename":"report.pdf","content_type":"application/pdf","size_bytes":4096,"sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}
```

<a id="websocket-events"></a>
<a id="4-websocket-registry-w01w22"></a>
## 4. WebSocket 登錄表 W01–W22

所有事件都是通用封套中的訊框。方向為用戶端→伺服器（C→S）或伺服器→用戶端（S→C）。除 W01 外，業務訊框都需要成功驗證。確切的必填欄位、方向與轉移如下：

| ID／事件 | 方向；承載資料與頂層欄位 | 行為 |
|---|---|---|
| <a id="event-w01"></a>W01 `auth.authenticate` | C→S `{access_token:string,device_id:DeviceID}` | 第一個業務訊框。驗證權杖與綁定的裝置；成功時進入 W02；無效時可能傳送 W17 後關閉，或直接關閉。 |
| <a id="event-w02"></a>W02 `auth.accepted` | S→C，與 W01 關聯：`{user_id:EntityID,device_id:DeviceID,expires_at:Timestamp,session_generation:int,heartbeat_interval_seconds:int,heartbeat_timeout_seconds:int}` | 公開身分與工作階段世代；本版心跳間隔 30 秒、逾時 90 秒。無游標影響。 |
| <a id="event-w03"></a>W03 `heartbeat.ping` | C→S `{nonce:string}` | `nonce` 必須非空；僅用於連線存活檢查，不會續期 JWT。[精確比對](#heartbeat-nonce)。 |
| <a id="event-w04"></a>W04 `heartbeat.pong` | S→C，與 W03 關聯 `{nonce:string}` | 回傳完全相同的 `nonce`，並與此連線上尚待回應的 W03 關聯；逾時只會關閉此連線。[比對規則](#heartbeat-nonce)。 |
| <a id="event-w05"></a>W05 `message.send` | C→S，頂層 `conversation_id`；`{client_message_id,type:"text"\|"image"\|"file",text? \| attachment_id?}` | 文字訊息只能包含 `text`；圖片／檔案訊息只能包含 `attachment_id`。同一 C1／相同承載資料可冪等處理；不同承載資料則衝突。 |
| <a id="event-w06"></a>W06 `message.ack` | S→C，與目前的 W05 相關聯，頂層 `conversation_id`；`{client_message_id,message_id,status:"persisted"}` | 僅在完整原子持久化後傳送；可能因中斷連線而遺失。 |
| <a id="event-w07"></a>W07 `message.created` | S→C，頂層 `conversation_id,sender_id`；`{message_id,client_message_id?,type,text? \| attachment_id?,order_key}` | 傳送給已授權的收件者；C1 僅傳送給寄件者。事件流重播時 event_id 穩定。即時事件永不推進游標。 |
| <a id="event-w08"></a>W08 `message.received` | C→S，頂層 `conversation_id`；`{message_id}` | 收件端把該訊息及後續同步／去重所需的識別資訊（至少 `message_id`、`conversation_id`）持久保存到本機後才傳送；不需先取得伺服器回條。回應為 W19；具冪等性。 |
| <a id="event-w09"></a>W09 `message.read` | C→S，頂層 `conversation_id`；`{message_id}` | 實際閱讀後傳送；已讀狀態具單調性，且表示已送達。 |
| <a id="event-w10"></a>W10 `message.status` | S→C，頂層 `conversation_id`；ReceiptProjection | 後端 B 已提交的一對一回條投影；群組回條為 null，不做群組彙總。也可透過同步復原。 |
| <a id="event-w11"></a>W11 `conversation.member_added` | S→C，頂層 `conversation_id`；`{member_id,role:"admin"\|"member",actor_id,membership_version}` | A14/A16 提交後傳送。新成員透過 A12 取得詳細資料；即時事件遺失時可透過事件流復原。 |
| <a id="event-w12"></a>W12 `conversation.member_removed` | S→C，頂層 `conversation_id`；本人：`{member_id,change:"removed",membership_version}`；其他成員也可包含 `actor_id` | A18 提交後傳送。被移除的成員只收到最少限度的本人通知，不會取得未授權的後續內容。 |
| <a id="event-w13"></a>W13 `sync.bootstrap.request` | C→S `{reason:"first_login"\|"cursor_reset",snapshot_id?,page_token?}` | 初始頁或續傳頁；續傳頁會綁定 snapshot_id 和 page_token。 |
| <a id="event-w14"></a>W14 `sync.bootstrap.page` | S→C，具關聯性；SyncBootstrapPage | 完整的已授權對話快照，包含近期訊息本文／狀態。在設定 start_cursor 前，先於同一快照下套用所有頁面。 |
| <a id="event-w15"></a>W15 `sync.request` | C→S `{cursor,snapshot_boundary?}` | 第一個請求使用已儲存的游標；後續請求使用同一輪的邊界。於重新連線／切回前景／定期核對時觸發。 |
| <a id="event-w16"></a>W16 `sync.batch` | S→C，具關聯性；SyncBatch | `next_cursor` 先原子套用事件和投影，再儲存游標。最多 100 事件、掃描 1000 個事件流位置；隱藏資料列仍可推進游標；游標過期時觸發 W17 SYNC_RESET_REQUIRED。 |
| <a id="event-w17"></a>W17 `error` | S→C，回覆請求時帶關聯： `{code,message,retryable,retry_after_ms?}` | [錯誤範圍與復原](#error-recovery)；`retry_after_ms` 可省略。 |
| <a id="event-w18"></a>W18 `presence.changed` | S→C `{user_id,presence:"online"\|"offline"\|"unknown"}` | 短暫且經授權的在線狀態；後端無法確認 Redis 狀態時為未知。 |
| <a id="event-w19"></a>W19 `receipt.ack` | S→C，與 W08/W09 關聯，頂層 `conversation_id`; `{message_id,status:"delivered"\|"read",changed}` | 回條請求結果；重複請求若為無操作，可能會傳回 `changed=false`。 |
| <a id="event-w20"></a>W20 `conversation.updated` | S→C，頂層 `conversation_id`; `{changes:{kind:"title",title:Title}\|{kind:"role",member_id,role:"admin"\|"member"},actor_id,membership_version}` | A15/A17 在提交後傳送給目前已獲授權的成員；版本缺口以 A12 修正。 |
| <a id="event-w21"></a>W21 `device.activity` | 本版範圍外（2026-10-01 PM 決議） | 保留 ID／錨點；不納入交付。 |
| <a id="event-w22"></a>W22 `device.activity.ack` | 本版範圍外（2026-10-01 PM 決議） | 保留 ID／錨點；不納入交付。 |

在巢狀 W16 中，每個事件都保留自己的 event_id 和 conversation_id；C1 仍僅供傳送者使用。W21／W22 本版範圍外；不與 W03／W04 心跳或 W18 線上狀態混用。

<a id="heartbeat-nonce"></a>
W03／W04 的 `nonce` 必填、非 null、非空 JSON 字串。發送端每次 W03 使用在本連線生命週期內不重用的值；不要求 UUID 或引入新的數值上限。W04 原樣回傳 `nonce`，`correlation_id` 必須是該條連線尚待回覆的 W03.event_id。只有 `nonce` 字串逐字相同且關聯／連線都相符才完成該次心跳；不轉數字、不修剪空白、不大小寫折疊。錯配、重複或舊連線的 W04 不延長本連線的存活判定；發送時間／逾時仍依 W02 宣告值，不影響活動租約。

<a id="wss-frame-examples"></a>
### WSS 訊框範例

以下 UUID 僅供示意；時間戳記皆為 UTC。存取權杖和 URL 範例皆為佔位值，並非憑證。

```json
{"event":"auth.authenticate","event_id":"10000000-0000-4000-8000-000000000001","timestamp":"2026-09-29T12:00:00Z","payload":{"access_token":"<jwt>","device_id":"d1"}}
```
```json
{"event":"auth.accepted","event_id":"10000000-0000-4000-8000-000000000002","timestamp":"2026-09-29T12:00:00Z","payload":{"user_id":"u1","device_id":"d1","expires_at":"2026-09-29T13:00:00Z","session_generation":1,"heartbeat_interval_seconds":30,"heartbeat_timeout_seconds":90},"correlation_id":"10000000-0000-4000-8000-000000000001"}
```
```json
{"event":"message.send","event_id":"10000000-0000-4000-8000-000000000005","timestamp":"2026-09-29T12:01:00Z","conversation_id":"c1","payload":{"client_message_id":"10000000-0000-4000-8000-000000000006","type":"text","text":"hello"}}
```
```json
{"event":"message.ack","event_id":"10000000-0000-4000-8000-000000000007","timestamp":"2026-09-29T12:01:00Z","conversation_id":"c1","payload":{"client_message_id":"10000000-0000-4000-8000-000000000006","message_id":"10000000-0000-4000-8000-000000000008","status":"persisted"},"correlation_id":"10000000-0000-4000-8000-000000000005"}
```
```json
{"event":"message.created","event_id":"10000000-0000-4000-8000-000000000009","timestamp":"2026-09-29T12:01:00Z","conversation_id":"c1","sender_id":"u1","payload":{"message_id":"10000000-0000-4000-8000-000000000008","client_message_id":"10000000-0000-4000-8000-000000000006","type":"text","text":"hello","order_key":"00000000000000000041"}}
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
{"event":"sync.bootstrap.page","event_id":"10000000-0000-4000-8000-000000000016","timestamp":"2026-09-29T12:06:01Z","correlation_id":"10000000-0000-4000-8000-000000000015","payload":{"snapshot_id":"s1","start_cursor":"opaque-user1-40","conversations":[{"id":"c1","type":"direct","title":null,"unread_count":0,"my_role":null,"recent_messages":[{"id":"33333333-3333-4333-8333-333333333333","event_id":"44444444-4444-4444-8444-444444444444","conversation_id":"c1","sender_id":"u2","created_at":"2026-09-29T11:59:00Z","order_key":"00000000000000000040","type":"text","text":"Earlier message","receipt":null}]}],"next_page_token":null,"has_more":false}}
```
```json
{"event":"sync.request","event_id":"10000000-0000-4000-8000-000000000017","timestamp":"2026-09-29T12:07:00Z","payload":{"cursor":"opaque-user1-40"}}
```
```json
{"event":"sync.batch","event_id":"10000000-0000-4000-8000-000000000018","timestamp":"2026-09-29T12:07:01Z","correlation_id":"10000000-0000-4000-8000-000000000017","payload":{"snapshot_boundary":"opaque-user1-41","events":[{"event":"message.created","event_id":"10000000-0000-4000-8000-000000000009","timestamp":"2026-09-29T12:01:00Z","conversation_id":"c1","sender_id":"u1","payload":{"message_id":"10000000-0000-4000-8000-000000000008","client_message_id":"10000000-0000-4000-8000-000000000006","type":"text","text":"hello","order_key":"00000000000000000041"}}],"next_cursor":"opaque-user1-41","has_more":false}}
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
{"event":"message.send","event_id":"10000000-0000-4000-8000-000000000026","timestamp":"2026-09-29T12:11:00Z","conversation_id":"c1","payload":{"client_message_id":"10000000-0000-4000-8000-000000000027","type":"image","attachment_id":"a2"}}
```

<a id="internal-handoffs"></a>
<a id="5-backend-a--backend-b-internal-contracts"></a>
## 5. 後端 A ↔ 後端 B 內部契約

這些是模組契約，不是公開端點，也不要求採用特定微服務架構。後端 A 會傳遞已驗證的主體／裝置資訊和請求關聯資訊；後端 B 會在每個變更資料的交易中重新檢查授權。將內部故障對應至共用的公開代碼，但不要暴露資料表名稱／私有欄位。

1. <a id="internal-validate-access"></a>`validateAccess(access_token:string,device_id:DeviceID)` → `{subject_id:EntityID,user_id:EntityID,session_id:EntityID,session_generation:int,expires_at:Timestamp,session_valid:boolean,invalidation_position:int}`。錯誤：UNAUTHENTICATED、DEPENDENCY_UNAVAILABLE。檢查簽章、簽發者／受眾、裝置綁定及撤銷狀態；`user_id` 為同次驗證取得的可信公開身分，`invalidation_position` 為驗證快照中的失效位置。
2. <a id="internal-authorize"></a>`authorize(subject_id:EntityID,device_id:DeviceID,session_id:EntityID,session_generation:int,action:"send"|"receive"|"read"|"history"|"attachment"|"manage_group",resource_type:"conversation"|"message"|"attachment",resource_id:EntityID)` → `{allowed:boolean,authorization_version:EntityID}`。錯誤：UNAUTHENTICATED、FORBIDDEN、NOT_FOUND、DEPENDENCY_UNAVAILABLE。僅供預先檢查；變更交易必須重新檢查，並驗證工作階段綁定。
3. <a id="internal-persist-if-absent"></a>`persistIfAbsent(subject_id:EntityID,device_id:DeviceID,session_id:EntityID,session_generation:int,conversation_id:EntityID,client_message_id:UUID,type:"text"|"image"|"file",payload:{text:string}|{attachment_id:EntityID},request_event_id:UUID)` → 恰好回傳 `created|existing_same` 其中之一，並附上 `{message_id:UUID,event_id:UUID,order_key:string,created_at:Timestamp,recipient_ids:EntityID[],status:"persisted",invalidation_position:int,membership_version:int|null}`。錯誤：UNAUTHENTICATED、FORBIDDEN、IDEMPOTENCY_CONFLICT、PERSISTENCE_FAILED、OUTCOME_UNCONFIRMED、DEPENDENCY_UNAVAILABLE。相同 C1／不同本文會觸發 IDEMPOTENCY_CONFLICT。訊息、C1 對應及每位必要收件者的事件流項目須在 W06 前原子提交。
4. <a id="internal-persist-receipt"></a>`persistReceipt(subject_id:EntityID,device_id:DeviceID,session_id:EntityID,session_generation:int,conversation_id:EntityID,message_id:UUID,kind:"delivered"|"read",request_event_id:UUID)` → `{message_id:UUID,status:"delivered"|"read",changed:boolean,updated_at:Timestamp,status_event_id:UUID|null,invalidation_position:int,observer_ids:EntityID[],membership_version:int|null}`。錯誤：UNAUTHENTICATED、FORBIDDEN、NOT_FOUND、PERSISTENCE_FAILED、OUTCOME_UNCONFIRMED、DEPENDENCY_UNAVAILABLE。狀態只能單向遞進；未變更的重複請求不會建立新的狀態事件；`status_event_id` 非 null 時 `observer_ids` 是 W10 收件者，否則為空陣列。
5. <a id="internal-read-bootstrap"></a>`readBootstrap(subject_id:EntityID,session_id:EntityID,session_generation:int,reason:"first_login"|"cursor_reset",snapshot_id?:EntityID,page_token?:OpaqueCursor)` → SyncBootstrapPage。錯誤：UNAUTHENTICATED、FORBIDDEN、CURSOR_INVALID、SYNC_RESET_REQUIRED、DEPENDENCY_UNAVAILABLE。快照狀態／最新位置會在短暫的 REPEATABLE READ 交易中一致讀取；分頁期間不可讓交易跨越網路請求。每頁前都要驗證工作階段與授權；快照過期時應重新開始，而非混用不同快照。
6. <a id="internal-read-feed"></a>`readFeed(subject_id:EntityID,session_id:EntityID,session_generation:int,cursor:OpaqueCursor,snapshot_boundary?:OpaqueCursor,limit:int)` → SyncBatch。錯誤：UNAUTHENTICATED、FORBIDDEN、CURSOR_INVALID、SYNC_RESET_REQUIRED、DEPENDENCY_UNAVAILABLE。固定延續邊界；可見與隱藏位置都要掃描；回傳已授權內容及最精簡的自身撤銷通知；不得讓一個已撤銷的對話阻塞事件流中其他位置。每頁重新驗證工作階段與授權。
7. <a id="internal-get-device-presence"></a>`getDevicePresence(subject_id:EntityID,device_id:DeviceID)` 回傳 `{online:"online"|"offline"|"unknown",activity:"unknown",valid_until:null}`；僅用於 A08 線上狀態，消費端不得使用 activity。<a id="internal-record-activity"></a>`recordActivity` 本版範圍外（2026-10-01 PM 決議）。
8. <a id="internal-dispatch-push-intent"></a>`dispatchPushIntent(message_id:UUID,recipient_user_id:EntityID,device_id:DeviceID)`：本版範圍外（2026-10-01 PM 決議）；不建立推播意圖或推播工作程序。

<a id="group-event-mapping-and-client-application"></a>
### 群組事件對應與用戶端套用

A14 建立操作會為建立者／初始成員發出 W11 投影。A15 重新命名會發出 `kind=title` 的 W20；A16 新增成員會發出 W11（不是 W12）；A17 變更角色會發出 `kind=role` 的 W20；A18 移除成員會發出 W12（不是 W13）。REST 呼叫端會依據 REST 結果更新自身檢視，不必等待 Pub/Sub。其他裝置會套用事件；新成員會擷取 A12；版本不連續時會擷取 A12。被移除的使用者在收到精簡 W12 或 A18 成功後離開該路由，且不會取得任何新的未授權本文。成員資格變更及每筆必要的使用者事件流項目會一併提交；Pub/Sub 僅加速提交後的傳遞。

<a id="在線狀態活動狀態與推播提案"></a>
<a id="presence-activity-and-push-proposal"></a>
### 在線狀態、活動狀態與推播

W21／W22、活動租約、Web Push 與原生推播本版範圍外（2026-10-01 PM 決議）；僅保留 W03／W04 連線心跳、W18 線上狀態及前端 Page Visibility 已讀判定。操作 7 `getDevicePresence` 的 activity 固定為 `"unknown"`，`valid_until:null`，消費端不得使用。

<a id="候選提交後通知與授權失效待批准"></a>
<a id="internal-notify-invalidation"></a>
### 提交後通知與授權失效（2026-10-01 PM 決議）

本節定義現行契約。C1–C6（C1–C4 依決議整合、C5 保留、C6 簡化）、C8–C14（C7 本版範圍外）、E1、G1–G3、S1–S2 均依 2026-10-01 PM 決議整合。A／W ID、持久化 ACK、游標／同步核心語義不變；不保留候選替代規則。

<a id="internal-applicability"></a>
#### 適用狀態

| 項目 | 狀態／現行定義 |
|---|---|
| 內部操作 1–6 與 9–10 | C1–C4、C8 及失效交接欄位已整合；C2 綁定工作階段；操作 7 僅查線上狀態，activity 固定 unknown；recordActivity／操作 8 本版範圍外 |
| A02 重複登入 | C5 已整合：同帳號同裝置舊工作階段於同一交易撤銷 |
| A03／A04 與即時遞送 | 已整合：依授權界線、狀態表及節點規則處理 |
| C6 A03 結果不明 | 已改寫：M3 單一恢復政策，見 [C6](#refresh-recovery-policy) |
| C7／W21／W22 | 本版範圍外（2026-10-01 PM 決議） |
| G1／G2／G3 | 已整合：裝置既有副本、撤權前待送內容及撤權後新查詢分別處理 |
| A20–A22、C9／C10 | 已整合：附件限制、核驗版本與 A22 中繼資料；A25 續期本版範圍外 |
| C11／C12 | 已整合：order_key 與 REST limit 規則及設定 |
| C13／C14 | 已整合：內部錯誤分層、C14-S 伺服器查詢值顯示 |

#### 三種保證

| 保證 | 定義 | 正確性依據 | 不依賴 |
|---|---|---|---|
| 授權失效 | 依提交序判定：撤銷後的資料不交付、舊身分的新操作被拒；工作階段及群組撤權前已授權資料依 15 秒界線處理 | PostgreSQL 交易內檢查與提交序；節點的新鮮狀態 | 任何通知是否送達、連線是否已關閉 |
| 連線清理 | 已失效的連線被標記失效、停止收發並關閉 | `realtime` 實例自後端 B 補齊失效紀錄；存取權杖到期 | 通知是否送達（通知只加速清理） |
| 通知傳遞 | 後端 B 的已提交結果經單一 `realtime` 實例與 Redis Pub/Sub 傳遞 | 無，盡力傳遞 | — |

關閉連線的時間上限只描述清理何時完成，不是可以繼續使用失效授權的時間。撤銷後還有哪些資料可能送出、最晚到何時，只由下文 D2／E1 規則決定。


<a id="authorization-boundary"></a>
#### 授權判定界線

**時點術語**

| 時點 | 定義 | 所在位置 |
|---|---|---|
| 資料產生 | 後端 B 的交易寫入資料（訊息、回條、成員異動），或讀取取得回應內容 | T2–T4 |
| 授權點 | 後端 B 為這筆資料做最後一次授權判定時所用的資料庫快照 | T2–T4 |
| 交易提交 | PostgreSQL COMMIT；讀取沒有提交 | T1–T3 |
| 應用程式排隊 | 節點收到通知或內部操作回應後，把訊框放入某條連線的送出佇列 | 節點 |
| 開始交付 | 節點把訊框交給該連線的寫入操作；此後不可撤回 | 節點 |

**順序定義：提交序。** 撤銷與資料的先後，一律以 PostgreSQL 的提交序判定。撤銷 R 在提交序中的位置是它的提交；資料 D 的位置是它的授權點。**R 先於 D，當且僅當 R 的提交已包含在 D 的授權點快照中。**

- **工作階段撤銷：** 事件交易的授權點，是 T2／T3 最後一個讀取計數器陳述式的快照；讀到的值就是 `invalidation_position = W`。計數器依提交序遞增且不跳號（T1），所以 R 先於 D 等同於 `r ≤ W`。讀取（W14、W16）的授權點是讀取快照；若 R 先於該讀取，讀取本身回 `UNAUTHENTICATED`。
- **群組撤權：** 訊息與回條交易以 `FOR SHARE` 鎖定對話列後才判定成員資格；A18 以 `FOR UPDATE` 鎖定同一列。所以 A18 先於 D，等同於 A18 在 D 取得該鎖前提交；此時 D 的收件者不含被移除者。
- **授權點不等於交易提交：** D 可能在 R 之後才提交，但只要它的授權點在 R 之前，就仍是「撤銷前資料」，適用 D2。與撤銷交易並行的交易屬於這種情況，不另立例外。

**撤銷的種類與作用範圍**

- **A03：** 工作階段目前世代由 `g` 變為 `g+1`，只有世代小於 `g+1` 的連線受影響；新世代連線與其他工作階段不受影響。
- **A04：** 撤銷目前裝置的工作階段（全部世代）；同帳號其他裝置不受影響。
- **A02（C5，行為變更）：** 建立新的 `session_id`，並在同一交易撤銷同帳號同裝置原有的有效工作階段（`reason:"replaced"`）。已撤銷的 `session_id` 不得復用，所以延遲到達的舊紀錄只影響它自己的 `session_id`。
- **A18：** 只撤銷被移除者在該對話的授權；不影響其他對話與任何工作階段，也不關閉連線。
- 本方案沒有以使用者為範圍撤銷所有連線的操作。

**交付與操作規則**

以下「R 撤銷的對象」：工作階段撤銷指 `session_id` 與世代相符的連線；群組撤權指被移除者在該對話的資料。

- **D1 撤銷後的資料不交付。** 授權點在 R 之後的資料，永不交付給 R 撤銷的對象，不論通知是否送達。
  - **事件（W07、W10、W11、W12、W20）：** 通知帶 `W`。節點在該事件開始交付前，必須已套用所有位置 `≤ W` 的紀錄（遞送閘門）；因此 `W ≥ r` 的事件遇到的相符連線都已標記失效。群組事件的收件者在提交時已排除被移除者。
  - **讀取回應（W14、W16）：**
    - 工作階段撤銷：授權點在 R 之後的讀取直接回 `UNAUTHENTICATED`，沒有回應內容。
    - 群組撤權：讀取不失敗，連線也不關閉。每頁重新授權；A19／A22 拒絕失權內容，W14 排除該對話，W16 過濾正文但保留被移除者自己的最小 W12；其他對話照常同步。
- **D2 撤銷前的資料：只在限定條件下交付；工作階段撤銷有明確上限。** 授權點在 R 之前、但在 R 提交後才開始交付的資料，包括已排隊的事件、並行交易產生的事件，以及在 R 之前讀取的 W14／W16 回應。所有資料開始交付時都須符合兩個共同條件：節點處於新鮮狀態（見[節點規則](#node-rules)），且連線的存取權杖未到期。
- **工作階段撤銷：** 另須節點尚未套用 R。節點套用 R 時，丟棄該連線佇列中所有尚未開始交付的訊框。R 提交後經過 `INVALIDATION_STALE_SECONDS` 才開始的交付，一定已套用 R；所以撤銷前資料最晚在提交後 15 秒內仍可能開始交付。這是有上限的延遲生效，不是立即生效。
- **群組撤權：只處理「撤權前已授權、服務端尚未開始交付」的內容。** 不與裝置已取得內容或撤權後新查詢合併決策，三者分別見[群組產品政策](#group-revocation-policy)。
- **E1 現行規則（2026-10-01 PM 決議）：** 對被移除者的該對話，A18 撤權位置為 `r`。套用 `r` 後不得再開始交付該對象該對話的舊授權內容；不依賴 A18 通知是否送達。最遲於 A18 提交後超過 `S = INVALIDATION_STALE_SECONDS = 15` 秒開始的交付，不得含舊授權內容。這是開始交付界線，不是網路抵達期限，不能追回已送出的資料；不以 60 秒移除紀錄保留窗作上限或放行依據。
- **D3 本地資料。** W18 線上狀態不經後端 B，沒有 `W`；其授權點視為節點最近一次完整補齊的開始時點，因此適用 D2 工作階段撤銷的條件與同一上限。W04 與 W17 是控制訊框，連線保留期間可以送出。
- **D4 新操作。**
  1. **經後端 B 的操作：** `authorize`、`persistIfAbsent`、`persistReceipt`、`readBootstrap`、`readFeed`（具 C2 工作階段綁定）與所有 REST 請求，都在交易或讀取快照內檢查工作階段。異動交易以 `FOR SHARE` 鎖定工作階段列，與 T1 序列化；被拒時，節點立即將該連線標記失效並關閉。
  2. **新 WSS：** R 之後 `validateAccess` 失敗；註冊競態見節點規則。
  3. W21、W22 本版範圍外；控制訊框依其各自規則處理。
- **開始交付前的檢查。** 通過遞送閘門只證明這筆事件不是 R 之後的資料（D1），不代表現在可以交付。每個訊框開始交付時，還要檢查連線未標記失效、存取權杖未到期、節點處於新鮮狀態（D2）。排隊時通過的檢查不能沿用到開始交付。

**D2 上限的推導。**
1. 節點只在「最近一次完整補齊的開始時點」距今不超過 `INVALIDATION_STALE_SECONDS` 時才交付資料。完整補齊是指 `readSessionInvalidations` 讀到 `has_more:false`。
2. 完整補齊在開始之後才於 PostgreSQL 讀取，所以一定包含開始前已提交的所有撤銷。
3. 若某次交付在 R 提交後超過 `INVALIDATION_STALE_SECONDS` 才開始，它所依據的完整補齊一定在 R 提交後才開始，因此已套用 R；相符的連線已被標記失效，不會交付。
4. 經過時間只用節點自己的單調時鐘量測，不比較不同主機的時鐘。

<a id="群組撤權三項分開批准的產品政策"></a>
<a id="group-revocation-policy"></a>
#### 群組撤權：三項分開處理的現行政策

1. **裝置已取得的歷史內容（G1）：** 裝置得知自己的 A18 成功或最小 W12 後，離開群組頁面並停止顯示不可存取內容；不新增退出後唯讀歷史頁。不承諾遠端安全抹除本機副本；離線且尚未得知撤權時可能仍顯示舊內容，截圖／下載檔無法追回。重新登入不同帳號不得讀取前帳號的本機投影。
2. **撤權前已授權的服務端待送內容（G2／E1）：** 依 [E1](#group-revocation-e1) 的 15 秒開始交付界線；不承諾資料抵達期限或追回已送出內容。
3. **撤權後新發起的查詢（G3）：** 新 A19／A22 不得重新取得群組內容；W14 排除該對話，W16 過濾正文但保留最小自身 W12。舊游標／頁面權杖不構成讀取權，每頁授權；其他對話繼續同步。已簽發下載 URL 到期前可能仍可用，不宣稱可即時追回。

<a id="e1服務端待送內容的主要推薦待批准"></a>
<a id="group-revocation-e1"></a>
#### E1：服務端待送內容的 15 秒開始交付界線（已整合）

沿用提交序與授權點定義。A18 提交位置為 `r`；事件授權點是 BB 最後授權快照，W14／W16 是各次讀取快照。`W < r` 為撤權前已授權待送內容，不因排隊或較晚提交變成新授權。對被移除者的該對話，節點尚未套用 `r`、仍新鮮且權杖未到期時，舊授權內容仍可能開始交付；套用 `r` 後不得再開始交付。最遲在 A18 提交後超過 `S = INVALIDATION_STALE_SECONDS = 15` 秒才開始的交付，不得含舊授權內容；這不是網路抵達期限，亦不追回已送出的資料。W14／W16 不得因拋棄舊回應而推進游標；W14 未完成不能安裝 H。保留識別被撤權使用者與對話所需的持久化紀錄及同步中繼資料；60 秒移除紀錄保留窗不是交付上限。

<a id="delivery-state-table"></a>
#### 交付與連線狀態表

「撤銷前資料」包括 D2、D3 的資料：已排隊或並行產生的事件、W14／W16 回應、W06／W19 回應與 W18。

| 狀態 | 連線 | 新操作 | 撤銷後資料（D1） | 撤銷前資料（D2、D3） | 關線 | 對應原文 | 驗收 |
|---|---|---|---|---|---|---|---|
| 1 正常：節點新鮮、連線未失效 | 保留 | 經後端 B 判定 | 由遞送閘門與收件者排除 | 可交付 | — | D1、D2 | [AC-N01](../testing/acceptance-matrix.md#ac-n01) |
| 2 事件的 `W` 大於已套用位置，補齊中 | 保留 | 照常 | 該事件等補齊完成後依 D1 判定 | 其他訊框照常 | — | 節點規則：遞送閘門 | [AC-N03](../testing/acceptance-matrix.md#ac-n03) |
| 3 補齊逾時（`NOTICE_CATCHUP_HOLD_MS`） | 保留 | 照常 | 放棄該事件在本節點的即時交付，由 W15／W16 補回 | 其他訊框照常（仍新鮮時） | 不因此關線 | 節點規則：遞送閘門 | [AC-N12](../testing/acceptance-matrix.md#ac-n12) |
| 4 R 已提交、節點尚未套用、仍新鮮 | 保留 | 經後端 B 的操作被拒，立即標記失效並關閉；新 W01 經補齊發現 R 而被拒 | 不交付（閘門先補齊 R） | 可交付，最晚到 R 提交後 `INVALIDATION_STALE_SECONDS` | 套用 R 時 | D2、D3 | [AC-N13](../testing/acceptance-matrix.md#ac-n13)、[AC-N15](../testing/acceptance-matrix.md#ac-n15)～[AC-N17](../testing/acceptance-matrix.md#ac-n17) |
| 5 節點已套用 R | 標記失效 | 全部拒絕 | 不交付 | 不交付；佇列中尚未開始交付的訊框丟棄 | 立即，盡力先送 W17 `UNAUTHENTICATED` | 套用一筆紀錄的節點規則 | [AC-N03](../testing/acceptance-matrix.md#ac-n03)、[AC-N14](../testing/acceptance-matrix.md#ac-n14) |
| 6 後端 B 無法連線，但仍新鮮 | 保留 | 經後端 B 的操作回錯誤，不回成功；新 W01 被拒 | 需補齊的事件逾時後放棄（同狀態 3） | 可交付，直到新鮮期滿 | — | 新鮮狀態的節點規則 | [AC-N04](../testing/acceptance-matrix.md#ac-n04) |
| 7 不新鮮（authority_stale） | 保留，只送 W04 與 W17 | 新 W01 回 W17 `DEPENDENCY_UNAVAILABLE`；經後端 B 的操作不回成功 | 不交付 | 不交付；佇列上限沿用 BA-08，超過即丟棄並由同步補回 | 存取權杖到期時 | 新鮮狀態的節點規則 | [AC-N04](../testing/acceptance-matrix.md#ac-n04)、[AC-N10](../testing/acceptance-matrix.md#ac-n10) |
| 8 由不新鮮恢復 | 先完整補齊並套用 | 恢復 | 依 D1 判定 | 依 D2 重新檢查後交付 | 補齊中發現已失效者立即關閉 | 新鮮狀態的節點規則 | [AC-N04](../testing/acceptance-matrix.md#ac-n04) |
| 9 存取權杖到期 | 關閉 | — | — | — | 到期時 | 存取權杖到期的節點規則 | [AC-N04](../testing/acceptance-matrix.md#ac-n04) |
| 10 已套用位置早於保留範圍（`CURSOR_INVALID`） | 全部關閉 | — | — | — | 立即，並從最新位置重新開始 | 位置過舊的節點規則 | [AC-N09](../testing/acceptance-matrix.md#ac-n09) |
| 11 群組撤權：被移除者在該對話 | 保留 | 該對話操作被拒；其他對話照常 | 收件者排除；新 W16 只含已授權內容與最小 W12，新 W14 不含該對話 | 依 E1：套用 r 後停止，最遲在 A18 提交後超過 15 秒才開始交付時不含舊內容 | 不關 | D1、D2、[E1](#group-revocation-e1) | [AC-N02](../testing/acceptance-matrix.md#ac-n02)、[AC-N18](../testing/acceptance-matrix.md#ac-n18)、[AC-N26](../testing/acceptance-matrix.md#ac-n26) |

<a id="使用者-feed-涵蓋範圍"></a>
#### 使用者事件流涵蓋範圍

0.4 原文中，每使用者事件流涵蓋 W07、W10、W11、W12、W20（見 W10、W16 定義，[群組事件對應](#group-event-mapping-and-client-application)，以及 BB-03、BB-05）。事件流不含 W17、W18、W21／W22，也不含工作階段失效。工作階段失效紀錄是持久化內部資料，不寫入事件流，也不回傳給用戶端。

<a id="候選內部型別"></a>
#### 現行內部型別

- <a id="internal-session-invalidation"></a>`SessionInvalidation`：`{position:int,session_id:EntityID,reason:"refresh"|"logout"|"replaced",min_valid_generation:int|null,committed_at:Timestamp}`，全部必填。
  - `position` 是正整數，嚴格遞增、不跳號，且與提交順序一致（[T1](#internal-transaction-order)）。
  - `reason:"refresh"`（A03）時，`min_valid_generation` 是新的目前世代，世代較小的連線失效。
  - `reason:"logout"`（A04）與 `reason:"replaced"`（A02 取代同裝置舊工作階段）時為 `null`，該工作階段全部世代失效。
  - 不含 `subject_id`、權杖或其他使用者資料。
- `RealtimeNotice`：Redis Pub/Sub 與 `publishCommitted` 共用的內部通知格式：`{notice_id:UUID,type:"conversation_events"|"session_invalidation",committed_at:Timestamp,invalidation_position:int,conversation_events?:ConversationEvents,session_invalidation?:SessionInvalidation}`。
  - 依 `type` 恰有一個內容欄位。
  - `session_invalidation` 類型的 `invalidation_position` 等於該紀錄的 `position`。
  - `conversation_events` 類型的 `invalidation_position`，是產生該事件的交易所讀到的 `W`。
- `ConversationEvents`：`{source:"W05"|"W08"|"W09"|"A14"|"A15"|"A16"|"A17"|"A18",conversation_id:EntityID,membership_version:int|null,deliveries:[{recipient_user_id:EntityID,envelope:WsEnvelope}]}`，`deliveries` 至少一筆。
  - 收件者由後端 B 在提交交易內決定。
  - `source` 為 A14–A18 時，`envelope` 由後端 B 產生，與該收件者事件流列的事件相同（同一 `event_id`）。`source` 為 W05／W08／W09 時，由處理請求的 `realtime` 實例依 `persistIfAbsent`／`persistReceipt` 的結果建構。
  - 一對一對話的 `membership_version` 為 `null`。
  - 通知超過候選大小上限時，後端 B 可拆成多則，每則各自獨立處理。

<a id="候選內部操作"></a>
#### 現行內部操作

9. <a id="internal-read-session-invalidations"></a>`readSessionInvalidations(after_position:int|null,limit:int)` → `{entries:SessionInvalidation[],next_position:int,head_position:int,has_more:boolean}`。
   - 提供者後端 B，呼叫者後端 A。
   - `after_position:null` 只回傳目前的 `head_position`（`entries` 為空），供節點啟動時使用；否則依位置遞增回傳位置大於 `after_position` 的紀錄。
   - `limit` 為 1–500。
   - 節點連續呼叫到 `has_more:false`，稱為一次「完整補齊」；它的開始時點是第一次呼叫送出的時點。
   - 錯誤：`UNAUTHENTICATED`（呼叫者服務身分無效）、`INVALID_ARGUMENT`、`CURSOR_INVALID`（位置早於保留範圍或大於最新位置）、`DEPENDENCY_UNAVAILABLE`。
   - 唯讀，可安全重試。
10. <a id="internal-publish-committed"></a>`publishCommitted(notice:RealtimeNotice)` → `{notice_id:UUID,published:true}`。
    - 提供者後端 A（任一 `realtime` 實例），呼叫者後端 B。
    - 只接受 `session_invalidation`，以及 `source` 為 A14–A18 的 `conversation_events`。W05／W08／W09 來源由後端 A 自行發布，傳入時回傳 `INVALID_ARGUMENT`。
    - 成功只代表接收請求的那一個實例已驗證通知並完成 Redis PUBLISH，不代表任何節點已遞送或已關線；Redis 回報的訂閱者數也不是完成訊號。
    - 錯誤：`UNAUTHENTICATED`、`INVALID_ARGUMENT`、`DEPENDENCY_UNAVAILABLE`（Redis 無法使用）。
    - 以 `notice_id` 達成冪等，重試必須沿用同一 `notice_id`。
    - 只能在交易提交成功後呼叫。

<a id="待批准既有操作的欄位與行為變更"></a>
<a id="internal-change-requests"></a>
#### C1–C14 決議變更清單（2026-10-01）

各項狀態與定義如下；已整合者為現行規則，範圍外者保留 ID 不作交付。

| 變更 | 類型 | 內容／狀態 | 理由 | 依賴 |
|---|---|---|---|---|
| C1 `validateAccess` | 內部欄位 | 已整合：輸出 `invalidation_position:int`，為驗證快照中的失效位置 | W01 註冊競態 | 操作 9 |
| C2 工作階段綁定 | 內部欄位 | 已整合：操作 2–6 必填 `session_id`、`session_generation`，由 `validateAccess` 傳入並驗證 | 經後端 B 操作依提交序生效 | 無 |
| C3 `persistIfAbsent` | 內部欄位 | 已整合：輸出 `invalidation_position:int`、`membership_version:int\|null` | D1 閘門及群組狀態 | 操作 9 |
| C4 `persistReceipt` | 內部欄位 | 已整合：輸出 `invalidation_position:int`、`observer_ids:EntityID[]`、`membership_version:int\|null` | 提交時決定 W10 觀察者 | 操作 9 |
| C5 A02 同裝置單一工作階段 | 行為 | 已整合：同帳號同裝置重登入時同交易撤銷舊工作階段，寫 `reason:"replaced"` | 防止舊連線繼續使用 | SessionInvalidation |
| C6 A03 結果不明 | 行為 | 已改寫：M3 單一刷新／重新登入終點，見 [C6](#refresh-recovery-policy) | 單操作分頁下簡化安全處理 | A03／FB |
| C7 多連線活動 | 範圍 | 本版範圍外（2026-10-01 PM 決議）；保留 `#activity-merge` 錨點 | 不做租約／活動合併 | 無 |
| C8 `validateAccess.user_id` | 內部欄位 | 已整合：可信公開 `user_id` 與 W02 同次驗證回傳 | 不推測公開身分 | 操作 1 |
| C9 A22 中繼資料 | 回應欄位 | 已整合：DownloadGrant 含必填 `filename`、`size_bytes` | 收件者附件顯示 | A22 |
| C10 簽署上傳 | 版本保護 | 已整合：獨立物件鍵、僅建立 PUT、A21 核驗版本、A22 固定簽核世代；每附件單次嘗試，過期新 A20 | 避免交付未核驗內容 | A20–A22 |
| C11 order_key | 排序 | 已整合：固定 20 位 ASCII 數字＋UUID 次排序 | 各端排序一致 | FA／BB |
| C12 REST `limit` | 分頁 | 已整合：預設 20、最大 50；非法值 `INVALID_ARGUMENT` | 一致限制 | A08／A11／A19 |
| C13 內部驗證分層 | 錯誤處理 | 已整合：`auth_layer` 區分 service_identity／user_session，依可信回覆決定登出或依賴錯誤 | 不把服務故障當登出 | 內部呼叫 |
| C14 `unread_count` | 計算規則 | 已整合 C14-S：只顯示伺服器最近查詢值；無本機合併 | 維持一致且簡化 | A11／A12／W14 |


<a id="c8後端-b--後端-a-可信公開身分待批准"></a>
<a id="public-identity-handoff"></a>
<a id="c8backend-b--backend-a-可信公開身分待批准"></a>
#### C8：後端 B → 後端 A 可信公開身分（已整合）

`validateAccess` 成功輸出必含非 null `user_id:EntityID`，由 BB 在同一驗證快照內查得，與該身分的 A02／A03.user_id、A05.id 一致。BA 將 `subject_id` 僅供內部操作、`user_id` 用於 W02／W07 和公開回條；不信任客戶端宣告，也不假設 JWT 有未定義 claim。無效映射不產生成功 W02。

<a id="c9附件接收端中繼資料待批准"></a>
<a id="attachment-handoff"></a>
<a id="c9附件接收端-metadata待批准"></a>
#### C9：附件接收端中繼資料（已整合）

收件者從 W07、A19、W14 或 W16 取得 `attachment_id` 後呼叫既有 A22。BB 確認附件就緒且呼叫者當下有權，回傳必填 DownloadGrant `{download_url,expires_at,content_type,filename,size_bytes}`；`filename`／`size_bytes` 來自 BB 保存並經 A21 核驗的中繼資料。

```json
{"data":{"download_url":"https://storage.googleapis.com/example-private/file?sig=example","expires_at":"2026-10-01T08:01:00Z","content_type":"application/pdf","filename":"notes.pdf","size_bytes":1024}}
```

<a id="c10簽署網址上傳交接待批准"></a>
<a id="signed-upload-contract"></a>
<a id="c10signed-url-上傳交接待批准"></a>
#### C10：簽署網址上傳交接（已整合）

**已有規則與本輪補足：** A21 驗證類型／大小／`sha256`、僅接受目前上傳嘗試，同一已完成嘗試冪等回傳原就緒結果。每個附件只建立一次上傳嘗試，授權過期即用新 Idempotency-Key 呼叫 A20 建立新附件嘗試；無 A25 續期。以下內部版本中繼資料、簽章標頭與交付規則共同構成 C10 現行契約，不新增 A／W API。

<a id="attachment-ready-invariant"></a>
**就緒不變條件：** 一個就緒 `attachment_id` 只能綁定一組由 BB 核驗的 `(upload_attempt_id, bucket, object_key, generation)` 與同次核驗的中繼資料快照。A21 的核驗結果／就緒提交、AttachmentView、C9 的 A22 中繼資料，以及 A22 URL 所指向的完整位元組都必須來自這組綁定。之後不得用另一個世代重新指派該就緒 ID；同內容／同檔名也不能豁免核驗。這是「不交付未核驗版本」的保證，不是物件永不遺失的可用性承諾。

1. **每個附件單次嘗試隔離。** BB 為每個 A20 嘗試在私有儲存桶配發唯一 object_key；不以使用者檔名當可重用物件鍵，不讓兩次上傳嘗試共用目標。相同 Idempotency-Key 的 A20 冪等重試回同一嘗試／目標；授權過期以新 Idempotency-Key 呼叫 A20 建立新附件及新目標。已就緒附件不重新開放上傳。
2. **上傳僅能建立，不依賴前端自律。** BB 仍簽發 XML API 的單次 `PUT`；FA／FB 傳送完整原始 File／Blob 位元組，不使用 multipart、JSON、base64，不附 HINE JWT／Cookie。UploadGrant.required_headers 必須包含相符的 `Content-Type`、`x-goog-if-generation-match:"0"` 與 `Cache-Control:"no-transform"`，所有值都納入 V4 標準化標頭／X-Goog-SignedHeaders（另含由瀏覽器管理的 `host`）。移除或改寫條件會使簽章驗證失敗，不能退回無條件 PUT。Host／Content-Length 由 HTTP 堆疊管理，DO CORS 必須允許所需標頭；CORS 本身不是防覆寫的安全界線。
   - 若同一物件鍵已有現存物件，GCS 會拒絕僅建立（僅建立）PUT，回應 **412 Precondition Failed**；內容相同或不同都一樣。**簽署網址不是一次性權杖**，未到期時可能重送；保護來自 GCS 原子前置條件，而不是「只呼叫一次」。
   - `0` 只檢查現存物件是否存在；刪除後可能再次允許建立，因此不能以刪除／重建「解決」412。BB／DO 不得覆寫、改動已核驗的內容／相關中繼資料，或讓例行清理刪除仍可交付的就緒物件；也不得讓用戶端取得 DELETE／中繼資料更新權限。僅清理已退出可完成狀態的廢棄嘗試，且清理按確切世代定位，object_key 不再配給其他嘗試。即使異常刪除後同一物件鍵出現新世代，就緒綁定仍不變，並依第 5 點失敗，而非改用新版本。
3. **新增的 BB 內部版本資料。** 待處理嘗試保存唯一儲存桶／object_key；核驗後的就緒記錄必須原子保存 `verified_upload_attempt_id`、`verified_object_key`、`verified_generation`、`verified_metageneration`，以及 `filename,kind,content_type,size_bytes,sha256` 的已核驗快照，儲存桶也屬固定綁定。世代／中繼世代以不失真的十進位字串保存，僅與同一物件比較，不轉為 JavaScript Number，也不以大小判定較新。這些是伺服器內部欄位，不加入 A21／A22 公開 JSON；URL 內的 GCS 世代參數由 BB 簽署，客戶端不組裝。
4. **A21 核驗與就緒提交。**
   - BB 從伺服器的嘗試對照取得目標，讀取 GCS 中繼資料以確定世代=`g`、中繼世代=`m`；完整讀取**指定 g 的原始位元組**，並以 g／m 前置條件核對同一版本的中繼資料。類型、實際位元組數、由 BB 計算的 SHA-256 必須符合原 A20 宣告與 A21 請求；不能信任前端聲稱的雜湊，也不能把 ETag 當作 SHA-256。拒絕非空 Content-Encoding，確認 no-transform，避免核驗的位元組與下載時轉碼的內容不同。
   - 若核驗期間中繼資料已變動、版本消失或前置條件不符，不提交就緒；完成前再次確認同一 g／m。提交 PostgreSQL 時，鎖定／條件更新該附件，重新檢查擁有者／授權、`state=pending` 與 current_upload_attempt_id 是否仍相符，並在**同一交易**中寫入就緒、版本綁定與核驗中繼資料。新 A20 嘗試只建立新的 attachment_id，不切換既有附件嘗試。
   - 同一已完成嘗試的相同 A21 重試，只回傳原先保存的就緒結果，不重讀最新版本、不重新核驗後改綁另一版本；不同嘗試／sha256 不得以冪等為由套用。此處不宣稱 PostgreSQL 與 GCS 具有跨系統原子交易；即使核驗後物件不可用，保存的引用也不能換版，下載依第 5 點拒絕。
5. **A22 固定交付已核驗版本。** 每次先執行既有讀取授權，再載入就緒的版本綁定與中繼資料快照，確認該 g 仍可讀，且 m 與核驗記錄一致。DownloadGrant 的 `filename`／size_bytes／content_type 取自保存的核驗快照，不取任意最新版本中繼資料。BB 簽發 GET URL 時必須含 **`generation=g`**，並將其納入標準化查詢／簽章；回應 Content-Type 也以簽入查詢的 `response-content-type` 綁定保存值。既有 DownloadGrant 欄位已足以承載，C9 的兩欄方案不變，不增加下載 required_headers 或公開 API。
   - 若 g 遺失、中繼資料版本不符或依賴不可查，A22 回傳既有 `DEPENDENCY_UNAVAILABLE`，不回傳另一版本的授權憑證，也不將就緒 ID 改指最新版本。若 URL 簽發後該 g 才變得不可用，GCS GET 可能失敗；FA／FB 只能重新請求 A22，針對同一綁定查核，不得移除世代、改動參數或自行改送最新物件。這不要求啟用 Object Versioning；若 g 未保留，就回報失敗。
6. **PUT／完成回覆遺失與衝突恢復。** PUT 200 只確認寫入，不代表就緒；W05／A06 仍須 A21 200 就緒。PUT 回覆遺失時，使用同一嘗試呼叫 A21；重送 PUT 仍帶原簽章的僅建立條件。遇到 412 只表示目標已有物件，**不是 HINE 上傳成功的證據**：使用同一嘗試呼叫 A21 核驗，符合才設為就緒；不符沿用既有 CONFLICT 拒絕，不能在該 attachment_id 上切換或續期嘗試。
   - 物件尚未存在時使用既有 UPLOAD_NOT_READY；舊嘗試、核驗內容／版本不符時使用既有 CONFLICT；依賴查詢無法完成時依共用 DEPENDENCY_UNAVAILABLE 處理，不把 412 當作認證過期而呼叫 A03。A21 就緒回覆遺失時，重試相同 A21，回傳原綁定結果。

以下為 C10 的 required_headers 範例（非已部署設定）：
```json
{"required_headers":{"Content-Type":"image/png","x-goog-if-generation-match":"0","Cache-Control":"no-transform"}}
```
§3 A20／A22 範例分別示意新附件嘗試與下載授權；版本規則、標頭、樣例與角色引用採同一不變條件，不可選擇性採用。

平台依據：[GCS XML API 的 PUT Object](https://docs.cloud.google.com/storage/docs/xml-api/put-object-upload)、[請求前置條件（0 與 412）](https://docs.cloud.google.com/storage/docs/request-preconditions)、[世代／中繼世代](https://docs.cloud.google.com/storage/docs/metadata#generation-number)、[標準化查詢／簽署標頭](https://docs.cloud.google.com/storage/docs/authentication/canonical-requests)、[指定世代的 GET](https://docs.cloud.google.com/storage/docs/xml-api/get-object-download)。這些是官方規格來源，不代表 HINE 已實作、已核准或已測試。

<a id="c11order_key-編碼與穩定排序待批准"></a>
<a id="ordering-pagination"></a>
#### C11：order_key 編碼與穩定排序（已整合）

- 編碼：JSON 字串，固定 20 個 ASCII 十進位數字，正整數左補 0，範圍 1～9223372036854775807；例如 41 編為 `"00000000000000000041"`。由 BB 指派、持久保存且訊息不變；只在同一對話比較，不含 conversation_id 前綴，不當作時間戳記或 SyncCursor。
- 比較：以 `(order_key,message_id)` 為元組；order_key 固定寬度逐 ASCII 位元組升序即整數順序，FA 不轉成 JavaScript Number、不用 localeCompare。同一鍵值時，UUID 正規化為 16 位元組升序。
- 聊天時間線採元組升序；A19 由新到舊採兩欄皆降序，歷史游標綁定同一元組。W07、W14、W16、A19 與 persistIfAbsent 回傳同一訊息的同一鍵值。

<a id="a08a11a19-首頁與-c12-limit數值待批准"></a>
<a id="rest-pagination"></a>
#### A08／A11／A19 首頁與 C12 `limit`（已整合）

| 操作 | 首次查詢 | 續頁 | 結束 |
|---|---|---|---|
| A08／A11 | 完全省略游標查詢鍵；例如 `/api/v1/contacts?limit=20` | 上次 `meta.next_cursor` 非 null 時，以 URL 查詢百分比編碼原字串傳游標 | `meta.next_cursor`:null 表示沒有下一頁，不送 `cursor=null` |
| A19 | 完全省略 `before` 查詢參數；例如 `/api/v1/conversations/c1/messages?limit=20` | 上次 `meta.next_cursor` 非 null 時，以原字串傳 `before`（名稱不同，仍是歷史游標） | null 表示結束，不拿使用者事件流游標填入 `before` |

空字串、字面 `"null"`、解碼／拆解後的游標都不是首頁傳法；伺服器依原 CURSOR_INVALID／CURSOR_EXPIRED 規則拒絕，僅重啟該 REST 查詢。GET 沒有 JSON 本文。

`limit` 是可省略的 HTTP 查詢正整數，以十進位數字傳送（不接受 null／空字串／小數／負值／重複鍵）；省略時預設 20，合法範圍 1–50。超界或格式錯誤不靜默裁切，以既有 `INVALID_ARGUMENT` 拒絕。W14 每頁 100 個邏輯項目、W16 每批最多 100 個事件且掃描最多 1000 個位置，彼此是不同限制。

<a id="contact-id-lookup"></a>
#### A07／FB-04：已知公開 user_id 查詢（範圍澄清）

A07 只查 `/users/{user_id}`，沒有關鍵字、電子郵件、顯示名稱搜尋。FB-04 提供公開 ID 輸入／貼上：ID 可由對方分享其 A02／A03.user_id 或 A05.id，或從呼叫者已獲授權的 A08 UserSummary.id／A12 MemberView.user_id 選取。先 A07 核對摘要，再由使用者確認 A09 加入聯絡人；錯誤沿用 NOT_FOUND 等既有規則，輸入 ID 本身不是授權。此流程不新增 QR、邀請碼或搜尋 API。若日後需要關鍵字找人，須另立產品需求與隱私／分頁／搜尋介面提案；本輪不納入，也不阻擋 ID 查詢。

<a id="receipt-projection-handoff"></a>
#### 回條交接與群組彙總的條件範圍

- **一對一交接：** BB 的 persistReceipt 回傳已提交的 `message_id`、`status`、`updated_at`、`status_event_id`。BA 用這些值加上已驗證的公開操作者（[C8](#public-identity-handoff) user_id，正是此筆回條的 recipient_id）組成完整一對一 ReceiptProjection；不能放 device_id／subject_id、不能用請求的 `kind` 覆蓋 BB 回傳的單調狀態。W10.event_id 取 `status_event_id`，`timestamp` 取 `updated_at`，conversation_id 取已授權的原請求；回條的關聯僅供 W19，不冒充 W10 的 event_id。
- C4 的 observer_ids 決定 W10 觀察者；`status_event_id:null` 時不產生 W10，observer_ids 為空，W19 仍回正式狀態／`changed`。重複回條可 `changed:false` 且 `status` 是 `read`，不能倒退成 `delivered`。BB 的事件流與 A19／W14 回傳相同投影，公開接收端不自行估算。
- **群組已讀彙總本版不做（2026-10-01 PM 決議）。** 不做群組已讀人數／名單、`read_count`／`member_count` 或群組 W10；群組 W08／W09／W19 個別回報與單調狀態保留；群組 MessageView／MessageSnapshot.receipt 必填 null。個別回條 `changed:true` 不產生群組彙總事件。

<a id="c14unread_count-語義與對話串新訊息提示待批准"></a>
<a id="unread-count"></a>
#### C14-S：`unread_count` 語義與對話串新訊息提示（2026-10-01 PM 決議）

<a id="unread-merge"></a>未讀徽章只顯示伺服器最近一次查詢值，不在前端維護加一／減一集合；不採用 C14-M。A11／A12／W14 的 `unread_count` 欄位與格式不變。

- **計算者與範圍：** BB 在讀取時計算，針對呼叫者使用者（不是裝置）：該對話中呼叫者依授權及[加入界線](#join-boundary)目前可讀的訊息，排除本人所發，計算已提交回條尚非 `read` 的數量。
- **已讀依據：** 只看 BB 經 `persistReceipt` 提交的 `read`（任一裝置 W09 皆可）；沿用逐訊息已讀語義。`delivered`、本機可見或只開啟對話串都不減少未讀。
- **更新時機：** A11／A12／W14 只回傳該次讀取時計算的伺服器值；同一使用者各裝置共用此值，不新增跨裝置未讀事件。進入／返回聊天清單執行 A11，開啟對話執行 A12，首次登入／游標重設以 W14 收斂。已讀在下一次成功查詢才反映，期間允許徽章短暫舊值。
- **群組回條：** 不擴充 W10；不做群組 read_count／member_count 彙總。
- **對話串提示：** 新訊息提示可維持本機提示，只供「跳至最新」使用；不得冒充權威 `unread_count`，也不代表已讀。
- **快照一致性：** W14 的值與同一快照 H 一致；A11／A12 是各自讀取時點的值，不宣稱與使用者事件流位置同步。

<a id="local-persistence-boundary"></a>
#### 本地持久保存與離線範圍（既有義務澄清）

不提供完整離線應用程式／PWA，不等於取消 FA-03／04／05 的本地持久保存：W05 前保存原 C1／承載資料與待確認狀態；W08 前完成已收訊息及其識別資訊的本機持久保存（不是先取得伺服器回條）；W16 只有在投影與游標原子保存後才能推進；W14 完整同快照暫存投影切換後才安裝 H。重啟／斷線仍須能恢復原意圖與已保存進度，不能只靠記憶體宣稱已持久化。

儲存失敗時，不送 W08（W08 代表收件端已持久保存該訊息）、不提前保存游標／H、不顯示無根據的成功；恢復時依原鍵值與同步語義處理。此義務不代表離線時能完成認證、群組異動或上傳，也不自動新增 Service Worker、離線搜尋或完整離線導覽；本輪不指定 IndexedDB 等新的本地儲存技術。G1 本機副本政策與登出隔離依 [群組撤權政策](#group-revocation-policy)。

<a id="c6a03-結果不明的單一政策fbbb-共用待批准"></a>
<a id="refresh-recovery-policy"></a>
#### C6：A03 結果不明的單一政策（FB／BB 共用；已改寫）

正常需要時 A03 自動刷新一次；等待 10 秒仍無法確認結果、收到 401 或刷新失敗，就停止 WSS／自動刷新、清除本機可用認證狀態並提示重新登入。BB 舊 Cookie 寬限 0 秒，不重播舊刷新請求，不做跨分頁協調接班或結果不明後額外恢復流程。`RATE_LIMITED` 有有效 `retry_after_ms` 時等候到期後最多再自動嘗試一次；省略／無效時停止自動刷新，由使用者手動操作。伺服器錯誤／網路問題不得冒充密碼錯誤；一般服務故障依 C13 處理。

<a id="c7同裝置多分頁-w21-合併待批准"></a>
<a id="activity-merge"></a>
本版範圍外（2026-10-01 PM 決議）：不做伺服器端前景／背景活動租約與合併；`recordActivity`、W21／W22 及 `ACTIVITY_LEASE_SECONDS` 均不納入交付。WSS 心跳、斷線重連與前端 Page Visibility 已讀判斷各自保留，不互相替代。

<a id="傳輸與呼叫者驗證主方案api-與-realtime-分開部署"></a>
#### 傳輸與呼叫者驗證（Compose 私有網路）

- 內部操作 1–6、9–10 以私有網路 HTTP 呼叫：`POST /internal/v1/<operation>`；本文為 JSON 輸入／輸出，錯誤使用共同 REST 錯誤封套。操作 7 僅由 api 呼叫查詢線上狀態；recordActivity／操作 8 本版範圍外。
- <a id="internal-caller-credential"></a>**內部呼叫憑證（2026-10-01 PM 決議）：** Compose 私有網路內每個服務使用由維運注入的內部呼叫 bearer secret，在 `Authorization` 標頭傳送；提供者依 `INTERNAL_ALLOWED_CALLERS` 驗證呼叫者。憑證不得提交 Git 或記錄。使用者存取權杖不是呼叫者憑證，`validateAccess` 收到的存取權杖僅是輸入資料。
- 公開反向代理不得轉送 `/internal/*`。
- <a id="internal-auth-layer"></a>**C13：內部 `UNAUTHENTICATED` 分層（2026-10-01 PM 決議）。** 不新增公開錯誤碼或完整告警平台：
  - **適用範圍：** 提供者只在 `code:"UNAUTHENTICATED"` 時於共同錯誤封套 `details` 加入 `auth_layer`：`"service_identity"` 表示呼叫者內部呼叫憑證無效或未獲允許；`"user_session"` 表示輸入的使用者存取權杖、工作階段或裝置綁定無效或已撤銷。其他錯誤碼（`FORBIDDEN`、`NOT_FOUND`、`INVALID_ARGUMENT`、`CONFLICT`、`RATE_LIMITED`、`IDEMPOTENCY_CONFLICT`、`OUTCOME_UNCONFIRMED`、`PERSISTENCE_FAILED`、`CURSOR_INVALID`、`SYNC_RESET_REQUIRED`、`DEPENDENCY_UNAVAILABLE` 等）不帶 `auth_layer`，照[錯誤分流](#error-recovery)處理，不得因缺少 `auth_layer` 改成 `DEPENDENCY_UNAVAILABLE`。
  - **可信回應：** 經設定的內部 URL（`API_INTERNAL_URL`／`REALTIME_INTERNAL_URL`，Compose 私有網路）取得，且本文可解析為 HINE 共同錯誤封套；公開反向代理不轉送 `/internal/*`。
  - **使用者工作階段失效：** 只有可信回應的 `UNAUTHENTICATED` 且 `auth_layer:"user_session"`，BA 才對這次呼叫所帶工作階段綁定的那條連線回 W17 `UNAUTHENTICATED`、標記失效並關閉，並觸發一次補齊；同一工作階段的其他連線仍依 SessionInvalidation 紀錄關閉。
  - **服務依賴失敗：** `auth_layer:"service_identity"`、缺少 `auth_layer` 的 `UNAUTHENTICATED`，以及非可信或無法解析為 HINE 封套的回應，一律按 `DEPENDENCY_UNAVAILABLE` 處理：記錄錯誤（不含憑證）、顯示服務暫時不可用，不觸發登出或刷新。新連線的 W01 不回 W02，回 W17 `DEPENDENCY_UNAVAILABLE`（可重試）後關閉這條尚未驗證的連線，不宣稱工作階段已撤銷（同 [AC-N10](../testing/acceptance-matrix.md#ac-n10)）；已驗證連線只讓該操作失敗，連線不因此錯誤關閉，其餘依[交付與連線狀態表](#delivery-state-table)與生命週期。BB 呼叫 BA 遇到同類失敗時，`publishCommitted` 改走恢復路徑，`getDevicePresence` 視為 `unknown`。
  - [M3 的重新登入規則](#refresh-recovery-policy)只適用已發起 A03 的認證流程，不用於一般服務故障。公開 W17／REST 錯誤不揭露 `auth_layer`。

<a id="internal-transaction-order"></a>
<a id="交易順序backend-b"></a>
#### 交易順序（後端 B）

- **T1 工作階段變更（A03、A04，以及 A02 取代同裝置舊工作階段）：**
  1. `FOR UPDATE` 鎖定工作階段列。
  2. 更新世代或撤銷。A02 撤銷同帳號同裝置原有的有效工作階段，並建立新工作階段。
  3. 以單列計數器 `UPDATE ... SET position = position + 1 RETURNING position` 取得 `r`。計數器的列鎖讓位置順序與提交順序一致；回滾時遞增一併回滾，所以不跳號。
  4. 寫入 SessionInvalidation，然後提交。
  5. 提交成功後才呼叫 `publishCommitted`；採用单一 api/realtime 實例與 Redis Pub/Sub，通知失敗不改變 REST 提交結果，依既有同步／輪詢恢復。

  REST 的狀態碼與內容只取決於提交結果，通知失敗不會改變它。
- **T2 帶工作階段綁定的異動（`persistIfAbsent`、`persistReceipt` 與 REST 異動）：**
  1. `FOR SHARE` 鎖定工作階段列，檢查狀態有效且世代等於目前世代。
  2. 群組對話再以 `FOR SHARE` 鎖定對話列，並檢查成員資格。
  3. 在交易內計算收件者或觀察者，寫入資料與事件流列。
  4. 最後一個陳述式讀取計數器（不加鎖），作為授權點與 `invalidation_position`。
  5. 提交。
- **T3 群組異動（A14–A18）：**
  1. 依 T2 檢查工作階段。
  2. `FOR UPDATE` 鎖定對話列，執行異動並遞增 `membership_version`。
  3. 寫入各使用者事件流列，讀取計數器，然後提交。
  4. 提交成功後，依 T1 的兩種模式之一呼叫 `publishCommitted(conversation_events)`。
- **T4 讀取（`readBootstrap`、`readFeed`、A19、A22 等）：** 在讀取快照內檢查工作階段與授權，不加鎖；授權點就是該快照。
- **提交結果不明**（例如提交途中與 PostgreSQL 斷線）：不得發送通知，REST 依共同錯誤規則回應。若實際已提交，節點經輪詢補齊工作階段失效，群組事件經事件流補回。
- **保留期限：** SessionInvalidation 至少保留 `INVALIDATION_RETENTION_SECONDS`，不得短於存取權杖的最長有效期。

<a id="node-rules"></a>
<a id="realtime-節點處理規則backend-a"></a>
#### 即時節點處理規則（後端 A）

本版只部署一個 `realtime` 實例；本節及狀態表中的「節點」即指該實例，規則不因此改變。

- **已套用位置：** 每個節點維護 `applied_position`，並且只連續推進。收到位置跳號的紀錄時，可以立即對本地連線套用（提早套用失效一定安全），但要補齊中間的紀錄後才推進。
- **新鮮狀態：**
  - 節點記錄最近一次完整補齊的開始時點（單調時鐘）。距今不超過 `INVALIDATION_STALE_SECONDS` 為新鮮，超過則不新鮮（authority_stale），不新鮮時依[狀態表](#delivery-state-table)第 7、8 列處理。
  - `INVALIDATION_POLL_SECONDS` 必須小於 `INVALIDATION_STALE_SECONDS`，讓正常節點不會因輪詢間隔而變成不新鮮。
  - 節點啟動時先完成一次完整補齊，之後才接受 W01；不新鮮時拒絕新的 W01。
- **套用一筆紀錄：**
  - 本地連線 `session_id` 相符，且 `min_valid_generation` 為 `null` 或連線世代小於該值者，立即標記失效：停止接受業務訊框，丟棄其佇列中尚未開始交付的訊框，停止所有交付，盡力送出 W17 `UNAUTHENTICATED` 後關閉。
  - 其他連線不受影響。
- **遞送閘門：** 遞送後端 B 產生的通知前，若 `invalidation_position > applied_position`，先以 `readSessionInvalidations` 補齊；在 `NOTICE_CATCHUP_HOLD_MS` 內無法補齊，就放棄這則通知在本節點的即時交付，由 W15／W16 補回。通過閘門後，每個訊框在開始交付時仍要做[開始交付前的檢查](#authorization-boundary)。遞送對象限於：收件者相符、已驗證、未標記失效、存取權杖未到期，且未被群組移除紀錄排除的連線。
- **後端 B 拒絕：** 內部操作對某連線的工作階段綁定回使用者工作階段層的 `UNAUTHENTICATED`（可信回應且 `details.auth_layer:"user_session"`，見 [C13](#internal-auth-layer)）時，節點立即將該連線標記失效並關閉，並觸發一次補齊。服務身分層、缺少分層或非可信回應按依賴失敗：已驗證連線不因此錯誤關線（其餘仍依狀態表與生命週期），新連線的 W01 依 [C13 連線階段](#internal-auth-layer)回 W17 `DEPENDENCY_UNAVAILABLE` 後關閉且不宣稱撤銷；其他錯誤碼照原規則，不因此關線。
- **W01 註冊競態：**
  - `validateAccess` 回傳驗證快照中的位置 `p`（C1）。
  - 節點讓「最後檢查＋註冊連線」與「套用失效紀錄」互斥執行，例如放在同一個序列化事件迴圈或同一把鎖內。這樣每筆紀錄要嘛在註冊前被檢查到，要嘛在註冊後套用到這條連線。
  - 最後檢查涵蓋節點已知、位置大於 `p` 的所有紀錄，包含提早套用、尚未連續推進的紀錄。
  - 節點保留最近套用的紀錄；若 `p` 早於保留範圍，先以 `readSessionInvalidations(after_position:p)` 查詢，查詢返回後在互斥區內重新檢查再註冊。
  - 任何紀錄使這條連線失效，就拒絕連線。
- **輪詢：** 每 `INVALIDATION_POLL_SECONDS` 從 `applied_position` 開始做一次完整補齊，不論是否收到通知。
- **位置過舊：** `readSessionInvalidations` 回 `CURSOR_INVALID` 時，節點關閉所有本地連線，並從最新位置重新開始；用戶端重連時重新驗證。
- **存取權杖到期：** 節點在連線的 `expires_at` 關閉它，這是連線清理的絕對上限。
- **去重：** 節點以 `notice_id` 去重；用戶端仍以 `event_id` 去重。

#### 連線清理的完成條件

- 單一連線的清理完成，是指 `realtime` 實例已將它標記失效並關閉傳輸連線。沒有全域完成回報；後端 B 的 REST 回應不等待清理。
- **通知正常：** `realtime` 實例經 Redis Pub/Sub 收到通知即套用；完成時間取決於通知延遲（未量測）。
- **通知遺失、後端 B 可連線：** `realtime` 實例最遲在下一次輪詢（`INVALIDATION_POLL_SECONDS`）加一次補齊的時間內套用；遞送閘門可能更早觸發補齊。
- **後端 B 無法連線：** 見[狀態表](#delivery-state-table)第 6、7 列。連線保留但不交付資料，最遲在存取權杖到期時關閉。

#### 故障處理

| 情境 | 處理 |
|---|---|
| 重複通知 | 節點以 `notice_id` 去重；套用失效紀錄是冪等的；用戶端以 `event_id` 去重 |
| 亂序 | 失效紀錄的套用可交換順序（世代取最大值，撤銷一經套用不可逆）；`applied_position` 只連續推進；群組事件依 `membership_version`，版本缺口沿用 A12 修正 |
| 延遲的 A03 紀錄 | 只讓世代小於 `min_valid_generation` 的連線失效，不影響之後建立的新世代連線 |
| 延遲的 A04 或 `replaced` 紀錄 | 只影響該 `session_id`；重新登入使用新的 `session_id` |
| `publishCommitted` 逾時或錯誤 | 通知失敗不改變已提交的 REST 結果；PostgreSQL 事件流與失效紀錄輪詢／補齊負責恢復，Pub/Sub 只加速傳遞 |
| Redis 無法使用 | `publishCommitted` 回 `DEPENDENCY_UNAVAILABLE`，即時遞送中斷；節點輪詢後端 B，仍會套用失效；群組事件經事件流補回 |
| 後端 B 或 PostgreSQL 無法使用 | 見[狀態表](#delivery-state-table)第 6、7、8 列 |
| 提交成功但通知失敗 | REST 照常回成功（A03 200、A04 204、A14–A18 各自的成功狀態）；工作階段失效由輪詢、遞送閘門與權杖到期處理；群組事件由 W15／W16 補回，無權成員因收件者在提交時決定而收不到撤權後的正文 |
| 提交結果不明 | 不發送通知；REST 依共同錯誤規則回應；A04 可冪等重試 |

<a id="多節點與多裝置"></a>
#### 單一實例與多裝置

- **單一 `realtime` 實例：** 本版只部署一個 `api` 與一個 `realtime` 實例；後端 B 提交後經內部 HTTP／JSON 呼叫該實例，再經 Redis Pub/Sub 遞送。多實例拓樸不屬本版交付。
- **連線範圍：** 單一 `realtime` 實例只服務本版單一可操作聊天分頁的 WSS；同瀏覽器其他分頁不得登入、刷新或建立 WSS，規則見 [FB 單一操作分頁](../prd/frontend-b.md#fb-multi-tab)。不同瀏覽器／裝置仍可各自登入；群組事件依收件者遞送到該使用者有效連線。
- **同帳號其他裝置：** 各自的工作階段不受 A02、A03、A04 影響；群組事件依收件者遞送到該使用者所有有效連線。

<a id="候選-json-範例"></a>
#### 內部 JSON 範例

A04 產生的工作階段失效通知：
```json
{"notice_id":"20000000-0000-4000-8000-000000000001","type":"session_invalidation","committed_at":"2026-09-29T12:20:00Z","invalidation_position":1042,"session_invalidation":{"position":1042,"session_id":"sess-d1","reason":"logout","min_valid_generation":null,"committed_at":"2026-09-29T12:20:00Z"}}
```
`readSessionInvalidations` 請求與回應（1041 為另一工作階段的 A03 更新）：
```json
{"request":{"after_position":1040,"limit":100},"response":{"entries":[{"position":1041,"session_id":"sess-d2","reason":"refresh","min_valid_generation":3,"committed_at":"2026-09-29T12:19:30Z"},{"position":1042,"session_id":"sess-d1","reason":"logout","min_valid_generation":null,"committed_at":"2026-09-29T12:20:00Z"}],"next_position":1042,"head_position":1042,"has_more":false}}
```
A18 提交後由後端 B 傳給 `publishCommitted` 的群組通知（被移除者只收到最小的自身通知）：
```json
{"notice_id":"20000000-0000-4000-8000-000000000002","type":"conversation_events","committed_at":"2026-09-29T12:21:00Z","invalidation_position":1042,"conversation_events":{"source":"A18","conversation_id":"g1","membership_version":6,"deliveries":[{"recipient_user_id":"u2","envelope":{"event":"conversation.member_removed","event_id":"20000000-0000-4000-8000-000000000003","timestamp":"2026-09-29T12:21:00Z","conversation_id":"g1","payload":{"member_id":"u2","change":"removed","membership_version":6}}},{"recipient_user_id":"u1","envelope":{"event":"conversation.member_removed","event_id":"20000000-0000-4000-8000-000000000004","timestamp":"2026-09-29T12:21:00Z","conversation_id":"g1","payload":{"member_id":"u2","change":"removed","membership_version":6,"actor_id":"u1"}}}]}}
```
`publishCommitted` 成功回應（只代表該實例已發布）：
```json
{"notice_id":"20000000-0000-4000-8000-000000000002","published":true}
```

<a id="deployment-config"></a>
<a id="6-deployment-and-operational-policy"></a>
## 6. 部署與營運政策

以下為本版環境設定（2026-10-01 PM 決議），不是已部署或量測結果。範圍外功能及其秘密參照不要求設定，也不阻擋核心服務就緒。

| 名稱 | 類型／必要性 | 使用端 | 設定者／來源 | 是否為機密？ | 缺少／無效時的行為 |
|---|---|---|---|---|---|
| `HINE_ENV` | 列舉／字串；必要 | BA, BB, DO | 維運部署設定 | 否 | 拒絕啟動／就緒 |
| `PUBLIC_ORIGIN` | HTTPS URL；必要 | BB, DO | 維運入口設定 | 否 | 拒絕就緒；不建構公開連結 |
| `API_BASE_URL` | HTTPS URL；必要 | FB, FA 設定；DO 入口 | 維運前端／發布設定 | 否 | 前端部署無效 |
| `WS_URL` | WSS URL；必要 | FA 設定；DO 入口 | 維運前端／發布設定 | 否 | 即時用戶端未就緒 |
| `DATABASE_URL` | PostgreSQL 連線 URI；必要 | BB | 維運機密參照（VM 上 Compose secrets／受控檔案，不提交 Git） | 是 | BB 啟動／就緒失敗 |
| `REDIS_URL` | Redis 連線 URI；暫時性即時／在線狀態功能必要 | BA | 維運機密參照（VM 上 Compose secrets／受控檔案，不提交 Git） | 是 | BA 未就緒；回報未知，而非錯誤地回報在線 |
| `GCS_BUCKET` | 儲存桶名稱；上傳時必填 | BB | 維運部署設定 | 否 | 附件功能尚未就緒 |
| `JWT_ISSUER` | 字串；必填 | BB 簽發，並在 `validateAccess` 驗證；BA 不讀取、不自行驗證 JWT | 後端 B 驗證負責人 + 維運 | 否 | BB 啟動／就緒檢查失敗（封閉失效）；BA 只經 `validateAccess` 取得結果，不另建驗證流程 |
| `JWT_AUDIENCE` | 字串；必填 | BB 簽發，並在 `validateAccess` 驗證；BA 不讀取、不自行驗證 JWT | 後端 B 驗證負責人 + 維運 | 否 | BB 啟動／就緒檢查失敗（封閉失效）；BA 只經 `validateAccess` 取得結果，不另建驗證流程 |
| `JWT_SIGNING_KEY_SECRET_REF` | Secret 參照；必填 | 僅 BB | 維運機密參照（VM 上 Compose secrets／受控檔案，不提交 Git）；BB 負責金鑰輪替 | 參照屬敏感資訊；值為機密 | BB 驗證服務不可用／未就緒；絕不接受假金鑰 |
| `FCM_CREDENTIAL_SECRET_REF` | Secret 參照；本版範圍外 | — | — | — | 本版不使用；缺少不影響核心就緒 |
| `APNS_KEY_SECRET_REF` | Secret 參照；本版範圍外 | — | — | — | 本版不使用；缺少不影響核心就緒 |
| `SYNC_PAGE_LIMIT` | 正整數；必填 | BB readBootstrap、BA/BB sync | 本版設定 100；維運注入／驗證 | 否 | 拒絕無效設定；不允許無上限分頁 |
| `SYNC_SCAN_LIMIT` | 正整數；必填 | BB readFeed | 本版設定 1000；維運注入／驗證 | 否 | 拒絕無效設定；未掃完不得當同步完成 |
| `UPLOAD_MAX_BYTES` | 正整數；啟用上傳時必填 | BB | 本版設定 10485760；維運注入／驗證 | 否 | 拒絕無效設定；上傳功能不可用 |
| `HEARTBEAT_TIMEOUT_SECONDS` | 正整數；必填 | BA；透過 W02 公布 | 本版設定 90；維運注入／驗證 | 否 | 拒絕無效設定／就緒檢查 |
| `HEARTBEAT_INTERVAL_SECONDS` | 正整數；必填 | BA 設定心跳頻率；W02 公布 | 本版設定 30；維運注入／驗證 | 否 | 拒絕無效設定／就緒檢查 |
| `ACTIVITY_LEASE_SECONDS` | 本版範圍外 | — | — | — | 缺少不影響核心就緒 |
| `SYNC_RECONCILE_SECONDS` | 正整數；前景同步必要 | FA 排程 W15/W16 | 本版設定 10；維運注入／驗證 | 否 | 拒絕無效設定 |

每個環境記錄設定值的負責團隊及參照／版本，不記錄秘密內容。`FCM_CREDENTIAL_SECRET_REF`、`APNS_KEY_SECRET_REF` 與 `ACTIVITY_LEASE_SECONDS` 本版範圍外；缺少不阻擋核心服務就緒。

<a id="候選設定提交後通知與授權失效待批准"></a>
<a id="deployment-config-candidates"></a>
### 已整合設定：提交後通知與授權失效

下列為本版設定（2026-10-01 PM 決議），未宣稱量測達標。必要核心設定缺少／無效時服務拒絕就緒；活動租約與推播秘密參照範圍外且不阻擋就緒。

| 名稱 | 類型／必填 | 消費者 | 設定者／來源 | 秘密？ | 本版值／缺少時的行為 |
|---|---|---|---|---|---|
| `API_INTERNAL_URL` | Compose 私有 HTTP URL；必填 | realtime 呼叫 api 操作 1–6、9 | 維運 Compose 網路 | 否 | 缺少時 realtime 不就緒 |
| `REALTIME_INTERNAL_URL` | Compose 私有 HTTP URL；必填 | api 呼叫 realtime 操作 7（A08 線上狀態）與操作 10 | 維運 Compose 網路 | 否 | 缺少時 api 不就緒；執行期無法連線時 `publishCommitted` 改走同步／失效紀錄恢復路徑，操作 7 失敗時線上狀態為 `unknown` |
| `INTERNAL_CALLER_TOKEN_SECRET_REF` | Secret 參照；必填 | 內部 HTTP 呼叫 | 維運注入 | 參照敏感；值為機密 | 缺少／無效時核心服務不就緒 |
| `INTERNAL_ALLOWED_CALLERS` | 服務呼叫者清單；必填 | api／realtime 驗證呼叫者 | 維運注入 | 否 | 缺少時拒絕所有內部請求並不就緒 |
| `INVALIDATION_POLL_SECONDS` | 正整數；必填 | realtime 輪詢操作 9 | 本版設定 5 | 否 | 缺少／無效時 realtime 不就緒 |
| `INVALIDATION_STALE_SECONDS` | 正整數；必填 | realtime 節點新鮮期 | 本版設定 15 | 否 | 缺少／無效時 realtime 不就緒；不是資料抵達期限 |
| `NOTICE_CATCHUP_HOLD_MS` | 正整數；必填 | realtime 遞送閘門 | 本版設定 1000 | 否 | 缺少／無效時 realtime 不就緒 |
| `INVALIDATION_RETENTION_SECONDS` | 正整數；未定 | BB 保留 SessionInvalidation | 未決候選 | 否 | 不得短於存取權杖最長有效期；值仍待決 |
| `ACTIVITY_LEASE_SECONDS` | 本版範圍外 | — | — | — | 缺少不影響核心就緒 |

內部 `/health/live` 回報程序存活狀態（200；相依項目可能為 `not_checked`）。`/health/ready` 回報必要相依項目就緒狀態（200 或 503），不含憑證。同步每頁上限 100、每次掃描上限 1000；附件上限 10,485,760 bytes；心跳間隔 30 秒／逾時 90 秒；訊息速率每使用者每秒 5 則、突發 10 則；登入每帳號每分鐘 10 次、每來源 IP 每分鐘 60 次；REST limit 預設 20、最大 50；群組最多 50 人；前景同步核對每 10 秒。授權失效 15 秒、輪詢 5 秒、單事件補齊 1000 毫秒。以上為本版初始設定，未量測；Web Push／原生推播停用，缺少推播金鑰不影響核心服務就緒。

完整健康狀態回應範例如下：
```json
{"status":"ok","service":"realtime","timestamp":"2026-10-01T08:00:00Z","dependencies":{"postgresql":"not_checked","redis":"not_checked"}}
```
```json
{"status":"unready","service":"api","timestamp":"2026-10-01T08:00:01Z","dependencies":{"postgresql":"fail","redis":"not_checked"}}
```
```json
{"status":"unready","service":"api","timestamp":"2026-10-01T08:00:02Z","dependencies":{"postgresql":"not_checked","redis":"not_checked"},"reason":"CONFIG_MISSING"}
```
此就緒狀態回應可指出設定失敗，但不會洩露設定名稱或值。
第一個是 `realtime` 的 `/health/live`（200，存活檢查不檢查相依項目）；第二個是 `api` 的 `/health/ready`（503，PostgreSQL 實際檢查失敗；`api` 不直接使用 Redis，故為 `not_checked`）；第三個是 `api` 設定缺漏時的 `/health/ready`（503）。監控分別測量 ACK、即時傳遞與同步復原。公開指標標籤不包含使用者 ID／權杖／訊息內文；日誌不包含完整權杖及私人訊息內文。

<a id="7-待定產品決策與變更紀錄"></a>
<a id="7-pending-product-decisions-and-change-ledger"></a>
## 本版決議狀態與變更紀錄
本版決策狀態（2026-10-01 PM 決議）：C1–C6（C1–C4 改寫、C5 保留、C6 改寫）、C8–C14、E1、G1–G3、S1–S2 已整合為現行規格；C7、A23–A25、W21／W22、活動租約、推播（Web 與原生）為本版範圍外。A01–A25、W01–W22 ID 保留；A18 是成員移除／退出，不是封鎖。EntityID／text 採[本輪工作值](#integration-baseline)，Title 待群組串接前共同確認，`INVALIDATION_RETENTION_SECONDS` 另屬內部部署待決事項。介面可依共同流程修改，不宣稱整份規格已凍結、產品已實作、部署或測試。
變更紀錄：持久化 ACK、C1 冪等性、游標／快照／同步核心語義維持不變；整合決議不重編 A／W／REQ／功能 ID。
