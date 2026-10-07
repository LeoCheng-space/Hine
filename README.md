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

> 本版不納入 FCM／APNs、推播工作程序及推播憑證（本版範圍外，2026-10-01 PM 決議）。API／Web／BA 的產品模組均已有實作且有本機產品證據；本地程式、資料庫 fault 與協定結果不等於已部署，亦不替代正式 VM／雲端、GCS、瀏覽器裝置及容量驗收。

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

- [Backend B API](backend/api/README.md)：`backend/api/src/hine_api/` 提供 Python／aiohttp REST、PostgreSQL migration／交易、JWT／工作階段與授權、訊息／回條／同步、GCS signed transfer；實際 PostgreSQL／API／瀏覽器產品驗證另見下方證據邊界。
- [Backend A](backend/realtime/README.md)：`backend/realtime/src/hine_realtime/` 提供 W01–W20（W21／W22 活動租約範圍外）、Redis 通知／在線狀態、W18 聯絡人 presence；BB 仍是 JWT／工作階段／授權／持久化權威。
- [Web 應用](frontend/app/README.md)：`frontend/app/src/` 為整合 FA＋FB 的 React／TypeScript 網站，含 Session、路由、資料頁、唯一 WSS、IndexedDB 原子投影與同步。
- [系統架構程式碼對應](docs/architecture/README.md#arch-code-map)：列出 API、Web、realtime、infra 與測試的實際來源目錄。
- [共用環境](infra/docker/README.md)：`sh infra/scripts/init-dev.sh` 產生不覆寫既有值的私有設定／Secret；`docker compose --profile product --profile realtime up -d --build --wait` 啟動 PostgreSQL／Redis 與真實 API、realtime 服務。資料卷保留，開發端口須明確選用 loopback override。
- [部署與維運](docs/deployment/README.md)：列出真實雲端／VM 部署前提、私網路由、備份／還原、回滾與 preflight；雲端執行結果不得由本機證據推論。
- [QA 協定工具](tests/load/README.md)：HTTP＋WebSocket 工具量測協定 ACK／收訊／歷史與負載節奏；協定呈現不等同瀏覽器保存／呈現。容量政策與實測結果分開記錄。
- [CI](.github/workflows/repository-checks.yml)：workflow 定義不等同已執行的 Actions 成功。

程式碼／測試工具／本機元件證據、瀏覽器呈現證據、正式政策核准與雲端／VM／GCS／實體裝置驗收是不同層級。當前本機產品證據與明確未達外部 gate 由 [CHANGELOG](docs/CHANGELOG.md) 及[驗收矩陣](docs/testing/acceptance-matrix.md)列示；不得以程式存在、fixture、協定負載或文件決議冒稱遠端 CI、雲端部署、Chrome／Edge／Android 全面驗收或團隊簽核。Title 1–80 字元仍是候選，未批准為全域政策。

學校作業階段暫緩 main 強制分支保護；一般功能分支／PR／Review／適用 CI 流程仍保留，見[協作指南](CONTRIBUTING.md)。
