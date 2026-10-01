<a id="deployment"></a>
# 部署

課程版部署目標為單台 GCP Compute Engine VM＋Docker Compose，含 Web 入口、各一實例的 `api`／`realtime`、PostgreSQL 與單一 Redis；附件沿用 GCS 私有儲存桶。不採 Cloud Run、Cloud SQL、Memorystore、外部 Load Balancer、執行個體群組、Kubernetes 或自動擴縮。

僅 Web HTTPS／WSS 入口對外；`/internal/*`、PostgreSQL、Redis 不公開或由反向代理轉送。Compose 私有網路內部呼叫使用服務身分 bearer secret；機密以 VM 上 Compose secrets 或權限受控環境檔注入，絕不提交 Git。保留持久化磁碟、備份／還原演練與部署回滾；缺少推播金鑰不影響核心就緒，活動租約及 FCM／APNS 本版範圍外。此為部署規格，不代表雲端資源已建立或已部署，亦不承諾高可用。
