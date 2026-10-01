<a id="hine-ic-04--devops-角色-prd"></a>
# HINE-IC-0.4 — 維運（DO）角色 PRD

**版本：** HINE-IC-0.4  
**狀態：** 現行規格（2026-10-01 PM 決議）
**來源：** [歷史來源：HINE-IC-0.4 角色 PRD](../HINE-IC-0.4-role-prds.md); 唯一現行介面規格依據為 [共同介面契約](../contracts/interface-contract.md).  
**角色目的：** 負責主機路由、設定／機密綁定、交付流程、監控及可重現的驗證環境。本 PRD 規定未來行為與驗收要求，不代表已實作或已完成測試。
**必讀／串接時查閱：** [系統架構](../architecture/README.md)、[共同介面契約](../contracts/interface-contract.md)、[驗收矩陣](../testing/acceptance-matrix.md)；各功能串接見下方追溯／交接。 [返回文件導覽](../README.md)。

## 範圍

- **範圍內：** 主機路由、設定／機密綁定、交付流程、監控及可重現的驗證環境；以及下方角色專屬功能卡。
- **範圍外：** 其他角色所負責的範圍；不得單方變更共用 API／事件 ID、正式資料、ACK、游標或同步語意。介面與跨模組啟動／部署設定可以依[共同變更流程](../../CONTRIBUTING.md#interface-changes)與受影響成員一起修改；內部工具選擇由負責人決定。先對齊[近期串接基線](../contracts/interface-contract.md#integration-baseline)，不要求一次鎖死整份規格。
- **共用 Web 行為：** 遵循 [Web／RWD 規格](../ui/web-rwd.md#web-rwd)；不得另訂斷點或重複定義版面規則。

## 功能索引

- [DO-01 — 網域、TLS、入口與路由](#do-01)
- [DO-02 — 型別化環境設定與機密管理](#do-02)
- [DO-03 — GitHub Actions 交付](#do-03)
- [DO-04 — 健康檢查、監控、警示與日誌隱私](#do-04)
- [DO-05 — 可重現的效能驗證環境](#do-05)
- [DO-06 — Web 資產與受保護深層連結的頁面路由回退](#do-06)

## 角色目的與責任界線

提供指定的主機路由、設定／機密綁定、交付流程、監控及可重現的驗證環境。課程版採單台 GCP Compute Engine VM＋Docker Compose；不承諾高可用。

<a id="do-01"></a>
<a id="do-01--domain-tls-ingress-and-routes"></a>
### DO-01 — 網域、TLS、入口與路由
**追溯：** [REQ-17 基礎設施、健康探測與 CI 交付](../testing/acceptance-matrix.md#req-17); [共同介面契約部署／健康設定](../contracts/interface-contract.md#deployment-config), 公開 REST `/api/v1` 與 WSS `/ws/v1` 路由。
- **前置條件：** 已核准的網域與目標環境。
- **正常流程：** 在 `hine.run.place` 下由單一 Web 入口提供公開 HTTPS REST `/api/v1` 與 WSS `/ws/v1`；只轉送 Web HTTPS／WSS，`/internal/*` 與資料庫、Redis 均不公開。`api` 與 `realtime` 各一實例，透過 Compose 私有網路以內部 HTTP＋JSON 呼叫。
- **失敗流程：** TLS、路由或必要依賴項失敗時，不得通過就緒檢查／部署驗收；公開反向代理不得轉送任何 `/internal/*` 路徑。
- **驗收條件：** 單一公開契約；內部健康端點不得暴露為使用者 API。Web 殼層頁面路由回退維持核准 UI 路徑，API/WSS 路由獨立。
- **交接：** [BA-01](backend-a.md#ba-01)/[BB-01](backend-b.md#bb-01) 連接埠／健康行為；[QA-05](qa.md#qa-05) 冒煙測試規格。

<a id="do-02"></a>
<a id="do-02--typed-environment-and-secret-management"></a>
### DO-02 — 型別化環境設定與機密管理
**追溯：** [REQ-17 基礎設施、健康探測與 CI 交付](../testing/acceptance-matrix.md#req-17); [部署設定登錄](../contracts/interface-contract.md#deployment-config)。
- **前置條件：** 已核准的環境清單與最小權限責任歸屬。
- **正常流程：** 依服務／環境注入型別化設定與機密參照；僅 BB 取得 JWT 簽署權限。GCS 使用私有附件流程；CORS 放行指定來源及簽署 PUT／GET 所需標頭，V4 簽章綁定僅建立條件與 GET 世代。不得給用戶端繞過簽章的覆寫／刪除／中繼資料更新權限；廢棄嘗試按確切世代清理，鍵值不重用。
- **失敗流程：** 必填設定缺少時封閉失效或就緒檢查失敗；絕不使用假憑證或記錄機密。`JWT_ISSUER`／`JWT_AUDIENCE` 僅注入 BB。內部呼叫使用由維運注入的 bearer secret：Secret 參照 `INTERNAL_CALLER_TOKEN_SECRET_REF`，呼叫方身分依 `INTERNAL_ALLOWED_CALLERS` 比對。GCS 就緒僅於儲存功能啟用時要求；活動租約、FCM／APNS 推播憑證本版範圍外。
- **驗收條件：** 依數值表使用一致的操作設定；必要 DB、內部驗證及已啟用儲存設定不完整則就緒失敗並清楚報錯。機密以 VM 上 Compose secrets 或權限受控環境檔注入，絕不提交 Git、寫入日誌或 PRD；不要求 GCS Object Versioning。
- **交接：** [BA-01](backend-a.md#ba-01)/[BB-01](backend-b.md#bb-01) 必填設定；[QA-05](qa.md#qa-05) 測試矩陣。

<a id="do-03"></a>
<a id="do-03--github-actions-delivery"></a>
### DO-03 — GitHub Actions 交付
**追溯：** [REQ-17 基礎設施、健康探測與 CI 交付](../testing/acceptance-matrix.md#req-17); [部署設定與健康檢查](../contracts/interface-contract.md#deployment-config)。
- **前置條件：** 已核准的品質閘門與受控部署環境。
- **正常流程：** CI 繼續使用現有 GitHub Actions 品質閘門與交付流程，不因語言選擇增設平台；各模組自行選擇語言／框架，使用介面文件、Schema／測試樣例維持跨語言契約。記錄各模組可重現的啟動及測試命令。
- **失敗流程：** 缺少設定或檢查失敗時停止推進，並保留可追溯的產物／版本。
- **驗收條件：** GitHub Actions 為 CI 基準（非 GitLab）；流程規格列明輸入、輸出、核准及回復產物。各模組提供可重現的啟動／測試命令；此 PRD 不宣稱流程已實作。
- **交接：** 建置／執行階段需求由 [BA-01](backend-a.md#ba-01)、[BB-01](backend-b.md#bb-01)、[FA-01](frontend-a.md#fa-01)、[FB-01](frontend-b.md#fb-01)、PM 與 [QA-05](qa.md#qa-05) 對接。

<a id="do-04"></a>
<a id="do-04--health-monitoring-alerting-and-log-privacy"></a>
### DO-04 — 健康檢查、監控、警示與日誌隱私
**追溯：** [REQ-16 統一錯誤與隱私保護](../testing/acceptance-matrix.md#req-16), [REQ-17 基礎設施、健康探測與 CI 交付](../testing/acceptance-matrix.md#req-17); [HealthResponse](../contracts/interface-contract.md#data-dictionary), [`/health/live` 與 `/health/ready`](../contracts/interface-contract.md#deployment-config)。
- **前置條件：** BA/BB 提供健康狀態與非敏感指標。
- **正常流程：** 區分存活及依賴就緒；`dependencies` 僅在實際檢查後回 `ok`／`fail`，未檢查或不使用的相依項目為 `not_checked`。監控 ACK、即時遞送、復原；內部服務身分驗證失敗依 C13 區分，不計為使用者登出。
- **失敗流程：** 缺設定原因可診斷（例如 CONFIG_MISSING），但不得暴露機密、本文、權杖或高基數公開使用者 ID 標籤。只設最小健康與錯誤警示，不建完整告警平台。
- **驗收條件：** 依賴失敗回報未就緒／503；日誌與指標標籤維持隱私安全。
- **交接：** [BA-08](backend-a.md#ba-08)/[BB-08](backend-b.md#bb-08) 健康依賴項；[QA-05](qa.md#qa-05) 警示門檻與驗收。

<a id="do-05"></a>
<a id="do-05--reproducible-performance-verification-environment"></a>
### DO-05 — 可重現的效能驗證環境
**追溯：** [REQ-18 效能驗證與容量界線](../testing/acceptance-matrix.md#req-18); [已核准的維運設定](../contracts/interface-contract.md#deployment-config)。
- **前置條件：** QA 工作負載與課程基線已明確規定。
- **正常流程：** 記錄可重現測試所需的 VM、資料集、網路、工具及版本，並記錄 PostgreSQL／Redis 與設定參照。
- **失敗流程：** 不可比較的環境不得共用容量結論；1,000／5,000／10,000 連線只作未來壓測，不回報為本版交付或通過。
- **驗收條件：** 環境描述足以重現課程基線測量；所有數值為目標，未量測，不宣稱效能結果。
- **交接：** 將可重現環境紀錄交給 [QA-05](qa.md#qa-05)。

<a id="do-06"></a>
<a id="do-06--web-assets-and-protected-deep-route-fallback"></a>
<a id="do-06--web-資產與受保護深層路由備援"></a>
### DO-06 — Web 資產與受保護深層連結的頁面路由回退
**追溯：** [REQ-21 Web 深層連結與授權後路由返回](../testing/acceptance-matrix.md#req-21); [FB-07](frontend-b.md#fb-07) 路由責任、[FA-05](frontend-a.md#fa-05) 聊天路由行為、[A12](../contracts/interface-contract.md#api-a12)、[A13](../contracts/interface-contract.md#api-a13)、`/api/v1` 與 `/ws/v1` 路由。
- **前置條件：** 單一 Web 建置資產與共用 UI 路徑命名空間。
- **正常流程：** 提供同一網站資產；允許根路徑 `/`、`/login`、`/register`、`/contacts`、`/chats`、`/chats/{conversation_id}`、`/profile`、`/groups/{conversation_id}/manage` 頁面路由回退。保留 `/api/v1` REST 與 `/ws/v1` WSS 獨立路由。
- **失敗流程：** 絕不將 API/WSS 路徑或錯誤改寫到 Web 殼層；未知 UI 路由顯示受控找不到頁面狀態；受保護路由授權前不得洩露內容。
- **驗收條件：** 所列路徑直接瀏覽／重新整理進入相同授權守衛，授權後返回原路由；根路徑初始化後以 replace 導向 `/login` 或 `/chats`。
- **交接：** [FB-07](frontend-b.md#fb-07) 路由命名空間；[BA-01](backend-a.md#ba-01)/[BB-03](backend-b.md#bb-03) 來源／入口；[QA-06](qa.md#qa-06) 深層連結矩陣。

## 決策與共用參照

- [響應式 Web 行為](../ui/web-rwd.md#web-rwd)
- [決策：Web Push 範圍](../decisions.md#decision-web-push)
- [決策：響應式 Web 版面](../decisions.md#decision-rwd)
- [返回文件導覽](../README.md)
