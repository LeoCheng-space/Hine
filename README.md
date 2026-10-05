# HINE

HINE 是以軟體工程期末專案形式開發的跨平台即時通訊系統。（2026-10-01 PM 決議）

<a id="project-goals"></a>
## 專案目標

- 即時一對一與群組訊息
- 基於 WebSocket 的雙向通訊
- 訊息持久保存與歷史紀錄
- 離線同步與重複資料防護
- 圖片與檔案傳輸
- 持續整合／持續交付、監控、測試及負載測試

> 本版不含 Web Push 或 iOS／Android 原生推播（本版範圍外，2026-10-01 PM 決議）；關閉網頁後不保證通知。

<a id="repository-structure"></a>
## 儲存庫結構

```text
Hine/
├── docs/
├── frontend/
├── backend/
├── infra/
├── tests/
└── .github/
```

<a id="main-areas"></a>
### 主要區域

- `docs/` — 架構、API、WebSocket、資料庫、部署及測試文件
- `frontend/` — 用戶端應用程式
- `backend/api/` — REST API 與業務資料服務
- `backend/realtime/` — WebSocket 與即時訊息服務
- `backend/common/` — 可選的後端共用程式碼；同語言模組可自行決定是否共用，非整合必要條件。跨語言整合依據為[共用介面契約](docs/contracts/interface-contract.md)、Schema 與測試樣例
- `infra/` — Docker、GCP、監控及維運指令稿
- `tests/` — 整合、端對端及負載測試
- `.github/` — GitHub Actions 與協作範本

<a id="core-technology-direction"></a>
## 核心技術方向

- WebSocket / WSS
- PostgreSQL
- Redis／Redis 發布／訂閱（Pub/Sub）
- Google Cloud Storage
- 單台 GCP Compute Engine VM＋Docker Compose；`api` 與 `realtime` 各一實例
- 各模組負責人自選熟悉的程式語言／框架，以 HTTP／JSON、WebSocket 事件格式及共用介面文件／Schema／測試樣例整合
- GitHub Actions
- GCP Logging 與基本 health／error 檢查；Prometheus／Grafana 非本版必交
- 負載測試工具由 QA 選擇一套 HTTP＋WebSocket 工具或語言，於 `tests/load/README.md` 記錄

> 本版不納入 FCM／APNs、推播工作程序及推播憑證（本版範圍外，2026-10-01 PM 決議）。已提供 BA 訊息／回條／同步、共用環境配置及 QA 協定工具；其他模組與完整產品部署／驗收不得由這些交付推論為完成。

<a id="collaboration"></a>
## 協作方式

此儲存庫採用適合六人學生團隊的簡易流程：

1. 拉取最新的 `main`
2. 建立 `feature/<name>` 或 `fix/<name>` 分支
3. 完成一項聚焦的變更
4. 提交並推送
5. 建立合併請求（PR）
6. 等待審查與持續整合檢查
7. 僅在檢查通過後合併

團隊工作流程請參閱[協作指南](CONTRIBUTING.md)。

<a id="team-areas"></a>
## 團隊職責

- 前端 A — 聊天介面與即時互動
- 前端 B — 認證、聯絡人、個人資料及路由
- 後端 A — WebSocket 與即時通訊
- 後端 B — REST API 與資料庫
- 專案管理／維運 — 架構、持續整合／持續交付、基礎設施及整合
- 品質驗證 — 整合、端對端、負載、迴歸及驗收測試

## 團隊文件入口

請從 [HINE-IC-0.4 文件地圖](docs/README.md)依角色閱讀，並先讀[系統架構](docs/architecture/README.md)。角色需求文件：[前端 A](docs/prd/frontend-a.md) · [前端 B](docs/prd/frontend-b.md) · [後端 A](docs/prd/backend-a.md) · [後端 B](docs/prd/backend-b.md) · [維運](docs/prd/devops.md) · [品質驗證](docs/prd/qa.md)。

## 可執行交付與驗證邊界

- [Backend A](backend/realtime/README.md)：Python 3.12＋aiohttp／Redis，提供 W01–W17／W19 與既有群組投影、BB 內部 HTTP 交接、提交後扇出、回條、初始化／事件流同步、工作階段失效與健康檢查；BA 不自行簽發／驗 JWT、不代替 BB 保存訊息、回條／游標或執行產品 quota。
- [共用環境](infra/docker/README.md)：`sh infra/scripts/init-dev.sh` 產生不覆寫既有值的私有設定／Secret；`docker compose up -d --wait` 啟動 PostgreSQL／Redis。資料卷保留，開發端口須明確選用 loopback override。
- [部署與維運](docs/deployment/README.md)：真實 BB／Web 交付後才做完整部署；公開反向代理禁止內部／health 路由，提供備份／還原、回滾與 preflight。Docker daemon、VM 存取與正式設定仍是實際部署前提。
- [QA 協定工具](tests/load/README.md)：一套 HTTP＋WebSocket CLI 驗證 ACK／收訊／歷史與真實負載節奏；工具供 Jackie 確認。協定訊框不等於瀏覽器保存／呈現，50 WSS 容量與重連目標須在真實產品環境量測。
- [CI](.github/workflows/repository-checks.yml)：檢查已實作的 Python、Redis 邊界、QA 證據與維運安全，並在具 Docker 的 runner 驗證資料服務、映像建置與一次性 DB 還原；未推送／未執行的 Actions 不宣稱成功。

首輪串接仍需要 BB 的 Schema／Migration、A01／A02／A05／A13／A19、`validateAccess`／`persistIfAbsent`／`authorize`／`readSessionInvalidations`，以及 FA／FB 的單一 Web、SessionContext／openChat 與本機保存交付。測試專用 BB authority 只驗 BA／工具，不是 BB 產品或 PostgreSQL／JWT／瀏覽器驗收。
回條／同步串接另外需要 BB 的 `persistReceipt`、`readBootstrap`、`readFeed`，以及每頁當前授權／加入界線；`SYNC_PAGE_LIMIT=100` 是本輪 BA 的必要設定。斷線 smoke 的 QA SQLite 投影不是 FA 瀏覽器儲存，仍需真正產品串接與瀏覽器驗收。

學校作業階段暫緩 main 強制分支保護；一般功能分支／PR／Review／適用 CI 流程仍保留，見[協作指南](CONTRIBUTING.md)。
