<a id="scripts"></a>
# 指令稿

維運、部署、環境設定與維護用指令稿。
部署與維運腳本配合單台 GCP Compute Engine VM＋Docker Compose；機密僅由 VM 上權限受控的 Compose secrets／環境檔注入，絕不提交 Git。

- `init-dev.sh`：不覆寫秘密的安全隨機產生。
- `backup-postgres.sh`／`restore-postgres.sh`：真實 PostgreSQL工具；還原必須使用 `--confirm-destructive`。
- `preflight.sh`：區分本地產物／設定驗證與真實公開DNS／TLS／REST／WSS／隔離探測。
- `stack.sh`：操作內建真 API／BA 的正式 Compose；`migrate` 僅明確執行 API 遷移，啟動不自行套用正式 DDL，禁止刪除資料卷。

命令與先決條件見 [部署手冊](../../docs/deployment/README.md)。指令稿不建立雲端資源，也不代表已完成部署。
