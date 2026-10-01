<a id="infrastructure"></a>
# 基礎設施

HINE 的部署與維運設定。
課程版部署採單台 GCP Compute Engine VM＋Docker Compose：單一 Web 入口、`api`、`realtime`（各一實例）、PostgreSQL 與單一 Redis；附件使用 GCS 私有儲存桶。只有 HTTPS／WSS Web 入口對外，內部路由、PostgreSQL、Redis 不公開；不採 Cloud Run、Kubernetes 或自動擴縮。不承諾高可用。
