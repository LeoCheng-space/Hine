<a id="database"></a>
# 資料庫

API 使用 PostgreSQL 作為帳戶、認證狀態、訊息、同步事件與附件中繼資料的權威持久層。Redis 僅供 realtime 暫態協調，不是訊息權威或可恢復的訊息佇列。資料庫 schema 與查詢由 `backend/api/migrations/` 和 `backend/api/src/hine_api/` 維護；不要在文件或手工 SQL 中建立第二套模型。

## Migration 與啟動

從 repository root 初始化開發秘密並啟動真實 API profile：

```sh
sh infra/scripts/init-dev.sh
docker compose --profile product --profile realtime up -d --build --wait --wait-timeout 120
```

API container 以 `python -m hine_api` 啟動。開發／測試環境連線時會套用遷移；staging／production 只核對 `schema_migrations` checksum 與檔案集合，不會自動套用 DDL。開發環境可明確執行：

```sh
docker compose --profile product run --build --rm --no-deps api python -m hine_api migrate
```

正式遷移必須先備份並停止所有寫入者；使用完整 production 環境及 `stack.sh` wrapper。先確保 PostgreSQL／Redis 已啟動，再明確執行唯一支援的零參數 migration 命令：

```sh
sh infra/scripts/stack.sh up -d postgres redis
sh infra/scripts/stack.sh migrate
```

Wrapper 執行 production preflight，建置並以 real API image 執行 `python -m hine_api migrate`。migration 完成後才啟動完整產品服務；API 之後只驗證遷移。遷移依 `NNN_*.sql` 排序，在 PostgreSQL transaction 中以 schema-scoped advisory lock 序列化，記錄 `schema_migrations` 的 SHA-256 checksum。已套用檔案 checksum 或檔案集合不一致會失敗關閉。遷移不會 drop database，也不會自動建立替代資料庫。只有 `DATABASE_SCHEMA` 可指定隔離 schema；預設 `public`。正式變更需先備份、審核遷移及確認應用相容性；不可改寫已套用 migration，新增向前遷移。

Production-mode API behavior was verified in an owned native environment (not Docker/VM): direct startup returned liveness but readiness 503 with no migration-created tables; the explicit migration recorded three checksums, after which the same process became ready. See [production migration evidence](../testing/evidence/product-production-migration.json). This is a configuration-level native check, not container-image or VM deployment acceptance.


`DATABASE_URL_SECRET_REF` 優先於 `DATABASE_URL`，指向的檔案內容是 PostgreSQL URI。Root Compose 掛載 `/run/secrets/database_url`；`infra/scripts/init-dev.sh` 根據 `POSTGRES_USER`、`POSTGRES_DB`、`postgres_password` 建立此檔，並在不一致時拒絕繼續。PostgreSQL 只在空資料 volume 初始化密碼；更換 secret 檔不等於輪替既有資料庫帳密。URI、密碼、JWT 與內部服務 token 均屬秘密，不放入 Git、命令列、日誌或文件範例的真值。

## 私有資料與安全備份／還原

資料包含帳戶識別、密碼雜湊、裝置／session 狀態、私訊及群組內容、收件回執、feed/snapshot/sync cursor 狀態和附件索引。備份同樣是私人敏感資料。限制目錄為操作者專有（建議 `.backups/` 0700、archive 0600），加密離機副本並限制存取與保留期限。PostgreSQL 資料 volume 是持久資料；Redis 的持久化不取代 PostgreSQL 備份。

建立不覆蓋既有檔案的 PostgreSQL 17 custom-format 備份：

```sh
mkdir -p .backups && chmod 700 .backups
sh infra/scripts/backup-postgres.sh .backups/pre-change.dump
```

`backup-postgres.sh` 使用容器內 `pg_dump`，以 `pg_restore --list` 驗證並原子發布，失敗不會宣稱備份成功；密碼不放在 argv。備份不能只看檔案存在：在明確授權、隔離且有足夠空間的既有測試目標演練還原並核對資料，才是可恢復證據。

還原會清理 archive 內涵蓋的資料庫物件，具有破壞性。先停止所有 API/realtime 與其他資料庫寫入者，先做另一份新備份，再明確確認：

```sh
docker compose --profile product --profile realtime stop api realtime
sh infra/scripts/restore-postgres.sh --confirm-destructive .backups/pre-change.dump
```

還原命令只使用已存在且設定吻合的 DB，不 drop/recreate DB、不建立 fallback target，並拒絕 active client、服務仍運行、危險 DB 名稱、空或 symlink archive 等情況。`pg_restore` 採 `--clean --if-exists --exit-on-error --single-transaction --no-owner --no-acl`。交易錯誤可回滾，但若連線在 commit 周邊中斷，結果可能未知；保持寫入者停止並檢查實際目標後再決定，不要盲目重試。Archive 只清理其中描述的物件，不保證移除建立於備份之後的無關物件。絕不對未確認的正式目標測試還原。

Restore 後依需執行 API migration 命令，並由產品負責人核對 schema、資料和應用相容性後才恢復寫入。程式碼回滾不會回滾已提交資料或 schema migration；保留先前 API/realtime/frontend 實際發佈產物及 image digest，並遵守核准的復原程序。

## 資料權責與一致性

- `users`, `devices`, `sessions`, `authority_state`, `session_invalidations`, `auth_rate_limits`：帳戶與授權核心（`001_accounts.sql`）。refresh token 以 hash 儲存；session、device、user 關係受 FK/unique constraints 保護。
- Contacts、conversations、memberships、messages、receipts、message quota、per-user feed、mutation keys、REST/sync cursors、snapshots：領域資料（`002_domain.sql`）。API transaction 與目前授權條件共同決定是否可讀寫；feed position 和 invalidation frontier 不是 Redis 計數器。
- Attachments：資料庫保存私人附件狀態、owner/scope、不可變 object key 與已確認 GCS generation metadata（`003_attachments.sql`）；內容本體由選配私人 GCS bucket 保存。只有完成檢查的 generation 可成為 ready 物件。

DB 是持久權威；外部 GCS/Redis 不可取代 DB transaction。附件清理會先把符合條件的 metadata row 關閉並 commit，再只刪除綁定 generation 的物件，不能刪除被替換的 generation。DB 與 GCS 備份策略分開規劃；這些腳本只備份 PostgreSQL，未替 GCS 建立版本保留或遠端備份。

已完成的本機產品故障演練另以 PostgreSQL 17.11 真實 `pg_dump` 與 atomic `pg_restore` 將完整資料集還原至自有隔離 clone，核對 archive table records、session/JWT 拒絕、原 C1/M1、feed、read receipt 等狀態；耗時分別為 54.993 ms 與 56.714 ms。完整可追溯結果見[本機 native 故障證據](../testing/evidence/product-native-faults.json) 的 PF08。這只證明該次本機 owned-clone 演練，不是 Compose/VM/cloud 還原驗收、RPO 保證或 GCS 備份證明。實際操作只可在操作者有權限且明確隔離的目標進行。
