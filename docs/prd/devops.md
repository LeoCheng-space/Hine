<a id="hine-ic-04--devops-角色-prd"></a>
# HINE-IC-0.4 — 維運（DO）角色 PRD

**版本：** HINE-IC-0.4  
**狀態：** 待產品核准  
**來源：** [歷史來源：HINE-IC-0.4 角色 PRD](../HINE-IC-0.4-role-prds.md); 唯一現行介面規格依據為 [共同介面契約](../contracts/interface-contract.md).  
**角色目的：** 負責主機路由、設定／機密綁定、交付流程、監控及可重現的驗證環境。本 PRD 規定未來行為與驗收要求，不代表已實作或已完成測試。
**必讀／串接時查閱：** [系統架構](../architecture/README.md)、[共同介面契約](../contracts/interface-contract.md)、[驗收矩陣](../testing/acceptance-matrix.md)；各功能串接見下方追溯／交接。 [返回文件導覽](../README.md)。

## 範圍

- **範圍內：** 主機路由、設定／機密綁定、交付流程、監控及可重現的驗證環境；以及下方角色專屬功能卡。
- **範圍外：** 其他角色所負責的範圍；亦不得變更共用 API／事件 ID、正式資料、ACK、游標或同步語意。共用欄位型別、封套、錯誤與限制均以共同介面契約為準。
- **共用 Web 行為：** 遵循 [Web／RWD 規格](../ui/web-rwd.md#web-rwd)；不得另訂斷點或重複定義版面規則。

## 功能索引

- [DO-01 — 網域、TLS、入口與路由](#do-01)
- [DO-02 — 型別化環境設定與機密管理](#do-02)
- [DO-03 — GitHub Actions 交付](#do-03)
- [DO-04 — 健康檢查、監控、警示與日誌隱私](#do-04)
- [DO-05 — 可重現的效能驗證環境](#do-05)
- [DO-06 — Web 資產與受保護深層連結的頁面路由回退](#do-06)

## 角色目的與責任界線

提供指定的主機路由、設定／機密綁定、交付流程、監控及可重現的驗證環境。GCP 運算架構尚未選定，不得假設使用 Kubernetes。

<a id="do-01"></a>
<a id="do-01--domain-tls-ingress-and-routes"></a>
### DO-01 — 網域、TLS、入口與路由
**追溯：** [REQ-17 基礎設施、健康探測與 CI 交付](../testing/acceptance-matrix.md#req-17); [共同介面契約部署／健康設定](../contracts/interface-contract.md#deployment-config), 公開 REST `/api/v1` 與 WSS `/ws/v1` 路由。
- **前置條件：** 已核准的網域與目標環境。
- **正常流程：** 在 `hine.run.place` 下路由公開 HTTPS REST `/api/v1` 與 WSS `/ws/v1`；探測端點維持內部使用。
- **失敗流程：** TLS、路由或必要依賴項失敗時，不得通過就緒檢查／部署驗收。
- **驗收條件：** 使用單一公開契約；內部健康端點不得暴露為使用者 API。Web 殼層的頁面路由回退僅限核准的 UI 路徑，並保留 API/WSS 路由。
- **候選（待批准）：** 公開入口不得轉送 `/internal/v1/*`；`api` 與 `realtime` 的內部操作只經私有網路 URL 呼叫（見[候選契約](../contracts/interface-contract.md#internal-notify-invalidation)）。
- **交接：** [BA-01](backend-a.md#ba-01)/[BB-01](backend-b.md#bb-01) 連接埠／健康行為；[QA-05](qa.md#qa-05) 冒煙測試規格。

<a id="do-02"></a>
<a id="do-02--typed-environment-and-secret-management"></a>
### DO-02 — 型別化環境設定與機密管理
**追溯：** [REQ-17 基礎設施、健康探測與 CI 交付](../testing/acceptance-matrix.md#req-17); [部署設定登錄](../contracts/interface-contract.md#deployment-config)。
- **前置條件：** 已核准的環境清單與最小權限責任歸屬。
- **正常流程：** 依服務／環境注入型別化設定與機密參照；僅 BB 取得 JWT 簽署權限；保護 GCS 與推播供應商憑證。待批准 [C10](../contracts/interface-contract.md#signed-upload-contract) 的 CORS 放行指定來源的 PUT／GET 與 Content-Type、x-goog-if-generation-match、Cache-Control 等簽署標頭；V4 簽章必須綁定僅建立值與 GET 世代，不能只靠 CORS。不得給用戶端繞過簽章的覆寫／刪除／中繼資料更新權限；既有服務／清理規則不得改動仍可交付的就緒版本／核驗相關中繼資料。廢棄嘗試清理按確切世代定位，鍵值不重用；不要求啟用 Object Versioning 來偷偷補版本可用性。這些是待批准規則，不是已完成的儲存桶／IAM／生命週期部署。
- **失敗流程：** 缺少必填設定時一律以封閉方式失效或使就緒檢查失敗；絕不代用假憑證或記錄機密資料。`JWT_ISSUER`／`JWT_AUDIENCE` 只注入 BB，由 `validateAccess` 使用；BA 不另建 JWT 驗證流程。`REALTIME_INTERNAL_URL` 同時供 `getDevicePresence` 與 `publishCommitted` 使用，故障影響依[設定表](../contracts/interface-contract.md#deployment-config-candidates)。
- **驗收條件：** 每項設定均有服務負責人、敏感度、必填性及缺值時行為。機密值不得進入 PRD／日誌。C10 的標頭、版本存取、清理限制與 [AC-R04](../testing/acceptance-matrix.md#ac-r04-version-cases) 只記錄文件預期結果；尚未核准、部署或實測。
- **候選（待批准）：** 注入[候選設定](../contracts/interface-contract.md#deployment-config-candidates)：兩個內部 URL、內部呼叫者允許清單與失效紀錄相關數值；為 `api`、`realtime` 各建立服務身分，只允許對方呼叫自己的內部操作。
- **交接：** [BA-01](backend-a.md#ba-01)/[BB-01](backend-b.md#bb-01) 必填設定；[QA-05](qa.md#qa-05) 測試矩陣。

<a id="do-03"></a>
<a id="do-03--github-actions-delivery"></a>
### DO-03 — GitHub Actions 交付
**追溯：** [REQ-17 基礎設施、健康探測與 CI 交付](../testing/acceptance-matrix.md#req-17); [部署設定與健康檢查](../contracts/interface-contract.md#deployment-config)。
- **前置條件：** 已核准的品質閘門與受控部署環境。
- **正常流程：** PR 檢查 → 受控測試部署 → 健康／REST／WSS 冒煙測試 → 核准後推進至正式環境，並保留可復原版本。
- **失敗流程：** 缺少設定或檢查失敗時停止推進，並保留可追溯的產物／版本。
- **驗收條件：** GitHub Actions 為 CI/CD 基準（非 GitLab）；流程規格須列明輸入、輸出、核准及回復產物。本 PRD 不宣稱此流程已實作。
- **交接：** 建置／執行階段需求由 [BA-01](backend-a.md#ba-01)、[BB-01](backend-b.md#bb-01)、[FA-01](frontend-a.md#fa-01)、[FB-01](frontend-b.md#fb-01)、PM 與 [QA-05](qa.md#qa-05) 對接。

<a id="do-04"></a>
<a id="do-04--health-monitoring-alerting-and-log-privacy"></a>
### DO-04 — 健康檢查、監控、警示與日誌隱私
**追溯：** [REQ-16 統一錯誤與隱私保護](../testing/acceptance-matrix.md#req-16), [REQ-17 基礎設施、健康探測與 CI 交付](../testing/acceptance-matrix.md#req-17); [HealthResponse](../contracts/interface-contract.md#data-dictionary), [`/health/live` 與 `/health/ready`](../contracts/interface-contract.md#deployment-config)。
- **前置條件：** BA/BB 提供健康狀態與非敏感指標。
- **正常流程：** 區分存活狀態與依賴項就緒狀態；`dependencies` 只在實際檢查後回 `ok`／`fail`，未檢查或該服務不使用的相依項目為 `not_checked`（[HealthResponse](../contracts/interface-contract.md#data-dictionary)）。監控 ACK、即時遞送、復原、活動到期及推播失敗；內部服務身分驗證失敗（待批准 [C13](../contracts/interface-contract.md#internal-auth-layer)）另列告警，不計為使用者登出。
- **失敗流程：** 缺少設定的原因須可診斷（例如 CONFIG_MISSING），但不得暴露機密、本文、權杖或高基數公開使用者 ID 標籤。
- **驗收條件：** 依賴項失敗時回報未就緒／503；日誌與指標標籤須維持隱私安全。
- **交接：** [BA-08](backend-a.md#ba-08)/[BB-08](backend-b.md#bb-08) 健康依賴項；[QA-05](qa.md#qa-05) 警示門檻與驗收。

<a id="do-05"></a>
<a id="do-05--reproducible-performance-verification-environment"></a>
### DO-05 — 可重現的效能驗證環境
**追溯：** [REQ-18 效能驗證與容量界線](../testing/acceptance-matrix.md#req-18); [已核准的維運設定](../contracts/interface-contract.md#deployment-config)。
- **前置條件：** QA 工作負載與 PM 門檻已明確規定。
- **正常流程：** 記錄重現測試所需的軟體版本、運算／資源、網路、DB 連線池、Redis 與設定參照。
- **失敗流程：** 不可比較的環境不得共用容量結論；未測試的規模絕不回報為通過。
- **驗收條件：** 環境描述須足以重現未來測量；本規格不宣稱任何效能結果。
- **交接：** 將可重現環境紀錄交給 [QA-05](qa.md#qa-05)。

<a id="do-06"></a>
<a id="do-06--web-assets-and-protected-deep-route-fallback"></a>
<a id="do-06--web-資產與受保護深層路由備援"></a>
### DO-06 — Web 資產與受保護深層連結的頁面路由回退
**追溯：** [REQ-21 Web 深層連結與授權後路由返回](../testing/acceptance-matrix.md#req-21); [FB-07](frontend-b.md#fb-07) 路由責任、[FA-05](frontend-a.md#fa-05) 聊天路由行為、[A12](../contracts/interface-contract.md#api-a12)、[A13](../contracts/interface-contract.md#api-a13)、`/api/v1` 與 `/ws/v1` 路由。
- **前置條件：** 已核准的 Web 資產建置與已知 UI 路由命名空間。
- **正常流程：** 提供同一 Web 專案資產；僅允許下列候選 UI 路徑樣式重新整理／深層連結的頁面路由回退：根路徑 `/`（行為見[根路徑規則](../ui/web-rwd.md#rwd-root-route)）、`/login`、`/register`、`/contacts`、`/chats`、`/chats/{conversation_id}`、`/profile` 與 `/groups/{conversation_id}/manage`。保留 `/api/v1` REST 與 `/ws/v1` WSS 的獨立後端路由。
- **失敗流程：** 絕不將 `/api/v1` 或 `/ws/v1` 路徑或錯誤改寫至 Web 殼層。未知 UI 路由顯示受控的找不到頁面狀態；受保護路由須等待授權，且不得洩露內容。
- **驗收條件：** 重新整理／直接瀏覽每個列出的 UI 路由，都會進入相同授權守衛並在授權後返回原路由；根路徑 `/` 依[根路徑規則](../ui/web-rwd.md#rwd-root-route)在初始化後導向 `/login` 或 `/chats`，初始化中不顯示受保護內容；頁面路由回退限於這些 UI 路徑樣式，API/WSS 路徑與狀態行為維持不變。
- **交接：** [FB-07](frontend-b.md#fb-07) 路由命名空間；[BA-01](backend-a.md#ba-01)/[BB-03](backend-b.md#bb-03) 來源／入口；[QA-06](qa.md#qa-06) 深層連結矩陣。

## 決策與共用參照

- [響應式 Web 行為](../ui/web-rwd.md#web-rwd)
- [決策：Web Push 範圍](../decisions.md#decision-web-push)
- [決策：響應式 Web 版面](../decisions.md#decision-rwd)
- [返回文件導覽](../README.md)
