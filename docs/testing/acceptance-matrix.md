# HINE-IC-0.4 — 驗收矩陣

**狀態：** 2026-10-01 PM 規格維持；使用者已要求跨全部角色補完產品。下方列出本版驗收條件；[目前實作與實測證據](#current-product-evidence)區分真正本機產品、協定量測、瀏覽器與仍缺存取的正式 VM／GCS，不把工具或文件當通過。

各列先列主要負責角色，再列協作者。API 與事件連結直達共用契約中的對應登錄列。
本輪局部交叉審查的補充定位：[REQ-01／身分](#ac-r03)、[REQ-02／07／16 錯誤分流](#ac-r02)、[REQ-03 已知 ID 查詢](#ac-r07)、[REQ-09／15 欄位排序分頁與心跳](#ac-r05)、[REQ-06／07／09／12 本地保存](#ac-r06)、[REQ-13 附件](#ac-r04)、[REQ-12 條件群組回條](#ac-r08)、[REQ-02／16 內部驗證分層](#ac-r09)、[REQ-12／20 未讀數](#ac-r10)；已讀正反案例放在 [REQ-20 詳細驗收](#req-20-detail)。這些案例不新增 REQ ID、不代表已執行。

<a id="current-product-evidence"></a>
## 目前實作與實測證據

本輪 PR #6 的已發佈來源為 `feature/hine-first-integration`／
`315afd8a1242332c4091d20c8e45907f88e3da2c`，目標 `main`，尚未合併。
Review 修正在原 PR 的隔離 worktree `pr-6`；尚未 commit／push／resolve 遠端 Review。
既有315head的四個Actions jobs成功，不代表本輪新修正已有遠端CI。
下列 `fc9eb08`／`feature/product-integration`／312項與product-* JSON為前輪歷史證據，
不改寫來源SHA或冒稱全部已重跑。角色欄是契約權責，不以分工阻擋可達實作，
也不替組員簽核。

### PR #6 本輪修正與新證據

- [八項Review及source SHA256](evidence/pr6-review-remediation.json)：過期SyncCursor有界清理、invalidation contiguous-prefix retention、確認缺物件終止cleanup、原PUT/A21 attempt重試、A14唯一recipient拆包、聊天清單事件刷新、完整Unicode canonical DeviceID、queued A12單調metadata。每项均保留實際失敗前／修正後觀察，無新公開介面／假provider。
- 109 API／100 BA／36 QA／25 infra／63 Web＝**333項**；typecheck、production bundle、Ruff、actionlint、shell及生成表檢查通過。60秒真背景tick、1,000筆有界刪除、floor／空head／frontier lock、真三WSS全部W11／stable feed／冪等／byte拆包均已驗。
- 10個真native metadata案例涵蓋old2/new3反序role/title/members、queuedIDB、withdraw/rejoin/session refresh、direct-null、201群組detail eviction、summary-only title/roles與uncached snapshot replay；4個fresh opening案例及實際release A14兩人表單直接開composer通過。特定fresh-join route handoff保持原票據安全與route/epoch/owner隔離，不泛用重試。
- 固定/chats remote join／rename／remove／server未讀、2次burst refresh／max concurrent1、A11分頁20＋3／23唯一render及舊owner response拒絕通過。Python3.12／Unicode15.0.0全部1,112,064 scalars consumer＋exact fold比對、真未知拼法login DeviceID／IDB draft／原C1／實際reload通過。
- 新[真native PF08](evidence/pr6-native-restore.json)停止自建writers並pg_dump／atomic clone restore通過；真HTTP/WSS/PG restart smoke20項通過。20個real peer W05／原C1持久W06到production DOM＋rAF的sample p95 37.7ms、max42.3ms，**不是50user／正式VM SLO**。
- apex／www公開API與WSS升級實際均nginx404；www首頁驗證TLS200只證明既有入口。SDK實際ADC unavailable、無project/bucket/signing／SSH target與Edge/adb/Docker/gcloud；正式VM、GCS physical bytes/CORS、physical hidden/soft keyboard及正式效能/restore門檻仍未通過。

### 已觀察的本機產品證據

- Python3.12.3、PostgreSQL17.11（SCRAM）、aiohttp3.14.3、asyncpg0.31.0、
  PyJWT2.15.1、Redis7.0.15／redis-py8.1.0、Caddy2.6.2；皆為真正原生服務，
  不是 test-memory BB。API96、BA100（含23個 W18）、QA oracle36、infra25項通過。
- [PF01–PF08 完整證據](evidence/product-native-faults.json)：API／BA SIGKILL、
  真 PostgreSQL／Redis 停止／重啟、遺失已提交登出通知、遺失真寫入200回覆、
  真 SQL trigger rollback，以及停止寫入者後 pg_dump／單交易 pg_restore 到自建 clone。
  還原後逐表記錄、JWT／公開身分、已撤銷 session、原 M1／C1、read 回條和 feed 核對通過。
  PostgreSQL 過期權威狀態時既有有效 socket 只保留 W04／W17，不誤要求立即斷線；
  另以真正 API 發行及 SQL 保存的30秒 token 驗到期關線。
- [正式模式 migration gate](evidence/product-production-migration.json)：對自建空 schema，
  原容器命令會自行套用 DDL；切換後實際 `HINE_ENV=production` service 為 live200／ready503、
  不建立 tables；明確 `migrate` 記錄3個checksum後，同一 service 命令 ready200。
  這是 native正式模式，不是 Docker／VM啟動證據。正式容器不再自動遷移；
  操作者須備份／停止寫入者，再以 `stack.sh migrate` 明確執行。
- [一對一基線](evidence/product-direct-load.json)：50已認證 WSS持續600秒、
  25聊天室、每人120次／合計6,000次，6,000全部 ACK＋收件成功，無遺漏時槽。
  **協定 W07** p95＝78.974ms；單一 BA CPU平均2.607%／最大8.994%，RSS最大48,168,960bytes。
- [獨立50人群組](evidence/product-group-load.json)：50已認證 WSS持續600秒、
  6,000個 intent，294,000／294,000個 distinct recipient 觀察，寄件端原 C1＋持久 ACK均驗明；
  所有50人 A12／A19核對。最慢收件者協定扇出 p95＝73.387ms；
  單一 BA CPU平均15.263%／最大21.989%，RSS最大48,824,320bytes。群組不是一對一基線。
- [協定重連](evidence/product-protocol-reconnect.json)：3／3訊息確認、
  真事件流／保存游標重播去重，QA SQLite原子投影；首次協定復原23.188ms，
  另一次保存游標重播6.864ms。**SQLite不是瀏覽器 IndexedDB**。
- [量測環境／資料集](evidence/product-load-provenance.json)：自建開發主機 loopback、
  私有CA驗證的HTTPS／WSS，52測試帳戶；兩個負載窗口後26個一對一、1群組、
  12,001訊息、314,504 feed rows。群組窗口與自建 fault／隔離回歸共用同一主機；
  CPU是單一 BA、單核心100%基準，RSS不是整台 VM。此後新增瀏覽器驗收資料另計。
- Chrome154.0.8037.97已實際操作兩隔離帳戶註冊／登入、公開ID聯絡人／聊天、
  發送／收件呈現、實際 IndexedDB訊息＋游標、重新載入、767／768草稿、
  單一Web Lock阻擋第二分頁（沒有 auth／WSS請求）、登出仍持鎖及釋放後Cookie重新驗證。
  瀏覽器只對本機私有CA使用測試例外；curl另已驗證憑證鏈與hostname，不是公開VM TLS。
- 本輪 Web55個行為測試、typecheck與production build通過。真native W05跨會員界線、
  混合W16舊正文、舊於20筆的group read刷新案例均已由失敗轉通過；原241筆／12頁UI
  歷史丟失亦已修正，200筆有界保留仍呈現最早頁，跳最新重新A19取得head。
  實際群組資訊dialog、Escape／焦點返回／767尺寸、A12網路失敗保留聊天室均驗明；
  同工作階段重連交錯A19／A12不再卡住最新按鈕。
- 實際UI A06個人資料重載、角色變更／最後admin退出HTTP409、同profile換帳號與
  不可授權深連結不洩露前帳戶內容；真正IDB quota abort停止全部WSS且不切memory。
  Chromium native IME組字Enter無W05、解除後Ctrl+Enter送出；兩頁W14bootstrap已實跑。
  另在實際保存/W08後驗未開對話不W09、native dialog遮罩不W09、恢復連續可見後一次W09，
  自己的訊息不W09。此headless環境兩頁原生visibility都為visible，不能冒稱真隱藏分頁驗收。
- [完整Chrome／native browser證據](evidence/product-browser.json)：35個已觀察UI檢查、
  7個真正API／PG／WSS／IDB場景全部通過，並保存修正前失敗與最後source SHA256。
  真PG cursor expiry的兩個receipt recovery缺陷均已由失敗轉通過：不可存取首群組
  不阻擋其他群組；完整目前歷史缺少舊target會保存原read意圖為terminal blocked，
  不假造read確認，下一輪不再掃完整歷史。`loadHistory`等待同一個實際A19 single-flight，
  221筆own＋peer的完整native歷史、舊response／換socket、原生draft／anchor／abort亦已驗明。
  最後全套96＋100＋36＋25＋55＝**312項**通過；外部實機門檻仍如下，不冒稱正式release完成。

### 逐需求實作與證據界線

| REQ | 目前實作／已觀察 | 不能由此推論的驗收 |
| --- | --- | --- |
| 01 | `auth.py`／Session／W01–W02；真PG96項、實際UI註冊登入／可信公開ID | 特定組員批准 |
| 02 | A03／A04、持久失效、唯一認證佇列與Web Lock；PF05、實際鎖／登出／釋放重驗 | 所有正式網路交錯的15秒統計SLO |
| 03 | `profiles.py`／聯絡人／ProfilePage；真API、公開ID查詢確認 | 真GCS頭像位元組／零對話頭像雲端驗收 |
| 04 | 唯一direct pair／A11–A13、Web導覽；真PG與實際兩人UI | 額外公開搜尋／邀請功能 |
| 05 | A14–A18／版本／50人／最後admin／加入界線；真PG及50人群組 | 未批准的Title全域政策、正式VM群組驗收 |
| 06 | 原子訊息／feed／C1、W06／W07、Web投影；6,000基線、真UI及PF08 | 收到ACK即等同收件端已保存／已讀 |
| 07 | canonical／授權／C1／quota precedence、原intent保存；PF06／07、真PG | 不明結果盲目換C1／無限重試 |
| 08 | 單BA、Redis通知＋PG事件流、當前授權；PF04、兩個50WSS窗口 | 多實例HA或Redis訊息持久性 |
| 09 | frozen多頁W14／固定boundary W16／A19歷史；真PG＋協定重連 | 尚未逐環境實測的瀏覽器矩陣 |
| 10 | staged快照＋即時C1合併、投影／游標原子保存；Web repository／controller | 存在程式碼即代表所有瀏覽器交錯通過 |
| 11 | 每頁／每次授權、最小自身W12、撤權路由／新加入界線；真PG／BA回歸 | 遠端抹除已下載副本 |
| 12 | 持久單調回條、W08保存後／W09可見後、群組receipt null；PF08／真UI | 群組已讀彙總、所有裝置實機可見性 |
| 13 | 真GCS SDK簽章、create-only、固定generation/meta、A20–A22及Web傳輸 | 真bucket PUT／GET／412／內容核驗；缺真憑證 |
| 14 | 範圍外；保留W15／W16復原 | 活動／背景推播 |
| 15 | 私有op11 `readPresenceTargets`＋W18、multi-device／unknown；23回歸 | 應用前景／送達／已讀狀態 |
| 16 | C13分層、受控錯誤、無私密日誌／公開ID隔離；API／BA／QA回歸 | 完整雲端告警平台 |
| 17 | 真API／BA映像來源、Compose／Caddy／secret／migration／CI定義；native服務及配置驗證 | Docker映像實際建置／遠端Actions／正式VM部署 |
| 18 | 兩個獨立50WSS600秒窗口、逐dispatch／全49扇出／全50歷史 | **收件端呈現**p95≤2秒、正式VM容量、瀏覽器≤100則復原≤5秒 |
| 19 | 單React19.3／TS7／Bun1.4.2 Web、唯一768斷點；Chrome767／768觀察 | Edge desktop／實體Android Chrome |
| 20 | IME／草稿／錨點／V3可見性與500ms計時程式、真UI草稿／read | 實體軟鍵盤／方向矩陣、所有V3正反幾何 |
| 21 | 授權Router、replace初始化、Caddy路由允許清單；真TLS路由及UI鎖／重驗 | 公開VM／所有支援瀏覽器深連結矩陣 |
| 22 | 範圍外，不建立SW／推播金鑰／native app | 關閉網頁後通知 |

### 尚缺的外部實機輸入

目前Notion只有公開網域／既有VM描述，沒有本輪可用VM登入目標／授權、
GCP project／私有bucket／真簽章credential；環境未設GCS／GCP／VM、ADC不可用、
SSH未設定host或alias。需提供正式VM存取、DNS／TLS／防火牆授權、真GCS bucket及
簽章／物件操作權限和同源CORS；Edge與Android Chrome須可操作的真瀏覽器／裝置。
本機沒有可用Docker daemon；容器／VM／真GCS驗收不能假造。已有VM的使用者陳述
不被否定，缺的是本輪可用存取。單VM不承諾HA；O未知、D未量化、不算假RPN或RTO／RPO。


<a id="first-integration-cases"></a>
## 首輪一對一文字串接：共同確認與驗收

依[近期串接基線](../contracts/interface-contract.md#integration-baseline)核對下列情境，不要求先驗收整份矩陣。首輪 EntityID／text 限制與後端權威驗證責任已由 PM 正式確認；目前實作／執行結果見上方證據節，不冒充 FA／FB／BA／BB 全員簽核。本節仍是可重跑的驗收條件，不取消其他需求。

| 範圍／角色 | 操作與必要邊界 | 預期結果與須留存證據 |
|---|---|---|
| A01／A02／A05、W01／W02；FB／BB／FA／BA | 用不同瀏覽器設定檔或裝置登入兩個測試帳號，各完成 W01；另以無效權杖驗證 | A02.user_id＝A05.id＝W02.user_id，裝置／世代一致；不得把 subject_id 交給前端。無效驗證不回成功 W02；遵循既有 W17／關線規則 |
| A13、openChat；FB／BB／FA | 以另一帳號公開 ID 建立一對一，重複建立；由 FB 把回傳 conversation_id 交 FA | 同一雙人配對只有一個對話；一對一 title／membership_version 為 null；聊天導覽不開第二條 WSS |
| W03／W04、W05／W06／W07；FA／BA／BB | 各端心跳；送出文字；分別讓 W06 或 W07 先到寄件端 | 同連線 nonce／correlation_id 精確匹配；完整提交後才回 W06。寄件端依 C1／M1 合併，兩端呈現同一 M1 且不重複；sender_id 取可信身分 |
| W05 冪等與拒絕；FA／BA／BB | 同 C1／相同合法文字重送；同 C1／不同合法文字重送；以無權對話送出合法文字 | 合法且已授權後才比對 C1；相同 payload 回同 M1，不多寫訊息／事件；不同合法 payload 回 IDEMPOTENCY_CONFLICT。輸入非法先 INVALID_ARGUMENT；無權合法操作依既有拒絕，不回成功 ACK、不登出整個帳號 |
| text 空字串；BB／BA／QA | 在有效授權／工作階段下以 W05 傳送 `text:""`，另直接對 BB 持久化入口傳相同輸入 | BB 拒絕且不持久化訊息、C1 對應或事件流；BA 映射既有 W17 INVALID_ARGUMENT、關聯原 W05，不回成功 W06 |
| text 長度 1；BB／BA／QA | 以 W05 傳送 ASCII `text:"A"` | 長度驗證接受；仍須通過其他既有驗證，完整原子提交後才回成功 W06 |
| text 長度 4096；BB／BA／QA | 以 W05 傳送 4096 個 ASCII `"A"` | 長度上合法；仍須通過其他既有驗證與持久化條件 |
| text 長度 4097；BB／BA／QA | 以 W05 傳送 4097 個 ASCII `"A"`，另直接對 BB 持久化入口傳相同輸入 | BB 回 INVALID_ARGUMENT，不持久化訊息、C1 對應或事件流；BA 映射 W17 INVALID_ARGUMENT，不回成功 W06 |
| EntityID 長度 128；BB／QA | 有效認證下，以 128 個 ASCII `"a"` 作 A12／A19 conversation_id，該 ID 結構合法但不存在 | 長度上合法後才查資源，依既有契約回 NOT_FOUND；消費端保持 opaque。UUID／游標不套用該上限 |
| EntityID 長度 129；BB／QA | 對 A06（非 null avatar_attachment_id）、A07、A09、A10（user_id）、A12、A13、A14–A22 中實際接收 EntityID 的欄位／path，以及 BB 接收 EntityID 的 internal 操作送出 129 個 ASCII `"a"`；含陣列／巢狀 ID | BB 先 INVALID_ARGUMENT，不查資源／授權／C1；A06 不做 attachment lookup／authorization，A10 不查使用者／聯絡人狀態。output-only、UUID／DeviceID／OpaqueCursor 及範圍外 API 不套此例；publishCommitted 由 BB 發送前驗長度，不要求 BA 重算 |
| A06 null；BB／FB／QA | 在原授權條件下呼叫 A06，avatar_attachment_id 明確為 null；另比較省略該欄位 | null 仍依既有語意移除頭像，省略仍是不修改；不得因 EntityID 長度規則改變 null／omission 語意 |
| 權威責任與內容；FB／FA／BA／BB／QA | 不啟用前端長度預檢，經 BA 將結構合法的上述空字串／超長文字送往 BB；使用前後帶空白的合法 ASCII 文字核對保存與接收內容 | 文字長度最終由 BB 判定，BA 不另立權威計數規則；拒絕不能回成功 ACK。前端提示僅屬 UX，不要求重現後端算法；原訊息不自動 trim／normalization 或做其他轉換 |
| BB canonical 單位；BB／QA | JSON 解碼後的 EntityID／text 分別用 `"😀"` 及 `"e\u0301"` 核對 BB 的長度單位 | BB 的 Unicode code point 數分別為 1、2，原內容不改。只驗 BB，不要求 FA／FB／BA 計數一致，不按 bytes／code units／grapheme 計數 |
| W05 quota Case 1；BB／BA／QA | 產品 quota exhausted，以新 C1 傳 5000 ASCII text（非法 payload） | canonical validation 先回 INVALID_ARGUMENT，不判產品 quota，不持久化／C1→M1／成功 W06；不是 RATE_LIMITED |
| W05 quota Case 2；BB／BA／QA | quota exhausted，新 C1、合法 "Hello"、有效認證／授權且 C1 尚不存在 | BB 在 C1 後、持久化前回 RATE_LIMITED，不持久化、不建立 C1→M1、不回成功 W06；安全 retry_after_ms 依既有契約，BA 映射 W17 |
| W05 quota Case 3；BB／BA／QA | 已成功 C1=X、合法 "Hello" 得 M1；quota exhausted 時重送同 C1／相同合法 payload | existing_same／原 M1，不新增訊息／C1 映射／事件，不再判產品 quota，不改回 RATE_LIMITED；沿用原成功 ACK 行為 |
| W05 quota Case 4；BB／BA／QA | 已成功 C1=X、"Hello"；quota exhausted 時重送同 C1／不同合法 "World" | IDEMPOTENCY_CONFLICT，不進 message-send quota、不持久化或回成功 W06 |
| W05 quota Case 5；BB／BA／QA | 已成功 C1=X、"Hello"；quota exhausted 時重送同 C1／非法 5000 ASCII（另核對空字串） | INVALID_ARGUMENT，不進 C1 comparison／quota，不新增訊息／C1 映射／事件、不回成功 W06 |
| BB 通知生成；BB／QA | 建立／送出 RealtimeNotice 前核對自己產生或從已驗證正式資料取得的巢狀 EntityID；令 BB 端資料 canonical 非法 | BB 負責 ≤128 JSON 解碼後 Unicode code points；非法資料不得送 publishCommitted，不能把補驗責任交 BA |
| publishCommitted 接收；BA／BB／QA | 由已通過 service identity 驗證的 BB 送出結構合法通知；另送 required／型別／enum／UUID／source 不符的通知，及非允許 caller | 合法結構的 authenticated BB notice 長度視為 BB 已完成，BA 不重算／不因巢狀 EntityID >128 做 canonical 拒絕。結構錯誤 INVALID_ARGUMENT；服務身分不合法依原 UNAUTHENTICATED／C13；不宣稱通知成功即產品送達 |
| BA transport 與產品 quota；BA／BB／QA | 通過既有 connection/frame gate 後，核對 W05 是交給 BB 做 canonical／C1／產品 quota；另驗既有 connection/frame defense | BA 保留 transport/frame abuse protection，但不執行 W05 5/s burst10 產品 quota；唯一權威 BB。五個產品案例不因 BA 先判產品 quota 改錯誤；不新訂 transport 限值或防護行為 |
| A19 保存核對；FA／BB／QA | 以成功 ACK 的 M1 查歷史，重新載入後再查，並比較 text／order_key | 查到同一 M1 與原文字／排序鍵，不以即時 UI 顯示充當持久化證據；使用既有 REST 清單封套、授權與歷史游標 |
| 共同變更；直接受影響角色 | 若串接發現欄位／錯誤／工作值須改，依任務／PR 列出新舊差異、受影響端、同步修改與切換方式 | 提供方與受影響消費方共同確認；契約、範例、驗收與實作同改。只有文件時明列尚未產品驗證，不單方改線上格式 |

QA／PM 保存實際環境、瀏覽器與模組版本、命令／步驟、提交、成功與失敗觀察；在 Notion 逐項記錄，沒有執行結果的項目不勾選完成。Title 與群組、附件、回條、完整重連／同步另於相應輪確認及驗收，不能由本輪通過推論全部功能完成。

## 全部需求驗收索引


| 需求 | 主要負責角色／協作者 | 介面 | 驗收摘要 |
|---|---|---|---|
| <a id="req-01"></a>REQ-01 帳號驗證與登入身分 | [FB](../prd/frontend-b.md#fb-01) / [BB](../prd/backend-b.md#bb-01), [BA](../prd/backend-a.md#ba-01), [FA](../prd/frontend-a.md#fa-01), [QA](../prd/qa.md#qa-02) | [A01](../contracts/interface-contract.md#api-a01), [A02](../contracts/interface-contract.md#api-a02), [A05](../contracts/interface-contract.md#api-a05), [W01](../contracts/interface-contract.md#event-w01), [W02](../contracts/interface-contract.md#event-w02) | 首次裝置登入會綁定伺服器端裝置；A02、W02、A05 的公開使用者身分一致；內部 subject_id 僅留在伺服器端。補充：[AC-N11](#ac-n11)。 |
| <a id="req-02"></a>REQ-02 憑證更新與登出轉換 | [FB](../prd/frontend-b.md#fb-02) / [FA](../prd/frontend-a.md#fa-02), [BB](../prd/backend-b.md#bb-01), [BA](../prd/backend-a.md#ba-01), [QA](../prd/qa.md#qa-02) | [A03](../contracts/interface-contract.md#api-a03), [A04](../contracts/interface-contract.md#api-a04), [W01](../contracts/interface-contract.md#event-w01), [W02](../contracts/interface-contract.md#event-w02) | 更新憑證時關閉舊 WSS 並建立新連線；登出停止目前裝置的連線，不支援同一連線重新驗證。補充：[AC-N03](#ac-n03)～[AC-N08](#ac-n08)、[AC-N10](#ac-n10)、[AC-N11](#ac-n11)、[AC-N13](#ac-n13)～[AC-N17](#ac-n17)、[AC-N19](#ac-n19)～[AC-N24](#ac-n24)、[AC-N28](#ac-n28)。 |
| <a id="req-03"></a>REQ-03 個人資料、頭像與聯絡人 | [FB](../prd/frontend-b.md#fb-03) / [BB](../prd/backend-b.md#bb-02), [FA](../prd/frontend-a.md#fa-06), [DO](../prd/devops.md#do-02) | [A05](../contracts/interface-contract.md#api-a05)–[A10](../contracts/interface-contract.md#api-a10), [A20](../contracts/interface-contract.md#api-a20)–[A22](../contracts/interface-contract.md#api-a22) | 零對話帳號可上傳／指派／讀取頭像；聯絡人游標可在本機復原；不得超出政策揭露電子郵件或頭像。 |
| <a id="req-04"></a>REQ-04 一對一聊天導覽與建立 | [FB](../prd/frontend-b.md#fb-05) / [FA](../prd/frontend-a.md#fa-05), [BB](../prd/backend-b.md#bb-03) | [A11](../contracts/interface-contract.md#api-a11)–[A13](../contracts/interface-contract.md#api-a13) | 重複建立一對一聊天會回傳唯一的雙人對話；FB 導向 FA 聊天頁，不另建連線。 |
| <a id="req-05"></a>REQ-05 群組管理、權限與成員異動 | [BB](../prd/backend-b.md#bb-03) / [FB](../prd/frontend-b.md#fb-05), [BA](../prd/backend-a.md#ba-05), [FA](../prd/frontend-a.md#fa-05) | [A14](../contracts/interface-contract.md#api-a14)–[A18](../contracts/interface-contract.md#api-a18), [W11](../contracts/interface-contract.md#event-w11), [W12](../contracts/interface-contract.md#event-w12), [W20](../contracts/interface-contract.md#event-w20) | 群組最多 50 人（含管理員），僅 admin／member；建立者為 admin；最後一位 admin 不可移除、降級或退出。加入界線：新成員不得經 A19／W14／W16／A22 讀取加入前訊息，退出後重加入以新界線開始。事件對應固定為 A14/A16→W11、A15/A17→W20、A18→W12；拒絕未授權操作／內容。補充：[AC-N01](#ac-n01)、[AC-N02](#ac-n02)、[AC-N18](#ac-n18)。 |
| <a id="req-06"></a>REQ-06 文字訊息與持久化 ACK | [BA](../prd/backend-a.md#ba-03) / [BB](../prd/backend-b.md#bb-04), [FA](../prd/frontend-a.md#fa-03) | [W05](../contracts/interface-contract.md#event-w05)–[W07](../contracts/interface-contract.md#event-w07), [A19](../contracts/interface-contract.md#api-a19) | 完整交易完成後才送 ACK；傳送端與接收端收斂至同一 M1；訊息顯示於歷史記錄。 |
| <a id="req-07"></a>REQ-07 ACK 遺失、重試與去重 | [BB](../prd/backend-b.md#bb-04) / [BA](../prd/backend-a.md#ba-03), [FA](../prd/frontend-a.md#fa-03), [QA](../prd/qa.md#qa-04) | [W05](../contracts/interface-contract.md#event-w05)–[W07](../contracts/interface-contract.md#event-w07), [W17](../contracts/interface-contract.md#event-w17) | 已知回滾不回成功 ACK；ACK 遺失後以相同合法 C1／payload 重試回原 M1；同 C1／非法 payload 先 INVALID_ARGUMENT，通過驗證與授權的不同合法內容才衝突。補充：[首輪 Case A–C](#first-integration-cases)、[AC-N06](#ac-n06)。 |
| <a id="req-08"></a>REQ-08 即時廣播與漏送復原（單一 realtime 實例） | [BA](../prd/backend-a.md#ba-05) / [BB](../prd/backend-b.md#bb-04), [FA](../prd/frontend-a.md#fa-05), [DO](../prd/devops.md#do-01) | [W07](../contracts/interface-contract.md#event-w07), [W15](../contracts/interface-contract.md#event-w15), [W16](../contracts/interface-contract.md#event-w16) | 本版驗收環境為單一 `realtime` 實例；收件者的每條有效連線（多使用者、多裝置）各收到一次即時事件；重複通知只處理一次，亂序或跳號的失效紀錄補齊後才推進；遺失的 Pub/Sub 通知由事件流對帳（W15／W16）與失效紀錄輪詢補回；UI 只顯示一則訊息。補充案例：[AC-N01](#ac-n01)、[AC-N09](#ac-n09)、[AC-N12](#ac-n12)、[AC-N26](#ac-n26)。 |
| <a id="req-09"></a>REQ-09 首次登入、授權快照與歷史分離 | [BB](../prd/backend-b.md#bb-06) / [BA](../prd/backend-a.md#ba-06), [FA](../prd/frontend-a.md#fa-05), [QA](../prd/qa.md#qa-03) | [W13](../contracts/interface-contract.md#event-w13)–[W16](../contracts/interface-contract.md#event-w16), [A19](../contracts/interface-contract.md#api-a19) | 多頁且屬同一快照的啟動同步，只有完整投影後才安裝 H；H 時點約定的有界啟動同步範圍／目前狀態均有呈現，可取得 >H 事件流位置，較早且已授權的歷史由 A19 提供。群組新成員經 A19／W14／W16／A22 不得取得加入前訊息；重加入依新加入界線。補充：[AC-N16](#ac-n16)、[AC-N26](#ac-n26)。 |
| <a id="req-10"></a>REQ-10 快照切換與即時投影合併 | [FA](../prd/frontend-a.md#fa-05) / [BA](../prd/backend-a.md#ba-06), [BB](../prd/backend-b.md#bb-06) | [W07](../contracts/interface-contract.md#event-w07), [W13](../contracts/interface-contract.md#event-w13)–[W16](../contracts/interface-contract.md#event-w16) | 切換期間觀察到的 C1／事件須保留；候選游標只與投影以原子方式一同前進。 |
| <a id="req-11"></a>REQ-11 撤權過濾、自身通知與多群組同步 | [BB](../prd/backend-b.md#bb-03) / [BA](../prd/backend-a.md#ba-06), [FA](../prd/frontend-a.md#fa-05), [FB](../prd/frontend-b.md#fb-05) | [A18](../contracts/interface-contract.md#api-a18), [W12](../contracts/interface-contract.md#event-w12), [W16](../contracts/interface-contract.md#event-w16), [A19](../contracts/interface-contract.md#api-a19), [A22](../contracts/interface-contract.md#api-a22) | 移除後不提供未授權正文；自身最小 W12 可收取，其他已授權事件流列繼續取得。新成員不得經 A19／W14／W16／A22 取得加入前訊息，重加入以新界線開始。補充：[AC-N02](#ac-n02)、[AC-N18](#ac-n18)、[AC-N25](#ac-n25)、[AC-N26](#ac-n26)。 |
| <a id="req-12"></a>REQ-12 已送達／已讀回條狀態機 | [BB](../prd/backend-b.md#bb-05) / [BA](../prd/backend-a.md#ba-04), [FA](../prd/frontend-a.md#fa-04) | [W08](../contracts/interface-contract.md#event-w08)–[W10](../contracts/interface-contract.md#event-w10), [W19](../contracts/interface-contract.md#event-w19), [W16](../contracts/interface-contract.md#event-w16) | 持久化回條狀態具單調性，重連後可復原；收到訊息本身不會標記為已讀。 |
| <a id="req-13"></a>REQ-13 圖片、檔案與上傳授權 | [BB](../prd/backend-b.md#bb-07) / [FA](../prd/frontend-a.md#fa-06), [FB](../prd/frontend-b.md#fb-03), [DO](../prd/devops.md#do-02) | [A20](../contracts/interface-contract.md#api-a20)–[A22](../contracts/interface-contract.md#api-a22), [W05](../contracts/interface-contract.md#event-w05), [W07](../contracts/interface-contract.md#event-w07) | JPEG／PNG／PDF，單檔最多 10 MiB、檔名最多 255 個 Unicode 字元；上傳授權 10 分鐘，過期以 A20 建立新嘗試（無 A25）；下載授權 5 分鐘。就緒且已授權檔案可傳送／下載。 |
| <a id="req-14"></a>REQ-14 裝置活動狀態與背景推播（本版範圍外，保留同步復原） | [BB](../prd/backend-b.md#bb-08) / [FA](../prd/frontend-a.md#fa-07), [FB](../prd/frontend-b.md#fb-06), [BA](../prd/backend-a.md#ba-07), [DO](../prd/devops.md#do-02), [QA](../prd/qa.md#qa-02) | [W15](../contracts/interface-contract.md#event-w15), [W16](../contracts/interface-contract.md#event-w16) | 活動上報、裝置活動狀態與背景推播部分本版範圍外（2026-10-01 PM 決議）；保留 W15／W16 同步復原，不新增活動／推播驗收。 |
| <a id="req-15"></a>REQ-15 線上狀態與多裝置存活狀態 | [BA](../prd/backend-a.md#ba-02) / [FA](../prd/frontend-a.md#fa-01), [FB](../prd/frontend-b.md#fb-04), [BB](../prd/backend-b.md#bb-02), [QA](../prd/qa.md#qa-02) | [W03](../contracts/interface-contract.md#event-w03), [W04](../contracts/interface-contract.md#event-w04), [W18](../contracts/interface-contract.md#event-w18), [A08](../contracts/interface-contract.md#api-a08), [getDevicePresence](../contracts/interface-contract.md#internal-get-device-presence) | W03／W04 心跳逾時只關閉該連線；單一裝置中斷不會使同使用者其他裝置離線；W18 與 A08 回報使用者線上狀態，無法確認時標為 `unknown`。裝置前景／活動狀態（W21／W22、活動租約）本版範圍外；前端 Page Visibility 只用於已讀判定（[REQ-20](#req-20)），不是伺服器活動狀態。補充案例：[AC-N08](#ac-n08)、[AC-N17](#ac-n17)；[AC-N27](#ac-n27) 本版範圍外，僅供追溯。 |
| <a id="req-16"></a>REQ-16 統一錯誤與隱私保護 | [QA](../prd/qa.md#qa-05) / [BA](../prd/backend-a.md#ba-08), [BB](../prd/backend-b.md#bb-05), [FA](../prd/frontend-a.md#fa-01), [FB](../prd/frontend-b.md#fb-01), [DO](../prd/devops.md#do-04) | [W17](../contracts/interface-contract.md#event-w17), [A22](../contracts/interface-contract.md#api-a22) | 錯誤／關聯識別碼語意一致；不得洩漏憑證、簽署網址、正文、SQL 或私人使用者識別碼。補充案例：[AC-N03](#ac-n03)、[AC-N04](#ac-n04)、[AC-N10](#ac-n10)。 |
| <a id="req-17"></a>REQ-17 基礎設施、健康檢查與 CI 交付 | [DO](../prd/devops.md#do-01) / [BA](../prd/backend-a.md#ba-01), [BB](../prd/backend-b.md#bb-01), [QA](../prd/qa.md#qa-05) | 公開路由、內部健康檢查、[A01](../contracts/interface-contract.md#api-a01)、[W01](../contracts/interface-contract.md#event-w01)、GitHub Actions | 公開路由與私有健康檢查符合契約；相依項目／設定缺漏時就緒檢查失敗；GitHub Actions 為交付基線。 |
| <a id="req-18"></a>REQ-18 效能驗證與容量界線 | [QA](../prd/qa.md#qa-05) / PM, [BA](../prd/backend-a.md#ba-08), [BB](../prd/backend-b.md#bb-06), [DO](../prd/devops.md#do-05) | [W05](../contracts/interface-contract.md#event-w05)–[W16](../contracts/interface-contract.md#event-w16), [A19](../contracts/interface-contract.md#api-a19) | 課程基線：50 個測試使用者／50 條 WSS、25 個一對一聊天室，每使用者平均每 5 秒發 1 則 ≤1 KiB 文字訊息、持續 10 分鐘；另驗收一個 50 人群組，不混入基線。記錄 VM、資料集、網路、工具與版本，量測成功率、p95、CPU／RAM；目標送出至收件端呈現 p95 ≤2 秒，待補 ≤100 則時重連同步 ≤5 秒；數值為目標，未量測。 |
| <a id="req-19"></a>REQ-19 共用響應式 Web 頁面 | [FB](../prd/frontend-b.md#fb-07) / [FA](../prd/frontend-a.md#fa-08), [DO](../prd/devops.md#do-06), [QA](../prd/qa.md#qa-06) | [Web/RWD](../ui/web-rwd.md#web-rwd), UI 路由允許清單 | 單一 Web 專案與 SessionContext；唯一斷點為 768 CSS px：較窄時清單／聊天室分頁切換，較寬時雙欄；依 Chrome／Edge 桌面版與 Android Chrome 驗收，記錄實際版本。 |
| <a id="req-20"></a>REQ-20 響應式聊天互動與已讀狀態 | [FA](../prd/frontend-a.md#fa-08) / [FB](../prd/frontend-b.md#fb-07), [BA](../prd/backend-a.md#ba-04), [BB](../prd/backend-b.md#bb-05), [QA](../prd/qa.md#qa-06) | [Web/RWD](../ui/web-rwd.md#web-rwd), [A12](../contracts/interface-contract.md#api-a12), [A19](../contracts/interface-contract.md#api-a19), [W08](../contracts/interface-contract.md#event-w08), [W09](../contracts/interface-contract.md#event-w09) | 輸入／IME、草稿／C1、錨點與捲動依中央規格；已讀依 V3（50% 可見、連續 500 ms）；互動依 V4；瀏覽器為 Chrome／Edge 桌面版與 Android Chrome。 |
| <a id="req-21"></a>REQ-21 Web 深層連結與授權路由返回 | [FB](../prd/frontend-b.md#fb-07) / [DO](../prd/devops.md#do-06), [FA](../prd/frontend-a.md#fa-05), [BB](../prd/backend-b.md#bb-03), [QA](../prd/qa.md#qa-06) | [A12](../contracts/interface-contract.md#api-a12), [A13](../contracts/interface-contract.md#api-a13), `openChat`, `/api/v1`, `/ws/v1` | 列出的 UI 路由使用驗證守衛與授權後返回；只有這些 UI 路由回退至 Web 殼層；API/WSS 路徑絕不回退。 |
| <a id="req-22"></a>REQ-22 Web Push 政策範圍與驗收治理 | PM / [BB](../prd/backend-b.md#bb-08), [FB](../prd/frontend-b.md#fb-06), [DO](../prd/devops.md#do-02), [QA](../prd/qa.md#qa-06) | [A23](../contracts/interface-contract.md#api-a23), [A24](../contracts/interface-contract.md#api-a24) | Web Push 與原生推播本版範圍外（2026-10-01 PM 決議）；保留 ID，無推播驗收與金鑰要求。 |

## REQ-19–REQ-22 Web 詳細驗收

以下為 2026-10-01 PM 決議後的本版 Web 驗收條件；已實跑及仍未實跑的環境分列於上方證據節。

| 需求 | 負責角色 | 協作者 | 介面 | 前置條件 | 操作 | 預期結果 |
|---|---|---|---|---|---|---|
| <a id="req-19-detail"></a>REQ-19 共用響應式 Web 頁面 | [FB](../prd/frontend-b.md#fb-07) | [FA](../prd/frontend-a.md#fa-08), [DO](../prd/devops.md#do-06), [QA](../prd/qa.md#qa-06) | [Web/RWD](../ui/web-rwd.md#web-rwd); UI 路由允許清單；既有 REST/API 模型 | 共用單一 Web 建置與已授權 UI 路由；驗收瀏覽器為 Chrome／Edge 桌面版與 Android Chrome（記錄版本） | 以 768 CSS px 斷點檢視窄版與寬版頁面，並檢視路由／深層連結 | 小於 768 CSS px 清單／聊天室分頁切換，≥768 雙欄；共用工作階段/API/事件/模型契約不變。搜尋只篩選本機已載入項目，不呼叫 A07；仍有下一頁時標示篩選範圍。 |
| <a id="req-20-detail"></a>REQ-20 響應式聊天互動與已讀狀態 | [FA](../prd/frontend-a.md#fa-08) | [FB](../prd/frontend-b.md#fb-07), [BA](../prd/backend-a.md#ba-04), [BB](../prd/backend-b.md#bb-05), [QA](../prd/qa.md#qa-06) | [Web/RWD](../ui/web-rwd.md#web-rwd); [A12](../contracts/interface-contract.md#api-a12), [A19](../contracts/interface-contract.md#api-a19), [W08](../contracts/interface-contract.md#event-w08), [W09](../contracts/interface-contract.md#event-w09) | 已驗證的瀏覽器、作用中對話、已保存草稿／待送 C1／已讀錨點 | 操作鍵盤／軟鍵盤／IME 輸入、調整大小／方向、前載歷史，並改變訊息實際交集／可見性 | 實體與軟鍵盤規則均成立；草稿／C1 與 `message_id`＋偏移量保持；較舊歷史的錨定保持穩定；自動跟隨／已讀條件依已決議政策；W08 仍獨立。已讀依[已讀判定](../ui/web-rwd.md#rwd-read-rule)：**應判已讀（送一次 W09）**——(a) 一般訊息一半以上可見連續 500 ms；(b) 超長訊息：V 為 800×400、泡泡 200×1000，泡泡填滿 V 高度（`I = Imax = 80000`）連續 500 ms 即判已讀，但不代表已讀完全文；(c) 200% 縮放或虛擬鍵盤開啟時，在剩餘可視區符合同一門檻。**不得判已讀**——(d) 可見 400 ms 即捲離；(e) 滿 500 ms 前頁面隱藏，回來後須重新累計滿 500 ms；(f) 模態預覽覆蓋對話串期間；(g) 訊息被撰寫區、頂列或虛擬鍵盤遮住而低於門檻，例如同一 200×1000 泡泡只露出 160 px 高（`I ÷ Imax` = 40%）；(h) 只開啟對話串、只出現在清單摘要或只送 W08；(i) 自己的訊息。鍵盤類型無法判別時 Enter 換行、「送出」按鈕可見、Ctrl／⌘+Enter 送出，改變視窗寬度不改變此行為。新訊息提示不改變 `unread_count`。 |
| <a id="req-21-detail"></a>REQ-21 Web 深層連結與授權路由返回 | [FB](../prd/frontend-b.md#fb-07) | [DO](../prd/devops.md#do-06), [FA](../prd/frontend-a.md#fa-05), [BB](../prd/backend-b.md#bb-03), [QA](../prd/qa.md#qa-06) | UI 路由允許清單；`openChat`; [A12](../contracts/interface-contract.md#api-a12), [A13](../contracts/interface-contract.md#api-a13); `/api/v1`, `/ws/v1` | 登出與已驗證路由案例；已知 UI 路由命名空間 | 載入／重新整理各列出的深層連結、完成驗證、使用前進／返回導覽，並請求 API/WSS 路徑 | 只返回已授權 UI 路由；只有列出的 UI 路徑會進入 Web 殼層；API/WSS 路徑與錯誤仍由後端處理且不變。根路徑 `/`：初始化中只顯示載入狀態、不顯示受保護內容；判定未登入後以取代歷史紀錄方式到 `/login`；判定已登入後到 `/chats`；返回鍵不回到空白的 `/`。 |
| <a id="req-22-detail"></a>REQ-22 Web Push 政策範圍與驗收治理 | PM | [BB](../prd/backend-b.md#bb-08), [FB](../prd/frontend-b.md#fb-06), [DO](../prd/devops.md#do-02), [QA](../prd/qa.md#qa-06) | [A23](../contracts/interface-contract.md#api-a23)/[A24](../contracts/interface-contract.md#api-a24) | 本版決議明確排除 Web／原生推播 | 不建立瀏覽器訂閱、Service Worker、供應商或推播工作程序 | 本版範圍外（2026-10-01 PM 決議）；關閉網頁後不保證通知，核心服務不依賴推播金鑰。 |

<a id="候選通知與授權失效驗收案例待批准"></a>
<a id="notify-invalidation-cases"></a>
## 通知與授權失效驗收案例（2026-10-01 PM 決議）

以下案例依據[共用契約](../contracts/interface-contract.md#internal-notify-invalidation)及[交付與連線狀態表](../contracts/interface-contract.md#delivery-state-table)。它們是本版條件，不以某個元件測試通過推論整張正式部署矩陣通過。N18 為不採用的比較方案（G2 選 E1）；N26 為 E1 驗收。
- 通知遺失案例需要能攔截 `publishCommitted` 並丟棄 Redis Pub/Sub 訊息。
- 時間窗口案例需要能控制 `realtime` 實例的補齊時點。
- **本版驗收環境為單一 `realtime` 實例（與單一 `api`）。** 下列案例中的「節點」「X」都指這個實例，不需要也不應為了案例增加第二個實例。多使用者、多裝置，以及以測試客戶端模擬的「同一工作階段新舊連線」（重連或 A03 換線交接期間尚未關閉的舊連線；屬工作階段安全測試，不代表支援多個可操作分頁）仍須測試。

| 案例 | 相關 REQ | 前置條件 | 操作 | 預期結果 |
|---|---|---|---|---|
| <a id="ac-n01"></a>AC-N01 成員通知扇出（單一 realtime 實例、多裝置） | [REQ-05](#req-05)、[REQ-08](#req-08) | 群組 g1 的成員 u1、u3 與待加入的 u4 都連在同一 `realtime` 實例；u1 有兩台裝置各一條有效連線 | 管理員以 A16 加入 u4 | 呼叫端依 REST 回應更新畫面；u1 兩台裝置、u3、u4 的每條有效連線各收到一次 W11，`membership_version` 與事件流列相同，`event_id` 與 W16 重播相同；u4 之後以 A12 取得成員名單 |
| <a id="ac-n02"></a>AC-N02 群組通知遺失與撤權後新查詢 | [REQ-05](#req-05)、[REQ-11](#req-11) | 按 G3 推薦；u2 是 g1 成員且在線，攔截 publishCommitted 並丟棄 Pub/Sub | A18 移除 u2，之後 u1 在 g1 傳送訊息；u2 發起 A19／A22／W13／W15，另使用撤權前的啟動同步頁面權杖續頁 | u2 收不到撤權後才授權的訊息正文；g1 的 W05／W08／W09／A19／A22 沿用各自拒絕規則。新 W14 不含 g1；W16 過濾 g1 正文並保留最小自身 W12，其他對話繼續。續頁仍檢查當下授權，不能藉舊權杖回傳 g1 正文；若該快照不能繼續，依既有錯誤恢復、不安裝未完成 H。其餘成員經 W15 補回 W12；不因群組撤權關閉連線；本案不決定 G1 裝置副本或 G2 舊授權待送內容 |
| <a id="ac-n03"></a>AC-N03 A04 撤銷且通知遺失 | [REQ-02](#req-02)、[REQ-16](#req-16) | 單一 `realtime` 實例 X；裝置 d1 的同一工作階段由測試客戶端保留兩條連線：c2 為目前連線，c1 模擬重連／A03 換線交接期間尚未關閉的舊連線（工作階段安全測試，非多個可操作分頁）；d2 是同帳號另一台裝置；攔截 `publishCommitted` 並丟棄 Pub/Sub；後端 B 可連線 | d1 以 A04 登出（204）；之後他人傳訊息給此使用者，c2 送出 W05，c1 送出 W15 | (a) c2 的 W05 回 W17 `UNAUTHENTICATED`，不產生訊息，c2 被關閉；(b) `invalidation_position ≥ r` 的訊息不會送到 c1、c2；(c) X 在 `INVALIDATION_POLL_SECONDS` 加一次補齊時間內關閉 d1 的所有連線；(d) c1 的 W15 經工作階段檢查被拒，回 W17 `UNAUTHENTICATED`、不回任何 W16 資料，c1 被關閉（與 [AC-N16](#ac-n16) (2) 相同語義）；(e) d2 的連線持續正常收發 |
| <a id="ac-n04"></a>AC-N04 A04 撤銷且後端 B 不可連線 | [REQ-02](#req-02)、[REQ-16](#req-16) | 與 AC-N03 相同的連線配置（單一 `realtime` 實例 X、d1 的 c1／c2、d2），但 A04 提交後 X 無法連到後端 B | d1 以 A04 登出（204）；之後 c2 送 W05、c1 送 W15；另以新連線送 W01；最後恢復後端 B | (a) 需補齊的事件一律不交付；(b) X 仍新鮮時，c2 的 W05、c1 的 W15 這類經後端 B 的操作回錯誤、不回成功，新 W01 被拒（[狀態表](../contracts/interface-contract.md#delivery-state-table)第 6 列）；(c) 最後一次完整補齊開始後超過 `S`，X 對所有連線只送 W04 與 W17，不送 W18、回應或任何資料，新 W01 回 W17 `DEPENDENCY_UNAVAILABLE`（第 7 列）；(d) 連線保留，最遲在存取權杖到期時關閉；(e) 後端 B 恢復後，X 先完整補齊並關閉 d1 的連線，其他連線再恢復交付（第 8 列） |
| <a id="ac-n05"></a>AC-N05 A03 新世代連線建立後，舊通知才到達 | [REQ-02](#req-02) | d1 以世代 g 連線 | A03 把世代更新為 g+1，FA 建立新連線 c'；之後才讓 `min_valid_generation = g+1` 的通知到達 `realtime` 實例，並再送達一筆更早、`min_valid_generation = g` 的紀錄 | c' 保持連線並正常收發；世代 g 的連線失效並關閉；較早的紀錄不改變任何連線 |
| <a id="ac-n06"></a>AC-N06 A03 期間舊連線的在途傳送 | [REQ-02](#req-02)、[REQ-07](#req-07) | A03 已提交，FA 尚未停止舊連線上的業務訊框 | 舊連線送出 W05（C1） | 回 W17 `UNAUTHENTICATED`；FA 不再觸發第二次更新，改在新連線以同一 C1 重送；最後只有一筆 M1 |
| <a id="ac-n07"></a>AC-N07 W01 註冊競態 | [REQ-02](#req-02) | 一個 W01 已通過 `validateAccess`（回傳位置 `p`），之後 A04 以位置 `r > p` 提交 | 兩種交錯：(1) `realtime` 實例 X 在註冊前已提早套用 `r`，但 `applied_position` 因缺少中間紀錄尚未推進到 `r`；(2) `r` 在 X 的最後檢查與註冊之間到達 | (1) 該連線在最後檢查時被拒；(2) 該連線在最後檢查時被拒，或在 `r` 套用時被關閉；兩種情況都收不到 `invalidation_position ≥ r` 的資料 |
| <a id="ac-n08"></a>AC-N08 同工作階段多連線與其他裝置 | [REQ-02](#req-02)、[REQ-15](#req-15) | 單一 `realtime` 實例；測試客戶端為 d1 的同一工作階段保留兩條連線（模擬重連交接期間的新舊連線，非多個可操作分頁）；d2 有一條連線 | 分別執行 d1 的 A04、d1 的 A03，以及 A18 移除此使用者 | A04 關閉 d1 的兩條連線，d2 不受影響；A03 只關閉 d1 的舊世代連線；A18 不關閉任何連線，只影響 g1 |
| <a id="ac-n09"></a>AC-N09 重複、亂序與過舊位置 | [REQ-08](#req-08) | 單一 `realtime` 實例；測試可注入通知與失效紀錄 | (1) 重送同一 `notice_id`；(2) 以相反順序送達兩筆失效紀錄；(3) 送達一筆位置跳號的紀錄；(4) 節點的已套用位置早於保留範圍 | (1) 同一通知只處理一次；(2) 最終連線狀態與依序處理相同；(3) `applied_position` 只在補齊中間紀錄後才推進；(4) `readSessionInvalidations` 回 `CURSOR_INVALID`，該實例關閉所有本地連線並從最新位置重新開始 |
| <a id="ac-n10"></a>AC-N10 權威工作階段／授權資料不可查 | [REQ-02](#req-02)、[REQ-16](#req-16) | PostgreSQL 或後端 B 無法使用 | 新連線送 W01；既有連線送 W05、W13、W15 | W01 回 W17 `DEPENDENCY_UNAVAILABLE`（可重試）並關閉；W05 不回成功；W13、W15 不回資料；不因無法查詢而假定仍有權 |
| <a id="ac-n11"></a>AC-N11 同裝置重新登入後登出 | [REQ-01](#req-01)、[REQ-02](#req-02) | d1 以工作階段 s1 連線；d2 是同帳號另一台裝置 | d1 再次 A02 取得 s2 並以 s2 連線；之後 d1 以 s2 呼叫 A04 | A02 提交時 s1 被撤銷（`reason:"replaced"`），s1 的連線被拒絕新操作、收不到之後的資料並被關閉；A04 後 d1 沒有任何有效工作階段或連線；d2 不受影響 |
| <a id="ac-n12"></a>AC-N12 補齊逾時 | [REQ-08](#req-08) | `realtime` 實例 X 的已套用位置為 `p`；後端 B 對 X 暫時不可連線，但 X 仍新鮮 | 一則 `W = p+3` 的訊息通知到達 X | 經 `NOTICE_CATCHUP_HOLD_MS` 後，X 放棄這則通知在 X 的即時交付；X 上的連線保留，其他訊框照常；收件者之後經 W15／W16 取得該訊息；沒有連線因此被關閉 |
| <a id="ac-n13"></a>AC-N13 撤銷前資料在撤銷後才開始交付 | [REQ-02](#req-02) | d1 的連線 c1 在`realtime` 實例 X，X 新鮮；給此使用者的訊息 E 的 `W < r` | E 排入 c1 佇列；A04 提交（`r`），通知被攔截；X 尚未套用 `r` 時，E 開始交付 | E 可以送達 c1（D2）。X 套用 `r` 後，c1 被關閉，佇列中尚未開始交付的訊框被丟棄。在 `T_R + S` 之後才開始的交付，都不會送到 c1 |
| <a id="ac-n14"></a>AC-N14 撤銷前資料排隊中，節點先套用撤銷 | [REQ-02](#req-02) | 同 AC-N13 | E 排入 c1 佇列、尚未開始交付時，X 經輪詢或通知先套用 `r` | E 不送達 c1；c1 被關閉；同一使用者其他裝置連線上的 E 照常交付 |
| <a id="ac-n15"></a>AC-N15 並行交易 | [REQ-02](#req-02) | A04 與一筆給此使用者的訊息交易 E 並行 | 情況 (1)：E 讀取計數器時 A04 尚未提交（`W < r`），但 E 在 A04 之後才提交。情況 (2)：E 讀取計數器時 A04 已提交（`W ≥ r`） | (1) E 屬撤銷前資料，依 AC-N13、AC-N14 處理；(2) E 永不送到 d1 的連線：節點遇到 `W ≥ r` 時先補齊 `r`，相符的連線已標記失效 |
| <a id="ac-n16"></a>AC-N16 W14／W16 回應與撤銷交錯 | [REQ-02](#req-02)、[REQ-09](#req-09) | c1 在`realtime` 實例 X | (1) c1 送 W15，`readFeed` 的快照早於 `r`，回應在 `T_R` 之後才抵達 X；(2) `T_R` 之後 c1 再送 W15；(3) W14 第 1 頁在 `r` 之前取得，第 2 頁請求在 `T_R` 之後送出 | (1) 依 D2：X 尚未套用 `r` 且新鮮時可交付，已套用則丟棄；(2) 回 W17 `UNAUTHENTICATED`，c1 被關閉；(3) 第 2 頁被拒，用戶端不安裝 `start_cursor` |
| <a id="ac-n17"></a>AC-N17 W18 與撤銷 | [REQ-02](#req-02)、[REQ-15](#req-15) | c1 在`realtime` 實例 X；此使用者聯絡人的上線狀態持續變化 | A04 提交後，攔截通知，並讓 X 暫停補齊 | X 套用 `r` 前，c1 仍可能收到 W18；X 套用 `r` 或變成不新鮮之後不再送出；在 `T_R + S` 之後才開始交付的 W18 都不會送到 c1 |
| <a id="ac-n18"></a>AC-N18 群組舊授權內容：非 E1 比較方案 | [REQ-05](#req-05)、[REQ-11](#req-11) | G2 採 E1 | — | 非 E1 比較方案不採用（2026-10-01 PM 決議）；依 [AC-N26](#ac-n26) 驗收 E1 界線。 |
| <a id="ac-n19"></a>AC-N19 單一可操作分頁：鎖定 | [REQ-02](#req-02) | T1、T2 同來源瀏覽器設定檔；T1 已取得並持有獨占 Web Lock `hine-session` | 開啟 T2 | T2 顯示「聊天已在另一個分頁開啟」，不登入、不刷新、不建立 WSS。 |
| <a id="ac-n20"></a>AC-N20 鎖釋放後重新驗證 | [REQ-02](#req-02) | T1 持鎖且已登入；T2 被阻擋 | 關閉 T1，待鎖釋放後由 T2 取得鎖 | T2 重新取得／驗證工作階段（A03 Cookie 可取得新 AccessSession，否則要求登入）後才啟動聊天；不讀取跨分頁紀元、不搶鎖。 |
| <a id="ac-n21"></a>AC-N21 鎖持有期間登出 | [REQ-02](#req-02) | T1 持有鎖並已登入，T2 顯示阻擋訊息 | T1 呼叫 A04 登出 | T1 停止 WSS 並清除本機認證狀態；T2 仍不啟動聊天，直至 T1 關閉並釋放鎖。 |
| <a id="ac-n22"></a>AC-N22 新分頁等待鎖 | [REQ-02](#req-02) | T1 持鎖；T2 未取得鎖 | T1 結束，T2 取得鎖 | T2 重新驗證工作階段後才建立一條 WSS；沒有跨分頁訊息或每分頁連線。 |
| <a id="ac-n23"></a>AC-N23 A03 結果不明的簡化恢復 | [REQ-02](#req-02) | 單操作分頁已發起一次正常 A03 | A03 結果逾 10 秒仍不明、回 401 或刷新失敗；另測 `RATE_LIMITED` 有效／省略或無效 `retry_after_ms` | 停止 WSS／自動刷新、清除本機可用認證並提示重新登入；舊 Cookie 寬限 0 秒、不重播舊請求。有效 `retry_after_ms` 到期後最多再自動嘗試一次；省略／無效則停止自動刷新，由使用者手動操作；不無限重試，網路／伺服器錯誤不顯示為密碼錯誤。 |
| <a id="ac-n24"></a>AC-N24 鎖定後重新登入或換帳號 | [REQ-01](#req-01)、[REQ-02](#req-02) | T1 持鎖並登入帳號 A；T2 被阻擋 | T1 登出／結束並釋放鎖；T2 取得鎖後以帳號 A 或 B 登入 | T2 僅在持鎖後登入；依新帳號初始化其工作階段與本機資料分區，不沿用前帳號內容；無跨分頁 epoch。 |
| <a id="ac-n25"></a>AC-N25 裝置已取得的群組內容 | [REQ-05](#req-05)、[REQ-11](#req-11) | 按 G1 決議；u2 的 d1、離線 d2 已取得 g1 訊息 | A18 移除 u2；d1 得知 A18 成功或自身 W12，d2 尚未同步 | d1 離開不可存取的對話畫面，不新增退出後唯讀頁；不把本機已有副本或匯出檔案宣稱為已遠端抹除。d2 得知撤權前可能仍顯示舊副本，得知後同樣退出；遲到內容不重新打開被移除的路由。新查詢按 G3，與 G2 待送內容上限分開驗收 |
| <a id="ac-n26"></a>AC-N26 E1 群組待送內容界線 | [REQ-08](#req-08)、[REQ-09](#req-09)、[REQ-11](#req-11) | G2 採 E1；E 與讀取回應授權點早於 A18；A18 於 T_R 提交，S＝15 秒 | 攔截通知並交錯撤權套用前／後及 T_R+15 秒後開始交付；另令已交網路訊框延遲 | 套用撤權即停止舊內容開始交付；最遲提交後 15 秒不再開始。這是開始交付界線，非抵達期限，不能追回已送出資料；單一 realtime 實例驗收。W14／W16 過濾結果不得推進未完成游標／安裝 H，依既有同步恢復。 |
| <a id="ac-n27"></a>AC-N27 活動合併（本版範圍外） | [REQ-14](#req-14)、[REQ-15](#req-15) | 活動租約及前景／背景活動推播本版範圍外（2026-10-01 PM 決議） | 不執行活動合併或 W21／W22 背景／unknown 收件者測試 | 本版範圍外（2026-10-01 PM 決議）；心跳、斷線重連、前景同步及實際可見才已讀仍保留。 |
| <a id="ac-n28"></a>AC-N28 必要瀏覽器能力缺少 | [REQ-02](#req-02)、[REQ-19](#req-19) | Chrome／Edge 桌面版或 Android Chrome；分別缺 Web Locks、Page Visibility、Cookie／本機儲存、WebSocket 或非安全環境 | 開啟登入或執行中令必要能力不可用 | 顯示不支援／阻擋原因，不啟用聊天；停止自動刷新與 WSS。必要能力含 HTTPS、同來源、Cookie、本機儲存、WebSocket、Page Visibility、Web Locks；不要求 BroadcastChannel、無鎖退路、原生 App 或 PWA。 |

<a id="review-handoff-cases"></a>
## 本輪 R2–R6 與範圍澄清：文件驗收條件

以下為 2026-10-01 PM 決議後的文件驗收條件，未執行產品測試。涉及已批准決議者依現行規格；其餘原有候選保持原狀。

| 案例／原文 | 相關 REQ／角色 | 條件與操作 | 預期／狀態 |
|---|---|---|---|
| <a id="ac-r02"></a>AC-R02 [共用錯誤分流](../contracts/interface-contract.md#error-recovery) | [REQ-02](#req-02)、[REQ-07](#req-07)、[REQ-16](#req-16)；FA-01／FB-02／BA-08／QA | 同一有效工作階段分別收到 W17 FORBIDDEN、RATE_LIMITED（有效／省略／非法 retry_after_ms）、SYNC_RESET_REQUIRED、OUTCOME_UNCONFIRMED；另斷線與權杖到期，認證限速後換分頁接手 | 只有認證失效／到期進唯一 FB 認證流程；業務拒絕不登出；有效權杖斷線重連而非盲 A03；事件流重設才 W13、REST 游標錯誤只重啟本查詢；不明 W05 保留 C1。等待值缺少時不做未定義值的加法／零延遲自動重試，手動再試仍守已知截止、可重試與 C6 剩餘額度；已失效舊連線錯誤不刷新較新工作階段 |
| <a id="ac-r03"></a>AC-R03 [C8 公開身分來源](../contracts/interface-contract.md#public-identity-handoff) | [REQ-01](#req-01)；BB-01／BA-01／FA-01／QA-01 | 比較 subject_id 與 user_id 不同的帳號；驗證回覆具有 C8，另測沒有映射／查詢失敗 | W02.user_id 等於 BB 映射的 A02／A03.user_id 與 A05.id，不是 subject_id；缺映射不成功 W02、不猜 JWT 宣告；C1 位置不能代替身分。C8 已整合（2026-10-01 PM 決議） |
| <a id="ac-r04"></a>AC-R04 [C9 附件中繼資料](../contracts/interface-contract.md#attachment-handoff)／[C10 同版本上傳交付](../contracts/interface-contract.md#signed-upload-contract) | [REQ-03](#req-03)、[REQ-13](#req-13)；FA-06／FB-03／BB-07／DO-02／QA-04 | 保留非擁有者有權／已失權查詢、原始位元組 PUT、標頭、A21 未就緒／回覆遺失等條件；追加本案例的[四項版本交錯](#ac-r04-version-cases) | 有權者以 A22 取中繼資料，不以 A21 當收件者查詢；PUT 200 仍須 A21 就緒。就緒／核驗中繼資料／A22 位元組必須綁同一已核驗版本；僅建立的 412 不是成功證據。C9／C10 為本版現行條件、未執行 |
| <a id="ac-r05"></a>AC-R05 [欄位](../contracts/interface-contract.md#field-presence)／[排序](../contracts/interface-contract.md#ordering-pagination)／[分頁](../contracts/interface-contract.md#rest-pagination)／[`nonce`](../contracts/interface-contract.md#heartbeat-nonce) | [REQ-09](#req-09)、[REQ-15](#req-15)、[REQ-16](#req-16)；FA／FB／BA／BB／QA | `receipt:null`、頭像 conversation_id:null 與缺少鍵比較；C11 的 9／10 與同一鍵值不同 UUID；A08／A11／A19 首頁、`limit` 省略／20／50／51／小數；W04 `nonce` 相同但關聯或連線不同 | 必填且可為 null 的欄位可以是 null，但不可省略；其他必填非 null 仍拒 null。C11 字串固定20位、不用 Number／語系，A19 兩欄皆降序且續頁不跳同一鍵值訊息；C12 首頁省略游標／`before`、預設20最大50、無效值 INVALID_ARGUMENT；心跳只接受同連線未完成請求的逐字相同的 `nonce`＋關聯，重複不延長。C11／C12 編碼與數值已整合（2026-10-01 PM 決議），未量測 |
| <a id="ac-r06"></a>AC-R06 [本地保存邊界](../contracts/interface-contract.md#local-persistence-boundary) | [REQ-06](#req-06)、[REQ-07](#req-07)、[REQ-09](#req-09)、[REQ-12](#req-12)；FA-03／04／05／QA-03 | 待送訊息後重啟；本地儲存失敗；W16 投影保存中斷；W14 只有部分頁 | 重啟沿用原 C1／承載資料；已收訊息未完成本機持久保存不送 W08；未原子保存投影不推進游標；未完整快照不裝 H。排除完整離線應用程式／PWA 不取消這些義務；不要求新增特定本地儲存技術 |
| <a id="ac-r07"></a>AC-R07 [A07 已知 ID 查詢](../contracts/interface-contract.md#contact-id-lookup) | [REQ-03](#req-03)；FB-04／BB-02／QA | 貼上對方分享的公開 user_id，或選取有權摘要／成員的 ID，再 A07、確認 A09；另輸入未知 ID／顯示名稱 | 只按 user_id 查公開摘要，不把名稱／電子郵件字串當關鍵字搜尋；A07 不提供 q 參數或搜尋清單，未知 ID 沿用 NOT_FOUND。不新增搜尋、QR 或邀請 API |
| <a id="ac-r08"></a>AC-R08 [一對一投影與條件群組](../contracts/interface-contract.md#receipt-projection-handoff) | [REQ-12](#req-12)；BB-05／BA-04／FA-04／QA-01／04 | 一對一收件者的 W09 提交，再重送較舊 W08；群組彙總未獲批准但有個別 W08／W09 | 一對一 W10 使用 BB 正式狀態／`updated_at`／event_id、C8 公開 recipient_id、C4 觀察者；不以請求 `kind` 使已讀倒退。`status_event_id:null` 不發 W10，W19 仍返回狀態。群組個別回條可處理，但 `receipt:null`、不產生虛構群組計數；不阻擋一對一。C4／C8 仍按批准相依整合 |
| <a id="ac-r09"></a>AC-R09 [內部驗證失敗分層](../contracts/interface-contract.md#internal-auth-layer)（C13） | [REQ-02](#req-02)、[REQ-16](#req-16)；BA-01／BA-08／BB-01／FA-01／FB-02／DO-04／QA-02 | 使用者工作階段有效；`api` 對內部操作分別回：(1) 可信 `UNAUTHENTICATED`＋`auth_layer:"user_session"`；(2) `UNAUTHENTICATED`＋`"service_identity"`；(3) 缺少 `auth_layer`；(4) 非 HINE 錯誤封套；(5) 其他錯誤碼；送 W01／W05 | (1) 僅該次呼叫所屬連線關閉並要求重新登入；(2)–(4) 不撤銷工作階段、不刷新／登出，視為 `DEPENDENCY_UNAVAILABLE` 並記錄。W01 不回 W02，回可重試 W17 後關閉；W05 依既有階段規則處理；C13 不新增公開錯誤碼。 |
| <a id="ac-r10"></a>AC-R10 [`unread_count` 語義](../contracts/interface-contract.md#unread-count)（C14-S） | [REQ-12](#req-12)、[REQ-20](#req-20)；BB-05／FB-05／FA-04／QA-06 | u1 有一對一及群組未讀訊息；分別執行 A11、A12、W14；本機或其他裝置已讀後再查詢，另令查詢失敗 | 徽章只顯示伺服器最近一次查詢值：A11 進入／返回清單、A12 開啟對話、W14 首次登入／游標重設成功時更新；本機／其他裝置讀取於下一次成功查詢反映，查詢失敗保留原值。未讀以使用者計，只計他人所發、目前可讀且未 read 的訊息，套用群組加入界線；新成員不回填加入前未讀。新訊息提示不是 `unread_count`；不採 C14-M 的交錯合併規則。 |

<a id="ac-r04-補充內容版本交錯同一案例未執行"></a>
<a id="ac-r04-version-cases"></a>
### AC-R04 補充：內容版本交錯（本版條件，未執行）

以 `t1/k1/g1` 表示原嘗試／獨立物件鍵／GCS 世代；不按 g1／g2 數值大小判斷新舊。每個附件只有一個上傳嘗試；授權逾期重新 A20 建立新嘗試及新 `attachment_id`。

1. **A21 就緒後，原 URL 再 PUT 不同內容。** t1 已就緒且 g1 仍為現存物件，原 URL 未到期；重送帶原簽章僅建立標頭的 PUT。預期 GCS 412，不替換 g1，就緒綁定與中繼資料不變，A22 仍只簽 g1。移除／改標頭也不能變成可覆寫請求；物件若異常消失，另依第 4 項，不得拿重新建立的版本頂替。
2. **舊授權 PUT 晚到。** 原授權已過期，以新 A20 建立 t2/k2；t1 舊 URL 的 PUT 即使成功，也只寫入自己的舊物件鍵 k1，不能完成新附件 t2；新附件須以其新授權上傳並經 A21 核驗。無 A25，不續期或切換目前嘗試。
3. **首次 PUT 成功但回覆遺失，再 PUT 遇到已存在。** 目前嘗試首次已建立 g1，但用戶端未收到 200；僅建立（不覆寫既有物件）的重試回 412。用戶端不得直接宣稱就緒，也不得刪物件／去掉前置條件；以 A21 核驗 g1。類型／大小／`sha256` 符合才提交就緒；不符回 CONFLICT，需重新上傳時另以 A20 建立新嘗試。若 A21 已提交但回覆也遺失，同嘗試重試只回原就緒綁定。
4. **A21 核驗版本與 A22 交付版本不一致／核驗版本不可取。** A21 核驗的是 g1；即使同一物件鍵後來有 g2，A22 也只能為保存的 g1 與核驗中繼資料簽 URL，不能選最新版本。g1 不可讀、中繼世代不符或依賴查詢失敗時，A22 回 DEPENDENCY_UNAVAILABLE，不發 g2 授權憑證、不改綁就緒。若簽出 URL 後 g1 才遺失，GCS GET 失敗，用戶端不得移除世代改取別版；A21 核驗過程已遭換版時亦不能提交就緒。
