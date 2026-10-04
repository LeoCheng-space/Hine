<a id="infrastructure"></a>
# 基礎設施

HINE 的部署與維運設定。
課程版部署採單台 GCP Compute Engine VM＋Docker Compose：單一 Web 入口、`api`、`realtime`（各一實例）、PostgreSQL 與單一 Redis；附件使用 GCS 私有儲存桶。只有 HTTPS／WSS Web 入口對外，內部路由、PostgreSQL、Redis 不公開；不採 Cloud Run、Kubernetes 或自動擴縮。不承諾高可用。

可執行的開發環境、秘密產生、備份／還原與正式環境交接命令見 [部署與維運手冊](../docs/deployment/README.md)。預設 `docker-compose.yml` 僅啟動真實 PostgreSQL17／Redis7；BA 使用選用 `realtime` profile。正式 Caddy overlay 必須配合 BB 提供的真實 `api` Compose 產物與 FA／FB Web 建置，缺少時明確失敗，不以假服務代替。本文件不宣稱 VM、DNS、TLS 或產品正式部署已完成。
