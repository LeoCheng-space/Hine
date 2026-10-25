# HINE 資安風險評估

- 評估日期：2026-10-21（Asia/Taipei）；引用與拆分檢查：2026-10-23。
- 基準版本：[main / 5c9d5e2](https://github.com/LeoCheng-space/Hine/commit/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41)
- 狀態：初步靜態評估草稿，待團隊審閱；下列優先順序與新增驗收建議尚未成為共同契約。
- 評估範圍：現有 HINE；語音／視訊通話僅列為未來擴充風險，不新增本版通話需求。
- 證據邊界：本次閱讀程式、設定、需求與既有測試文件，未執行滲透測試、依賴弱點掃描、產品測試或正式環境探測。程式中看到控制不表示該控制已在正式環境通過驗收；未驗證的攻擊情境不列為已證實漏洞。

## 1. 評估摘要

現有設計已包含工作階段驗證、成員授權、更新憑證輪替、WSS 訊框限制、附件版本核驗、私有資料服務及機密掃描。優先追蹤的靜態缺口是密碼強度與雜湊參數、註冊回應可推知帳號存在、WebSocket 握手來源限制，以及瀏覽器安全標頭；另外需確認附件下載授權的撤銷時間窗、惡意檔案處理、正式環境權限、備份與供應鏈風險。

本文件將「已觀察到的實作／設定缺口」「已有防護但仍待驗證的攻擊情境」及「設計保留的殘餘風險」分開記錄。現有 BA 細部故障與失效邊界沿用 [BA 失效分析](../testing/backend-a-failure-analysis.md)，不重設其已列出的 release gates 或把本機證據升格為正式環境證據。

## 2. 資產與信任邊界

| 資產／邊界 | 主要風險 | 必須保持的安全性質 |
|---|---|---|
| 帳號、密碼雜湊、JWT 與更新憑證 | 撞庫、離線猜密碼、憑證竊取與重播 | 憑證不進 URL／日誌；工作階段仍由 BB 權威判定 |
| 私人訊息、群組、回條、歷史與同步游標 | 跨帳號讀寫、撤權後收訊、重加入後讀舊資料 | 依目前身分、成員與加入界線授權，不以不透明 ID 或本機快取代替授權 |
| 瀏覽器與 HTTPS／WSS 入口 | XSS、跨站連線、快取洩漏、資源耗盡 | 同來源政策、嚴格事件驗證、敏感資料最小化及資源限制 |
| BA／BB 內部 HTTP、PostgreSQL、Redis | 服務冒用、內部端口公開、主機失陷 | 私有路由與獨立服務憑證；Redis 不成為正式資料權威 |
| 瀏覽器直連 GCS 與 signed URL | 連結外洩、惡意檔案、撤權後使用既有授權 | 物件私有、短效且固定版本、授權核對；明確記錄撤銷限制 |
| GitHub Actions、映像、VM、備份 | 供應鏈污染、密鑰外洩、資料遺失 | 最小權限、可追溯版本、可驗證且受保護的恢復資料 |

本次不宣稱 HINE 提供端對端加密。HTTPS／WSS 保護傳輸；後端與資料儲存的信任、管理權限及主機風險仍須評估。

## 3. 評估方法與狀態

沿用 [BA 失效分析的嚴重度與優先級定義](../testing/backend-a-failure-analysis.md#3-風險評分與-release-判定方法)：S5 涉及未授權內容／憑證外洩或資料不可恢復；S4 涉及廣泛服務不可用；S3 涉及局部功能不可用。此處的 S 是防護失效時的可能影響，不代表已發生事故。

- **P0**：沿用既有授權、身分與資料不變量；如驗證發現違反，阻擋對應發佈。
- **P1**：建議正式對外服務前完成改善或由 PM 與受影響角色具名決定殘餘風險處置；本文件不自行核准例外。
- **P2**：持續改善與監控；不以此級別豁免現行必要驗收。
- **已觀察到缺口**：基準版本的指定程式／設定可直接看到缺少某項控制；不等於已證實可利用。
- **待驗證**：已有相關控制或環境前提，但本次沒有重跑負向案例或檢查真實部署。
- **殘餘風險**：既有機制即使正確運作仍保留的限制，需有清楚政策與處置。

目前缺少正式運行樣本與攻擊資料，發生機率為 UNKNOWN，不計算機率乘積、RPN 或假定發生百分比。

## 4. 目前可追溯的控制

| 區域 | 靜態觀察與證據 | 本次證據限制 |
|---|---|---|
| 登入與工作階段 | [auth.py](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/api/src/hine_api/auth.py#L117) 限定 JWT 演算法與 claims；驗證資料庫工作階段。登入有帳號／IP 配額；更新憑證使用 Secure／HttpOnly／SameSite=Strict，並輪替與記錄失效 | 沒有因此宣稱能抵擋所有帳號接管；密碼政策缺口另列 SEC-01 |
| Cookie 來源防護 | [cookie_request](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/api/src/hine_api/auth.py#L231) 對 refresh／logout 核對完整 Origin 與 Sec-Fetch-Site | 不等同 WebSocket 握手已做來源限制 |
| 授權與撤銷 | [對話成員查核](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/api/src/hine_api/conversations.py#L64)、[附件授權](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/api/src/hine_api/attachments.py#L54) 與 [BA 失效分析](../testing/backend-a-failure-analysis.md) | 成員競爭、逐事件授權及正式部署結果仍須依既有驗收判定 |
| 附件 | [MIME 允許清單](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/api/src/hine_api/attachments.py#L41)、[大小檢查](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/api/src/hine_api/attachments.py#L47)（取設定值與 [10 MiB 硬上限](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/api/src/hine_api/storage.py#L25) 的較小值；[設定傳入點](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/api/src/hine_api/attachments.py#L99)）、[內容特徵辨識](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/api/src/hine_api/storage.py#L47)、[固定版本／雜湊核驗](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/api/src/hine_api/storage.py#L238)；[前端 PDF 僅下載](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/frontend/app/src/AttachmentViewer.tsx#L47) | 檔頭與 SHA-256 核對不等於惡意內容掃描 |
| 入口與內部隔離 | [Caddy 路由](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/infra/docker/Caddyfile#L10) 不公開 internal／health；[正式 Compose](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/infra/docker/compose.production.yml#L15) 僅由入口發布 80／443；內部服務有獨立 bearer 憑證 | 文件／模板不等同雲端防火牆、IAM、磁碟與主機均已驗證 |
| 連線與資源 | [WSS 入口](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/realtime/src/hine_realtime/server.py#L532) 有連線上限、訊框大小／速率限制並關閉壓縮；[密碼雜湊](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/api/src/hine_api/auth.py#L105) 限制同時執行數 | 不是網路層 DDoS 防護或正式容量證明 |
| CI 與機密 | [Repository Checks](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/.github/workflows/repository-checks.yml#L7) 使用唯讀 contents 權限並定義 Gitleaks 掃描 | 本次未執行 CI／掃描，也未核對歷史掃描結果 |

## 5. 現有功能風險登錄

| ID | 情境與可能影響 | S／建議優先級 | 狀態與證據 |
|---|---|---|---|
| SEC-01 | 弱密碼、註冊帳號列舉及信箱持有未確認會增加釣魚／撞庫風險；資料庫外洩後低成本離線猜解可擴大帳號接管 | S5／P1（帳號接管的可能影響；不表示列舉即能接管） | **密碼強度已實作；雜湊參數、帳號列舉與信箱驗證仍是缺口**：基準版本的 [credentials](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/api/src/hine_api/auth.py#L85) 只檢查非空及至多 1024 字元。2026-10-23 起 A01 依使用者決議套用[註冊密碼規則](https://github.com/LeoCheng-space/Hine/blob/6adfec371b59915fdd5153c5e323f5aae63f4e2e/backend/api/src/hine_api/auth.py#L87)（8–128 字元、四類中至少 2 類、不含帳號名稱、無 4 個以上連續或重複字元），註冊頁以[相同規則](https://github.com/LeoCheng-space/Hine/blob/6adfec371b59915fdd5153c5e323f5aae63f4e2e/frontend/app/src/password.ts#L3)逐條提示；既有帳號與登入不受影響，舊的弱密碼不會被強制更換。尚未實作常見外洩密碼阻擋。[雜湊](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/api/src/hine_api/auth.py#L69) 仍為 scrypt N=16384、r=8、p=1，低於 OWASP 列出的相同 N／r 下 p=5 參考組合。[註冊重複 email 回 CONFLICT](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/api/src/hine_api/auth.py#L249)／A01 契約明訂 409，與新 email 的 201 不同，可推知是否註冊；信箱所有權驗證另見 [#8](https://github.com/LeoCheng-space/Hine/issues/8)。這些觀察不代表已證實未授權登入或帳號入侵 |
| SEC-02 | 非預期網站建立 WSS 連線，增加跨站使用與未驗證連線耗用的攻擊面 | S3／P1 | **已實作；正式環境待驗證**：基準版本的 [websocket](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/realtime/src/hine_realtime/server.py#L532) 未見 Origin allowlist，[BA Settings](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/realtime/src/hine_realtime/config.py) 未讀取 PUBLIC_ORIGIN。2026-10-23 起 BA [讀取並驗證](https://github.com/LeoCheng-space/Hine/blob/2572067cee8c33d8f320a076feb33e954c21af9d/backend/realtime/src/hine_realtime/config.py#L83) PUBLIC_ORIGIN（缺少或非裸 HTTPS 來源即不就緒），並在[升級前](https://github.com/LeoCheng-space/Hine/blob/2572067cee8c33d8f320a076feb33e954c21af9d/backend/realtime/src/hine_realtime/server.py#L536)拒絕缺少、不同、null 或重複的 Origin（403 FORBIDDEN）。依使用者決議，沒有 Origin 的非瀏覽器用戶端一律拒絕。Origin 可由非瀏覽器程式偽造，此控制只阻擋瀏覽器跨站連線；認證仍依 W01 JWT |
| SEC-03 | 竄改對話／訊息／附件 ID、舊游標或群組角色，造成跨帳號讀寫或撤權後取得內容 | S5／P0（違反既有邊界時） | **已有負向測試；競爭／恢復待驗證**：已有 BB 成員與資源授權；BA 的失效時間窗、加入界線與補送規則已有專門分析。`tests/product/test_authorization.py` 以三個隔離帳號驗證 REST、內部 `authorize` 與經真實 BA 的 WSS 對外人、被移除／重加入成員及他人游標的拒絕。丟棄 publish 的競爭與 API／BA 重啟恢復（AC-N02）尚未驗證。依 [現有驗收矩陣](../testing/acceptance-matrix.md) 與 BA gates 驗證，不以持有合法 JWT 代替逐資源授權 |
| SEC-04 | 竊得 JWT／更新憑證，或撤銷通知延遲，造成工作階段冒用 | S5／P1；實際撤銷越界沿用 P0 | **待驗證**：[JWT 綁定、輪替與撤銷](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/api/src/hine_api/auth.py#L117) 已存在；[auth 負向測試](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/tests/product/test_auth.py#L28) 有舊憑證拒絕案例，但本次未重跑。2026-10-23 新增 `tests/product/test_session_attacks.py`（16 個案例，真實 API／PostgreSQL／Redis／BA）：公開 `/api/v1/users/me` 與內部 validateAccess 對竄改／過期／舊世代／被取代 JWT 一律 401，W01 逐一拒絕偽造或已撤銷憑證，登出（通知送達與 Redis PUBLISH 被拒）、refresh、同裝置取代與並行 refresh 皆關閉既有 WSS；另有 `tests/integration/test_realtime_boundaries.py` 5 個假後端案例與 `infra/tests/test_sql_static.py` 的 SQL 字串拼接靜態防線。事件失效新鮮度沿用 BA 分析，不承諾零延遲全域撤銷 |
| SEC-05 | 合法 JPEG／PNG／PDF 外觀中夾帶惡意內容，下載後傷害收件者 | S5／P1 | **已觀察到控制範圍限制**：[sniff_content_type](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/api/src/hine_api/storage.py#L47) 辨識檔頭；核驗流程另比對大小／SHA-256。指定流程未見惡意程式掃描或檔案重建；前端 PDF 僅下載可降低內嵌風險，不能保證檔案安全 |
| SEC-06 | 已核發 signed URL 外洩，或使用者撤權後仍在有效期內存取固定版本 | S5／P1 | **殘餘風險**：[下載授權](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/api/src/hine_api/attachments.py#L258) 發放前有再次核權，但 DOWNLOAD_TTL 為 5 分鐘；Google signed URL 是持有者可用的短效授權，GCS 不會逐次回查 HINE 工作階段。已下載副本亦無法由伺服器收回 |
| SEC-07 | XSS／UI 嵌入或瀏覽器共用快取導致私人資訊與可操作工作階段暴露 | S5／P1 | **快取、嵌入防護與完整 CSP 已實作；正式環境待驗證**：基準版本的 [Caddyfile](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/infra/docker/Caddyfile) 未明設 CSP／frame-ancestors／Referrer-Policy，[REST 回應 helper](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/api/src/hine_api/support.py#L55) 未明設 Cache-Control: no-store，尤其 [A02 login](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/api/src/hine_api/auth.py#L289)／[A03 refresh](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/api/src/hine_api/auth.py#L311) 回傳含 access_token 的 AccessSession。2026-10-23 起 API 對[所有 /api/v1 回應](https://github.com/LeoCheng-space/Hine/blob/27ed2cc9864901ec73c1d911c535c00c1bb2193f/backend/api/src/hine_api/server.py#L110)（含錯誤與 204）設 no-store；正式與本機 [Caddy](https://github.com/LeoCheng-space/Hine/blob/27ed2cc9864901ec73c1d911c535c00c1bb2193f/infra/docker/Caddyfile#L11) 對所有回應設 `frame-ancestors 'none'`、`Referrer-Policy: same-origin`（`no-referrer` 會讓同源 POST 的 Origin 變成 null，使 refresh 失敗）與 nosniff。同日再於 Caddy 啟用完整 CSP：script／style 只允許同源、圖片只允許同源與 `blob:`、連線只允許同源（含 WSS）與 GCS 簽章網址，`default-src`／`object-src`／`base-uri` 為 `'none'`，不含 `unsafe-inline`／`unsafe-eval`。未據此宣稱已有可利用的 XSS |
| SEC-08 | 服務密鑰、GCS 身分或主機遭濫用可造成資料外洩；UID 與 secret owner 不符則可能使服務無法就緒 | S5（憑證失陷）／S4（啟動失敗）；P1 | **本機啟動前檢查已實作；正式環境與憑證治理待驗證**：[正式 build.sh](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/build.sh#L474) 指定執行者 UID／GID 並建立對應權限的目錄；[init-dev.sh](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/infra/scripts/init-dev.sh#L15) 依實際 secret owner 傳入 ID，[init-env.sh](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/infra/scripts/init-env.sh#L12) 只建立缺少的 .env，不覆寫舊值。[Compose](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/docker-compose.yml#L51-L53) 的 UID／GID 在未提供值時才回退到 0，明確設定 0 或舊值也須核對；drop ALL capabilities／禁止提權仍存在，UID 0 不代表可繞過其他 owner 的 0600 檔案權限。無檔案讀權時可能 CONFIG_MISSING／ready 503，不能直接當成已取得額外密鑰權限；正式 wrapper 指定的 ID 亦不自動保證非 root。2026-10-23 起本機 `./build.sh` 在[產生密鑰後、建置與啟動前](https://github.com/LeoCheng-space/Hine/blob/fc3b22d35992219f231768cbe50f4d82d68e682f/build.sh#L345)比對 `.env` 的 ID 與 `.secrets` 擁有者，不符即停止並指出應填的值，不放寬檔案權限；直接執行 Compose、正式模式與 IAM／輪替不在此檢查範圍。[手冊](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/docs/deployment/README.md#L18) 說明檔案掛載不等於加密儲存。實際正式 UID、權限、IAM、防火牆均未由本次重驗 |
| SEC-09 | 大量連線、昂貴認證／附件請求或單 VM 故障造成整體服務不可用 | S4／P1 | **待容量／部署驗證**：有應用層配額與連線防護，但 [單 VM 拓樸](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/docs/deployment/README.md#L105) 及 [BA G-05](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/docs/testing/backend-a-failure-analysis.md#L261) 的主機／磁碟／恢復風險仍在。應用配額不等於上游頻寬防護 |
| SEC-10 | 備份外洩、備份與主機同時遺失，或還原失敗造成私人資料洩漏／不可恢復 | S5／P1 | **殘餘風險／待驗證**：[備份腳本](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/infra/scripts/backup-postgres.sh#L1) 使用私有檔案權限與 archive 驗證；[手冊](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/docs/deployment/README.md#L85) 要求加密異地副本，並記錄尚未配置遠端備份。pg_restore --list 不等於完整還原演練 |
| SEC-11 | 依賴、容器映像或第三方 Actions 更新引入弱點／供應鏈風險 | S5／P1 | **依賴與產品映像掃描已實作，並列為 main 必要檢查**：基準版本的 [CI](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/.github/workflows/repository-checks.yml#L14) 未見依賴／映像 CVE 掃描。2026-10-23 首次掃描發現 API／BA／壓測工具使用的 aiohttp 3.14.3 有 8 筆已知弱點（修正於 3.14.4），已升級。新增 [dependency-audit](https://github.com/LeoCheng-space/Hine/blob/3d7223b06a071cba5faeab2942523a65a77f4592/.github/workflows/dependency-audit.yml)：pip-audit 與 bun audit 有任何已知弱點即失敗；Trivy 掃描 API／BA 映像，HIGH／CRITICAL 且已有修補版本即失敗；每日於 main 定時重跑。Dependabot 每月依類別提出分組更新 PR（Python、前端、Docker、Actions；Actions 大版本另成一組），已知弱點仍由每日 dependency-audit 發現。仍有缺口：PostgreSQL／Redis／Caddy 上游映像使用可變標籤且未掃描；Actions 以版本標籤而非 commit 固定；Python 間接依賴未鎖定版本，每次安裝與掃描可能解析到不同版本 |

## 6. 改善與驗證追蹤

下列為候選工作項目。Owner 為既有角色，尚未指派到個人或宣稱團隊已承諾時程。涉及密碼政策、公開設定、WSS 或授權語意時，依 [共同介面變更流程](../../CONTRIBUTING.md#interface-changes) 共同確認後另立實作 PR。

| ID | 建議處置與責任 | 完成判準／需保存的證據 |
|---|---|---|
| SEC-01 | BB 主責、FB／QA 協作：註冊密碼強度已實作；仍需評估常見外洩密碼阻擋、Argon2id／scrypt 工作因子與漸進升級，並將帳號列舉／信箱驗證與 [#8](https://github.com/LeoCheng-space/Hine/issues/8) 一併設計 | 密碼規則已有 [API 回歸測試](https://github.com/LeoCheng-space/Hine/blob/6adfec371b59915fdd5153c5e323f5aae63f4e2e/tests/product/test_auth.py#L131)（10 種弱密碼回 400 且不建立帳號、不消耗配額；8／128 字元、空格長句、非 ASCII、BMP 外字元可註冊並登入；登入不套用規則）與前端同向量測試。2026-10-23 隔離 stack 實測：經 Caddy 弱密碼 400、合規 201；桌面 Chrome 註冊頁對過短、單一類別、含帳號名稱、連續字元逐條提示且未送出請求，合規密碼註冊後可登入。其餘待辦：升級成功／失敗、限速與 VM 記憶體／延遲量測；以隔離新／既有信箱核對註冊回應差異，若採一致回應與驗證信流程須共同更新 A01／UI／狀態。不能只提高 N 而忽略 maxmem=64 MiB 與同時雜湊數 |
| SEC-02 | BA／DO 主責、FA／QA 協作：PUBLIC_ORIGIN 讀取、格式驗證與 WSS 升級前精確 allowlist 已實作；正式部署時確認 PUBLIC_ORIGIN 與實際網域一致 | 已有[回歸測試](https://github.com/LeoCheng-space/Hine/blob/2572067cee8c33d8f320a076feb33e954c21af9d/tests/integration/test_realtime_boundaries.py#L339)（無 Origin、外站、null、尾斜線、http、重複 Origin 皆 403；正確 Origin 可完成 W01／W02；非法設定不就緒）。2026-10-23 隔離 stack 經 Caddy 實測：無／外站／null Origin 為 403，正確 Origin 為 101；[協定工具](https://github.com/LeoCheng-space/Hine/blob/2572067cee8c33d8f320a076feb33e954c21af9d/tests/load/protocol.py#L594)改帶頁面 Origin 後 e2e 通過；桌面 Chrome 登入後 WSS 101 且收到 auth.accepted，外站頁面連線收到 403。正式網域未驗證 |
| SEC-03 | BB／BA 主責、FA／QA 協作：保留逐資源與目前成員授權，補齊安全負向證據 | 至少三個隔離帳號覆蓋跨帳號 ID、非成員、遭移除／重加入、舊游標、歷史、回條與附件；在競爭／排隊／恢復後均不洩漏未授權內容。已由 `tests/product/test_authorization.py` 覆蓋除競爭／排隊／恢復外的各項（REST／內部 authorize／真實 BA WSS）；丟棄 publish、API／BA 重啟後的不洩漏仍待補。記錄 baseline、環境與實際觀察 |
| SEC-04 | BB／BA／FB／QA：追蹤憑證外洩處置、輪替／登出／取代工作階段及失效傳遞 | 篡改／過期 JWT、錯裝置／世代、舊 refresh 重播、並行 refresh、登出／取代後的 REST 與既有 WSS 皆有案例；Redis／通知失效時依既有 fail-closed 規則，不錯誤冒稱撤銷已完成。已由 `test_session_attacks.py`、`test_realtime_boundaries.py` 與 `test_sql_static.py` 涵蓋上述 REST／WSS 情境及 SQL 字串拼接防線；仍待：通知遺失加上 BA→API 連線中斷的真實產品演練（AC-N04）、Redis 完全停機時的真實登出，以及兩項待決策行為（refresh 重播不偵測重用、無 cookie 登出回 204 但不撤銷）|
| SEC-05 | BB／DO／QA：評估上傳隔離、惡意程式掃描與檔案重建需求；掃描服務失效時不得把「未掃描」顯示為安全 | 以受控安全樣本測試 MIME 偽裝、損毀／多格式檔、超限檔與掃描失敗；若新增掃描狀態，先共同修改附件契約。未上掃描前明確揭露下載風險與現行防護範圍 |
| SEC-06 | PM 決策、BB／DO／FA／QA：確認 5 分鐘下載窗口是否可接受，限制連結留存及輸出；若要求即時撤銷，另評估每次核權的下載代理 | 真實私有 GCS 驗證過期與錯版本、撤權後新 grant 拒絕、舊 grant 的實際行為；日誌／錯誤／分析工具不含完整 URL。CORS 不是存取控制；固定版本不等於立即撤銷 |
| SEC-07 | FA／FB／DO／BB／QA：login／refresh 及其他 API 回應的 no-store、防止嵌入、referrer 最小化與完整 CSP 已實作；下一步在正式網域觀察 | 已有[回歸測試](https://github.com/LeoCheng-space/Hine/blob/27ed2cc9864901ec73c1d911c535c00c1bb2193f/tests/product/test_auth.py#L45)（login／refresh／一般／404／401／204 皆為 no-store）。2026-10-23 於隔離本機 stack 經 Caddy 實測頁面、靜態檔與 API 回應標頭；桌面 Chrome 156 註冊、登入、重新整理後以 cookie refresh 恢復工作階段，外站 iframe 被拒絕。CSP 先以 report-only 在 CI 的 Chrome／Edge 瀏覽器驗收跑完全部情境且零違規，才改為強制；瀏覽器驗收現在使用與正式 Caddyfile 相同的標頭區塊（兩份 Caddyfile 不一致即失敗），檢查全部頁面零違規，並確認注入的 inline script 與外站圖片會被阻擋。附件上傳／下載需真 GCS，本機與 CI 未實測 GCS 連線；正式同等環境仍須逐一觀察，並測試惡意文字呈現、登出／換帳號 |
| SEC-08 | DO 主責、BB／BA／QA 協作：在啟動前核對實際 runtime UID／GID、必要 secret 的 owner／mode 與可讀性；識別舊 .env／明確 0／直接 Compose 等路徑，避免套用「wrapper 一定非 root」的假設；另核定最小 IAM、受限 SSH、私有端口與憑證輪替 | 以匹配／不匹配 UID 與 owner-only 檔案在隔離環境測試：合法配置可就緒，無讀權配置應被 preflight 提早指出或維持 CONFIG_MISSING／ready 503；保留 cap_drop 與禁止提權，不以放寬機密檔讀權換取啟動。本機模式已有[回歸測試](https://github.com/LeoCheng-space/Hine/blob/fc3b22d35992219f231768cbe50f4d82d68e682f/infra/tests/test_build.py#L397)，並於 2026-10-23 在隔離 checkout 實跑：沿用範例 `.env` 的 0／0 時於第 2 步停止並提示 1000／1000，依提示修改後五個服務均 healthy。另保存去識別 IAM／防火牆與舊密鑰失效證據；外部不得連 5432／6379／8080／8081。正式模式未重跑，不將本機結果當成正式演練證據 |
| SEC-09 | DO／BA／BB／QA：在隔離環境量測連線、昂貴請求與依賴失效的降級；評估邊界限流／監控及資源預算 | 保存請求速率、拒絕比例、CPU／RAM、回復時間與負載條件；採可停止的受控測試。正式站／他人環境的負載或攻擊測試需另有明確授權 |
| SEC-10 | DO 主責、BB／QA 協作：建立加密異地備份、保留與刪除政策、最小存取及定期隔離還原 | 從異地副本還原到授權隔離目標，核對資料／schema／授權邊界，實測並記錄 RPO／RTO 與資料損失；存有 archive 或列出目錄不能當作還原通過 |
| SEC-11 | DO／各模組／QA：dependency-audit 失敗時修補或升級後再合併；評估上游資料服務映像掃描、固定 Actions commit／映像 digest，保留更新機制 | 本機已驗證 gate 有效：aiohttp 3.14.3 使 pip-audit 回傳 1、alpine:3.10 使 Trivy 回傳 1；修正後四份 Python 需求與前端依賴無已知弱點，API／BA 映像無可修補的 HIGH／CRITICAL。保存每次掃描結果、版本／digest、適用性判斷與有期限的例外；固定 digest 不代表無弱點，掃描通過也不代表沒有未公開弱點 |

追蹤每項風險時補上實際工作／PR、負責人、預定日期、驗證環境、基準提交、結果及殘餘風險決定。未取得證據前維持未驗證，不先填「已修復」或「通過」。

## 7. 未來語音／視訊通話風險

本節為後續設計輸入，狀態均為「未來功能／未驗證」。不加入本版 REQ／A／W 編號、麥克風權限、通話資料表或部署端口。

| ID | 未來情境 | 設計時應納入的控制 | 未來驗證重點／角色 |
|---|---|---|---|
| CALL-01 | 冒名來電、猜測房間、舊邀請重播或成員撤權後繼續加入 | 通話 ID 與經驗證參與者綁定；邀請短效且限制狀態轉移；逐次核對通話與對話權限 | 非參與者／舊邀請拒絕，忙線、多裝置搶接、撤權／登出／token 刷新可預期；BB／BA／FA／QA |
| CALL-02 | 無意開啟鏡頭／麥克風，掛斷後持續擷取，或錄製缺少使用者知情 | 由使用者明確操作與瀏覽器授權啟用；拒接不開始傳送；清楚顯示裝置與錄製狀態；結束／失敗釋放 tracks；錄製另訂同意與保留政策 | 權限拒絕、取消來電、掛斷、登出、裝置切換與失敗清理；FA／FB／QA，錄製政策由 PM 決定 |
| CALL-03 | 直接連線暴露網路位址；影音服務／SFU 的信任界線被誤認為產品端對端加密 | 選型時分析 ICE、relay 與 SFU 的可見資料；必要時評估 relay-only 的隱私／成本取捨；明確定義加密終點、金鑰與錄製邊界 | 驗證候選位址與日誌最小化；依實際架構說明哪些服務能取得影音，不僅以「使用 WebRTC」宣稱 E2EE；DO／BA／FA／QA |
| CALL-04 | TURN 憑證被分享、轉送濫用、連往不應存取的內部位址或頻寬費用失控 | 經認證核發短效 TURN 憑證，限制 peer 目標與內部／loopback 存取、用量／並行配額及告警；不在前端放長效共享 secret | 過期／未授權使用拒絕，私有目標依政策封鎖，受控濫用觸發限額；DO／BB／BA／QA |
| CALL-05 | 來電騷擾、信令洪水、過大 SDP／ICE 或過期信令重播 | 每帳號／收件者／通話的限流、大小限制、逾時與去重；信令和離線聊天重送分流；封鎖／拒接政策另行設計 | 洪水、亂序、重播、斷線恢復、關閉網頁情境；不能假定現有 WSS 代表網頁關閉後可收來電；BA／FA／PM／QA |

WebRTC 的權限、通訊安全及 IP 隱私設計依 [RFC 8827](https://www.rfc-editor.org/rfc/rfc8827.html) 評估。TURN／SFU 的實際服務與部署尚未選定，不能先核定安全或容量結論。

## 8. 建議落地順序

1. PM 與受影響角色審閱 SEC-01／02／06，確認密碼／註冊隱私政策、來源設定與限制、下載撤銷窗口；需要契約變更時另立聚焦 PR。
2. QA 將 SEC-03／04 連到既有驗收與 BA gates，補齊缺少的負向情境和真實部署證據；保留目前已列出的未驗證項目。
3. FA／FB／BB／DO 規劃瀏覽器標頭、檔案安全、最小權限與憑證輪替；驗證成功後才更改狀態。
4. DO／QA 建立弱點掃描、異地備份／隔離還原與容量證據，再具名處理剩餘風險。
5. 通話另行啟動需求與設計評估時，以 CALL-01～05 為輸入，不因本文件而視為通話已批准開發。

## 9. 本次檢查紀錄與後續維護

本次已完成指定基準版本的靜態閱讀及官方安全建議對照。提交文件前檢查文件結構、風險 ID、來源路徑／行號與新增導覽連結；依 #34 審閱補正後，核對關鍵引用行的實際程式內容。2026-10-23 依 #35 將內容特徵辨識連至函式定義、SEC-08 連至實際權限設定行，並檢查風險評估可獨立閱讀與導覽。這些檢查未執行表中的產品／安全驗證，不把測試存在當成測試通過。

後續每次修改認證、授權、附件、WSS、公開入口、服務憑證或影音架構，都應更新受影響列的證據與驗證狀態。發生疑似憑證外洩時，由 DO／BB 先限制暴露、輪替受影響憑證並保全去識別紀錄，再由 PM 協調通知與復原；不在公開議題或日誌貼出私人訊息、完整 token、signed URL 或備份。

## 10. 外部參考

以下官方資料於 2026-10-21 查閱，用於提出改善建議，並非 HINE 已完成的認證或法遵聲明：

- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)：密碼強度與登入防護。
- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)：雜湊工作因子與升級方向。
- [OWASP WebSocket Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html)：握手來源、訊息授權及資源防護。
- [OWASP File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)：允許清單、內容檢查與惡意檔案處理。
- [Google Cloud Storage signed URLs](https://docs.cloud.google.com/storage/docs/access-control/signed-urls)：持有者授權與有效期。
- [IETF RFC 8827：WebRTC Security Architecture](https://www.rfc-editor.org/rfc/rfc8827.html)：裝置權限、通訊安全與 IP 隱私。

