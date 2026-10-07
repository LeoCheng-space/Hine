# Docker

課程部署使用單台 VM 上的 Docker Compose，包含 Web 入口、`api`、`realtime`、PostgreSQL 與單一 Redis；GCS 私有桶保存附件。內部路由及資料服務不由公開入口轉送。
本機開發容器與 Docker 相關設定。

- 根目錄 `docker-compose.yml`：私有 PostgreSQL17／Redis7；`product` profile 建置真實 API，`realtime` profile 加入 BA。
- `compose.dev.yml`：明確選用的127.0.0.1連接埠，不得套用於正式環境。
- `compose.production.yml` 與 `Caddyfile`：同源 Web／API／WSS 入口與正式設定；Web 使用 `frontend/app/dist` 的實際建置，需明確指定隔離 proxy CIDR。
- `compose.gcs.yml`：僅在提供真實私有桶與簽章憑證檔時由正式 wrapper 加入；沒有假儲存 fallback。
- 完整啟動、限制與精確公開路由見 [部署手冊](../../docs/deployment/README.md)。
