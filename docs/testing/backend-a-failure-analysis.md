<a id="backend-a-failure-analysis"></a>
# Backend A 失效分析與故障演練交接

**分析基線：** `feature/realtime-receipts-sync`，`f3588c9690653b963d34303152be064be31c28ff`。

**範圍：** 單一 BA 程序的驗證、心跳、訊息／回條入口、Redis 通知、失效閘門、快照／事件流代理與資源防護。本文是完整的工程失效分析，不是正式部署驗收證書。

**權威規格：** [BA PRD](../prd/backend-a.md)、[共同契約](../contracts/interface-contract.md)、[驗收矩陣](acceptance-matrix.md)。[架構失效表](../architecture/README.md#arch-failure-modes)是摘要；有差異時以現行契約及明列的實作邊界為準。

## 1. 結論與證據分層

BA 的安全降級方向是「不捏造授權、不捏造提交、不替用戶端推進游標」。BB 成功提交後 Redis 出錯不撤銷已確認结果；無法取得可信結果時不成功 ACK。資料交付受目前連線、到期、新鮮度及撤權閘門約束；恢復依 BB 正式事件流，不依 Redis 持久性。

下列層級不能互相替代：

| 層級 | 本文可引用的事實 | 不代表什麼 |
|---|---|---|
| **CODE** | 基線已存在的處理器／設定／永久測試符號；以下提供精確連結 | 寫有測試不等於本輪跑過；程式碼檢查不等於實際 VM 行為 |
| **HISTORICAL** | [2026-10-04 變更紀錄](../CHANGELOG.md)：77 BA、19 QA、23 維運測試通過及隔離 reconnect smoke；本文只轉述既有紀錄，不重新確認 | 本輪故障演練、產品 PostgreSQL／JWT、Docker／VM、真實瀏覽器或容量驗收 |
| **LOCAL_COMPONENT_WITH_TEST_BB** | DR-01～DR-06 對真實 BA 子程序／Redis／本機 HTTP socket 的觀察；結果以 [機器證據](evidence/backend-a-local-faults.json)為準 | BB fixture 是持續存活的記憶體權威，不是 PostgreSQL、JWT 或正式 BB 備援；本機 WS 不是正式 WSS |
| **UNVERIFIED PRODUCT GATE** | 第 8 節真實 BB、瀏覽器、VM／磁碟／DB、備份及容量門檻 | 不可因文件完整、local PASS 或歷史測試而標示通過 |

**新增本地演練：6／6 PASS，exit 0。** 實際 run_id `19c60b3c-a5d4-4eef-af4f-998e9a01478a`，UTC `2026-10-05T13:39:42.614672Z`～`2026-10-05T13:40:18.812125Z`；公開 JSON 的14份source SHA256已與本機檔案逐一吻合。結果限於 `LOCAL_COMPONENT_WITH_TEST_BB`，不能簽掉第8節產品／部署門檻。

### 已知修正前／後的風險（只引用有紀錄的事實）

- [變更紀錄 2026-10-04 首輪交付](../CHANGELOG.md)：兩個群組授權情境記載修正前洩漏、修正後阻擋。現行實作在 A18 分段通知中立即套用排除、保留 membership version／M1，並在 socket 鎖等待後重查；對應 T17～T20。這不是生產事故率或真實 PostgreSQL E1 證明。
- [同日回條／同步交付](../CHANGELOG.md)：排隊同步回應過時時曾默默丟棄，已重現並修正 dequeue／socket-lock 末端為關聯 `DEPENDENCY_UNAVAILABLE`；對應 T35，不送原正文／游標。這不表示每次 W17 都能穿越已斷的網路。
- 目前 `PUBLISH_ONCE` 先 PUBLISH、後 completion marker 且在同一 Lua 操作內，失敗不能 poison 去重；T15 用實際 Redis ACL 拒絕覆蓋此風險。本文沒有額外宣稱其修正前曾有真實事故。

## 2. 元件界線、狀態與正確性不變量

### 元件責任

| 元件／角色 | 權威與責任 | 不能越界的責任 |
|---|---|---|
| BA | [server.py](../../backend/realtime/src/hine_realtime/server.py)：WSS、連線、傳送佇列、健康與內部 provider；[invalidation.py](../../backend/realtime/src/hine_realtime/invalidation.py)：連續位置／新鮮度／註冊鎖；[receipts.py](../../backend/realtime/src/hine_realtime/receipts.py)；[synchronization.py](../../backend/realtime/src/hine_realtime/synchronization.py) | 不簽 JWT、不直接讀寫 PostgreSQL、不建立 local persistence fallback、不複製 BB canonical／產品 quota |
| BB | JWT／公開 user_id 映射、工作階段／授權、交易／C1→M1／feed／回條／快照／加入界線／失效紀錄；提交後通知 | fixture 只能測 BA 消費行為，不能代交正式 BB |
| Redis | Pub/Sub 加速；UUID／hash completion metadata。裝置在線查詢在 Redis PING 成功後取 BA 本地有效連線 | 不保存正式訊息、回條或游標；marker 遺失不是訊息回滾 |
| FA／FB | 唯一 WSS、有效憑證重連、C1 意圖／去重、投影與游標原子保存、完整快照切換；FB 唯一更新憑證流程 | 不把依賴故障当登出，不把 ACK 當收件保存／已讀 |
| DO／QA | DO：私網、TLS、secret、程序與磁碟／備份／監控。QA：真實故障、隱私、瀏覽器、容量及證據 | 不因 live=200 或 `published:true` 宣告端到端成功 |

**實作覆蓋差異：** [BA README](../../backend/realtime/README.md)明列 W01–W17、W19 與 BB committed group projections；W18 聯絡人在線通知尚未實作，是 REQ-15 的產品覆蓋缺口，不是假故障、不以 `getDevicePresence` 冒充 W18。活動租約、W21／W22、Web／原生推播及群組回條彙總本版範圍外。GCS／REST 游標處理仍歸 BB／前端，本文只列交接、不新增 BA 路徑。

### 不變量

1. **可信身分：** W01 必須先於業務操作；BB 驗證結果完整、有可信公開 `user_id` 才有 W02。所有 BB 業務操作攜帶 C2 工作階段綁定。只有可信 HINE `UNAUTHENTICATED`＋`details.auth_layer:"user_session"` 能作使用者失效；服務／缺層／非 HINE 回覆依 C13 降級。
2. **提交先於 ACK：** 完整 BB confirmed result 才可 W06／W19；known rollback、結果不明、畸形 success 無成功 ACK。提交確認也不保證 ACK 穿越失效／新鮮度／socket 故障。原 C1＋相同合法內容查回原 M1；不得換 C1 隱藏不明結果。
3. **收件權威：** 只用交易內 `recipient_ids`／`observer_ids`／`deliveries`；開始交付前重查資源授權與本地閘門。W07 以 message-resource authorize 保護加入界線，不只查「目前是群組成員」。
4. **撤權局部性：** A03 只關相符 session 的舊世代；A04／A02 replaced 只關相符 session；A18 只排除該成員該對話的舊授權內容，保留最小自身 W12、較新合法內容與其他對話，不清空整條群組使用者連線。
5. **逐框閘門：** 位置連續才前進；早到紀錄可以先撤銷但不能跳過缺口。排隊時的許可不能替代 `send_str` 開始前的 validity／expiry／freshness／group exclusion 檢查。W01 最後檢查與註冊和 apply 共鎖。
6. **同步不擅改進度：** 完整驗證整頁／整批；讀取後重新完整 catchup，再做目前 read／history authorize，最後排隊／寫入檢查。錯誤或過時回應不交付正文／H／next_cursor；BA 不保存、解碼、猜測或替前端推進游標。
7. **公開最小化：** private subject／session、service auth metadata、credentials、正文／SQL／signed URL 不進公共錯誤、log 或結果報告；C1 只給寄件者自己的裝置。W10 direct-only；W19 不等於全群已讀。

### 狀態與時間的真正意義

以下摘要服從[正式交付狀態表](../contracts/interface-contract.md#delivery-state-table)及[授權判定界線](../contracts/interface-contract.md#authorization-boundary)，不沿用「60 秒內仍可送」等舊假設。

| 狀態 | 可保留／可送 | 禁止／恢復條件 |
|---|---|---|
| 未驗證／未完成初始 catchup | W17 盡力回應；10 秒 admission deadline | 不成功 W02、不交付資料；可信 W01＋閘門完成才註冊 |
| fresh、valid | 業務經 BB 判定，逐框重查 | 事件 W 大於 applied_position 先補齊；不能先送再補 |
| 單事件補齊逾時 | 連線保留，其他仍符合閘門的框可送 | 丟棄該次即時交付；用 W15／W16 補回，不因這一事件 logout |
| BB 不可查但尚 fresh | 連線保留；撤銷前資料只有仍通過全部閘門才可能開始交付 | BB 操作失敗、新 W01 不成功；需新 authorize 的資料可能更早停止，不保證 fresh 期間一律可送 |
| authority_stale | 有效連線可 W04／W17 | 無資料、W02、成功業務結果；恢復先完整 catchup／apply，再重新授權 |
| 已套用 session R／到期／heartbeat timeout | 關閉受影響 transport、清 unsent queue | 不能維持舊連線；W17 不保證送達；其他裝置不全域登出 |
| A18 applied | 連線保留、最小自身 W12／其他對話可用 | 不送相符舊授權內容；重加入只容許較新／目前可讀內容 |
| invalidation cursor 過舊 | 標記失效並關閉所有本地連線，reset head | 不在保留原連線的狀態下跳到 head；新 W01 必須重新驗證 |

- **poll=5 秒、stale=15 秒、notice hold=1000 ms** 是標準設定／正確性邊界，非量測 SLO。freshness 是 BA 單調時鐘距「最近完整補齊的開始」，不是收到通知時間、最後一頁抵達時間或跨主機 wall-clock 差。catchup 必須到 `has_more:false` 才更新此依據；失敗不延長期限。`/health/ready` 本身會做 catchup，量測者須記錄這個副作用。
- **E1 的 15 秒** 限制「撤權提交後何時還能開始 socket write」，不是網路到達時間、W17到達時間或關線p95；已開始傳送的資料不能追回。真實PostgreSQL提交序／快照完整性仍須BB gate證明。DR-03／04只在實時16秒探測時觀察控制回覆及操作／同步拒絕，沒有直接量測stale轉換瞬間或舊排隊資料開始socket write的時間。
- **30／90 秒** 是心跳間隔／逾時設定；有效新 W03 延长 lifetime，nonce 不轉型、不重用，W04 精確 echo／correlation。expiry 也受 BA monotonic／Unix deadline 檢查；不能因 BB down 無限延長 token。
- **2 秒 HTTP／socket deadline、10 秒 admission deadline** 是 runtime 限制，不是端到端 RTO；事件補齊 hold 另為 ≤1000 ms。事件迴圈／OS 失去排程的 VM freeze 不是此本機測試已證明的即時界線。
- **SYNC_PAGE_LIMIT=100、BB scan≤1000、50 WSS／600 秒、正常呈現 p95≤2 秒、符合前提同步≤5 秒** 分別是規格或課程目標；本報告不把設定或單次 elapsed 當實測容量／p95。`INVALIDATION_RETENTION_SECONDS` 值仍待部署共同決定，至少不得短於最大 access-token lifetime。

## 3. 風險評分與 release 判定方法

**Severity 是失效未被正確隔離時的影響，不是發生機率。** 此处主觀工程尺度為 S5：未授權內容／credentials 洩漏、假持久化成功或正式資料不可恢復；S4：廣泛服務／同步不可用、正式身份語意錯誤；S3：局部連線／功能不可用但有正確恢復；S2：暫態即時／presence 降級且 feed 可復原；S1：不影響正式資料／授權的可診斷不便。相同 S 可因安全界線不同有不同 release priority。

- **P0**：安全／持久化／游標不變量未滿足即阻擋對應產品發佈，不能豁免為「有同步」。
- **P1**：正式發佈前必須完成依賴、部署、恢復及命名功能 gate；缺前提仍為 UNVERIFIED，不可用本機 PASS 簽掉。
- **P2**：允許契約内 recoverable local degradation（例即時通知漏送），但必須有明確恢復、可觀察錯誤及通過對應 gate；不等於可忽略失效。

**Occurrence：全部 UNKNOWN，沒有事故／運行時間／樣本資料集。Detection 只有可用訊號，未量化漏偵率。RPN：NOT CALCULATED，缺有效 O／D 輸入，不用主觀 S×任意分數造排行。** 第 4 節 gate 都是必要條件；嚴重度不是 PASS 證明。

## 4. BA 失效模式矩陣

各模式同時列原因、使用者／系統影響、偵測、隔離／恢復、owner、證據與完成條件。Txx 精確符號見第 5 節；DRxx 的新增執行狀態只見第 6 節。CODE／T 路徑是可追溯防護，不預設本輪跑過。

### 設定、身分、連線與依賴

| ID／嚴重度 | 原因及使用者／系統影響 | 偵測與降級 | 恢復／責任 | Trace、殘餘風險與 acceptance gate |
|---|---|---|---|---|
| **FM-01 S4/P1 設定缺失／非法／secret ref 不可讀** | 遺漏 required、URL／數值非法、secret 格式錯誤、owner／mode／掛載使程序無法讀取、兩個 service token 相同；BA 無法可信串接，使用者不能登入 | `Settings.from_env` 檢查可讀性及內容，不檢查可讀secret的owner／mode是否過度寬鬆；不可讀或內容非法時live可200、ready503 `CONFIG_MISSING`，W01不W02、不揭露值 | DO修正owner／mode／掛載／required並重啟；BA提供fail-closed診斷；QA重驗；可讀但過度開放的secret另依G-02做DO權限／隱私稽核 | [config.py](../../backend/realtime/src/hine_realtime/config.py)、T01。非法值／unreadable／same-token有CODE，沒有專屬執行證據；**gate：缺失／非法／不可讀逐類注入不得W02，修復且真catchup／subscription完成才ready200；過度寬鬆但可讀的secret不能用ready判安全**。不能以live取代ready |
| **FM-02 S5/P0 非允許 service caller** | 用 user credential／錯 BB credential 呼叫內部 provider，可能偽造 notice／查 presence | `provider` 在讀 body 之前 constant-time 比對 allowed api；401＋內部 C13 service layer | BA 拒絕；DO 私網／proxy 路由隔離與 secret 配對；BB 使用正確 caller；QA 負例 | [server.provider](../../backend/realtime/src/hine_realtime/server.py#L563)、T03。**gate：錯 caller＋畸形 body 仍先401、不得 PUBLISH／presence；公開 `/internal/*` 不可達**；真實網路 gate G-02 尚未驗 |
| **FM-03 S4/P0 C13 service failure 誤當 user logout** | BB service 401／缺 auth_layer／非 HINE 回覆；錯誤實作會登出有效使用者或誤成功 | `InternalClient.call` 靜態 log `internal_service_identity_failure`；已驗證 W17 dependency、不公開 details，不因此 logout；新 W01 無 W02並關未驗證 socket | DO／BB 修復 service identity；BA 恢復前先 catchup；FA／FB 不刷新逃避 service 故障；QA 分層 | [internal.py](../../backend/realtime/src/hine_realtime/internal.py)、T04、DR-05。**gate：service fault 保留有效 socket、control 可用、恢復同 session 可業務；真 user fault 僅關相符 binding**。真實部署 rotation 配對仍待 G-02 |
| **FM-04 S5/P0 無效／到期／錯 device／缺公開映射 W01** | JWT／binding 不合法、BB 缺 `user_id`，會造成冒名／private identity 洩漏 | `authenticate` 完整 access_result／expiry 驗證；不信 client subject/sender；無可信结果不 W02 | BB 修正正式 JWT／公開映射；FA／FB 過期走唯一驗證流程、新 WSS；BA 關未驗證連線 | [Runtime.authenticate](../../backend/realtime/src/hine_realtime/server.py#L423)、T05。**gate：各負例無 W02／資料、合法僅公開 user_id；真 JWT 簽章／issuer／audience gate G-01 未驗** |
| **FM-05 S3/P1 expiry／heartbeat／admission 超時** | client 停心跳、重 nonce、未 W01、token 到期；舊 transport／資源可能停留 | `Connection.lifetime`、`dispatch`；獨立於 BB availability，立即停止 unsent data；control echo 精確 | BA 清連線；FA 有效 token 重連＋W15，到期交 FB；QA 驗 deadline／nonce；DO 看 transport 數 | [server.py](../../backend/realtime/src/hine_realtime/server.py#L226)、T06。**gate：token expiry 即使 BB down 仍關、重 nonce 不延長 lifetime；heartbeat90／admission10 真配置時序另驗**。不能保證關線控制框到達 |
| **FM-06 S4/P1 BB 連線不可達／timeout／惡劣回覆** | socket拒絕、延遲、redirect、超大／非 JSON／非 HINE；user 操作與同步不可用 | connect／response 靜態 log；bounded HTTP／body；新 W01 dependency＋close，read無資料；write 若結果不明按 FM-12 | BB／DO 恢復私網服務；BA 完整 catchup後恢復，FA保留原C1／cursor；QA | [InternalClient.call](../../backend/realtime/src/hine_realtime/internal.py#L31)、T02、T07、T34、DR-03。**gate：不假 ACK／不放行 read，不把非 HINE401當撤銷；恢復有效 session可同cursor續讀**。非 HINE非200只可稱 dependency，不推定DB rollback |
| **FM-07 S5/P0 authority_stale** | poll連續失敗／完整catchup太久，最近完整開始超15秒；漏撤銷風險 | `Invalidations.fresh`、dispatch／dequeue／socket final gate；只W04／W17，拒W01，不清用戶身份假登出 | BA恢復先完整catchup／apply；BB提供一致失效頁；DO依賴告警；FA同cursor重試；QA測timebasis | [invalidation.py](../../backend/realtime/src/hine_realtime/invalidation.py#L23)、T08、T35、DR-03／04。**gate：標準5／15實時等待後無新資料／cursor，control可用，恢復先apply**。VM freeze與真DB提交15秒證明仍G-03／05 |
| **FM-08 S3/P2 newer-position notice 補齊hold逾時** | W>applied、BB不可查／慢；該次即時事件失去可證授權frontier | `gate` ≤1000ms嘗試，false不開始該次即時write；靜態catchup fail可診斷 | BA丟該live attempt、保持session；BB feed／FA W15補回；QA檢hold及event stable | [Invalidations.gate](../../backend/realtime/src/hine_realtime/invalidation.py#L113)、T20。**gate：逾時不得越frontier，不因事件關其他socket，後續W16找回**。T20覆蓋hold中A18隔離；專屬1000ms elapsed／完整recover不是已量測 |

### 失效紀錄、持久寫入與 Redis

| ID／嚴重度 | 原因及使用者／系統影響 | 偵測與降級 | 恢復／責任 | Trace、殘餘風險與 acceptance gate |
|---|---|---|---|---|
| **FM-09 S5/P0 lost／reordered／gapped invalidation** | logout通知失去、位置跳號、早到舊紀錄；若錯誤前進會漏撤銷或關新世代 | poll／delivery gate；early apply可關相符session，但frontier只連續前進；conflicting同position使fresh無效 | BB完整權威頁；BA補缺口、只關matching session/generation；QA交錯；FA新binding | [Invalidations._apply_locked／catchup](../../backend/realtime/src/hine_realtime/invalidation.py)、T09、T10、DR-04。**gate：lost logout最終補齊；跳號不建立fresh／W02；亂序結果一致、其他device保留**。真PG連續提交序尚G-03 |
| **FM-10 S4/P0 invalidation cursor 太舊／retention 不足** | BA斷太久、BB保留窗不足、position範圍錯；不能重建原session撤銷史 | `readSessionInvalidations CURSOR_INVALID`；先invalidate所有local socket、fresh無效，再head reset | BA不帶舊連線跳head；BB／DO決定保留≥最大token lifetime；FA全部重連W01／W15；QA | [Invalidations.catchup／register](../../backend/realtime/src/hine_realtime/invalidation.py)、T11。**gate：所有old連線失效在reset前、新W01重驗才通**。保留秒數仍待定且真資料清理未驗；不得簽G-03 |
| **FM-11 S5/P0 W01 validate／register race** | validate回p後r>p早到或在最後註冊間apply；bounded history被修剪 | 同lock最後fresh／matching newer known／historical coverage再註冊，不能只比applied_position | BA互斥／超時fail-closed；BB保留可重讀history；QA覆蓋兩種交錯 | [Invalidations.register](../../backend/realtime/src/hine_realtime/invalidation.py#L123)、T09。**gate：拒絕或立即關race binding且無r之後data；其他device正常**。history-floor re-read存在CODE，壓力下完整歷史race另需實驗 |
| **FM-12 S5/P0 rollback／uncertain write／malformed success** | DB已知rollback、commit後回覆斷線、200缺字段／錯UUID／不完整receipt；假ACK會把未確認當成功 | `write=True`區分 connector unavailable與可能送達後response failure；persisted_result／committed_result；known `PERSISTENCE_FAILED`、uncertain `OUTCOME_UNCONFIRMED`，不W06／W19／fanout | BB保證transaction atomic及canonical／C1；BA保守mapping；FA原intent／C1查回，不換鍵；QA | [send_message](../../backend/realtime/src/hine_realtime/server.py#L449)、[receipts](../../backend/realtime/src/hine_realtime/receipts.py)、T12、T23、DR-06。**gate：commit barrier前無ACK；rollback無正式列，uncertain不宣稱commit/rollback；恢復sameC1回同M1且one intent**。fixture不能證明PGdurability，G-01／04必驗 |
| **FM-13 S5/P0 ACK loss／duplicate C1／quota precedence** | 已提交W06丟失，client新C1重送或BA提前quota／authorize會重複／改錯誤順序 | BB canonical→auth→C1→僅new合法intent quota；BA結構／frame defense，stable M1；W06與W07無先後保證 | FA保留同C1＋原合法內容、新request event_id；BB same返回原M1／合法不同內容conflict；QA歷史／projection去重 | [Runtime.send_message](../../backend/realtime/src/hine_realtime/server.py#L449)、T13、DR-01／02／06。**gate：retry同M1，非法同C1先INVALID_ARGUMENT、合法不同IDEMPOTENCY_CONFLICT、same合法不consume quota，只有new合法RATE_LIMITED**。真DBunique／transaction與browser原子狀態G-01／04 |
| **FM-14 S2/P2 Redis process down／reset** | Redis退出／無持久重啟，Pub/Sub與completion markers消失；presence未知、live漏送 | realPING fail、subscription false、ready503；getDevicePresence unknown；confirmedBB commit仍可W06／W19（另須valid/fresh gate） | DO恢復Redis與private設定；BA重訂閱／PING／catchup；FA savedcursor W15；QA故障／恢復 | [Runtime.subscribe／publish／health](../../backend/realtime/src/hine_realtime/server.py)、T15、T24、DR-02。**gate：unknown非offline、ready503、已確認ACK不受publish error撤銷；恢復200需訂閱與catchup，missedM1由W16、sameC1不重寫**。marker重置可重播，不能宣稱Redis訊息durability |
| **FM-15 S2/P2 PUBLISH denial／lost PubSub／notice queue full** | ACL拒絕、無subscriber、發佈或收取中斷、bounded notice queue滿；接收者未即時見內容 | static `redis_publish_unavailable`／`redis_subscription_unavailable`／`notice_queue_full_sync_required`；`published:true`只代表PUBLISH不是交付 | BA不poison marker、不回滾confirmed result；BB可同notice重試；FA W15對帳；DO alert；QA | [Runtime.publish／subscribe](../../backend/realtime/src/hine_realtime/server.py#L324)、T15、T25、DR-02。**gate：denied後same notice重試可送，漏訊完整feed找回stable event且一份projection**。queue-full精確容量與真BB lostpublish仍G-04，不以單publisher成功率當user成功率 |
| **FM-16 S3/P0 repeated／changed notice_id** | 重試、重新用同UUID但內容變更、Redis marker loss；重複或錯意圖fanout | `PUBLISH_ONCE` hash相同no-republish、不同拒INVALID_ARGUMENT；localseen有界 | BB same notice_id內容不變，正式event_id穩定；BA不從marker推持久化；FA replay去重；DO容量 | [Runtime.publish／already_seen](../../backend/realtime/src/hine_realtime/server.py#L364)、T03。**gate：同ID同內容不重送、改內容拒絕；Redisreset仍可安全event去重**。Rediscompletion keys不過期、localseen4096／24h有限，長運行memory及reset重播未全面量測G-06 |

### 群組、回條與同步

| ID／嚴重度 | 原因及使用者／系統影響 | 偵測與降級 | 恢復／責任 | Trace、殘餘風險與 acceptance gate |
|---|---|---|---|---|
| **FM-17 S5/P0 A18 inflight／socket-lock race** | 舊authorize允許回覆延遲，A18分段僅送其他member、catchup hold或write lock後才套用；可能洩漏oldbody | `apply_group_removals`在queue／gate waits之前對removeduser套version；finalgroup_allows再查 | BA丟相符oldframe，不logout、不阻其他對話；BB正確source/member/version；FA處理minimalW12；QA交錯 | [server.py](../../backend/realtime/src/hine_realtime/server.py#L392)、T17～T20。**gate：allowed舊snapshot＋真鎖等待均無oldbody，最小W12／較新rejoin及otherdialog可用**。CODE／隔離歷史不是PG提交E1計時G-03 |
| **FM-18 S5/P0 lost A18／rejoin舊歷史** | A18丟失後rejoin，僅檢目前conversation member會讓上一membership M1洩漏 | W07 message-resource `authorize(receive)`，sync逐message read／conversation history；加入boundary归BB | BB新加入transaction記錄order_key；BA不猜／不cachemember權限；FA同cursor过滤續讀；QA | [write_loop](../../backend/realtime/src/hine_realtime/server.py#L165)、[SyncGuard](../../backend/realtime/src/hine_realtime/synchronization.py#L157)、T19、T31。**gate：lost notice/rejoin oldM1不可讀、newM1可讀、oldmarker不blackhole較新currentread**。正式join query与A19／A22G-03 |
| **FM-19 S4/P0 receipt亂序／造假／群組彙總** | W08在W09後、重報、不相關recipient、BB不完整／錯observer；UI可能read倒退／群組錯讀 | W19只用BB正式state／M1、changed；W10 direct-only、BBtime/event/observer、公眾actor | BB持久monotonic/no-op；BA完整result validation／無群組W10；FA monotonic合併、receipt不等於讀本文；QA | [receipts.py](../../backend/realtime/src/hine_realtime/receipts.py)、T21～T24。**gate：read不倒退、commit前無W19/W10、stableevent不重複、group個別W19且projection null／無aggregate**。正式DBreceipt与browser已讀條件G-01／04 |
| **FM-20 S5/P0 partial／expired bootstrap／snapshot tokens** | 頁面失敗、頁token過期、續頁混snapshot、malformedpage；提前H會永久跳內容 | pairednonnull opaque tokens、完整page／logicalitems驗證；不同snapshot拒；trustedBB SYNC_RESET_REQUIRED原碼 | BB一致snapshot與expiry／每頁auth；BA不安装H、不假造head；FA同snapshot全頁stage＋atomic switch才H，失敗discardstage；QA | [synchronization._bootstrap／handle](../../backend/realtime/src/hine_realtime/synchronization.py)、T26～T29、T38。**gate：部分／malformed不installH、snapshot不混、續頁撤權重新auth；expired按syncreset不logout**。expired page-token専項無本輪執行證據、FA真atomic未驗G-04 |
| **FM-21 S5/P0 opaque boundary／hidden gaps／cursor過期** | 解碼opaque、boundary混輪、把empty page當完成、scan超1000、錯把RESTcursor當sync | BAshape／requestedboundary相等、page/event≤configured100；BB opaqueauthority／has_more、QA檢前進；SYNC_RESET_REQUIRED不是sessionfault | BB安全scan／filter與expiredcursorreset；FA投影成功才保存next、has_more續同boundary；REST錯只重啟RESTquery | [synchronization._batch](../../backend/realtime/src/hine_realtime/synchronization.py#L125)、T27、T28、T29、T30。**gate：hidden空頁可安全前進；真正empty可不前進；has_more不能假完成；boundary mismatch不cursor**。BA無權驗opaque內部進度／1000scan，真BB及no-progress oracle G-04未驗 |
| **FM-22 S5/P0 sync read中／authorize後session或group revoke** | read開始時可讀、返回／排隊時已撤權；舊整批帶cursor若部分過濾會跳事件 | read後必新完整catchup，即使empty；request-start removed_versions、currentauthorize、dequeue／finalwrite再查 | BA拒整頁／整批不body/H/next；sessionrevoke清unsent／closebinding，group保留連線；FA同cursor重讀由BBfilter，otherdialog續走 | [SyncGuard／handle](../../backend/realtime/src/hine_realtime/synchronization.py#L150)、T31～T34、T36、T38。**gate：各交錯無oldbody／cursor、session只關binding、minimalselfW12及同cursorotherdialog仍能復原**。真DBsnapshot/sessionlockG-03 |
| **FM-23 S4/P0 stale queued sync／silent drop／無cursor progress** | 排隊後stale／groupversion變更／write lock等待、整批授權逾時；沉默丟棄使client等待或誤commit | SyncGuard correlation保留、stale dequeue／lock final發關聯dependency、不帶oldbody/cursor；2秒整組authorize deadline | BA不進度、不鎖重入；FA保留savedcursor、恢復再讀；BB不以不可見資料重發已失權body；QA timeout／retry | [Connection.write_loop](../../backend/realtime/src/hine_realtime/server.py#L165)、T34、T35。**gate：兩個末端都回原request相關W17而非W16、不保存cursor，恢復samecursor有合法batch；若transport已斷不宣稱W17送達**。真frontend無限empty/nonprogress防護需G-04 |
| **FM-24 S5/P0 public privacy／錯誤字段洩漏** | BB私人message/details／SQL、senderC1散給receiver、signedURL、actor或subject進sync；高基數log | Fault固定messages、safe retry delay；strictfeed/snapshot unions、sender-onlyC1、minimalownW12；QA負oracle | BA拋棄整malformedbatch不cursor、log只staticcategory；BB修正式output；FA不保存非法batch；DO審proxy/log；QA | [internal.py](../../backend/realtime/src/hine_realtime/internal.py)、[protocol.py](../../backend/realtime/src/hine_realtime/protocol.py)、T07、T14、T32、T37、T39。**gate：公開錯誤／runtime stdout與stderr／演練JSON無credentials/privateIDs/body/SQL/auth_layer；合法授權資料回應仍按契約攜帶正文；receiver無C1，selfW12無actor**。真proxyaccesslogs/browserstorage未驗G-02／04 |

### 資源、程序與部署邊界

| ID／嚴重度 | 原因及使用者／系統影響 | 偵測與降級 | 恢復／責任 | Trace、殘餘風險與 acceptance gate |
|---|---|---|---|---|
| **FM-25 S3/P1 slow consumer／frame／connection exhaustion** | 不讀socket、突發frame／大frame、握手占位；局部queue／CPU／memory壓力，可能拖全服務 | queue128／輸出限額／socket2s／frame65536／connections1000含pendinghandshakes、frame120/s burst240；overflow關該transport | BA局部cleanup、丟unsent由feed恢復；DO監測CPU/RSS／連線／ready；FA重連savedcursor；QA壓力 | [Connection.enqueue／websocket](../../backend/realtime/src/hine_realtime/server.py)、T16、T40。**gate：slow一條被隔離、其他sessioncontrol正常、frame非法不BBwrite；capacity不是configured1000即proved**。queue size以serialized string len計數，不能當精確RSS；真abuse／50WSS G-06 |
| **FM-26 S5/P0 metadata／memory pressure** | A18排除map過多、nonce fingerprints隨有效心跳累積、invalidation hints／Redis永久completion hashes增長；silenteviction會漏撤權，OOM可全程序死 | groupmap上限4096／connection達限fail-closedcleanup；known/pending10000、localseen4096有界；DO memory／Redispressure | BA不evict有效exclusion，resource-reconnect非logout；DO隔離容量／Redispolicy／restart，FAfreshW01/W15；BBauthority仍必需 | [apply_group_removal](../../backend/realtime/src/hine_realtime/server.py#L133)、[Invalidations](../../backend/realtime/src/hine_realtime/invalidation.py)、T20。**gate：metadataoverflow不能送protectedoldbody、其他session可用；longrun／OOM測試需G-06**。nonce無獨立countcap，tokenlifetime才限存留；Redishash不expire，不能稱所有metadata總量已bounded |
| **FM-27 S4/P1 BA SIGKILL／restart** | crash／OOM／部署restart，localqueue／bindings／subscription失去；所有WS斷線及ACKlost | 程序退出、oldWSclosed、live不可達；nativechildrestart後ready需Redis／subscription／catchup | DO重啟正確artifact／secret；BA新process不信舊bindings；FA有效tokenW01/W02後SAVEDcursorW15、sameC1查回 | [Runtime.start／stop](../../backend/realtime/src/hine_realtime/server.py#L286)、T25、DR-01。**gate：kill是真child、oldtransportclosed，重啟再auth、committedM1／stableevent回復、sameC1oneintent，分開ready／client-sync elapsed**。BBfixture不死，不能證PG／VM durabilityG-05 |
| **FM-28 S5/P1 single VM／disk／real DB failure** | VM失去網路／電源、filesystem滿／唯讀、PG crash／WAL／volume損壞；同host各服務共因故障，可有永久資料損失 | DO實際health、disk／IO／PGlogs／archive驗證；BA自身PG一律not_checked，BB依賴不可查按FM-06/12，不能fallback | DO修復host／storage，BB核驗transaction／schema／data，QA重播正式history/feed/C1；FA重連；需off-host可用archive | [架構部署／failure](../architecture/README.md#arch-deployment)、[部署手冊](../deployment/README.md)、G-05。**UNVERIFIED：沒有實際VM／磁碟／PG故障證據；gate必須在隔離真host／volume執行並核驗ACKedmessage、C1、feed**。單VM無HA，沒有宣稱RTO／RPO=0 |
| **FM-29 S5/P1 maintenance／backup restore／artifact rollback** | 混版本契約、secretowner失配、archive不可讀、activewriter restore、回到舊DB造成ACKeddata丟失／cursorinvalid | preflight與restore拒livewriters／缺archive／錯target；backup nooverwrite、archive list；deploy後健康不等DB一致 | DO停止writers／保護archive／明確destructiveconfirm／核schema再開；BB定migration與一致復原點；FA處理syncreset、sameC1；QA比復原前資料 | [backup script](../../infra/scripts/backup-postgres.sh)、[restore script](../../infra/scripts/restore-postgres.sh)、T41、G-05。**gate：實際restore到隔離existingDB、無writers、錯archivefail，不刪volume；rollback版本compatible、ACKed資料loss如實揭露**。safetests不是成功restore，DB舊備份損失不能用BAretry憑空恢復 |
| **FM-30 S3/P1 W18 coverage／presence誤用** | 期待W18聯絡在線事件，但現行未實作；把deviceonline推成foreground／delivered會誤報 | CODE僅internalgetDevicePresence localconnection；Redisdownunknown、activityunknown／valid_untilnull | BA／BB／FA按REQ-15補真實產品交接與驗收；QA區分W18缺口；不新增活動租約／群組回條 | [BA README](../../backend/realtime/README.md)、T42、DR-02。**UNVERIFIED PRODUCT COVERAGE：device查詢不能簽W18eventgate；REQ-15命名功能發佈前需真實W18或經共同流程批准範圍變更**。不以「範圍外活動」掩蓋W18仍在PRD |

## 5. 精確永久測試追溯

以下皆為現有符號，不是新跑測結果。`B`＝`test_realtime_boundaries.RealtimeBoundaryTests`、`R`＝`test_realtime_receipts.ReceiptBoundaryTests`、`S`＝`test_realtime_sync.SyncBoundaryTests`、`D`＝`test_realtime_delivery_gates.SyncDeliveryGateTests`。每個連結指向定義行；完整 qualified symbol 為「上述 module.Class＋表中 method」。所有 BA integration 使用真實 HTTP／WS／Redis與 test-only memory BB，部分刻意用縮短設定／barrier／真socketlock；不能把它們的 elapsed 當標準5／15／1000設定或DB驗收。

| Trace | 類別與精確 method（同格各符號都須獨立理解） |
|---|---|
| T01 | B.[test_missing_configuration_is_live_but_unready_and_auth_fails_closed](../../tests/integration/test_realtime_boundaries.py#L319) |
| T02 | B.[test_missing_bb_is_live_but_not_ready_despite_real_redis](../../tests/integration/test_realtime_boundaries.py#L547) |
| T03 | B.[test_notice_auth_precedes_body_validation_source_mapping_and_idempotence](../../tests/integration/test_realtime_boundaries.py#L406)；B.[test_user_credential_cannot_authenticate_internal_provider](../../tests/integration/test_realtime_boundaries.py#L624) |
| T04 | B.[test_service_identity_failure_does_not_logout_authenticated_client](../../tests/integration/test_realtime_boundaries.py#L377)；R.[test_c13_service_identity_keeps_socket_user_session_fault_closes_it](../../tests/integration/test_realtime_receipts.py#L270)；S.[test_current_read_c13_service_failure_is_not_logout](../../tests/integration/test_realtime_sync.py#L673) |
| T05 | B.[test_missing_public_mapping_and_invalid_access_never_emit_w02](../../tests/integration/test_realtime_boundaries.py#L494) |
| T06 | B.[test_token_expiry_closes_even_when_authority_polling_is_down](../../tests/integration/test_realtime_boundaries.py#L504)；B.[test_duplicate_nonce_does_not_complete_a_second_heartbeat](../../tests/integration/test_realtime_boundaries.py#L653) |
| T07 | B.[test_non_hine_and_invalid_retry_delay_do_not_leak_or_invent_success](../../tests/integration/test_realtime_boundaries.py#L609) |
| T08 | B.[test_stale_authority_keeps_heartbeat_but_suppresses_data_and_new_auth](../../tests/integration/test_realtime_boundaries.py#L460)；B.[test_freshness_is_rechecked_after_delayed_receive_authorization](../../tests/integration/test_realtime_boundaries.py#L692) |
| T09 | B.[test_out_of_order_logout_blocks_racing_auth_and_preserves_other_device](../../tests/integration/test_realtime_boundaries.py#L424)；B.[test_lost_logout_notice_is_caught_by_delivery_gate](../../tests/integration/test_realtime_boundaries.py#L448) |
| T10 | B.[test_refresh_invalidates_only_old_generation_not_new_session](../../tests/integration/test_realtime_boundaries.py#L514)；B.[test_invalidation_stream_jump_cannot_establish_freshness_or_auth](../../tests/integration/test_realtime_boundaries.py#L664) |
| T11 | B.[test_cursor_invalid_closes_every_local_session_before_reset](../../tests/integration/test_realtime_boundaries.py#L476) |
| T12 | B.[test_no_ack_or_fanout_before_commit_and_c1_is_sender_only](../../tests/integration/test_realtime_boundaries.py#L333)；B.[test_incomplete_persist_result_never_becomes_ack_or_fanout](../../tests/integration/test_realtime_boundaries.py#L395) |
| T13 | B.[test_bb_canonical_conflict_and_quota_errors_preserve_original_request](../../tests/integration/test_realtime_boundaries.py#L360)；B.[test_ba_does_not_apply_bb_product_burst_quota_to_valid_sends](../../tests/integration/test_realtime_boundaries.py#L644) |
| T14 | B.[test_both_sender_devices_get_sender_c1_and_stable_event_not_receiver_c1](../../tests/integration/test_realtime_boundaries.py#L630) |
| T15 | B.[test_failed_redis_publish_does_not_mark_notice_complete](../../tests/integration/test_realtime_boundaries.py#L557) |
| T16 | B.[test_bounded_output_closes_slow_recipient_without_blocking_other_session](../../tests/integration/test_realtime_boundaries.py#L671) |
| T17 | B.[test_consumed_fragmented_removal_blocks_allowed_inflight_group_message](../../tests/integration/test_realtime_boundaries.py#L767) |
| T18 | B.[test_group_removal_is_rechecked_after_socket_write_lock_wait](../../tests/integration/test_realtime_boundaries.py#L770) |
| T19 | B.[test_lost_removal_notice_and_rejoin_use_message_readability_not_current_conversation](../../tests/integration/test_realtime_boundaries.py#L773) |
| T20 | B.[test_removal_applies_before_its_notice_catchup_gate_finishes](../../tests/integration/test_realtime_boundaries.py#L793)；B.[test_removal_metadata_exhaustion_never_evicts_an_active_exclusion](../../tests/integration/test_realtime_boundaries.py#L820) |
| T21 | R.[test_read_then_received_keeps_read_status_and_original_message](../../tests/integration/test_realtime_receipts.py#L66)；R.[test_receipt_ack_and_status_wait_for_commit_barrier](../../tests/integration/test_realtime_receipts.py#L81) |
| T22 | R.[test_direct_projection_uses_bb_time_id_public_actor_and_exact_observers](../../tests/integration/test_realtime_receipts.py#L97)；R.[test_retry_stable_status_event_does_not_duplicate_w10](../../tests/integration/test_realtime_receipts.py#L148)；R.[test_group_receipts_ack_without_aggregate_status](../../tests/integration/test_realtime_receipts.py#L177) |
| T23 | R.[test_incomplete_and_malformed_write_results_never_ack_or_publish](../../tests/integration/test_realtime_receipts.py#L220)；R.[test_refused_writes_produce_sanitized_c13_faults_without_ack](../../tests/integration/test_realtime_receipts.py#L255) |
| T24 | R.[test_confirmed_ack_survives_actual_redis_publish_denial](../../tests/integration/test_realtime_receipts.py#L288) |
| T25 | S.[test_saved_cursor_recovers_offline_message_without_receiver_c1](../../tests/integration/test_realtime_sync.py#L190) |
| T26 | S.[test_bootstrap_pages_keep_snapshot_and_complete_sender_private_snapshots](../../tests/integration/test_realtime_sync.py#L210)；S.[test_bootstrap_request_tokens_are_paired_nonnull_and_opaque](../../tests/integration/test_realtime_sync.py#L251) |
| T27 | S.[test_response_snapshot_and_boundary_must_match_requested_opaque_value](../../tests/integration/test_realtime_sync.py#L363) |
| T28 | S.[test_expired_cursor_is_sync_reset_not_session_failure](../../tests/integration/test_realtime_sync.py#L291) |
| T29 | S.[test_malformed_bootstrap_rejects_whole_page_without_installable_cursor](../../tests/integration/test_realtime_sync.py#L302)；S.[test_malformed_feed_and_c13_do_not_close_healthy_session](../../tests/integration/test_realtime_sync.py#L336)；S.[test_page_logical_items_and_feed_events_obey_configured_limit](../../tests/integration/test_realtime_sync.py#L372) |
| T30 | S.[test_hidden_feed_positions_advance_and_boundary_replay_is_stateless](../../tests/integration/test_realtime_sync.py#L264) |
| T31 | S.[test_current_message_authorization_blocks_lost_notice_and_rejoin_old_history](../../tests/integration/test_realtime_sync.py#L453)；S.[test_old_removal_marker_does_not_blackhole_rejoined_current_read](../../tests/integration/test_realtime_sync.py#L473) |
| T32 | S.[test_minimal_own_removal_survives_without_history_permission](../../tests/integration/test_realtime_sync.py#L484)；S.[test_own_removal_with_old_body_taints_entire_response_not_just_one_event](../../tests/integration/test_realtime_sync.py#L499)；S.[test_minimal_own_removal_does_not_block_other_dialog_and_rejects_actor_leak](../../tests/integration/test_realtime_sync.py#L621) |
| T33 | S.[test_session_revoke_during_read_never_delivers_old_cursor_or_body](../../tests/integration/test_realtime_sync.py#L509)；S.[test_complete_catchup_after_empty_read_not_just_cached_freshness](../../tests/integration/test_realtime_sync.py#L525)；S.[test_failed_post_read_catchup_does_not_trust_previous_freshness](../../tests/integration/test_realtime_sync.py#L664) |
| T34 | S.[test_authorization_dependency_timeout_is_bounded_and_session_survives](../../tests/integration/test_realtime_sync.py#L533) |
| T35 | D.[test_stale_final_and_dequeue_gates_return_both_correlated_errors](../../tests/integration/test_realtime_delivery_gates.py#L9) |
| T36 | S.[test_group_removal_during_authority_read_rejects_old_body_then_same_cursor_filters](../../tests/integration/test_realtime_sync.py#L386)；S.[test_group_removal_during_allowed_authorization_discards_whole_batch](../../tests/integration/test_realtime_sync.py#L447)；S.[test_group_removal_after_authorization_while_waiting_write_lock_discards_cursor](../../tests/integration/test_realtime_sync.py#L450)；S.[test_session_revoke_during_allowed_read_authorization_prevents_old_cursor](../../tests/integration/test_realtime_sync.py#L743)；S.[test_session_revoke_after_authorization_at_write_lock_prevents_old_cursor](../../tests/integration/test_realtime_sync.py#L746) |
| T37 | S.[test_snapshot_image_file_union_is_complete_and_private_metadata_is_rejected](../../tests/integration/test_realtime_sync.py#L590)；S.[test_receiver_feed_c1_and_attachment_union_leaks_reject_entire_cursor](../../tests/integration/test_realtime_sync.py#L759) |
| T38 | S.[test_bootstrap_metadata_current_history_denial_does_not_logout_or_install_h](../../tests/integration/test_realtime_sync.py#L779)；S.[test_bootstrap_continuation_reauthorizes_frozen_snapshot_after_removal](../../tests/integration/test_realtime_sync.py#L796) |
| T39 | `test_protocol_tool.EvidenceTests.`[test_public_errors_reject_internal_auth_metadata_without_echoing_value](../../tests/e2e/test_protocol_tool.py#L140)；同類 [test_sync_boundary_change_or_invalid_event_never_saves_cursor](../../tests/e2e/test_protocol_tool.py#L96)。這是 QA oracle 測試，不是產品browser |
| T40 | B.[test_unsupported_event_and_structural_nulls_do_not_write_or_close_session](../../tests/integration/test_realtime_boundaries.py#L532)；R.[test_structurally_invalid_receipts_do_not_reach_write_authority](../../tests/integration/test_realtime_receipts.py#L187) |
| T41 | `test_operations.OperationsSafetyTests.`[test_restore_requires_destructive_flag_before_any_docker_call](../../infra/tests/test_operations.py#L83)；同類 [test_restore_rejects_missing_archive_even_with_confirmation](../../infra/tests/test_operations.py#L88)、[test_backup_does_not_overwrite_existing_output](../../infra/tests/test_operations.py#L93)、[test_down_rejects_volume_flags_before_production_prerequisites](../../infra/tests/test_operations.py#L100)。這是 safety regression，不是restore成功證據 |
| T42 | B.[test_presence_requires_api_credential_and_reports_actual_device](../../tests/integration/test_realtime_boundaries.py#L486) |

## 6. 新增 local 故障演練 DR-01～DR-06

**執行入口：** [runner](../../tests/faults/ba_fault_drill.py)、[安全／前提说明](../../tests/faults/README.md)。BA 用實際 `python -m hine_realtime` 子程序，Redis 為runner自建／自殺的loopback ephemeral process，BB僅重用 [AddonAuthority](../../tests/integration/receipt_sync_support.py) 與既有 integration helpers，持續存活於測試記憶體。不得連／kill operator Redis、productionBB、SSH／VM，不需要root，不讀真產品credentials。

| ID／scenario name | 實際故障種類／對應FM | 必須觀察的故障期→恢復期assertions | 本次結果／elapsed |
|---|---|---|---|
| DR-01 `BA_SIGKILL_RECOVERY` | actualprocess：只SIGKILL ownedBA；FM-13／27 | oldWSclose；新child重新W01/W02；SAVEDcursor找回同M1／stableevent；receiver無C1；原C1重試仍只有1筆fixtureintent | **PASS**；SIGKILL→ready **217.060ms**，啟動→ready215.203ms；ready後重新驗證兩端及同步5.966ms |
| DR-02 `REDIS_STOP_RESTART` | actualprocess：stopownedRedis＋同port無持久重啟／markerreset；FM-14～16／30 | ready503／presenceunknown；Redis down仍收到confirmedW06；receiver live數0；重啟訂閱數1、ready200／presenceonline；W16找回1筆原M1，原C1不新增intent | **PASS**；Redis重啟→ready **810.945ms**，停止→ready1159.048ms；ready後client sync2.210ms |
| DR-03 `BB_LINK_OUTAGE` | actualsocket：關forwarding listener及keepalive transport、BBmemory不死；FM-06／07 | 實際TCP拒絕；新W01無W02、既有W05無ACK／write；16秒探測heartbeat可用、sync／write回dependency且無cursor；恢復同session與savedcursor可用 | **PASS**；listener關閉→探測 **16001.643ms**；恢復listener→完整catchup ready11.739ms。不是停止舊資料write的起點量測 |
| DR-04 `LOST_LOGOUT_BB_OUTAGE` | actualsocket＋fixturelogout不送通知；FM-07／09 | fixture提交R後16秒探測：舊binding W05／W15拒絕、ACK數0；恢復catchup只關該binding；其他device保持並實際提交訊息 | **PASS**；fixtureR→探測 **16000.854ms**；恢復link→受撤銷binding關閉12.227ms；R→關閉16017.470ms。非PG提交／15秒交付界線證明 |
| DR-05 `C13_SERVICE_CREDENTIAL_FAILURE` | HTTPfixturefault：BB service／user 401，非物理BB crash；FM-03／24 | 錯inbound與outbound-as-inbound皆401、正確credential200；2次service401不誤登出、無新W02；恢復同binding heartbeat；1次user401只關該binding、其他device仍能提交 | **PASS**；含setup／cleanup全情境 **412.278ms**；WS錯誤未echo內部auth metadata |
| DR-06 `UNCERTAIN_WRITE_AND_ACK_RECOVERY` | actualsocket：丟已提交BBresponse；另在confirmedresponse barrier時abort client；knownrollback另為HTTPfixturefault；FM-12／13 | unknown回OUTCOME_UNCONFIRMED、無假W06；savedcursor與原C1找原M1；ACK-loss已確認BBresponse成功forward1次、已斷client無W06；2個原intent重試總量仍2；structuredPERSISTENCE_FAILED不ACK／新增write | **PASS**；client transport abort→重新驗證、兩端sync及原C1確認 **6.748ms**；含setup／cleanup全情境414.432ms。不是實際PGrollback或ACK packet-drop量測 |

### Evidence／timing 格式與發布規則

已發布runner實際產出的[公開JSON](evidence/backend-a-local-faults.json)，未改寫觀察值。格式：

- `schema_version:1`、UUID `run_id`、`started_utc`／`completed_utc`；`provenance.analysis_baseline`、實際`git_head`與14份relative`source_sha256`；實際`environment`為Linux x86_64、Python3.12.3、aiohttp3.14.3、redis-py8.1.0、Redis7.0.15。`scope`固定為`LOCAL_COMPONENT_WITH_TEST_BB`；HEAD不表示新runner／文件已提交或push。
- `scenarios`逐項 `id`、`name`、`status`、`checks`（觀察boolean／count／HTTPstatus）、`timings_ms`（具名實際monotonic elapsed）、`fault_kind`、`limits`。fixtureintent count只能稱testmemory count，不能稱PostgreSQL rows；不可只有「沒有throw」。
- 計時起止：DR-01 `kill_to_ready`在SIGKILL前起算、200ready後結束；`restart_to_ready`只含新程序啟動；client-sync起點在ready後重新auth之前。DR-02分別從停止／重啟Redis至ready，另記ready後W15。DR-03從listener關閉完成至16秒probe、從listener恢復之前至ready。DR-04從fixtureR建立之前至probe／關閉，另記恢復link至關閉。DR-06從abort client之前至重新驗證、兩端savedcursor同步及原C1确认。`scenario_including_setup_and_cleanup`包含完整setup／cleanup；單次數值不相加成p95／RTO／SLO。
- PASS只授予所有必要觀察成立的該localscenario；失敗必須非零且保存合法FAIL證據、靜態diagnostic；沒跑／未達前提不得PASS。CLI prereq／input失敗exit2，已執行assertion失敗exit1；既有output不可覆寫。
- stdout／stderr／JSON無rawuser/session/device/C1/M1/eventIDs、token／password／URIcredential、body／SQL／signedURL。`run_id`、sourcehash、固定scenarioID不是使用者識別。私有childlogs也不可提交；以staticcategories與必要counts代替。
- JSON與實際檔案hash／branch不相符時不能用該證據宣稱currentchanges通過。程式、test、evidence、doc的結論要同一scope；realDB／JWT／browser／VM／50WSS／HA明列未驗。

### 本輪 Review 與工具安全 smoke

- 矩陣／runner分別做獨立Review及scoped re-review，原有重要發現已修正；不以review取代執行證據。
- ACK-loss初版會等WS close handshake，實際診斷出2次`persistIfAbsent` response failure，其中一次是非預期的第二個authority timeout。修正為owned client transport立即abort、held200確實prepare／write_eof後才續行；同診斷修正後僅剩故意注入的1次failure，ACK-loss區間由2015.755ms降至19.434ms（診斷run，非上表最終run）。
- 另做throwaway safety smoke：缺Redis argument→exit2且全NOT_EXERCISED；既有output→exit2且bytes不變；檔案0600、無殘留private evidence temp；不屬BA child的ready200 listener **HTTP探測數0**；兩次獨立cancellation後 **owned children存活數0**、private temp directory已移除。沒有操作operator服務。診斷腳本非永久產品測試，結果不計入歷史119。
- runner Ruff通過；程序啟動保留Redis multicall symlink拼法；BA readiness前驗owned socket inode；cleanup逐次shield cancellation；JSON以同filesystem的private tempfile/fsync/atomic no-clobber link發布，不暴露空／半份最終檔案。

## 7. 可重跑命令

從repositoryroot操作。localdrill需Linux可讀`/proc`、已安裝依賴、Python3.12+及可執行本機Redis；下面的binary path由操作者提供。output須不存在且父目錄可寫；runner另建private0700dirs／0600secretfiles、randomports／prefix，只清理ownedPIDs。

```sh
mkdir -p .local
chmod 700 .local
.venv/bin/python tests/faults/ba_fault_drill.py \
  --redis-server /absolute/path/to/operator-provided/redis-server \
  --python .venv/bin/python \
  --output .local/backend-a-local-faults.json
```

若operator提供的Redis需額外dynamic-library path，只在此命令環境提供其真實 `LD_LIBRARY_PATH`，不hardcode專屬機器路徑。不執行 `FLUSHALL`、`killall`、systemRedis／Docker／VM故障。詳細CLI、安全退出及資源清理見runnerREADME；scope外或missingprereq必須停而非換fakeRedis／mockBA。

既有regression交接命令（指定一個獨立realRedis；需ACL管理权的T15/T24不得用production）如下，與新故障演練證據分開：

```sh
HINE_TEST_REDIS_URL=redis://127.0.0.1:6397/0 \
  PYTHONPATH=backend/realtime/src \
  .venv/bin/python -m unittest discover -s tests/integration -p 'test_realtime*.py'
.venv/bin/python -m unittest discover -s tests/e2e -p 'test_protocol_tool.py'
.venv/bin/python -m unittest discover -s infra/tests
```

6397是需操作者事先提供的隔離testservice示例，不是runnerRedisport、不保證此機器已有。明確testRedis不可用應fail；skip不是驗收success。不用過去119的數字替新run結果。

## 8. 真實產品／部署手動演練前提與嚴格門檻

### 必要輸入，不可用fixture代替

DO提供授權的**隔離**singleVM／Compose目標、可用Dockerdaemon、真TLS/private網路、artifact版本、secretowner／filemode、容量／磁碟布局及復原權限；BB提供實際APIimage／migration／schema／JWT／內部HTTP操作／transactionhooks／正式C1/feed/snapshot/session records；FA／FB提供實際單一Webartifact與有效testaccount流程；QA提供資料集與tool/browser版本、受保護配置。還需off-host私有archive與能驗證其可用性的restoretarget。沒有这些時結論是UNVERIFIED，不是測試沒錯所以PASS。現有來源只記錄缺Docker／VM／真BB／Web交付，本文沒有取得這些外部權限。

**每次演練記錄：** target為隔離環境的聲明、versions／SHA、故障控制point與ownedscope、正式commit／authorization／start-write觀察機制、before／during／after逐項assertions、私有原始資料位置、公開sanitizedcounts及monotonic起止；監測CPU/RAM/disk/IO而不輸出credentials／body／IDs。不得用跨主機UTC相減證15秒，需可關聯的測試控制時鐘／instrumentation及真DBcommit證明，不公開rawidentity。完成後關閉faulthook、復原隔離環境、檢查沒有殘留writer／proxy變更。

| Gate／owner | 可執行程序與必須通過的完成條件 | 目前判定 |
|---|---|---|
| **G-01 真實 BB commit／JWT／C1／receipt（BB＋BA＋QA，P0）** | 正式JWTvalid／expired／revoked／wrongdevice／mapping負例；真transactionbarrier驗無precommitW06/W19；knownrollback查訊息/C1/feed全無；提交後截回覆sameC1原M1且單一正式intent；receiptread單調／exactobserver/groupnoaggregate；A19在重載後查同M1／text/order。BB quota exhausted五案例含canonicalUnicode責任全驗 | UNVERIFIED；fixture不是正式資料庫 |
| **G-02 service identity／隱私／公開路由（DO＋BB＋BA＋QA，P0）** | 真Compose私網錯caller／service401／usersession401；外部 `/internal/*`／`/health/*`不公開、僅exactWSSroute；TLSupgrade含RFC6455accept；DO逐一稽核secret owner／mode與掛載，拒絕過度寬鬆但可讀的檔案（BA ready不驗此項）；publicerrors／proxy/app/log/metrics／evidence無privatebody/IDs/authmetadata；rotation失配→dependency不是logout，修復後有效session恢復 | UNVERIFIED；localHTTP不能簽TLS／realproxy |
| **G-03 real invalidation／group E1（BB＋BA＋QA，P0）** | 以真A03/A04/A02生成同transaction連續紀錄，攔通知／dropPubSub／斷BBlink，測fresh→stale→restore；同session多連線與otherdevice，W01兩種race、亂序／缺口／retentioncursorinvalid；真A18對話列鎖／joinorder界線、allowedresponse／socketlock／lostnotice／rejoin交錯；R提交後超15秒無開始oldwrite且已apply立即停，無假全球logout | UNVERIFIED；PG提交序／snapshot/locks與retention值仍需實測 |
| **G-04 feed／snapshot／frontend recovery（BB＋BA＋FA／FB＋QA，P0）** | 真多頁同snapshot、partial／expiredpage-token不得installH；hiddenpositions、1000scan、100eventpages、opaqueboundary綁定、真正empty與has_more前進；revokedread／stalequeue不body／cursor，同savedcursor恢復otherdialogs/minimalW12；對有has_more但反覆next_cursor不前進的故障不能宣稱完成／忙迴圈；browser投影／cursoratomic、pendingC1／receipt重載、stableevent去重、RESTcursor錯不觸發syncreset | UNVERIFIED；QA SQLite／protocoloracle不等於browser |
| **G-05 single VM／磁碟／PG／備份／版本復原（DO＋BB＋QA，P1）** | 隔離host依序BAcrash、Redisreset、PGstop/restart、真PG已提交回覆丟失、專用scratchvolume滿／唯讀、VMrestart／連線中斷；正式ACKedM1/C1/feed回復逐項核；privateoff-hostarchive真restore到隔離existingDB，不帶activewriters；schema／data／C1／feed／revocation核驗後才重開；artifactrollback須與migrationcompatible、secretowner正確；unrecoverable/backupgap如實列資料loss／實際時間，不聲稱HA | UNVERIFIED；不在正式VM填磁碟或刪volume；無RTO/RPO證明 |
| **G-06 resource／capacity（BA＋DO＋QA，P1）** | slowreader／frameburst／handshake占位／metadata極值／longnonce與completionhash／Redismemorypressure在隔離環境，其他有效連線可用且不漏撤權；依課程50users/50WSS/25rooms/600s真cadence，另50人group；記成功率、實際CPU/RAM、browser呈現p95與recovery前提。若未達≤2s／≤5s目標公開原因，不把ACK／小样本當呈現 | UNVERIFIED；drill不做50WSS或HA |
| **G-07 W18 product coverage（BA＋BB＋FA＋QA，P1）** | 交付PRD要求的可信W18／contactauthorization、deviceaggregation、Redisunknown與freshness；不冒充前景／receipt；或依共同變更流程經直接受影響者批准調整命名功能範圍後同步契約／tests／docs | UNVERIFIED；現行W18尚未實作，不虛構測例PASS |

### 真實部署可重跑入口及復原順序

參照[部署手冊](../deployment/README.md)，先提供真BBprovider／Webartifact與私有 `.env`／secrets；不寫不存在的image／workingtoken。下列入口是既有工具，不是本輪執行證據：

```sh
./infra/scripts/preflight.sh --local
./infra/scripts/preflight.sh --public
.venv/bin/python tests/load/protocol.py e2e --config .local/qa-users.json \
  --reconnect --state .local/qa-sync.sqlite
.venv/bin/python tests/load/protocol.py load --config .local/qa-users.json
```

QA配置由BB／QA按[負載工具說明](../../tests/load/README.md)填真實隔離endpoint／login-env，不將password／token寫命令或公開報告。preflight／load若前提不符必須失敗，不切fixture宣稱realproduct通過；browser另驗。

備份／還原只在DO明確授權的**隔離target**執行，這段是destructive手動演練，不是一般localdrill。選一個全新archive路徑並確保父目錄私有：

```sh
./infra/scripts/backup-postgres.sh --production /absolute/private/path/new-ba-drill.dump
./infra/scripts/stack.sh stop api realtime
./infra/scripts/restore-postgres.sh --production --confirm-destructive \
  /absolute/private/path/new-ba-drill.dump
```

1. 故障前保存正式成功ACK的驗證集合與cursor／意圖；archive含private資料不進Git，另有off-host復原副本。單次`pg_dump`不等於跨服務時間一致的DR保證。
2. 故障由DO只作用於隔離ownedcontainer／VM／scratchvolume。磁碟填滿／唯讀不可寫通用production命令；先確認mount與snapshot、停止新業務、預定移除fault與hostrecovery步驟。BB提供實際DBtransaction／connection fault控制，BA不直接操作正式DB。
3. restore工具要求existingexacttarget／安全名稱／zeroactiveclients，會拒絕api/realtime仍running；不要加down-volume旗標、不要drop其他DB，不以archive-list取代restore。
4. restore失敗維持writers停止，核驗target／transactionoutcome再處理；成功也先由BB／QA核schema/data/C1/feed與復原前ACK集合，DO核secret/route/readiness後才按部署手冊重開compatibleartifacts。
5. 從savedcursor重新auth／sync；cursor因較舊DBrestore不可用就按SYNC_RESET_REQUIRED完整snapshot。備份之後已ACK而archive未含的資料不能憑此恢復，必須記實際loss及處置；只有artifactrollback不能倒退DB掩蓋資料不一致。

## 9. 交付與 release 最終判定

- **分析完整：** FM-01～FM-30都有原因／影響／偵測／隔離／恢復／角色／嚴重度與必要gate；testtrace、localdrill及externalgates分層。不表示全部gate通過。
- **localdrill通過：** 上述run的DR-01～DR-06均PASS、exit0；14份sourcehash逐一吻合。這是6個本機代表性故障情境，不是30種模式全部實機驗收、更不是119种失效／coverage%。文件／runner／JSON的發佈以`feature/realtime-receipts-sync`的Git紀錄為準；JSON的`git_head`是演練時的基線提交，不是後續發佈提交。
- **產品／部署release：** G-01～G-07目前UNVERIFIED；只有對應P0或P1命名功能／部署驗收不能簽release-ready，這不否認既有BA模組交付或歷史119項結果。recoverableRedis/live漏送只有在正式feed恢復與privacy/invalidation gates成立時才是可接受降級。W18是特定產品scope未驗項，不概括宣稱BA所有功能未完成；真BB／browser／VM前提不能被文件或fixture消除。
- **沒有虛構統計：** O未知、D未量化、RPN不計；單次monotonicelapsed不是availability／RTO／p95／SLO；單VM沒有HA承諾。若有失敗公開fixeddiagnostic、affectedmode／gate及真實後果，不用mock／重試掩盖失敗。
