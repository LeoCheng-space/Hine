# 一鍵安裝與部署（`./build.sh`）操作手冊

`./build.sh` 是 HINE 的單一入口：在本機一個指令就能建好並啟動整套服務；在 GCP VM 上加 `--production` 完成正式部署。它只編排既有的 `infra/scripts`（`init-dev.sh`、`preflight.sh`、`stack.sh`、`backup-postgres.sh`），不另外建立第二套部署方式。

## 1. 適用環境

| 項目 | 說明 |
|---|---|
| 作業系統 | 自動安裝支援 Ubuntu／Debian（含 GCP 的 Ubuntu LTS 映像）。其他 Linux 或 macOS 需先手動安裝前置工具，`build.sh` 會列出清單後停止 |
| 處理器 | x86_64 或 arm64 |
| 權限 | 需要能使用 `sudo` 的帳號；**第一次執行可能會要求輸入 sudo 密碼**，之後重跑通常不會再問 |
| 網路 | 需要能連到 `download.docker.com`、`github.com`（下載 Bun）與 Docker Hub |

`build.sh` 會自動處理：

- Docker Engine 與 Compose 外掛（Docker 官方 apt 套件來源；需要 Compose v2.20 以上）、`git`、`curl`、`python3`、`openssl`、`unzip`、`iproute2`。
- 把目前使用者加入 `docker` 群組，並在**同一次執行中**以 `sg docker` 繼續，不需要登出。
- Bun 1.4.2：從 GitHub 官方發行檔下載，以腳本內寫死的 SHA-256 驗證後安裝到 `~/.local/share/hine/bun-1.4.2/`；若電腦上已有 Bun 1.4.2 則直接使用，**不會覆蓋**你自己的 Bun。

## 2. 本機快速開始

```sh
git clone https://github.com/LeoCheng-space/Hine.git
cd Hine
./build.sh
```

畫面只顯示進度，例如：

```text
[1/5] 檢查並安裝前置工具
[2/5] 產生密鑰與設定（已存在就沿用）
[3/5] 建置前端
[4/5] 啟動服務並等待健康檢查
[5/5] 完成

HINE 已啟動：https://localhost:8443
```

完成後用瀏覽器開 **https://localhost:8443**。

### 2.1 第一次開啟的憑證警告

本機 HTTPS 使用 Caddy 自己的本機憑證機構，瀏覽器不認得，所以第一次會顯示「你的連線不是私人連線」：

1. 按「進階」。
2. 按「繼續前往 localhost（不安全）」。

只有本機會這樣；`build.sh` 不會修改系統或瀏覽器的憑證信任設定。

### 2.2 本機指令

| 指令 | 作用 |
|---|---|
| `./build.sh` | 安裝／更新並啟動；可重複執行 |
| `./build.sh stop` | 停止所有服務，資料保留 |
| `./build.sh status` | 顯示各服務狀態與網址 |
| `./build.sh logs` | 顯示所有服務最後 200 行記錄 |
| `./build.sh logs api --follow` | 持續顯示某個服務的記錄（`Ctrl+C` 結束）；服務名稱：`api`、`realtime`、`postgres`、`redis`、`caddy` |
| `./build.sh --help` | 顯示用法 |

剛被 `build.sh` 加入 `docker` 群組、還沒重新登入的終端機裡，`stop`／`status`／`logs` 也會自動以 `docker` 群組重新執行（並維持你原本的主要群組），不需要登出；重新登入後就不再需要切換。

### 2.3 重跑與更新

改了程式或 `git pull` 之後，再執行一次 `./build.sh` 即可：重新建置前端，Compose 只重建有變動的容器，資料保留。服務正在執行時重跑也沒問題（`build.sh` 認得自己的 Caddy 占用 8443）。

### 2.4 資料存在哪裡

| 內容 | 位置 |
|---|---|
| 開發密鑰 | `.secrets/`（0700，檔案 0600；不進 Git） |
| 設定 | `.env`（不進 Git） |
| 資料庫、Redis、Caddy 憑證 | Docker volume：`hine-dev_postgres_data`、`hine-dev_redis_data`、`hine-dev_caddy_local_data`、`hine-dev_caddy_local_config` |
| 每次執行的完整記錄 | `.build-logs/`（不進 Git） |

`build.sh` **沒有任何刪除資料的指令**。若真的要清空本機資料重來（**破壞性、無法復原**）：

```sh
./build.sh stop
docker compose --project-directory . --env-file .env -f docker-compose.yml -f infra/docker/compose.local.yml \
  --profile product --profile realtime --profile local down -v
```

`.secrets/` 與 `.env` 要保留：PostgreSQL volume 被刪除後，下次會用同一組密鑰重新初始化。

### 2.5 完全重新安裝（清除所有本機資料與設定）

**破壞性、無法復原**：會刪除本機所有帳號、訊息與開發密鑰。在 repo 根目錄執行：

```sh
./build.sh stop
docker compose --project-directory . --env-file .env -f docker-compose.yml -f infra/docker/compose.local.yml \
  --profile product --profile realtime --profile local down -v --remove-orphans
rm -rf .env .secrets .build-logs frontend/app/dist frontend/app/node_modules
./build.sh
```

若 `.env` 已經不存在，第二行改成 `docker volume rm hine-dev_postgres_data hine-dev_redis_data hine-dev_caddy_local_data hine-dev_caddy_local_config`（不存在的會顯示錯誤，可忽略）。

## 3. 正式機部署（GCP Compute Engine VM）

正式機使用 repo 既定的架構：**單台 Compute Engine VM＋Docker Compose**（`docs/decisions.md`）。`./build.sh --production` 走既有的 `preflight.sh` 與 `stack.sh`，不使用 Cloud Run、Cloud SQL 或 GKE。

### 3.1 VM 準備清單（`build.sh` 不會幫你做）

1. **建立 VM**：Ubuntu 24.04 LTS 映像；建議至少 2 vCPU、4 GB 記憶體、30 GB 磁碟。
2. **固定對外 IP**：在 VPC 網路保留靜態外部 IPv4，綁到這台 VM。
3. **防火牆**：只開放 TCP 80、443（所有來源）與 22（只限你的來源 IP）。**絕對不要**開放 5432、6379、8080、8081。
4. **DNS**：在網域服務商把網域（例如 `hine.run.place`）的 **A 紀錄**指向第 2 步的 IP，並**刪除 AAAA 紀錄**。用 `getent ahosts 你的網域` 確認只出現這個 IP。
5. **80／443 不能被占用**：既有的 `hine-web` VM 上跑著 Nginx 占用 80／443；在那台機器部署前必須先停用 Nginx，或改用新的 VM。
6. **選用：GCS**：要開放附件與頭像上傳時，先建立私有 bucket、服務帳號與簽章權限，把金鑰檔放在 VM 上的絕對路徑（例如 `/srv/hine/gcs/credentials.json`，權限 0600）。詳見 [部署手冊 §3](README.md#3-optional-real-gcs-attachments)。

### 3.2 第一次部署

在 VM 上：

```sh
git clone https://github.com/LeoCheng-space/Hine.git
cd Hine
./build.sh --production
```

第一次會建立 `deploy.env` 範本後停下：

```text
build.sh：已建立 deploy.env 範本：/home/你/Hine/deploy.env
請填入 HINE_DOMAIN、ACME_EMAIL、HINE_EXPECTED_IP（GCS 欄位可留空），完成後重新執行 ./build.sh --production
```

編輯 `deploy.env` 後再執行一次 `./build.sh --production`，之後全程不需要人操作，共 8 個步驟：

| 步驟 | 內容 |
|---|---|
| 1 | 檢查並安裝前置工具 |
| 2 | 讀取並驗證 `deploy.env` |
| 3 | 部署前檢查：80／443 沒被其他程式占用、DNS 完全符合、子網路不衝突 |
| 4 | 建立 `/srv/hine` 目錄 |
| 5 | 在 `/srv/hine/secrets` 產生正式機密鑰（已存在就沿用、不會換掉） |
| 6 | 以 `https://你的網域` 建置前端並發布到 `/srv/hine/releases/<commit>/web` |
| 7 | 啟動：`preflight.sh --local` → PostgreSQL／Redis → `stack.sh migrate` → 全部服務 → `preflight.sh --public` |
| 8 | 寫入 `/srv/hine/active.env` 記錄目前版本 |

Caddy 會在第一次對外請求時向 Let's Encrypt 申請憑證，所以 DNS 必須先正確（第 3 步就會擋下不正確的 DNS，避免憑證申請失敗次數累積）。

### 3.3 `deploy.env` 欄位

格式：每行 `KEY=VALUE`；值不可有空白、引號、`$` 或反引號；`#` 開頭為註解。`build.sh` 只讀取下表欄位並逐一檢查格式，**不會把它當成 shell 程式執行**。

| 欄位 | 必填 | 說明 |
|---|---|---|
| `HINE_DOMAIN` | 是 | 對外網域，只填主機名稱，例如 `hine.run.place`（不含 `https://` 與連接埠） |
| `ACME_EMAIL` | 是 | Let's Encrypt 聯絡信箱（憑證到期等通知） |
| `HINE_EXPECTED_IP` | 是 | VM 的對外 IPv4；多個以逗號分隔。DNS 解析結果必須**完全等於**這個集合 |
| `HINE_EDGE_SUBNET` | 預設 `172.30.1.0/24` | 正式 edge 網路固定子網路 |
| `HINE_BACKEND_SUBNET` | 預設 `172.30.2.0/24` | 正式 backend 網路固定子網路；兩者都必須是私有網段、`/16`–`/28`、互不重疊，也不能與機器上其他 Docker 網路重疊 |
| `GCS_BUCKET` | 否 | 私有 bucket 名稱 |
| `GCS_CREDENTIALS_FILE` | 否 | 簽章金鑰檔的**絕對路徑** |
| `GCS_PROJECT` | 否 | GCP 專案 ID |
| `GCS_SIGNING_SERVICE_ACCOUNT` | 否 | 以 IAM 簽章時使用的服務帳號信箱 |

API 只信任 `HINE_EDGE_SUBNET` 與 `HINE_BACKEND_SUBNET` 這兩段內的反向代理（`TRUSTED_PROXY_NETWORKS` 由兩者自動組成），不需要另外設定。

### 3.4 正式機目錄

| 路徑 | 權限 | 內容 |
|---|---|---|
| `/srv/hine` | 755 | 部署根目錄（擁有者為執行 `build.sh` 的使用者） |
| `/srv/hine/releases/<commit>/web` | 755／檔案 644 | 每個版本的前端；舊版本保留供回滾 |
| `/srv/hine/secrets` | 700／檔案 600 | 正式機密鑰，與開發的 `.secrets/` 完全分開 |
| `/srv/hine/backups` | 700 | 升級前自動備份的資料庫（`hine-<UTC 時間>.dump`） |
| `/srv/hine/active.env` | 600 | 目前上線版本的紀錄（不含密鑰） |

資料庫、Redis 與憑證存在 Docker volume：`hine-production_postgres_data`、`hine-production_redis_data`、`hine-production_caddy_data`、`hine-production_caddy_config`。

**`active.env`** 只在一次部署**完整成功**（包含最後的公開探測）後才更新，內容包括目前的 commit、`WEB_ROOT`、部署時間、子網路與執行身分。`stop`、`status`、`logs` 只看這個檔與 `deploy.env`，所以即使你已經 `git pull` 到新 commit、或新版本部署到一半失敗，這些指令仍然操作目前上線的版本。

### 3.5 正式機指令

| 指令 | 作用 |
|---|---|
| `./build.sh --production` | 部署或升級 |
| `./build.sh --production status` | 服務狀態、網址、目前版本 commit 與部署時間；尚未部署會直接說明 |
| `./build.sh --production stop` | 停止服務，資料保留（透過 `stack.sh stop`） |
| `./build.sh --production logs [服務] [--follow]` | 記錄 |

### 3.6 升級

```sh
cd Hine
git pull
./build.sh --production
```

偵測到既有資料時，`build.sh` 會依部署手冊的規則自動：停止 `api` 與 `realtime`（停止寫入）→ 確認 PostgreSQL／Redis 在執行 → 用 `backup-postgres.sh --production` 備份到 `/srv/hine/backups/` → `migrate` → 啟動新版本。升級期間服務會短暫無法使用。

同一個 commit 但改了 `deploy.env` 的 `HINE_DOMAIN` 時，前端會用新網域重新建置並**直接替換**該 commit 的 `web` 目錄，並重建 Caddy 容器讓它讀到新的檔案。

### 3.7 回滾到舊版本

`build.sh` 沒有一鍵回滾，請依下列步驟手動處理：

1. 確認要回到的 commit：`ls /srv/hine/releases/`，或看 `git log`。
2. 回到該版本程式碼並重新部署：`git checkout <commit>`，然後 `./build.sh --production`。
3. **資料庫 migration 不會自動倒退。** 若新版本已經套用了舊版本不認得的 migration，需要用升級前的備份還原（破壞性操作，先讀 [部署手冊 §4](README.md#4-postgresql-backup-and-restore)）：
   ```sh
   ./build.sh --production stop
   # 在已匯出正式環境變數的 shell 中（或依部署手冊的方式）：
   sh infra/scripts/restore-postgres.sh --production --confirm-destructive /srv/hine/backups/hine-<時間>.dump
   ```
4. 回到最新版本：`git checkout main && git pull && ./build.sh --production`。

## 4. 疑難排解

每次執行的完整輸出都在 `.build-logs/<UTC 時間>-<模式>.log`。失敗時畫面會印出錯誤原因、記錄檔最後 30 行與完整路徑。

| 訊息 | 原因與處理 |
|---|---|
| `連接埠 8443 已被容器 X（專案 Y）占用` | 另一套 stack 占用了 8443。用 `docker stop X` 停掉後再執行 |
| `連接埠 N 已被其他程式占用（不是 Docker 容器）` | 用 `sudo ss -ltnp 'sport = :N'` 找出程式並停止（正式機常見是 Nginx：`sudo systemctl disable --now nginx`） |
| `已切換到 docker 群組但仍無法連線 Docker` | Docker 服務沒有在執行：`sudo systemctl status docker`，必要時 `sudo systemctl enable --now docker` |
| `使用者 X 還不在 docker 群組；請先執行 ./build.sh` | 執行 `stop`／`status`／`logs` 時，帳號還不在 `docker` 群組（子指令不會自行改動群組）。先執行一次 `./build.sh`，它會用 sudo 把帳號加入 `docker` 群組並啟動服務 |
| `init-secrets: run initialization as the existing secret owner UID/GID` | `.secrets/` 裡的檔案擁有者（使用者或群組）與目前執行的使用者不同，`build.sh` 拒絕改動既有密鑰。用 `ls -ln .secrets` 對照 `id`；若是用 `sudo` 或其他帳號產生的，改回正確擁有者（`sudo chown -R 你的帳號:你的群組 .secrets .env`）後重跑。若確定不需要舊資料，依 §2.5 完全重新安裝 |
| `需要 Docker Compose v2.20 以上` | Docker 太舊；Ubuntu／Debian 可移除舊版後重新執行 `./build.sh` 由官方來源安裝 |
| 第 4 步逾時，`./build.sh logs api` 出現 PostgreSQL 密碼驗證失敗（`password authentication failed`） | 資料庫 volume 是用**另一組密鑰**初始化的：同一台電腦上另一份 checkout 用過同樣的 project 名稱（預設 `hine-dev`），但兩份 `.secrets/` 不同。處理方式擇一：在這份 checkout 的 `.env` 把 `COMPOSE_PROJECT_NAME` 改成不同名稱；或把原本那份 checkout 的 `.secrets/` 複製過來；或確認舊資料不需要後依 §2.4 清除資料 |
| `Bun 下載檔的 SHA-256 不符` | 下載內容遭到修改或不完整，已拒絕安裝；檢查網路或代理後重試 |
| `deploy.env 第 N 行：…` | 依訊息修正該行（不允許的欄位、重複欄位、空白／引號等字元） |
| `DNS 預檢未通過` | DNS 尚未生效、指向錯誤 IP 或還有 AAAA 紀錄；修正後等 DNS 生效再執行 |
| `子網路檢查未通過` | 子網路與機器上其他 Docker 網路重疊：在 `deploy.env` 換成其他私有網段。若是「本部署的網路已存在但子網路不同」，表示改過子網路：先 `./build.sh --production stop`，再 `docker network rm hine-production_edge hine-production_backend`，然後重新部署 |
| Caddy 記錄出現 Let's Encrypt 錯誤 | 檢查 DNS、防火牆 80／443；Let's Encrypt 有失敗次數限制，修正後再重試 |
| `已有另一個 build.sh 在執行（PID N）` | 真的有另一個在執行就等它結束。若該 PID 已不存在（例如中途關掉終端機），刪除 repo 根目錄的 `.build.lock/` 後重試 |
| `正式機尚未部署（找不到 /srv/hine/active.env）` | 還沒有任何一次成功的正式部署 |

## 5. `build.sh` 不會做的事

- 不建立或修改任何雲端資源（VM、防火牆、DNS、GCS、服務帳號）。
- 不刪除任何資料、Docker volume 或 Docker 網路。
- 不信任或安裝任何憑證到系統或瀏覽器。
- 不輸出任何密鑰內容到畫面或記錄檔。
- 不自動回滾資料庫。

## 6. 進階

- `HINE_PRODUCTION_HOME`：正式機目錄預設 `/srv/hine`；若要改用其他絕對路徑，每次執行（含 `status`／`stop`／`logs`）都要帶相同的值，例如 `HINE_PRODUCTION_HOME=/opt/hine ./build.sh --production`。
- 本機的 Compose project 名稱取自 `.env` 的 `COMPOSE_PROJECT_NAME`（預設 `hine-dev`），與一般開發流程共用同一組 volume。
