# Docker

課程部署使用單台 VM 上的 Docker Compose，包含 Web 入口、`api`、`realtime`、PostgreSQL 與單一 Redis；GCS 私有桶保存附件。內部路由及資料服務不由公開入口轉送。
本機開發容器與 Docker 相關設定。

- 根目錄 `docker-compose.yml`：私有 PostgreSQL17／Redis7 與選用 BA profile。
- `compose.dev.yml`：明確選用的127.0.0.1連接埠，不得套用於正式環境。
- `compose.production.yml` 與 `Caddyfile`：僅真實入口／BA設定；`api` 與 Web產物由原負責人提供。
- 完整啟動、限制與精確公開路由見 [部署手冊](../../docs/deployment/README.md)。
