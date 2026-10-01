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
- `backend/common/` — 後端共用程式碼
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
- Prometheus / Grafana
- 負載測試工具由 QA 選擇一套 HTTP＋WebSocket 工具或語言，於 `tests/load/README.md` 記錄

> 本版不納入 FCM／APNs、推播工作程序及推播憑證（本版範圍外，2026-10-01 PM 決議）。上述為決議方向，尚未實作或測試。

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
