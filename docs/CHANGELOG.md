# HINE 文件變更紀錄

## 2026-10-01 — PR #3 最新通知／ID 覆蓋／產品 quota 修正

- Finding 1：BB 在生成／送出 RealtimeNotice 前驗所有 canonical EntityID；authenticated BB 的結構合法 notice 視為 BB 已完成長度責任。BA 驗 caller／JSON／required／null／型別／enum／UUID／source，不重算 Unicode 長度，結構錯誤仍 INVALID_ARGUMENT。同步 BB→BA 內部 ID 交接，公開 REST／W05 的 BB 前置驗證不變。
- Finding 2：EntityID 129 驗收補 A06 非 null avatar_attachment_id、A10 user_id，不做 attachment／使用者／聯絡人 lookup 或授權；A06 null／omission 語意保留，共用 15 個 receiving REST 清單一致，不新增其他 ID／output-only／範圍外邊界。
- Finding 3：正式 PM 將 W05 每使用者 5/s、burst 10 的產品 quota 唯一權威改為 BB 的 persistIfAbsent，C1 判定後／持久化前只作用於新合法 intent。BA-08 保留 transport/frame defense 與 W17 mapping，不先判或雙重維護產品 quota；不指定 BB 實作。
- 六階段與 quota exhausted 五個結果同步：非法 payload → INVALID_ARGUMENT；新合法 C1 → RATE_LIMITED；相同合法 C1 → existing_same／原 M1；不同合法 C1 payload → IDEMPOTENCY_CONFLICT；非法同 C1 payload → INVALID_ARGUMENT。拒絕不持久化、不建 C1→M1、不回成功 W06；retry_after_ms 沿用既有規則。
- 只修相關契約／驗收／角色／架構交接／決策與五步摘要，原 5/s burst10 數值、Unicode／內容、Title 候選、部署 pending、模組自由、A／W／REQ 及推播／活動／群組回條 scope 不變。先前五階段說明由本輪 W05 六階段取代；沒有產品程式，尚未產品驗證，不代替組員批准。
- 本輪文件 smoke：14 份相關文件的 1,270 個相對連結／anchor、34 個 JSON 區塊通過；A25／W22／REQ22 ID 集合、既有 JSON 範例與原 32 項 PM 正文未改。五個 quota 與 A06 129/null/omission、A10 129 驗收資料只做 JSON 往返；沒有執行產品 quota、通知接收、DB／C1／W06 或瀏覽器測試，尚未產品驗證。

## 2026-10-01 — PR #3 三項契約一致性修正

- Issue 1：明訂 BB 的 EntityID／text canonical 單位為 JSON 解碼後 Unicode code points（Unicode 碼點），排除 UTF-8 bytes、UTF-16 code units 與 grapheme clusters。僅增加 😀＝1、e 加組合重音＝2 的 BB 案例；FA／FB／BA 不需重現算法，不 trim／normalization 或改內容。
- Issue 2：所有 Client／其他模組輸入的 EntityID（含 path、欄位、陣列與巢狀參數）先驗結構／長度；超長 INVALID_ARGUMENT 先於資源／授權。同步實際接收 EntityID 的 REST／internal error list 及引用；只輸出 EntityID、只收其他 ID 型別或範圍外操作不機械新增錯誤。
- Issue 3：結構、輸入合法性、認證／授權、C1 比對、持久化依序；同 C1＋非法 text 先 INVALID_ARGUMENT，合法 World 才 IDEMPOTENCY_CONFLICT，相同合法 Hello 回 existing_same／同 M1。同步 W05／W17、persistIfAbsent、角色／QA／矩陣及原架構圖的順序說明，不新增架構或 A／W／REQ ID。
- 仍保留首輪登入／一對一／W06／W07／A19、Title 群組前候選、內部保留時間部署待決、分輪治理與模組自由；不改推播、活動租約或群組回條。這是文件修正，尚未產品驗證，也不是 FA／FB／BA／BB 的對接確認。
- 本輪文件 smoke：14 份相關文件的 1,275 個相對連結／anchor 與 34 個 JSON 區塊通過；A25／W22／REQ22 的 ID 集合及既有 JSON 範例值未增刪或改動，原 32 項 PM 決議正文未改。兩個 BB Unicode 與三個 C1 情境只做 JSON 解碼／資料往返探查，沒有產品後端、WSS、持久化或瀏覽器測試；尚未產品驗證。

## 2026-10-01 — PM 正式確認首輪限制與後端權威驗證

- PM 已正式確認 EntityID 上限固定為 128、對消費端仍為 opaque string；超長輸入由後端依既有契約回 INVALID_ARGUMENT。text 必須非空，有效範圍固定為 1～4096。
- Canonical validation 由後端負責；文字最終權威驗證由 BB 在持久化前完成。BA 可驗證 envelope、必要欄位與型別，BB 拒絕後 BA 映射既有 W17 INVALID_ARGUMENT，不持久化、不回成功 W06；前端提示／字數／預先阻擋僅屬 UX。
- 前輪移除消費端或不同語言必須重現相同計數模型的要求，以 ASCII 資料驗 text 空、1、4096／4097 及 EntityID 128／129；上方本次修正另明訂 BB 專屬單位及兩個最小 BB Unicode 案例，不恢復消費端算法義務。不 trim／normalization 或改內容。
- Title 1～80 保留 A14／A15 群組串接前候選，`INVALIDATION_RETENTION_SECONDS` 保留部署／維運待決；不阻擋首輪登入與一對一文字聊天。分輪治理與模組內自由維持不變，共同修改僅要求提供方及直接受影響消費方確認。
- 本次僅同步政策文件、角色交接、導覽、協作／PR 清單與驗收條件；不新增 API／WSS ID，不改其他產品規格。PM 確認不代表 FA／FB／BA／BB 已確認；尚未產品驗證，不宣稱全介面已凍結或產品已實作／測試通過。
- 本次已執行文件 smoke：13 份文件的 1,192 個相對連結／錨點與 34 個 JSON 區塊通過檢查，六個 ASCII 邊界資料已實際產生並完成 JSON 往返檢查。這是文件／測試資料驗證，不是後端、WSS 或瀏覽器產品測試；尚未產品驗證。

## 2026-10-01 — 近期共同介面與分輪變更政策

- 依使用者指示改採「先對齊近期串接介面，模組內自由開發；介面可以修改，但與受影響成員一起改」，不要求一次鎖死整份規格。
- 共同契約新增首輪一對一文字路徑：A01／A02／A05／A13／A19、W01–W07／W17、FA↔FB 工作階段／導覽及 BA↔BB 驗證／寫入／提交後通知交接；既有欄位、授權、ACK、C1 冪等、游標／保存語意及 API／事件 ID 不重編。
- 初稿以 EntityID ≤128、text 1–4096 為工作值並提出消費端一致計數；此驗證責任提案已由上方 PM 正式確認取代，不再是現行契約要求。Title 1–80 保留群組串接前候選；內部部署保留時間仍另行協調。
- 協作指南與 PR 範本補上提供方／直接受影響消費方共同確認、同步契約／範例／驗收／實作與切換、驗證及更新 Notion 的流程；六角色文件、決策紀錄、驗收矩陣與文件導覽同步引用，不要求內部實作逐項請 PM 批准。
- 前輪曾執行 34 個 JSON 區塊解析、相對連結／錨點檢查及兩種語言各 13 個計數探查情境；計數探查不是本次必要驗收或對消費端的算法要求。這些不是產品 API／瀏覽器串接測試；未實作或部署產品，未取得 FA／FB／BA／BB 共同確認，不宣稱整份規格已凍結。
- 來源為 `17c25ec`；本次修訂透過 `docs/incremental-interface-baseline` 分支交付，以該分支提交紀錄追溯。分支交付不代表已 Review／合併，不宣稱 GitHub main 已更新。

## 2026-10-01 — 決議一致性修正（單一實例、範圍外功能、共用程式碼）

- 驗收矩陣：REQ-08 與 AC-N01、N03、N04、N08、N09 改為單一 `realtime` 實例；保留多使用者、多裝置及以測試客戶端模擬的同工作階段新舊連線（重連／A03 換線交接的安全測試，不代表多個可操作分頁）。AC-N03／N04 以 W05／W15 取代 W21 步驟；REQ-15 改列 W03／W04、W18、A08，AC-N27 與 REQ-14 標示本版範圍外。
- 架構與角色文件：元件圖、部署圖、元件表與路由表標明本版提供 A01–A22、W01–W20（A23–A25、W21／W22 僅保留 ID）；BA-05 等標題與交接改為單一實例；後端 B 角色目的移除推播意圖；共同契約節點規則註明「節點」即單一 `realtime` 實例。
- `backend/common/` 改為可選共用程式碼；跨語言整合依據為共用介面契約、Schema 與測試樣例。
- 未新增或重編 A／W／REQ／功能卡／AC ID，舊標題錨點保留；未改 ACK、冪等、游標、快照、同步、撤銷或 C14-S 語義。此次僅修文件，未實作、部署或執行產品測試。

## 2026-10-01 — PM 決議整合

- Notion「HINE 待 PM 批准項目（HINE-IC-0.4）」共 32 項均已由 PM 決定；`docs/decisions.md` 改為現行決議登錄，不再表示仍待批准。已批准及需修改後採用的政策依決議更新；已否決／本版不做的推播、活動租約等明確標示為本版範圍外。
- 現行方向包括單一 GCP Compute Engine VM＋Docker Compose、依模組自選語言／框架，以及 QA 選定一套負載測試工具；README 與文件導覽同步更新推播範圍及角色摘要。
- 共同契約：C1–C6（C6 簡化為單次刷新後重登）、C8–C13、C14-S、E1（S＝15 秒）、G1–G3、S1–S2 改為現行規格；新增[加入界線](contracts/interface-contract.md#join-boundary)與[內部呼叫憑證](contracts/interface-contract.md#internal-caller-credential)；A23–A25、W21／W22、C7、活動租約、Web／原生推播標示本版範圍外（ID 與錨點保留）。
- 前端：M1 改為同一瀏覽器設定檔單一可操作分頁（Web Lock `hine-session`），移除多分頁交接；B1 驗收瀏覽器為 Chrome／Edge 桌面與 Android Chrome；Web/RWD 只有 768 CSS px 一個斷點；V3／V4 已讀、鍵盤、根路徑與本機篩選定案。
- 數值：REST 20／50、W14 每頁 100、W16 每批 100／掃描 1000、心跳 30／90 秒、訊息每秒 5 則（突發 10）、登入每帳號每分鐘 10 次／每 IP 每分鐘 60 次、群組 50 人、附件 JPEG／PNG／PDF ≤10 MiB、上傳授權 10 分鐘、下載授權 5 分鐘；課程效能基線為 50 使用者／50 條 WSS。驗收矩陣 N19–N24、N23、N27、N28、AC-R04、AC-R09、AC-R10 依決議改寫，未新增 ID。
- 此次僅整合文件決議，沒有實作產品功能、部署或執行測試／壓測；相關數值與效能目標仍未量測。

## HINE-IC-0.4 — 獨立文件提案，待批准

- 現行提案文件分為[獨立共用介面契約](contracts/interface-contract.md)、[網頁／響應式規格](ui/web-rwd.md)、[`prd/`](prd/) 下六份獨立角色需求文件、獨立[驗收矩陣](testing/acceptance-matrix.md)及中央[待決策事項登錄表](decisions.md)。
- 較早的整合版 [HINE-IC-0.4 契約](HINE-IC-0.4-contract.md)與[六角色需求文件](HINE-IC-0.4-role-prds.md)僅作歷史整合來源保存，不具共同權威性，也不是現行導覽目標。
- 新增可點選的[角色與主題文件地圖](README.md)，串連角色職責、契約查找、驗收及待決政策。
- 新增共用網頁響應式文件並於角色需求文件中互相連結。文件說明已確認的單一網頁應用程式交付基線，也明確將候選版面與互動規則標示為待批准；不推定原生應用程式或漸進式網頁應用程式（PWA）範圍。
- 拆分導覽讓角色職責、共用契約查找及待決政策更容易查閱；標準需求列與 REQ-19–REQ-22 網頁詳細驗收已收錄於獨立驗收矩陣。
- 補齊六角色共 43 項功能卡的具名需求、實際 API／事件／內部操作與協作功能章節連結；FB-06 直接指向未核准的瀏覽器推播決策，與既有原生 A23/A24 契約區分。共用契約僅增加現有內部操作的錨點，不改介面語義。
- 新增[系統架構](architecture/README.md)：元件與責任邊界、資料權威、識別碼與排序、連線／傳送／群組事件／附件／推播流程、部署拓樸、失效模式、安全、可觀測性、交付與容量驗證。另於[待決策事項](decisions.md)登錄 GCP 執行環境、技術棧、`api`／`realtime` 部署單元、REST 寫入後的即時通知路徑與負載測試工具等架構決策。本次未修訂 A01–A25、W01–W22 或任何契約語意。
- 新增候選方案（待批准，未實作）：
  - [提交後通知與授權失效](contracts/interface-contract.md#internal-notify-invalidation)：
    - 分開定義授權失效、連線清理與通知傳遞三種保證。
    - 以 PostgreSQL 提交序與資料的授權點定義撤銷前／後資料（D1–D4），撤銷前資料的工作階段上限為 `INVALIDATION_STALE_SECONDS`，並附[交付與連線狀態表](contracts/interface-contract.md#delivery-state-table)。
    - 新增候選內部操作 `readSessionInvalidations`／`publishCommitted`、既有操作的欄位與行為變更 C1–C5（C5 為 A02 的行為變更）、[適用狀態](contracts/interface-contract.md#internal-applicability)與[候選設定](contracts/interface-contract.md#deployment-config-candidates)。
  - [架構 6.6](architecture/README.md#flow-invalidation) 補上流程與摘要。
  - [前端 B 多分頁工作階段交接](prd/frontend-b.md#fb-multi-tab)。
  - [待決策事項](decisions.md#architecture-proposals)：五項架構決策的主方案，批准清單改為「目前方案／還缺」表，並補上 Cloud Run 適用條件與來源。
  - 相關後端 A、後端 B、維運、品質驗證、FA-02、FB-02 功能卡加註候選行為。
  - [驗收矩陣](testing/acceptance-matrix.md#notify-invalidation-cases)新增 AC-N01～AC-N24，並由既有 REQ 引用。

  以上都未修訂 A01–A25、W01–W22 的請求與回應格式，也未修訂確認回覆、游標與同步核心語義。
- 產品政策收斂（本地文件候選，未批准）：新增 [PM 六欄行為批准表](decisions.md#behavior-approval)，將群組撤權分為裝置已取得、舊授權服務端待送、撤權後新查詢；待送內容主要推薦已存在的 [E1](contracts/interface-contract.md#group-revocation-e1)，明列不採 E1 沒有相對 A18 固定停止上限，60 秒不是最大交付延遲。15 秒新鮮期限同時列為舊授權資料開始交付窗口，並分開[需求／候選配置／量測結果](decisions.md#spec-config-measure)。
  - 多分頁補上 C6 不給舊更新憑證寬限、一次結果不明恢復與明確重登終點；C7 各連線租期、任一前景優先；缺少必要瀏覽器能力採不支援政策。相關角色卡只補候選引用，六份需求文件與 A／W／REQ／角色功能 ID 保留。
  - 修訂 N18、N23，新增 N25–N28 文件驗收條件；原文改為比較基準，批准後才整合唯一現行定義。沒有產品程式、部署、產品測試、壓測或新的平台範圍；所有量測結果仍為未量測。
- 本輪交叉審查局部修訂：修正表格型別聯集的 `|` 跳脫（不改既有 JSON 字串）；對齊 [W17 錯誤與恢復](contracts/interface-contract.md#error-recovery)、可省略的 `retry_after_ms` 缺值處理、心跳識別值比對、必填／可為空值與[本地保存範圍](contracts/interface-contract.md#local-persistence-boundary)。新增待批准 C8–C12：後端 B 公開 `user_id`、A22 收件者中繼資料、簽署 PUT 上傳、`order_key` 編碼與 REST 分頁上限；不新增 A／W ID 或另一份權威契約。
  - FB-04 明訂已知 ID 查詢；群組彙總維持條件功能、一對一交接補齊；FA-07 認證交接改連 FB-01／02。補 [AC-R02–R08 文件條件](testing/acceptance-matrix.md#review-handoff-cases)；六份角色需求文件、43 個功能 ID、文件地圖保留，S／E1／多分頁批准狀態不變。本輪不實作、不部署、不執行產品測試／壓測。
- C10／R4 內容一致性補足（具體方案待批准，非 PM 簽核）：先引用 A21 目前上傳嘗試的核驗／冪等與 A25 待處理狀態／新上傳嘗試規則，再於[既有 C10](contracts/interface-contract.md#signed-upload-contract)補每次嘗試的獨立物件鍵、簽入 `x-goog-if-generation-match:0`、核驗物件世代／中繼資料世代、就緒狀態與中繼資料原子綁定、A22 固定物件世代交付及不可取得時拒絕替換。單次 PUT 不宣稱簽署網址一次性；不新增 A／W API，C8／C9／C11／C12 主方案與 S／E1／多分頁狀態不變。
  - 擴充同一 [AC-R04](testing/acceptance-matrix.md#ac-r04-version-cases) 的就緒後重傳、A25 後舊 PUT、回覆遺失後 412、交付版本不符四項文件預期結果；同步 BB-07／FA-06／FB-03／DO-02／QA。[R1～R6 狀態](decisions.md#review-resolution-status)明確分為「格式／既有矛盾已修正」與「已提供具體方案、待批准」，不把待批准誤寫成未回應；未執行產品測試或部署。
- 文件語言統一：README、協作與範本文件、各目錄說明、現行契約、歷史整合契約與角色需求文件、角色 PRD、網頁／響應式規格、架構、待決策事項與驗收矩陣的說明文字改為繁體中文。API／事件名稱、欄位與列舉值、錯誤碼、路徑、網址、環境變數、JSON 範例與 A／W／REQ／角色功能／AC ID 維持原樣；原英文標題的連結錨點保留。只改語言，不改任何規格語意、提案或批准狀態。
- 中文版 Review 局部修訂（非 PM 簽核）：文字澄清 Cookie 分工（BB `Set-Cookie`、瀏覽器保存、FB 管 AccessSession 與流程、FA 只消費）、W08 本機保存、非完整離線但保留本機保存義務、H 前後銜接、`logged_out` 欄位、BB 不可連線摘要、健康範例 `not_checked` 語義、JWT／`REALTIME_INTERNAL_URL` 設定說明、術語（儲存桶、物件鍵、一對一、頁面路由回退）與 BA-08／QA-02 交接。新增待批准契約提案 [C13 內部驗證失敗分層](contracts/interface-contract.md#internal-auth-layer)、[C14 `unread_count` 語義](contracts/interface-contract.md#unread-count)，以及 Web/RWD 候選的[已讀判定](ui/web-rwd.md#rwd-read-rule)、[鍵盤判別](ui/web-rwd.md#rwd-keyboard)、[根路徑](ui/web-rwd.md#rwd-root-route)與[本機清單篩選](ui/web-rwd.md#rwd-local-filter)；新產品選擇登錄為 [V1–V4](decisions.md#review-auth-layer)。補 AC-R09、AC-R10 與 REQ-20 正反案例。不新增 A／W／REQ／功能 ID，不改 ACK／C1／游標／快照核心規則，C8–C12 與 S／E1／多分頁狀態不變。
- 本次文件地圖與內容拆分未修訂 A01–A25、W01–W22 名稱／ID、標準資料、確認回覆／游標／同步語意；不代表已批准、實作、部署或完成產品測試。

## HINE-IC-0.3 — 歷史來源

HINE-IC-0.3 資料是 HINE-IC-0.4 提案的歷史唯讀參考，不代表現行整合來源。現行提案導覽請參閱上方獨立 HINE-IC-0.4 契約與拆分後的角色需求文件；批准狀態仍待定。
