# HINE 資安風險評估

- 評估日期：2026-10-21（Asia/Taipei）
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
| 附件 | [MIME 允許清單](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/api/src/hine_api/attachments.py#L41)、[大小檢查](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/api/src/hine_api/attachments.py#L47)（取設定值與 [10 MiB 硬上限](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/api/src/hine_api/storage.py#L25) 的較小值；[設定傳入點](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/api/src/hine_api/attachments.py#L99)）、[內容特徵辨識](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/api/src/hine_api/storage.py#L48)、[固定版本／雜湊核驗](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/api/src/hine_api/storage.py#L238)；[前端 PDF 僅下載](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/frontend/app/src/AttachmentViewer.tsx#L47) | 檔頭與 SHA-256 核對不等於惡意內容掃描 |
| 入口與內部隔離 | [Caddy 路由](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/infra/docker/Caddyfile#L10) 不公開 internal／health；[正式 Compose](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/infra/docker/compose.production.yml#L15) 僅由入口發布 80／443；內部服務有獨立 bearer 憑證 | 文件／模板不等同雲端防火牆、IAM、磁碟與主機均已驗證 |
| 連線與資源 | [WSS 入口](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/realtime/src/hine_realtime/server.py#L532) 有連線上限、訊框大小／速率限制並關閉壓縮；[密碼雜湊](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/api/src/hine_api/auth.py#L105) 限制同時執行數 | 不是網路層 DDoS 防護或正式容量證明 |
| CI 與機密 | [Repository Checks](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/.github/workflows/repository-checks.yml#L7) 使用唯讀 contents 權限並定義 Gitleaks 掃描 | 本次未執行 CI／掃描，也未核對歷史掃描結果 |

## 5. 現有功能風險登錄

| ID | 情境與可能影響 | S／建議優先級 | 狀態與證據 |
|---|---|---|---|
| SEC-01 | 弱密碼、註冊帳號列舉及信箱持有未確認會增加釣魚／撞庫風險；資料庫外洩後低成本離線猜解可擴大帳號接管 | S5／P1（帳號接管的可能影響；不表示列舉即能接管） | **已觀察到缺口**：[credentials](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/api/src/hine_api/auth.py#L85) 只檢查非空及至多 1024 字元，未見最低強度／常見外洩密碼阻擋；[雜湊](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/api/src/hine_api/auth.py#L69) 為 scrypt N=16384、r=8、p=1，低於 OWASP 列出的相同 N／r 下 p=5 參考組合。[註冊重複 email 回 CONFLICT](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/api/src/hine_api/auth.py#L249)／[A01 現行契約](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/docs/contracts/interface-contract.md#api-a01) 明訂 409，與新 email 的 201 不同，可推知是否註冊；雖有註冊配額，仍保留帳號存在性揭露。信箱所有權驗證另見 [#8](https://github.com/LeoCheng-space/Hine/issues/8)。這些觀察不代表已證實未授權登入或帳號入侵 |
| SEC-02 | 非預期網站建立 WSS 連線，增加跨站使用與未驗證連線耗用的攻擊面 | S3／P1 | **已觀察到缺口**：[websocket](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/realtime/src/hine_realtime/server.py#L532) 與 [Caddy WSS 路由](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/infra/docker/Caddyfile#L25) 未見 Origin allowlist；[Compose](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/docker-compose.yml#L105) 雖傳入 PUBLIC_ORIGIN，[BA Settings](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/realtime/src/hine_realtime/config.py) 尚未讀取／驗證此設定。HINE 仍要求第一個業務訊框提供 JWT，不能據此推論 Cookie 可直接劫持或讀取聊天 |
| SEC-03 | 竄改對話／訊息／附件 ID、舊游標或群組角色，造成跨帳號讀寫或撤權後取得內容 | S5／P0（違反既有邊界時） | **待驗證**：已有 BB 成員與資源授權；BA 的失效時間窗、加入界線與補送規則已有專門分析。依 [現有驗收矩陣](../testing/acceptance-matrix.md) 與 BA gates 驗證，不以持有合法 JWT 代替逐資源授權 |
| SEC-04 | 竊得 JWT／更新憑證，或撤銷通知延遲，造成工作階段冒用 | S5／P1；實際撤銷越界沿用 P0 | **待驗證**：[JWT 綁定、輪替與撤銷](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/api/src/hine_api/auth.py#L117) 已存在；[auth 負向測試](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/tests/product/test_auth.py#L28) 有舊憑證拒絕案例，但本次未重跑。事件失效新鮮度沿用 BA 分析，不承諾零延遲全域撤銷 |
| SEC-05 | 合法 JPEG／PNG／PDF 外觀中夾帶惡意內容，下載後傷害收件者 | S5／P1 | **已觀察到控制範圍限制**：[sniff_content_type](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/api/src/hine_api/storage.py#L48) 辨識檔頭；核驗流程另比對大小／SHA-256。指定流程未見惡意程式掃描或檔案重建；前端 PDF 僅下載可降低內嵌風險，不能保證檔案安全 |
| SEC-06 | 已核發 signed URL 外洩，或使用者撤權後仍在有效期內存取固定版本 | S5／P1 | **殘餘風險**：[下載授權](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/api/src/hine_api/attachments.py#L258) 發放前有再次核權，但 DOWNLOAD_TTL 為 5 分鐘；Google signed URL 是持有者可用的短效授權，GCS 不會逐次回查 HINE 工作階段。已下載副本亦無法由伺服器收回 |
| SEC-07 | XSS／UI 嵌入或瀏覽器共用快取導致私人資訊與可操作工作階段暴露 | S5／P1 | **已觀察到模板缺口／部署待驗證**：[Caddyfile](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/infra/docker/Caddyfile) 未明設 CSP／frame-ancestors／Referrer-Policy；[REST 回應 helper](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/api/src/hine_api/support.py#L55) 未明設敏感 JSON 的 Cache-Control: no-store，尤其 [A02 login](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/api/src/hine_api/auth.py#L289)／[A03 refresh](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/backend/api/src/hine_api/auth.py#L311) 回傳含 access_token 的 AccessSession。未據此宣稱已有可利用的 XSS，或目前實際回應一定被共用快取 |
| SEC-08 | 服務密鑰、GCS 身分或主機遭濫用可造成資料外洩；UID 與 secret owner 不符則可能使服務無法就緒 | S5（憑證失陷）／S4（啟動失敗）；P1 | **部署前提已可追溯、實際環境待驗證**：[正式 build.sh](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/build.sh#L474) 指定執行者 UID／GID 並建立對應權限的目錄；[init-dev.sh](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/infra/scripts/init-dev.sh#L15) 依實際 secret owner 傳入 ID，[init-env.sh](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/infra/scripts/init-env.sh#L12) 只建立缺少的 .env，不覆寫舊值。[Compose](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/docker-compose.yml#L45) 的 UID／GID 在未提供值時才回退到 0，明確設定 0 或舊值也須核對；drop ALL capabilities／禁止提權仍存在，UID 0 不代表可繞過其他 owner 的 0600 檔案權限。無檔案讀權時可能 CONFIG_MISSING／ready 503，不能直接當成已取得額外密鑰權限；正式 wrapper 指定的 ID 亦不自動保證非 root。[手冊](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/docs/deployment/README.md#L18) 說明檔案掛載不等於加密儲存。實際 UID、權限、IAM、防火牆及任何現場故障均未由本次重驗 |
| SEC-09 | 大量連線、昂貴認證／附件請求或單 VM 故障造成整體服務不可用 | S4／P1 | **待容量／部署驗證**：有應用層配額與連線防護，但 [單 VM 拓樸](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/docs/deployment/README.md#L105) 及 [BA G-05](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/docs/testing/backend-a-failure-analysis.md#L261) 的主機／磁碟／恢復風險仍在。應用配額不等於上游頻寬防護 |
| SEC-10 | 備份外洩、備份與主機同時遺失，或還原失敗造成私人資料洩漏／不可恢復 | S5／P1 | **殘餘風險／待驗證**：[備份腳本](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/infra/scripts/backup-postgres.sh#L1) 使用私有檔案權限與 archive 驗證；[手冊](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/docs/deployment/README.md#L85) 要求加密異地副本，並記錄尚未配置遠端備份。pg_restore --list 不等於完整還原演練 |
| SEC-11 | 依賴、容器映像或第三方 Actions 更新引入弱點／供應鏈風險 | S5／P1 | **待掃描／版本政策驗證**：[CI](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/.github/workflows/repository-checks.yml#L14) 的 Actions 使用版本標籤；[資料服務映像](https://github.com/LeoCheng-space/Hine/blob/5c9d5e2bbfa251c6744f3a266e456f6ec2c72c41/docker-compose.yml#L1) 使用可變標籤；本次閱讀的 workflow 未見依賴／映像 CVE 掃描。Gitleaks 檢查機密，不能替代弱點掃描；未宣稱任何套件已有可利用 CVE |

## 6. 改善與驗證追蹤

下列為候選工作項目。Owner 為既有角色，尚未指派到個人或宣稱團隊已承諾時程。涉及密碼政策、公開設定、WSS 或授權語意時，依 [共同介面變更流程](../../CONTRIBUTING.md#interface-changes) 共同確認後另立實作 PR。

| ID | 建議處置與責任 | 完成判準／需保存的證據 |
|---|---|---|
| SEC-01 | BB 主責、FB／QA 協作：訂定密碼強度與常見外洩密碼政策，評估 Argon2id／scrypt 工作因子與漸進升級；將帳號列舉／信箱驗證與 [#8](https://github.com/LeoCheng-space/Hine/issues/8) 一併設計 | 註冊強度負例、既有帳戶相容性、升級成功／失敗、Unicode／長密碼、限速與 VM 記憶體／延遲量測。另以隔離新／既有信箱核對註冊回應差異；若採一致回應與驗證信流程，須共同更新 A01／UI／狀態，驗證收信、過期／重播／重寄及濫用限制，不只把 409 改成成功碼。登入對不存在帳號／錯密碼仍不可區分，DEVICE_NOT_RECOGNIZED 仍只在密碼通過後回傳；信箱驗證不保證消除所有列舉。不能只提高 N 而忽略 maxmem=64 MiB 與同時雜湊數；政策仍待共同確認 |
| SEC-02 | BA／DO 主責、FA／QA 協作：先在 BA Settings 新增 PUBLIC_ORIGIN 的讀取與完整來源格式驗證，再於 WSS 升級前套用精確 allowlist；明定缺值、非法值與無 Origin 用戶端政策。這會涉及共同介面的啟動／部署設定，須共同確認，不能只新增握手判斷 | 正確設定／來源可用；缺少或非法設定依核定政策 fail closed，不靜默允許任意來源；外站、null、近似網域及未核准缺值被拒絕；無 JWT 仍不得認證；既有 W01／W02、PUBLIC_ORIGIN 設定與協定工具相容性受驗證 |
| SEC-03 | BB／BA 主責、FA／QA 協作：保留逐資源與目前成員授權，補齊安全負向證據 | 至少三個隔離帳號覆蓋跨帳號 ID、非成員、遭移除／重加入、舊游標、歷史、回條與附件；在競爭／排隊／恢復後均不洩漏未授權內容。記錄 baseline、環境與實際觀察 |
| SEC-04 | BB／BA／FB／QA：追蹤憑證外洩處置、輪替／登出／取代工作階段及失效傳遞 | 篡改／過期 JWT、錯裝置／世代、舊 refresh 重播、並行 refresh、登出／取代後的 REST 與既有 WSS 皆有案例；Redis／通知失效時依既有 fail-closed 規則，不錯誤冒稱撤銷已完成 |
| SEC-05 | BB／DO／QA：評估上傳隔離、惡意程式掃描與檔案重建需求；掃描服務失效時不得把「未掃描」顯示為安全 | 以受控安全樣本測試 MIME 偽裝、損毀／多格式檔、超限檔與掃描失敗；若新增掃描狀態，先共同修改附件契約。未上掃描前明確揭露下載風險與現行防護範圍 |
| SEC-06 | PM 決策、BB／DO／FA／QA：確認 5 分鐘下載窗口是否可接受，限制連結留存及輸出；若要求即時撤銷，另評估每次核權的下載代理 | 真實私有 GCS 驗證過期與錯版本、撤權後新 grant 拒絕、舊 grant 的實際行為；日誌／錯誤／分析工具不含完整 URL。CORS 不是存取控制；固定版本不等於立即撤銷 |
| SEC-07 | FA／FB／DO／BB／QA：先對回傳 access_token 的 A02 login／A03 refresh 回應明設 Cache-Control: no-store，再確認其他私人資料回應的快取政策；依建置評估 CSP 報告模式與正式策略、防止嵌入及最小化 referrer | 在正式同等環境逐一觀察 login／refresh 回應確實含 Cache-Control: no-store，並核對其他敏感回應與代理行為；測試惡意文字呈現、iframe 嵌入、登出／換帳號、快取；CSP 需允許必要 GCS／blob 圖片與應用資源，不任意加入 unsafe-inline 迴避問題 |
| SEC-08 | DO 主責、BB／BA／QA 協作：在啟動前核對實際 runtime UID／GID、必要 secret 的 owner／mode 與可讀性；識別舊 .env／明確 0／直接 Compose 等路徑，避免套用「wrapper 一定非 root」的假設；另核定最小 IAM、受限 SSH、私有端口與憑證輪替 | 以匹配／不匹配 UID 與 owner-only 檔案在隔離環境測試：合法配置可就緒，無讀權配置應被 preflight 提早指出或維持 CONFIG_MISSING／ready 503；保留 cap_drop 與禁止提權，不以放寬機密檔讀權換取啟動。另保存去識別 IAM／防火牆與舊密鑰失效證據；外部不得連 5432／6379／8080／8081。未重跑現場 PermissionError 事件，不將留言敘述當成正式演練證據 |
| SEC-09 | DO／BA／BB／QA：在隔離環境量測連線、昂貴請求與依賴失效的降級；評估邊界限流／監控及資源預算 | 保存請求速率、拒絕比例、CPU／RAM、回復時間與負載條件；採可停止的受控測試。正式站／他人環境的負載或攻擊測試需另有明確授權 |
| SEC-10 | DO 主責、BB／QA 協作：建立加密異地備份、保留與刪除政策、最小存取及定期隔離還原 | 從異地副本還原到授權隔離目標，核對資料／schema／授權邊界，實測並記錄 RPO／RTO 與資料損失；存有 archive 或列出目錄不能當作還原通過 |
| SEC-11 | DO／各模組／QA：建立依賴及映像掃描、版本更新與嚴重弱點處置流程；評估固定 Actions commit／映像 digest，保留更新機制 | 保存實際掃描結果、版本／digest、適用性判斷、修補或有期限的例外；固定 digest 不代表無弱點。PR 機密掃描與必要 CI 照常執行，本文件不宣稱結果已通過 |

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

本次已完成指定基準版本的靜態閱讀及官方安全建議對照。提交文件前檢查文件結構、風險 ID、來源路徑／行號與新增導覽連結；依 #34 審閱補正後，另核對 58 個報告連結及 8 個關鍵引用行的實際程式內容。這些檢查未執行表中的產品／安全驗證，不把測試存在當成測試通過。

後續每次修改認證、授權、附件、WSS、公開入口、服務憑證或影音架構，都應更新受影響列的證據與驗證狀態。發生疑似憑證外洩時，由 DO／BB 先限制暴露、輪替受影響憑證並保全去識別紀錄，再由 PM 協調通知與復原；不在公開議題或日誌貼出私人訊息、完整 token、signed URL 或備份。

## 10. 外部參考

以下官方資料於 2026-10-21 查閱，用於提出改善建議，並非 HINE 已完成的認證或法遵聲明：

- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)：密碼強度與登入防護。
- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)：雜湊工作因子與升級方向。
- [OWASP WebSocket Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html)：握手來源、訊息授權及資源防護。
- [OWASP File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)：允許清單、內容檢查與惡意檔案處理。
- [Google Cloud Storage signed URLs](https://docs.cloud.google.com/storage/docs/access-control/signed-urls)：持有者授權與有效期。
- [IETF RFC 8827：WebRTC Security Architecture](https://www.rfc-editor.org/rfc/rfc8827.html)：裝置權限、通訊安全與 IP 隱私。
