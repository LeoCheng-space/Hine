<a id="scripts"></a>
# 指令稿

維運、部署、環境設定與維護用指令稿。
部署與維運腳本配合單台 GCP Compute Engine VM＋Docker Compose；機密僅由 VM 上權限受控的 Compose secrets／環境檔注入，絕不提交 Git。

- 根目錄 `build.sh`：一鍵安裝／部署入口，編排下列指令稿；操作手冊見 [one-click.md](../../docs/deployment/one-click.md)。
- `init-dev.sh`：不覆寫秘密的安全隨機產生（呼叫 `init-secrets.sh` 與 `init-env.sh`）。
- `init-secrets.sh ABSOLUTE_DIR POSTGRES_USER POSTGRES_DB`：在指定絕對目錄產生／驗證7個owner-only密鑰檔；保留既有值、不一致即失敗不輪替。開發用 `.secrets/`，正式機用 `/srv/hine/secrets`。
- `init-env.sh UID GID`：由 `.env.example` 建立一次 `.env` 並填入runtime owner IDs；既有 `.env` 不改寫。
- `deploy-config.py deploy|active FILE`：嚴格解析 `deploy.env`／`active.env`（白名單欄位、拒絕shell字元、格式驗證），不執行檔案內容。
- `deploy-checks.py subnets|dns`：正式部署預檢；子網路重疊（略過本部署相同CIDR的網路）與DNS結果完全比對（不得有AAAA）。
- `backup-postgres.sh`／`restore-postgres.sh`：真實 PostgreSQL工具；還原必須使用 `--confirm-destructive`。
- `preflight.sh`：區分本地產物／設定驗證與真實公開DNS／TLS／REST／WSS／隔離探測。
- `stack.sh`：操作內建真 API／BA 的正式 Compose；`migrate` 僅明確執行 API 遷移，啟動不自行套用正式 DDL，禁止刪除資料卷。
- `check-product.py`：`python infra/scripts/check-product.py --output NEW_PATH [--docker PATH] [--web-root PATH]`；只對fresh owned local Compose project建置真API／BA、明確production migration、verified privateCA HTTPS/WSS、持久回條、restart與pg_dump／atomic clone restore做驗收。拒絕remote Docker及既有output／symlink，scrub inherited Compose／product設定，不讀checkout `.env`／`.secrets`、不碰operator DB。0700 temp／0600秘密和報告；缺Docker exit2／NOT_EXERCISED，絕不PASS。只有新owned project及image tags可清理，無global prune。

命令與先決條件見 [部署手冊](../../docs/deployment/README.md)。指令稿不建立雲端資源，也不代表已完成部署。
