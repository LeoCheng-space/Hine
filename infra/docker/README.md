# Docker

課程部署使用單台 VM 上的 Docker Compose，包含 Web 入口、`api`、`realtime`、PostgreSQL 與單一 Redis；GCS 私有桶保存附件。內部路由及資料服務不由公開入口轉送。
本機開發容器與 Docker 相關設定。

- 根目錄 `docker-compose.yml`：私有 PostgreSQL17／Redis7；`product` profile 建置真實 API，`realtime` profile 加入 BA。
- `compose.dev.yml`：明確選用的127.0.0.1連接埠，不得套用於正式環境。
- `compose.local.yml`：`./build.sh` 本機 stack；Caddy 使用本機私有CA，只綁 `127.0.0.1:8443`，與 `compose.acceptance.yml` 共用 `Caddyfile.acceptance`。不得用於公開主機。
- `compose.production.yml` 與 `Caddyfile`：同源 Web／API／WSS 入口與正式設定；Web 使用 `frontend/app/dist` 的實際建置。`edge`／`backend` 網路以 `HINE_EDGE_SUBNET`／`HINE_BACKEND_SUBNET` 固定子網路，`TRUSTED_PROXY_NETWORKS` 為這兩段。
- `compose.gcs.yml`：僅在提供真實私有桶與簽章憑證檔時加入：正式機由 `stack.sh`（`GCS_CREDENTIALS_FILE`），本機由 `./build.sh`（`.env` 的 `GCS_BUCKET` 與 `GCS_CREDENTIALS_FILE` 皆有效時）；沒有假儲存 fallback。
- `compose.acceptance.yml`／`Caddyfile.acceptance`：僅供 `check-product.py` 的fresh owned local／CI project；正式模式API／BA、隔離backend／edge CIDR、private Caddy CA與唯一loopback HTTPS publication。不是正式VM overlay；不自動接管現有Nginx／PostgreSQL16，不提供GCS假provider。真production Web可由 `--web-root` 提供，匹配random origin的runtime-config只寫owned temp，不改原build。
- 完整啟動、限制與精確公開路由見 [部署手冊](../../docs/deployment/README.md)。
