# 基礎設施

HINE 的部署與維運設定。

## 目前開發環境

目前 HINE 開發／整合環境部署於 Google Cloud Platform。

- Web Server：GCP Compute Engine
- Database Server：GCP Compute Engine
- Database：PostgreSQL 16
- Web Server：Nginx
- TLS：Let's Encrypt
- Domain：`hine.run.place`

目前開發環境暫時採 Web 與 PostgreSQL 分離部署，詳細資訊請參考：

- [`infra/gcp/README.md`](./gcp/README.md)

## HINE-IC-0.4 目標架構

課程版目標架構仍採：

```text
Single GCP Compute Engine VM
└─ Docker Compose
   ├─ Web
   ├─ api
   ├─ realtime
   ├─ PostgreSQL
   └─ Redis
```

目前分離部署的 PostgreSQL16／Nginx 環境紀錄與下列課程版 Compose PostgreSQL17 目標分開管理；本次整合不升級、搬移或覆寫既有 VM／資料庫。

課程版部署採單台 GCP Compute Engine VM＋Docker Compose：單一 Web 入口、API、realtime（各一實例）、PostgreSQL 與單一 Redis；附件可選用 GCS 私有儲存桶。只有 HTTPS／WSS Web 入口對外，內部路由、PostgreSQL、Redis 不公開；不採 Cloud Run、Kubernetes 或自動擴縮，不承諾高可用。

根目錄 Compose 已包含實際 API 建置，不需要外部 `API_PROVIDER_COMPOSE` 或假 API：預設只啟動 PostgreSQL17／Redis7；`product` profile 加入 API，`realtime` profile 加入 BA。從 repository root 初始化並啟動完整本機服務：

```sh
sh infra/scripts/init-dev.sh
docker compose --profile product --profile realtime up -d --build --wait --wait-timeout 120
```

初始化器會保留既有 `.env`／秘密檔；資料庫目標解析器只讀取單行 assignment（可有 `export`，不會執行 shell），且 `POSTGRES_USER`／`POSTGRES_DB` 必須是 literal identifier，不接受變數展開或多行／續行值。無法解析時會 fail closed，不會自動輪替不一致的 `database_url`／PostgreSQL 帳密。API 開發／測試環境連線時套用真實 schema migration；production 啟動只驗證、絕不自動套用 DDL，正式 migration 須先備份、停止寫入者並執行 `sh infra/scripts/stack.sh migrate`。前端 build instructions 在[Web app README](../frontend/app/README.md)。

反向代理的 `TRUSTED_PROXY_NETWORKS` 預設空值、API 不信任任何轉送標頭；正式 Compose 會要求明確設定。必須使用營運方實際驗證、隔離的代理 CIDR，並確保代理覆寫外部傳入的 `X-Hine-Client-IP`、用戶無法從該網段直連 API。不可複製寬廣或臆測的子網，也不可把此標頭當認證。

GCS 為選配，只有實際私有 bucket 與可簽署的真實服務身分備妥後才啟用 `infra/docker/compose.gcs.yml`。正式 `stack.sh` 透過 `GCS_BUCKET`、絕對路徑 `GCS_CREDENTIALS_FILE` 加入 overlay；不產生假憑證。實際建置／設定、GCS 操作限制、私有資料備份還原與安全邊界請見[部署與維運手冊](../docs/deployment/README.md)。前端 build instructions 由[Web app README](../frontend/app/README.md) 管理。

上方既有 VM、DNS、Nginx／TLS 與分離 PostgreSQL16 進度以 [GCP 環境紀錄](./gcp/README.md) 為準；不能由此推論課程版完整 Compose API／WSS、真 GCS 或備份回滾已驗收。目標產品的 Docker 啟動、雲端權限與實體環境驗收須依實際可用資源單獨記錄。
