# HINE 文件變更紀錄

## 2026-10-08 — Native browser使用pinned SDK的crash reporting policy

- [run37681214482](https://github.com/LeoCheng-space/Hine/actions/runs/37681214482) 的bounded native Edge diagnostic已分類為`CRASHPAD_FATAL`／SIGTRAP(-5)，不是已驗明的sandbox故障；不猜加`--no-sandbox`或替換browser。
- InstalledPlaywright1.63的實際common switches包含`--disable-breakpad`，成功的SDK主browser沿用此policy。Native recipient同樣停用測試browser crash reporting，保留原sandbox、fresh profile、loopback CDP及`no_defaults`真实visibility；不操作production browser／global kernel或trust。
- 相同Chrome154完整owned headed59checks／hidden delivered→foreground read及100則DOM/IDB/rAF394.01ms通過，Ruff／privacy canary通過。此policy parity是否解除Edge fatal仍須新hosted Edge gate，不能拿Chrome结果代填。

## 2026-10-08 — 完整container gate成功，保留Edge fatal分類

- [run37674312851](https://github.com/LeoCheng-space/Hine/actions/runs/37674312851) 七個jobs SUCCESS，僅native Edge startup失敗。真API／BA images、production migration、verifiedTLS、雙WSS原C1／M1／W08-W09／history、PG／Redis restart後原session、停止writers後full tables／sequence atomic clone restore、API綁clone保留JWT並真新寫入與static Web全部通過。
- Chrome headed59checks／真正hidden→foreground回條及100則補回通過；Edge private startup log318bytes、SIGTRAP(-5)，目前只能辨明fatal，不能由主SDK launch成功推論native Edge通過。擴充固定Chromium component category（zygote／sandbox／profile singleton／crashpad／unclassified），不發布rawlog／source path／本文，不猜變更sandbox。
- Matrix更新338項／完整container實測與仍未完成的Edge／正式五門檻。新分類Ruff／privacy canary formatter通過；每個新增／修改批次commit，仍僅feature-only push、無main PR。

## 2026-10-08 — Redis private runtime config與fixed startup diagnostics

- [run37666361557](https://github.com/LeoCheng-space/Hine/actions/runs/37666361557) 的Chrome headed59checks全通過、100則復原273.82ms；Edge在native child/CDP ready之前退出，PG healthy但Redis restart unhealthy。保持兩gate失敗，不以主SDK Edge啟動或初始container flow冒稱整體完成。
- Redis bootstrap不再重寫sticky `/tmp`內已redis-owned的固定0600檔案；每次在root-controlled `/run`建立fresh private directory/config，交給redis UID及原entrypoint。64hex credential、non-root runtime、`/data` inode／AOF everysec不變。這消除restart-sensitive來源hazard，但是否為本次Redis退出原因仍須真Docker proof。
- 失敗時只在owned scope內分類Redis health/log的stdout＋stderr，發布固定class counts／最多10個numeric exits；native Edge只分類最多64KiB private log為固定category、child exit及captured byte count。無rawlog／exception／path／password／ID／本文，不猜sandbox或替換browser。
- Privacy canary formatter、Ruff、shell、infra30及兩份scoped Read-only reviews通過；真Redis restart/full clone restore與Edge root cause以新CI artifact判定，未放寬任何acceptance assertion。

## 2026-10-08 — 容器復原先恢復data services再啟動consumers

- [run37661758660](https://github.com/LeoCheng-space/Hine/actions/runs/37661758660) 的sanitized report證明真API／BA images建置、production migration、verified privateCA HTTPS及2個original C1/M1／W08-W09／history均通過；整體仍在四service同時restart後的health gate失敗，restore未執行，不宣稱全部容器完成。
- 對owned project沿用正式handoff順序：先停止API／BA，重啟原PG／Redis並等真健康，再啟動原API／BA與完整health/JWT/history/C1/receipt驗證。same containers／keys／volumes不變，不增timeout、不盲重試、不略過失敗；若仍timeout，只記固定service名稱與health enum，不上傳private logs。
- 修改後Ruff與infra30通過，實際Docker recovery／完整clone restore仍由新功能分支CI決定；既有VM／PG16不涉及此操作。

## 2026-10-08 — 真native headed hidden／foreground browser驗收

- 不使用Playwright強制visible的recipient context：headed收件者使用同指定Chrome／Edge真binary、fresh0700 native profile、原Components持有／清理child，透過公開 `connect_over_cdp(no_defaults=True)` 接管default context。保留SDK固定版本、privateCA限制；不接用operator profile或browser，不合成visibility事件。
- 已實驗驗明secondary CDP session無法取消Playwright原session的focus override；真native no-defaults同window兩tab切換才觀察hidden／visible。實際UI互動先foreground，純收件／hidden觀察不foreground；所有role／HTTP／WSS／IDB／原C1／reload／receipt／撤權路徑保持。
- owned非rootauthenticated Xvfb＋Chrome154.0.8037.97 **headed59checks全通過**：真正hidden時只提交delivered、不提交read，實際foreground後才read；100則已提交訊息DOM／IDB各單筆與rAF404.99ms。無unexercised browser case；這仍非physical Android／IME、正式VM或50users/600秒SLO。

## 2026-10-08 — 修正真 Docker nullable network metadata

- [run37656312011](https://github.com/LeoCheng-space/Hine/actions/runs/37656312011) 已保留sanitized reports；container真runtime指出 `isolated_subnets` 在Docker無IPAM的network遇到合法`Config:null`便TypeError，尚未建置映像。修正只把無地址配置視為空迭代，不略過已占用CIDR或放寬service隔離。
- 新確定性consumer regression以null IPAM及已占用172.29.0.0/24驗明分配172.29.1.0/24、172.29.2.0/24；先重現同一TypeError，修正後完整infra30／Ruff通過。這是topology演算法邊界測試，不是偽造Docker、產品authority或映像成功。
- 同run的Chrome／Edge均停在genuine hidden斷言：Playwright預設focus override令各tab可見。保持失敗、不跳過或合成visibility事件；後續native no-defaults browser驗收與遠端image啟動按實際結果記錄。

## 2026-10-08 — 保留功能分支 CI 的 sanitized 失敗證據

- [首輪功能分支run37654735137](https://github.com/LeoCheng-space/Hine/actions/runs/37654735137) 實際5個jobs成功、Chrome／Edge／container三個新runtime gates失敗；不以本機56checks或Review當遠端成功。原product／data-services／QA-infra／scanner與完整native8faults均成功。
- GitHub artifact API實際只列`hine-web`，三類報告在hidden directories被 `actions/upload-artifact@v4` 的預設`include-hidden-files:false`略過。只對既有明確的sanitized JSON glob啟用hidden files；不擴大上傳secret／log／browser profile／trace／HAR。
- 兩個acceptance CLI失敗報告補充**本runner函式名與行號**，不保留exception message、local path、SQL、credential、ID或本文；用真失敗external command驗明exit1及兩個source-only位置，4個CLI安全回歸／Ruff／actionlint通過。這批恢復可診斷證據，不抑制或跳過仍失敗的runtime assertions；新CI按後續實際run判定。

## 2026-10-07 — 功能分支補齊可重跑 browser／container／fault CI

- 從使用者已合併的main `26f13f19c50d260bf65567a009098e36880410e6` 建立 `feature/acceptance-completion`；每個修改按驗證批次commit，不自行提出main PR／merge／auto-deploy。既有兩VM／Nginx／PG16與使用者原checkout保持原樣；正式存取缺件不拿假provider或角色分工代替。
- 新 `tests/browser/browser_acceptance.py` 固定Playwright1.63.0，重用原native Components与真production React bundle；實際UI／HTTP／WSS／PG／Redis／IDB／reload／原C1／receipt／群組與session撤權。修正runner自身缺prerequisites、strict locator、SDK keyword-only callback、SQL JSON codec及async membercontrol等待；未變更production App／API／BA邏輯。
- 本機Chrome154.0.8037.97 headless56個實際檢查全通過：100個offline期間已提交訊息由保存游標重連，raw DOM／native IDB各恰好一筆同M1／原文，加rAF驗回376.05ms；真committed-response loss令原C1仍unconfirmed時實際reload並核回同C1／M1／intent，sender read投影／owner撤權cache／33個frontend inputs與4個compiled assets provenance驗明。另一device登出後真WSS傳訊存續通過。不是50人／正式VM SLO；headed hidden與physical Android不可由headless代填。
- 新fresh own-project container runner建置兩真image、production explicit migration、secret owner UID/GID／64hex／private CIDR、verifiedCA TLS／WSS／readreceipt／restart／完整archive及restored-product flow。4個no-clobber／private NOT_EXERCISED／實際SIGTERM child reaping回歸先red後green，完整infra29通過；本機缺Docker不冒稱映像已執行，Standalone Compose真解析private5service／sole loopback Caddy通過。
- API109＋BA100＋QA36＋infra29＋Web63＝337項與完整8個native product faults通過；本次lost notify實際WSS撤銷4675.354ms。CI保留原四jobs／Gitleaks，新增Chrome／Edge headed/Xvfb、完整native故障／atomicrestore與container gates，加Unicode artifact `--check`。遠端Actions按後續真run記錄，不把workflow存在當全綠。
- Repo／Notion／SSH／ADC／GitHub secrets-variable存取查核仍無正式target／授權；真VMrouting／GCSbytes/IAM/CORS／AndroidIME旋轉／正式50人與VMbackup/rollback/monitoring仍Blocked，原始歷史JSON與source時點不改寫。

## 2026-10-07 — PR #6 同步 main 並解決 CI／infra 衝突

- 將 `origin/main`／`0736110178a186816b94731caa80149879c44931` 整合進 PR #6 來源，保留已發布 `828fd33` 的全部修正；這是 source branch 同步，不是 merge PR 到 main，不 rebase／force-push／刪分支。
- CI 同時保留 main 的每分支 push／pull_request、`contents: read`、完整 checkout 與 Gitleaks v3，以及原四個 jobs 的真 PG／Redis、disposable restore、API／Web／QA／infra 測試。Checkout 統一 v6；秘密掃描仍按 push／PR commit 範圍執行，沒有關掉 scanner、comments／artifact 的既有 false 設定不變。
- `infra/README.md` 保留現有兩台 VM／Nginx／Let's Encrypt／PostgreSQL16 與 GCP 記錄連結，分清單 VM Compose PostgreSQL17／Redis7 目標；保留真 API profiles、secret／trusted proxy／migration／GCS／備份安全。修補 code fence，`infra/gcp/README.md` 的 main 更新原樣保留，不操作或升級現有 VM／資料庫。
- Gitleaks v8.24.3 實際 history scan 命中三個不可變歷史 evidence source SHA256；已對照真正 `auth.py`／`api.ts` bytes 驗明，不是憑證。`.gitleaksignore` 只列 commit＋path＋rule＋line 精確誤報指紋，不修改歷史 JSON、不略過整個 path／rule／未來 commit。同 evidence path 的新 synthetic PAT detector canary 仍被攔截；全46 commits redacted scan 通過。
- 解衝突 Git index 的隔離 checkout 重新109 API＋100 BA＋36 QA＋25 infra＋63 Web＝333項及20個真HTTP/WSS/PG restart smoke通過；actionlint／Ruff／typecheck／release build／shell／default-realtime-product Compose通過，兩份獨立CI／infra Review無重要缺陷。新 merge commit／遠端 CI 以發布及 Notion 記錄為準；既有環境進度與正式產品驗收仍分開。

## 2026-10-06 — PR #6 八項 Review 修正與實際 UI 收斂

- 由已發佈 `feature/hine-first-integration`／`315afd8a1242332c4091d20c8e45907f88e3da2c` 的原 PR #6 隔離 worktree `pr-6` 修正，不改原工作區／使用者 `.omp/`。本輪尚未 commit／push／resolve 遠端 Review／merge main／刪分支；既有 head 的 Actions 全綠不冒稱本輪新 CI。
- 新增有界 API retention：每60秒各最多1,000筆 expired SyncCursor／invalidation，reuse既有索引、維持live TTL、frontier序列化 contiguous prefix／floor／空log head。MAC／owner／kind驗過但已prune的SyncCursor仍回 `SYNC_RESET_REQUIRED`，真Web會bootstrap；非法MAC／scope／REST不混同。無新增migration或其他table清理。
- provider確認不存在的closed attachment亦終止 `cleaned_at`，之後不重掃；cloud錯誤仍可重試，ready／fresh／24h reconciliation horizon及固定generation刪除不變。PUT503／不明結果先核原A21；確認不存在才用原grant／attempt／bytes／SHA／key／create-only headers再PUT，不偽造412成功或更新過期授權。
- A14 private notices遇重複recipient或既有700KB預算即拆批，保留全部stable events／durable Cartesian feed／順序／冪等。聊天清單消費既有事件，以single-flight＋trailing A11刷新，server未讀／20筆分頁及舊owner/token/lifetime拒絕維持。DeviceStore完整Python3.12／Unicode15 casefold，未知等價拼法保留server DeviceID與原draft/C1 partition；無locale／NFKC／單字元特例。
- A12在queued nativeIDB commit比較獨立metadata floor，與self-join boundary分離，涵蓋detail eviction、summary-only title／roles、uncached staged snapshot replay。舊成功read不降版／假unknown／重連，equal／direct-null仍更新。正式bundle A14初開UI另實際重現兩種self-join交错，修正為identity／epoch／ticket限定的fresh authorized route handoff，不重試failed work、不安裝舊read、不讓close／withdraw／換binding啟動舊房間。
- 實際先red再green；109 API＋100 BA＋36 QA＋25 infra＋63 Web＝**333項通過**。10個真API/WSS/IDB metadata案例、4個fresh opening／close／withdraw案例、queued原C1／all-touched W16／PG prune後Web自動bootstrap通過；正式A14兩人表單直接顯示composer及實際group dialog／Escape／767 layout驗明。13份source SHA256及界線見[本輪證據](testing/evidence/pr6-review-remediation.json)。
- 新[owned PF08](testing/evidence/pr6-native-restore.json)真pg_dump／單交易clone restore通過；20個peer原C1持久W06到production DOM+rAF全部成功，sample p95 37.7ms、max42.3ms，僅loopback/privateCA小樣本。公開www首頁TLS200但apex／www API和WSS升級均nginx404；沒有SSH／ADC／bucket／signing／Edge／adb／Docker／gcloud可用目標，正式VM/GCS/physical browser/50user呈現SLO/RTO-RPO仍保留具體門檻，不冒充完成。

## 2026-10-06 — 修復 PR #5 的 Compose 交付遺漏

- GitHub Actions run `37426162599` 的 `compose-data-services` 已失敗：根目錄 `docker-compose.yml` 在 `9a30c63` 仍是父分支版本，未包含真正 API provider；合併 development overlay 後 `api` 只有 ports，因此無 image/build context。這是提交範圍遺漏，不是以假 image 或額外 profile 可解決的服務實作問題。
- 補納完整根檔：真 `api.build`／product profile、JWT／database_url secret、private backend／edge、readiness、trusted-proxy 預設 none。預設仍只啟動 PostgreSQL／Redis；沒有強制啟動 API 或改動 production migration／資料卷安全規則。
- 驗證從實際 Git 暫存區檔案重建的隔離目錄，而非只測工作目錄：初始化後 default config、CI realtime development config、product config、product＋realtime development config 均通過。解析 model 驗明 default 為 PostgreSQL／Redis、product 才加入含真 build context 的 API。infra25、Ruff、actionlint 通過；完整遠端 CI 以修正提交的後續 run 為準。

## 2026-10-06 — 全角色真實產品補完與本機驗收

- 依使用者已直接合併 PR #4 與跨角色補完指示，由 `fc9eb08` 建立 `feature/product-integration`；不再以 BB／FA／FB／BA 的責任分工阻擋缺項。後續依使用者要求 commit／push，實際 SHA／遠端發布以 Git 紀錄及 Notion 發布紀錄為準；不建立新 PR、不修改 main 強制保護、不冒充組員批准或遠端 Actions。
- `backend/api/` 交付真正 aiohttp／PostgreSQL17 migration、JWT／scrypt／session／Cookie、可信服務身分、C2／C13、聯絡人、50人群組／最後admin／新加入界線、C1／quota／訊息回條、原子user feed／frozen snapshot／opaque cursor與W18私有op11。原內容／Unicode／null欄位保持，不以記憶體authority取代BB。
- 附件用真正 Google Cloud Storage3.16 SDK、V4 create-only PUT／固定原授權期限、核驗同generation／metageneration bytes／MIME／SHA256、固定版本A22與safe filename，以及短DB交易後cloud I/O／terminal abandoned exact-generation清理。沒有假GCS／本機storage fallback；真bucket／signing／ADC與CORS仍缺存取，未冒稱實際上下載。
- `frontend/app/` 交付單React19.3／TS7／Bun1.4.2 Web：唯一Session／WSS／Web Lock、登入／路由／資料頁、IDB v1/v2→v3保留資料升級、投影／游標／原C1／回條原子保存、granular草稿／錨點、IME、唯一768斷點、V3可見性、附件復原與原生群組資訊dialog。Production bundle只定義公開NODE_ENV，關閉任意環境注入。
- 實際失敗再修正：較舊A19頁被newest-only cache丟棄；同帳戶刷新卡住舊read；queued W05跨移除／重加入；W16等待B授權時重裝A舊正文；不可讀群組阻擋其他回條；完整目前歷史不存在的舊target無限重掃；initial A19 single-flight未等待；同工作階段重連卡住跳最新控制。現在保護requested history window與原意圖、所有touched conversation tickets、terminal blocked但不假read、Promise identity cleanup；原C1不更換、不盲目自動重送。
- 補BA W18：private `readPresenceTargets` 查當前授權聯絡人，彙總所有有效裝置、Redis未知、不混活動／已讀；最後socket-lock後重查、過時／撤銷不送、metadata與frame／byte有界、單幀無法裝入即資源清理。23個W18回歸納入BA100項。
- 移除外部 `API_PROVIDER_COMPOSE` cutover；root Compose包含真API／BA、JWT與database_url secret、可信proxy預設none／正式明確CIDR、真GCS credential overlay。正式API容器只校驗migration，新增零參數 `stack.sh migrate` 明確遷移；dotenv重複／空override／multiline／colon continuation 在任何secret mutation前fail closed。CI提供真正PG17＋Redis與兩套Python依賴、Web55行為／typecheck／build。
- 最後96 API＋100 BA＋36 QA＋25 infra＋55 Web＝**312項通過**；Ruff／actionlint／shell／Compose及Caddy配置已驗。[完整逐REQ證據](testing/acceptance-matrix.md#current-product-evidence)區分實作與物理環境。
- [Chrome證據](testing/evidence/product-browser.json)保存35個實際UI檢查、7個真正API／PG／WSS／IDB場景、修正前失敗與8份最後source SHA256。實跑註冊登入／換帳戶隔離、兩頁bootstrap、IDB quota abort、深241訊息12頁／有界200仍可看舊頁、原生IME、群組role／最後admin拒絕、dialog焦點／767、保存後W08／遮罩與連續可見後W09；hidden實機／Edge／Android未冒稱完成。
- [native PF01–PF08](testing/evidence/product-native-faults.json)全部PASS：真process／PG／Redis／提交回覆／SQL rollback；停止寫入者後真正pg_dump／單交易pg_restore到自建clone，還原後表記錄／JWT／撤銷／原M1-C1／feed／read核對。[正式模式gate](testing/evidence/product-production-migration.json)驗無implicit DDL、明確3個checksum後ready200，不代表Docker或VM已啟動。
- [一對一50WSS／600秒](testing/evidence/product-direct-load.json)：6,000／6,000成功，W07協定p95 78.974ms；[獨立50人群組／600秒](testing/evidence/product-group-load.json)：6,000 intent、294,000／294,000收件與全50歷史驗明，fanout協定p95 73.387ms。是loopback／私有CA／單BA程序CPU-RSS，不是瀏覽器呈現p95、正式VM容量或HA／RTO／RPO／SLO。
- 現有Notion只有既有VM／網域描述，沒有本輪可用VM登入／GCP project／bucket／signing或ADC credentials；SSH無host/alias、本機無Docker daemon。完成可達程式與native產品驗收，正式VM／公開TLS／真GCS／Edge-Android實機仍須真存取。推播／活動租約／PWA／native app依既有決議範圍外；Title 1–80仍候選。

## 2026-10-05 — BA 專用失效分析與本地故障演練

- 新增[BA 失效分析](testing/backend-a-failure-analysis.md)：30種模式，原因／影響／偵測／降級／復原、角色、主觀工程嚴重度、42筆既有測試trace及7個正式產品／部署gate。O未知、D未量化、不捏造RPN；歷史119項不當作失效模式數。
- 新增[可重跑工具](../tests/faults/README.md)：只操作自建BA／Redis子程序、loopback BB forwarding socket與測試專用記憶體authority；標準poll5／stale15／hold1000。實際DR-01～DR-06全PASS、exit0；[公開JSON](testing/evidence/backend-a-local-faults.json)保存版本、觀察、monotonic計時及14份吻合的source SHA256。
- Review與實際診斷修正演練工具的ACK-loss誤踩第二次authority timeout；補owned BA listener證明、逐次shield cancellation及atomic no-clobber evidence。缺前提／既有輸出安全拒絕、不接觸無關ready服務，雙cancellation後owned children存活0；runner Ruff及scoped re-review通過。
- 不修改BA產品runtime／公開介面；不以fixture記憶體證明PostgreSQL／JWT持久性，不以單次恢復時間證明15秒socket-write界線、p95／RTO／RPO／SLO。真BB／Web／VM／磁碟／備份還原／50WSS及W18仍按具名gate驗收；單VM不承諾HA。依使用者要求提交並推送至`feature/realtime-receipts-sync`，發佈以實際Git紀錄為準；不建立PR、不合併main。

## 2026-10-04 — 子分支 BA 回條與斷線同步

- 依使用者要求，由已發佈 `feature/hine-first-integration`／`5b71178` 建立 `feature/realtime-receipts-sync`，獨立交付回條與同步；原分支不改寫。子分支發佈不等於合併 main、成員批准或正式產品驗收。
- 新增 `receipts.py`：W08／W09 經 BB 持久化後回 W19，保留單調 read、未變更結果、正式 M1／公開操作者／觀察者／時間與穩定事件；一對一 W10 走既有 Redis 通知，群組只回個別 W19、不發彙總。Redis 故障不撤回已確認回條，畸形寫入結果不冒充成功。
- 新增 `synchronization.py`：W13／W14 多頁快照、W15／W16 固定邊界／事件流；保留不透明游標、完整投影、sender-only C1 與最小自身 W12。公開回應不假造內部 watermark，讀取後完整補齊工作階段失效；排隊寫入前再次核對當前資源授權、到期／新鮮度及撤權版本。
- `SYNC_PAGE_LIMIT` 成為必要設定，合法範圍1–100，標準100；既有測試呼叫者及啟動說明同步更新，Compose 原本已有100。BB 仍負責1000位置掃描上限、游標／快照與正式權威，FA 仍負責瀏覽器投影／游標原子保存。
- Review 發現過時的排隊同步回應會默默被丟棄；已實際重現，再修正 dequeue／socket-lock 末端兩處為關聯 DEPENDENCY_UNAVAILABLE，不洩露原正文／游標、不造成鎖重入，恢復後可重試同一游標。
- 已執行77項真實 HTTP／WS／Redis BA 邊界測試、19項 QA、23項維運，共119項通過；Ruff／actionlint／Compose配置通過。兩個新功能先有消費失敗測試；回條及同步 scoped Review 通過。實際 QA CLI reconnect smoke 完成3／3訊息、斷線補回、QA SQLite 原子投影／游標與舊游標去重。
- 隔離 BB authority／QA SQLite 不是產品 PostgreSQL／JWT 或瀏覽器證據；真實 BB／FA／FB 串接、Docker／VM部署、GitHub Actions與50WSS仍未驗收。本輪不新增公開 API／欄位、群組已讀彙總、推播或原生 App。

## 2026-10-04 — 首輪 Backend A、共用環境、QA 與 CI 交付

- 依使用者決議暫緩 main Branch Protection／Rulesets；保留一般功能分支／PR／Review／適用 CI 協作流程，不設定 GitHub 強制保護。
- 新增可執行 `backend/realtime/`：Python 3.12、aiohttp 3.14.3、redis 8.1.0，首輪 W01–W07／W17、可信 BB 身分／持久化交接、提交後 Redis 扇出、心跳、失效輪詢／新鮮度／到期、健康檢查與有界輸出。BB 保留 JWT、canonical 計數、C1／產品 quota 與 PostgreSQL 權威。
- 群組資料遞送沿用既有安全義務：A18 在等待／排隊前套用撤權，包含只送給其餘成員的分段通知；訊框保留內部 membership version／M1，寫入前再次檢查。W07 以既有 message-resource receive 授權核對當前可讀／加入界線，不因重新加入或通知遺失而交付舊內容；不新增公開欄位／API 或群組 CRUD。
- 新增 PostgreSQL 17／Redis 7 Compose、私有 Secret 初始化、loopback 開發 override、真實 BB／Web provider 的 Caddy 部署交接與備份／還原／preflight。修正 cap-drop Runtime 與 Secret owner 身分；禁止任何 volume 刪除旗標繞過；缺失 Web 發布不再阻擋既有服務停止／DB 復原。
- 新增一套 QA HTTP／WebSocket CLI；ACK、收訊、歷史／C1／排序、保存／游標、公開錯誤隱私、實際派送節奏與已驗證 WS／WSS 連線分開核對。未達 50 使用者／600 秒的真實負載節奏，不宣稱基線；工具供 Jackie 確認，瀏覽器保存／呈現仍另驗。
- CI 新增適用 Python／Redis 邊界／QA／維運檢查，以及具 Docker runner 的真實資料服務、映像建置與一次性還原場景。明確設定測試 Redis 卻不可用時會失敗，不以 skip 假造綠燈。
- 已執行：31 項 BA（真實 HTTP／WS／Redis＋隔離 BB 測試 authority）、19 項 QA、23 項維運測試，共 73 項通過；Ruff、actionlint、shell syntax、Compose 配置與原生 Caddy 配置通過。兩個群組漏送授權情境實際重現修正前洩漏／修正後阻擋；實際 CLI、小負載及 Caddy→BA upgrade／fail-closed smoke 已執行。
- 證據邊界：上述 BB authority、歷史與前端路由樣本僅為隔離 smoke，不是 BB PostgreSQL／JWT、真實產品 E2E、瀏覽器或 50 WSS 容量證據。Docker daemon／VM 存取、BB／Web 真實交付與成員確認仍缺；未執行容器建置／DB 還原／雲端部署或 GitHub Actions，不宣稱成功。功能分支發佈不等於合併 main、成員批准或遠端驗收通過。

## 2026-10-02 — PR #3 最新通知／ID 覆蓋／產品 quota 修正

- Finding 1：BB 在生成／送出 RealtimeNotice 前驗所有 canonical EntityID；authenticated BB 的結構合法 notice 視為 BB 已完成長度責任。BA 驗 caller／JSON／required／null／型別／enum／UUID／source，不重算 Unicode 長度，結構錯誤仍 INVALID_ARGUMENT。同步 BB→BA 內部 ID 交接，公開 REST／W05 的 BB 前置驗證不變。
- Finding 2：EntityID 129 驗收補 A06 非 null avatar_attachment_id、A10 user_id，不做 attachment／使用者／聯絡人 lookup 或授權；A06 null／omission 語意保留，共用 15 個 receiving REST 清單一致，不新增其他 ID／output-only／範圍外邊界。
- Finding 3：正式 PM 將 W05 每使用者 5/s、burst 10 的產品 quota 唯一權威改為 BB 的 persistIfAbsent，C1 判定後／持久化前只作用於新合法 intent。BA-08 保留 transport/frame defense 與 W17 mapping，不先判或雙重維護產品 quota；不指定 BB 實作。
- 六階段與 quota exhausted 五個結果同步：非法 payload → INVALID_ARGUMENT；新合法 C1 → RATE_LIMITED；相同合法 C1 → existing_same／原 M1；不同合法 C1 payload → IDEMPOTENCY_CONFLICT；非法同 C1 payload → INVALID_ARGUMENT。拒絕不持久化、不建 C1→M1、不回成功 W06；retry_after_ms 沿用既有規則。
- 只修相關契約／驗收／角色／架構交接／決策與五步摘要，原 5/s burst10 數值、Unicode／內容、Title 候選、部署 pending、模組自由、A／W／REQ 及推播／活動／群組回條 scope 不變。先前五階段說明由本輪 W05 六階段取代；沒有產品程式，尚未產品驗證，不代替組員批准。
- 本輪文件 smoke：14 份相關文件的 1,270 個相對連結／anchor、34 個 JSON 區塊通過；A25／W22／REQ22 ID 集合、既有 JSON 範例與原 32 項 PM 正文未改。五個 quota 與 A06 129/null/omission、A10 129 驗收資料只做 JSON 往返；沒有執行產品 quota、通知接收、DB／C1／W06 或瀏覽器測試，尚未產品驗證。

## 2026-10-01 — PR #3 三項契約一致性修正

- Issue 1：明訂 BB 的 EntityID／text canonical 單位為 JSON 解碼後 Unicode code points（Unicode 碼點），排除 UTF-8 bytes、UTF-16 code units 與 grapheme clusters。僅增加 😀＝1、e 加組合重音＝2 的 BB 案例；FA／FB／BA 不需重現算法，不 trim／normalization 或改內容。
- Issue 2：所有 Client／其他模組輸入的 EntityID（含 path、欄位、陣列與巢狀參數）先驗結構／長度；超長 INVALID_ARGUMENT 先於資源／授權。同步實際接收 EntityID 的 REST／internal error list 及引用；只輸出 EntityID、只收其他 ID 型別或範圍外操作不機械新增錯誤。
- Issue 3：結構、輸入合法性、認證／授權、C1 比對、持久化依序；同 C1＋非法 text 先 INVALID_ARGUMENT，合法 World 才 IDEMPOTENCY_CONFLICT，相同合法 Hello 回 existing_same／同 M1。同步 W05／W17、persistIfAbsent、角色／QA／矩陣及原架構圖的順序說明，不新增架構或 A／W／REQ ID。
- 仍保留首輪登入／一對一／W06／W07／A19、Title 群組前候選、內部保留時間部署待決、分輪治理與模組自由；不改推播、活動租約或群組回條。這是文件修正，尚未產品驗證，也不是 FA／FB／BA／BB 的對接確認。
- 本輪文件 smoke：14 份相關文件的 1,275 個相對連結／anchor 與 34 個 JSON 區塊通過；A25／W22／REQ22 的 ID 集合及既有 JSON 範例值未增刪或改動，原 32 項 PM 決議正文未改。兩個 BB Unicode 與三個 C1 情境只做 JSON 解碼／資料往返探查，沒有產品後端、WSS、持久化或瀏覽器測試；尚未產品驗證。

## 2026-10-01 — PM 正式確認首輪限制與後端權威驗證

- PM 已正式確認 EntityID 上限固定為 128、對消費端仍為 opaque string；超長輸入由後端依既有契約回 INVALID_ARGUMENT。text 必須非空，有效範圍固定為 1～4096。
- Canonical validation 由後端負責；文字最終權威驗證由 BB 在持久化前完成。BA 可驗證 envelope、必要欄位與型別，BB 拒絕後 BA 映射既有 W17 INVALID_ARGUMENT，不持久化、不回成功 W06；前端提示／字數／預先阻擋僅屬 UX。
- 前輪移除消費端或不同語言必須重現相同計數模型的要求，以 ASCII 資料驗 text 空、1、4096／4097 及 EntityID 128／129；上方本次修正另明訂 BB 專屬單位及兩個最小 BB Unicode 案例，不恢復消費端算法義務。不 trim／normalization 或改內容。
- Title 1～80 保留 A14／A15 群組串接前候選，`INVALIDATION_RETENTION_SECONDS` 保留部署／維運待決；不阻擋首輪登入與一對一文字聊天。分輪治理與模組內自由維持不變，共同修改僅要求提供方及直接受影響消費方確認。
- 本次僅同步政策文件、角色交接、導覽、協作／PR 清單與驗收條件；不新增 API／WSS ID，不改其他產品規格。PM 確認不代表 FA／FB／BA／BB 已確認；尚未產品驗證，不宣稱全介面已凍結或產品已實作／測試通過。
- 本次已執行文件 smoke：13 份文件的 1,192 個相對連結／錨點與 34 個 JSON 區塊通過檢查，六個 ASCII 邊界資料已實際產生並完成 JSON 往返檢查。這是文件／測試資料驗證，不是後端、WSS 或瀏覽器產品測試；尚未產品驗證。

## 2026-10-01 — 近期共同介面與分輪變更政策

- 依使用者指示改採「先對齊近期串接介面，模組內自由開發；介面可以修改，但與受影響成員一起改」，不要求一次鎖死整份規格。
- 共同契約新增首輪一對一文字路徑：A01／A02／A05／A13／A19、W01–W07／W17、FA↔FB 工作階段／導覽及 BA↔BB 驗證／寫入／提交後通知交接；既有欄位、授權、ACK、C1 冪等、游標／保存語意及 API／事件 ID 不重編。
- 初稿以 EntityID ≤128、text 1–4096 為工作值並提出消費端一致計數；此驗證責任提案已由上方 PM 正式確認取代，不再是現行契約要求。Title 1–80 保留群組串接前候選；內部部署保留時間仍另行協調。
- 協作指南與 PR 範本補上提供方／直接受影響消費方共同確認、同步契約／範例／驗收／實作與切換、驗證及更新 Notion 的流程；六角色文件、決策紀錄、驗收矩陣與文件導覽同步引用，不要求內部實作逐項請 PM 批准。
- 前輪曾執行 34 個 JSON 區塊解析、相對連結／錨點檢查及兩種語言各 13 個計數探查情境；計數探查不是本次必要驗收或對消費端的算法要求。這些不是產品 API／瀏覽器串接測試；未實作或部署產品，未取得 FA／FB／BA／BB 共同確認，不宣稱整份規格已凍結。
- 來源為 `17c25ec`；本次修訂透過 `docs/incremental-interface-baseline` 分支交付，以該分支提交紀錄追溯。分支交付不代表已 Review／合併，不宣稱 GitHub main 已更新。

## 2026-10-01 — 決議一致性修正（單一實例、範圍外功能、共用程式碼）

- 驗收矩陣：REQ-08 與 AC-N01、N03、N04、N08、N09 改為單一 `realtime` 實例；保留多使用者、多裝置及以測試客戶端模擬的同工作階段新舊連線（重連／A03 換線交接的安全測試，不代表多個可操作分頁）。AC-N03／N04 以 W05／W15 取代 W21 步驟；REQ-15 改列 W03／W04、W18、A08，AC-N27 與 REQ-14 標示本版範圍外。
- 架構與角色文件：元件圖、部署圖、元件表與路由表標明本版提供 A01–A22、W01–W20（A23–A25、W21／W22 僅保留 ID）；BA-05 等標題與交接改為單一實例；後端 B 角色目的移除推播意圖；共同契約節點規則註明「節點」即單一 `realtime` 實例。
- `backend/common/` 改為可選共用程式碼；跨語言整合依據為共用介面契約、Schema 與測試樣例。
- 未新增或重編 A／W／REQ／功能卡／AC ID，舊標題錨點保留；未改 ACK、冪等、游標、快照、同步、撤銷或 C14-S 語義。此次僅修文件，未實作、部署或執行產品測試。

## 2026-10-01 — PM 決議整合

- Notion「HINE 待 PM 批准項目（HINE-IC-0.4）」共 32 項均已由 PM 決定；`docs/decisions.md` 改為現行決議登錄，不再表示仍待批准。已批准及需修改後採用的政策依決議更新；已否決／本版不做的推播、活動租約等明確標示為本版範圍外。
- 現行方向包括單一 GCP Compute Engine VM＋Docker Compose、依模組自選語言／框架，以及 QA 選定一套負載測試工具；README 與文件導覽同步更新推播範圍及角色摘要。
- 共同契約：C1–C6（C6 簡化為單次刷新後重登）、C8–C13、C14-S、E1（S＝15 秒）、G1–G3、S1–S2 改為現行規格；新增[加入界線](contracts/interface-contract.md#join-boundary)與[內部呼叫憑證](contracts/interface-contract.md#internal-caller-credential)；A23–A25、W21／W22、C7、活動租約、Web／原生推播標示本版範圍外（ID 與錨點保留）。
- 前端：M1 改為同一瀏覽器設定檔單一可操作分頁（Web Lock `hine-session`），移除多分頁交接；B1 驗收瀏覽器為 Chrome／Edge 桌面與 Android Chrome；Web/RWD 只有 768 CSS px 一個斷點；V3／V4 已讀、鍵盤、根路徑與本機篩選定案。
- 數值：REST 20／50、W14 每頁 100、W16 每批 100／掃描 1000、心跳 30／90 秒、訊息每秒 5 則（突發 10）、登入每帳號每分鐘 10 次／每 IP 每分鐘 60 次、群組 50 人、附件 JPEG／PNG／PDF ≤10 MiB、上傳授權 10 分鐘、下載授權 5 分鐘；課程效能基線為 50 使用者／50 條 WSS。驗收矩陣 N19–N24、N23、N27、N28、AC-R04、AC-R09、AC-R10 依決議改寫，未新增 ID。
- 此次僅整合文件決議，沒有實作產品功能、部署或執行測試／壓測；相關數值與效能目標仍未量測。

## HINE-IC-0.4 — 獨立文件提案，待批准

- 現行提案文件分為[獨立共用介面契約](contracts/interface-contract.md)、[網頁／響應式規格](ui/web-rwd.md)、[`prd/`](prd/) 下六份獨立角色需求文件、獨立[驗收矩陣](testing/acceptance-matrix.md)及中央[待決策事項登錄表](decisions.md)。
- 較早的整合版 [HINE-IC-0.4 契約](HINE-IC-0.4-contract.md)與[六角色需求文件](HINE-IC-0.4-role-prds.md)僅作歷史整合來源保存，不具共同權威性，也不是現行導覽目標。
- 新增可點選的[角色與主題文件地圖](README.md)，串連角色職責、契約查找、驗收及待決政策。
- 新增共用網頁響應式文件並於角色需求文件中互相連結。文件說明已確認的單一網頁應用程式交付基線，也明確將候選版面與互動規則標示為待批准；不推定原生應用程式或漸進式網頁應用程式（PWA）範圍。
- 拆分導覽讓角色職責、共用契約查找及待決政策更容易查閱；標準需求列與 REQ-19–REQ-22 網頁詳細驗收已收錄於獨立驗收矩陣。
- 補齊六角色共 43 項功能卡的具名需求、實際 API／事件／內部操作與協作功能章節連結；FB-06 直接指向未核准的瀏覽器推播決策，與既有原生 A23/A24 契約區分。共用契約僅增加現有內部操作的錨點，不改介面語義。
- 新增[系統架構](architecture/README.md)：元件與責任邊界、資料權威、識別碼與排序、連線／傳送／群組事件／附件／推播流程、部署拓樸、失效模式、安全、可觀測性、交付與容量驗證。另於[待決策事項](decisions.md)登錄 GCP 執行環境、技術棧、`api`／`realtime` 部署單元、REST 寫入後的即時通知路徑與負載測試工具等架構決策。本次未修訂 A01–A25、W01–W22 或任何契約語意。
- 新增候選方案（待批准，未實作）：
  - [提交後通知與授權失效](contracts/interface-contract.md#internal-notify-invalidation)：
    - 分開定義授權失效、連線清理與通知傳遞三種保證。
    - 以 PostgreSQL 提交序與資料的授權點定義撤銷前／後資料（D1–D4），撤銷前資料的工作階段上限為 `INVALIDATION_STALE_SECONDS`，並附[交付與連線狀態表](contracts/interface-contract.md#delivery-state-table)。
    - 新增候選內部操作 `readSessionInvalidations`／`publishCommitted`、既有操作的欄位與行為變更 C1–C5（C5 為 A02 的行為變更）、[適用狀態](contracts/interface-contract.md#internal-applicability)與[候選設定](contracts/interface-contract.md#deployment-config-candidates)。
  - [架構 6.6](architecture/README.md#flow-invalidation) 補上流程與摘要。
  - [前端 B 多分頁工作階段交接](prd/frontend-b.md#fb-multi-tab)。
  - [待決策事項](decisions.md#architecture-proposals)：五項架構決策的主方案，批准清單改為「目前方案／還缺」表，並補上 Cloud Run 適用條件與來源。
  - 相關後端 A、後端 B、維運、品質驗證、FA-02、FB-02 功能卡加註候選行為。
  - [驗收矩陣](testing/acceptance-matrix.md#notify-invalidation-cases)新增 AC-N01～AC-N24，並由既有 REQ 引用。

  以上都未修訂 A01–A25、W01–W22 的請求與回應格式，也未修訂確認回覆、游標與同步核心語義。
- 產品政策收斂（本地文件候選，未批准）：新增 [PM 六欄行為批准表](decisions.md#behavior-approval)，將群組撤權分為裝置已取得、舊授權服務端待送、撤權後新查詢；待送內容主要推薦已存在的 [E1](contracts/interface-contract.md#group-revocation-e1)，明列不採 E1 沒有相對 A18 固定停止上限，60 秒不是最大交付延遲。15 秒新鮮期限同時列為舊授權資料開始交付窗口，並分開[需求／候選配置／量測結果](decisions.md#spec-config-measure)。
  - 多分頁補上 C6 不給舊更新憑證寬限、一次結果不明恢復與明確重登終點；C7 各連線租期、任一前景優先；缺少必要瀏覽器能力採不支援政策。相關角色卡只補候選引用，六份需求文件與 A／W／REQ／角色功能 ID 保留。
  - 修訂 N18、N23，新增 N25–N28 文件驗收條件；原文改為比較基準，批准後才整合唯一現行定義。沒有產品程式、部署、產品測試、壓測或新的平台範圍；所有量測結果仍為未量測。
- 本輪交叉審查局部修訂：修正表格型別聯集的 `|` 跳脫（不改既有 JSON 字串）；對齊 [W17 錯誤與恢復](contracts/interface-contract.md#error-recovery)、可省略的 `retry_after_ms` 缺值處理、心跳識別值比對、必填／可為空值與[本地保存範圍](contracts/interface-contract.md#local-persistence-boundary)。新增待批准 C8–C12：後端 B 公開 `user_id`、A22 收件者中繼資料、簽署 PUT 上傳、`order_key` 編碼與 REST 分頁上限；不新增 A／W ID 或另一份權威契約。
  - FB-04 明訂已知 ID 查詢；群組彙總維持條件功能、一對一交接補齊；FA-07 認證交接改連 FB-01／02。補 [AC-R02–R08 文件條件](testing/acceptance-matrix.md#review-handoff-cases)；六份角色需求文件、43 個功能 ID、文件地圖保留，S／E1／多分頁批准狀態不變。本輪不實作、不部署、不執行產品測試／壓測。
- C10／R4 內容一致性補足（具體方案待批准，非 PM 簽核）：先引用 A21 目前上傳嘗試的核驗／冪等與 A25 待處理狀態／新上傳嘗試規則，再於[既有 C10](contracts/interface-contract.md#signed-upload-contract)補每次嘗試的獨立物件鍵、簽入 `x-goog-if-generation-match:0`、核驗物件世代／中繼資料世代、就緒狀態與中繼資料原子綁定、A22 固定物件世代交付及不可取得時拒絕替換。單次 PUT 不宣稱簽署網址一次性；不新增 A／W API，C8／C9／C11／C12 主方案與 S／E1／多分頁狀態不變。
  - 擴充同一 [AC-R04](testing/acceptance-matrix.md#ac-r04-version-cases) 的就緒後重傳、A25 後舊 PUT、回覆遺失後 412、交付版本不符四項文件預期結果；同步 BB-07／FA-06／FB-03／DO-02／QA。[R1～R6 狀態](decisions.md#review-resolution-status)明確分為「格式／既有矛盾已修正」與「已提供具體方案、待批准」，不把待批准誤寫成未回應；未執行產品測試或部署。
- 文件語言統一：README、協作與範本文件、各目錄說明、現行契約、歷史整合契約與角色需求文件、角色 PRD、網頁／響應式規格、架構、待決策事項與驗收矩陣的說明文字改為繁體中文。API／事件名稱、欄位與列舉值、錯誤碼、路徑、網址、環境變數、JSON 範例與 A／W／REQ／角色功能／AC ID 維持原樣；原英文標題的連結錨點保留。只改語言，不改任何規格語意、提案或批准狀態。
- 中文版 Review 局部修訂（非 PM 簽核）：文字澄清 Cookie 分工（BB `Set-Cookie`、瀏覽器保存、FB 管 AccessSession 與流程、FA 只消費）、W08 本機保存、非完整離線但保留本機保存義務、H 前後銜接、`logged_out` 欄位、BB 不可連線摘要、健康範例 `not_checked` 語義、JWT／`REALTIME_INTERNAL_URL` 設定說明、術語（儲存桶、物件鍵、一對一、頁面路由回退）與 BA-08／QA-02 交接。新增待批准契約提案 [C13 內部驗證失敗分層](contracts/interface-contract.md#internal-auth-layer)、[C14 `unread_count` 語義](contracts/interface-contract.md#unread-count)，以及 Web/RWD 候選的[已讀判定](ui/web-rwd.md#rwd-read-rule)、[鍵盤判別](ui/web-rwd.md#rwd-keyboard)、[根路徑](ui/web-rwd.md#rwd-root-route)與[本機清單篩選](ui/web-rwd.md#rwd-local-filter)；新產品選擇登錄為 [V1–V4](decisions.md#review-auth-layer)。補 AC-R09、AC-R10 與 REQ-20 正反案例。不新增 A／W／REQ／功能 ID，不改 ACK／C1／游標／快照核心規則，C8–C12 與 S／E1／多分頁狀態不變。
- 本次文件地圖與內容拆分未修訂 A01–A25、W01–W22 名稱／ID、標準資料、確認回覆／游標／同步語意；不代表已批准、實作、部署或完成產品測試。

## HINE-IC-0.3 — 歷史來源

HINE-IC-0.3 資料是 HINE-IC-0.4 提案的歷史唯讀參考，不代表現行整合來源。現行提案導覽請參閱上方獨立 HINE-IC-0.4 契約與拆分後的角色需求文件；批准狀態仍待定。
