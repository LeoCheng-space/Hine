# HINE-IC-0.4 — 待決策事項

**狀態：** 本表供審閱；列入本表不代表任何項目已獲批准。[共用介面契約](contracts/interface-contract.md)、[角色 PRD](README.md#按角色閱讀)及[Web/RWD 候選規格](ui/web-rwd.md#web-rwd)中標示待批准的內容仍屬提案。本表集中整理尚未定案的政策、成本／影響與相關負責角色，不授權實作，也不表示已有部署行為。

| 決策項目 | 狀態與待選事項 | 決策成本／影響 | 相關負責角色與來源 |
|---|---|---|---|
| <a id="decision-web-push"></a>Web Push 範圍與供應商 | 待決。決定是否納入瀏覽器推播；若納入，須批准供應商、訂閱生命週期、權限、前景抑制規則及交付／驗收契約。A23/A24 維持原生 `ios\|android`，本規格未定義瀏覽器 API／事件。 | 需新增供應商整合、瀏覽器權限與訂閱生命週期、服務工作者／安全／隱私審查、維運密鑰及 QA 測試矩陣；若暫不納入，則只維持原生權杖行為。 | PM 與 [BB](prd/backend-b.md#bb-08)、[FB](prd/frontend-b.md#fb-06)、[DO](prd/devops.md#do-02)、[QA](prd/qa.md#qa-06)；[契約](contracts/interface-contract.md#api-a23)、[Web UI](ui/web-rwd.md#web-rwd)。 |
| <a id="decision-rwd"></a>Web 響應式版面與互動 | 待批准候選版面斷點／頁面配置、路由允許清單、無障礙與觸控規則、輸入／IME、捲動／自動跟隨及已讀可視條件。已確認基線為桌面、平板及手機瀏覽器共用單一 Web 應用程式；不推定原生應用程式／PWA 範圍。 | 決定不同寬度與輸入方式下的前端設計、實作及 QA 範圍；閾值調整會影響已讀狀態與測試涵蓋。 | PM 與 [FA](prd/frontend-a.md#fa-08)、[FB](prd/frontend-b.md#fb-07)、[DO](prd/devops.md#do-06)、[QA](prd/qa.md#qa-06)；[Web/RWD](ui/web-rwd.md#web-rwd)。 |
| <a id="decision-device-id"></a>DeviceID 核發、重用與重新安裝 | 待決。決定重新安裝、切換帳號及遺失本機 DeviceStore 時，伺服器核發與重用 DeviceID 的界線。DeviceID 仍為不透明識別碼，並非憑證。 | 影響帳號／裝置綁定、復原、推播權杖所有權、登出及隱私；不得削弱驗證。 | PM/BB/FB/BA；[A02](contracts/interface-contract.md#api-a02)、[工作階段字典](contracts/interface-contract.md#data-dictionary)。 |
| <a id="decision-activity-push"></a>活動租期與未知狀態推播對象 | 待批准。本輪多分頁主要推薦為 [M2](#multi-tab-activity)：每連線計租、任一有效前景優先；租期與既有背景／未知對象另需批准，並不納入 Web Push。 | 背景分頁不能覆蓋前景；關頁未偵測時可能維持到原租期，不能當作即時前景真相或收件回條。 | PM／FA-07／BA-07／BB-08／QA-02；[C7](contracts/interface-contract.md#activity-merge)、[AC-N27](testing/acceptance-matrix.md#ac-n27)。 |
| <a id="decision-operational-values"></a>營運上限與速率 | 待決。批准同步分頁／掃描上限、上傳大小與 MIME 允許清單、心跳間隔／逾時、活動租期、前景同步週期、訊息／登入速率限制及供應商憑證缺漏政策。契約中的數值均為候選值，不是 SLO。 | 影響資源使用上限、使用者體驗／重試、基礎設施容量、濫用防護、就緒檢查及 QA 門檻。 | PM/DO 與 [BA](prd/backend-a.md#ba-08)、[BB](prd/backend-b.md#bb-07)、[FA](prd/frontend-a.md#fa-07)、[QA](prd/qa.md#qa-05)；[部署設定](contracts/interface-contract.md#deployment-config)。 |
| <a id="decision-group-policy"></a>群組角色、人數與成員政策 | 待決。決定既有 `admin`／`member` 與最後一位管理員不可移除之外的人數及角色規則；目前未定義封鎖操作。 | 影響授權交易、成員 UI、事件流扇出與容量；政策須維持 A14/A16→W11、A15/A17→W20、A18→W12 的對應。 | PM/BB 與 [FB](prd/frontend-b.md#fb-05)、[BA](prd/backend-a.md#ba-05)、[QA](prd/qa.md#qa-04)；[REST](contracts/interface-contract.md#rest-api)、[事件](contracts/interface-contract.md#websocket-events)。 |
| <a id="decision-group-receipts"></a>群組回條可見性 | 待決，**本輪不納入群組已讀彙總**。保留條件型別，不發未定義的群組 W10／計數；不影響一對一回條與群組個別 W08／W09／W19。 | 若日後納入，需批准觀察者、read_count／member_count 政策及 BB→BA 完整已提交 ReceiptProjection 交接，不能由 BA 從個別狀態猜數量。 | PM／BB-05／BA-04／FA-04／QA-01；[一對一與條件群組交接](contracts/interface-contract.md#receipt-projection-handoff)。 |
| <a id="decision-history-membership"></a>歷史與群組撤權（分項批准） | 待批准。**[G1 裝置已取得內容](#group-device-content)、[G2 舊授權服務端待送內容](#group-pending-content)、[G3 撤權後新查詢](#group-new-queries)** 分開選擇，不能用「退出後歷史是否可見」一次批准三項。加入前歷史仍是原有獨立待決事項，不在本輪收斂範圍。 | G1 是本機副本與畫面政策，G2 是開始交付界線，G3 是新授權資格；批准其中一項不推出其他兩項。 | PM／FA-05／FB-05／BA-05／BA-06／BB-03／BB-06／QA-03；[三項政策](contracts/interface-contract.md#group-revocation-policy)。 |
| <a id="decision-attachment-policy"></a>附件限制與支援類型 | 待決。批准檔名、大小、MIME 限制及續期／過期政策；候選 20 MiB 與允許清單尚未批准。 | 影響儲存／輸出流量成本、濫用掃描、上傳體驗、簽署授權憑證生命週期及安全／QA 涵蓋。 | PM/BB/DO 與 [FA](prd/frontend-a.md#fa-06)、[FB](prd/frontend-b.md#fb-03)、[QA](prd/qa.md#qa-04)；[A20](contracts/interface-contract.md#api-a20)–[A25](contracts/interface-contract.md#api-a25)。 |
| <a id="decision-historical-slos"></a>歷史效能與重連目標 | 待決。確認先前記錄的目標哪些仍有效；使用前須批准工作負載、環境、門檻及量測方法。 | 影響容量規劃與發佈準則；保留過時目標可能造成錯誤的通過／失敗判斷，移除則須明確替代。 | PM/QA/DO 與 [BA](prd/backend-a.md#ba-08)、[BB](prd/backend-b.md#bb-06)；[驗收 REQ-18](testing/acceptance-matrix.md#req-18)。 |
| <a id="decision-runtime-platform"></a>GCP 執行環境與託管服務 | 待批准。候選主方案：Cloud Run 上的 `api`、`realtime` 兩個服務，搭配 Cloud SQL for PostgreSQL、Memorystore for Redis、GCS、Secret Manager 與外部 HTTPS Load Balancer；替代方案為 Compute Engine 代管執行個體群組。詳見[候選方案](#proposal-runtime-platform)。 | 影響 WSS 長連線與平台請求逾時、`realtime` 水平擴展、常駐成本、備份／還原、部署與回滾流程，以及效能驗證環境能否重現。 | 提案：維運；PM/DO 與 [BA](prd/backend-a.md#ba-05)、[BB](prd/backend-b.md#bb-06)、[QA](prd/qa.md#qa-05)；[DO-01](prd/devops.md#do-01)、[DO-05](prd/devops.md#do-05)、[架構：部署拓樸](architecture/README.md#arch-deployment)。 |
| <a id="decision-tech-stack"></a>前後端框架與程式語言 | 待批准。候選主方案：全端 TypeScript（前端 React＋Vite；後端 Node.js LTS）。專案 README 註明前後端框架尚未鎖定；Notion PM 控制台 §2 的「MySQL / Django」字樣與 §8-A 的 PostgreSQL 主資料庫方向衝突，現行文件以 PostgreSQL 為準，且未採用 Django。詳見[候選方案](#proposal-tech-stack)。 | 影響 `backend/common` 共用型別、CI 建置工作、測試工具、團隊學習成本與交付時程。 | 提案：PM 彙整，FA/FB 與 BA/BB 提供團隊適用性依據；[FA](prd/frontend-a.md#fa-01)、[FB](prd/frontend-b.md#fb-07)、[BA](prd/backend-a.md#ba-01)、[BB](prd/backend-b.md#bb-01)、[DO](prd/devops.md#do-03)；[README 技術方向](../README.md#core-technology-direction)、[架構：程式碼對應](architecture/README.md#arch-code-map)。 |
| <a id="decision-service-topology"></a>`api`／`realtime` 部署單元與內部呼叫方式 | 待批准。候選主方案：`api` 與 `realtime` 分開部署（同一儲存庫、兩個部署單元），內部操作經私有網路 HTTP 並驗證呼叫者服務身分，推播工作程序與 `api` 屬同一部署單元；替代方案為同程序部署。與通知路徑合併提案，見[候選方案](#proposal-notify-topology)。 | 影響 ACK 路徑延遲、故障隔離、獨立擴展、部署複雜度與內部安全邊界；內部操作不得成為公開路由。 | 提案：BA 與 BB，維運協作；[BA-03](prd/backend-a.md#ba-03)、[BB-04](prd/backend-b.md#bb-04)、[BB-08](prd/backend-b.md#bb-08)、[內部交接](contracts/interface-contract.md#internal-handoffs)、[架構：元件](architecture/README.md#arch-components)。 |
| <a id="decision-realtime-notify"></a>REST 寫入後的即時通知與授權失效 | 待批准。候選主方案：後端 B 提交後呼叫任一 `realtime` 實例的候選操作 `publishCommitted`，經 Redis Pub/Sub 分發；群組撤權以提交時決定的收件者保證，工作階段失效以新的持久化失效紀錄、交易內工作階段檢查與遞送閘門保證，通知只加速。見[候選方案](#proposal-notify-topology)與[契約候選小節](contracts/interface-contract.md#internal-notify-invalidation)。 | 決定授權失效界線、群組事件延遲、連線清理上限，以及新增的內部操作、欄位與設定。通知只能在提交後送出；群組事件遺失時由 W15/W16 補回。 | 提案：BA 與 BB，維運、QA 協作；[BA-01](prd/backend-a.md#ba-01)、[BA-05](prd/backend-a.md#ba-05)、[BB-01](prd/backend-b.md#bb-01)、[BB-03](prd/backend-b.md#bb-03)、[部署設定](contracts/interface-contract.md#deployment-config)、[架構：6.6](architecture/README.md#flow-invalidation)。 |
| <a id="decision-load-tool"></a>負載測試工具 | 待批准。候選主方案：Artillery（WebSocket 引擎）加自訂 JavaScript 處理 HINE 的訊框格式；替代方案為 JMeter 加 WebSocket Samplers 外掛。`tests/load` 規劃的 1,000 → 5,000 → 10,000 條連線是測試階段，不是已核准的容量目標。詳見[候選方案](#proposal-load-tool)。 | 影響 WSS 情境腳本（W01、W05、W15）、CI 整合、結果格式、壓力產生器環境與成本。 | 提案：QA，維運提供產生器環境，BA 提供 WSS 情境；[QA-05](prd/qa.md#qa-05)、[DO-05](prd/devops.md#do-05)、[REQ-18](testing/acceptance-matrix.md#req-18)、[負載測試規劃](../tests/load/README.md)、[架構：容量驗證](architecture/README.md#arch-capacity)。 |

<a id="architecture-proposals"></a>
## 架構決策候選方案

以下是上表五項架構決策的候選主方案，全部待 PM 批准；列入本節不代表已批准、已實作或已量測。本節不提供雲端費用數字、組員熟悉度或效能結果；需要這些資訊的地方列為「需要補充的資訊」。

<a id="behavior-approval"></a>
### PM 行為批准表（全部待批准）

「現有候選」描述本輪收斂前的候選文字會導致的結果，**不是部署觀察或已批准政策**。「主要推薦」是供本次選擇的單一預設提案，不是實作授權。G1–G3 必須分別記錄選擇；未批准部分繼續保留候選狀態。

<a id="review-resolution-status"></a>
**R1～R6 回應狀態（不是 PM 簽核）：**
- **格式／既有矛盾已修正：** R1 表格切欄；R2 W17 分流與可省略等待值處理；R5 必填／可為 null、`nonce` 與首頁游標傳法；R6 本地持久保存與完整離線產品的邊界。已知 ID 查詢範圍及 FA-07 認證交接連結也已澄清。
- **已提供具體方案、待批准：** R3 的 C8、R4 的 C9／C10、R5 的 C11／C12。C10 本輪只補同一已核驗物件版本的保護與復原；不是重新提案整個 R4。**待批准不等於尚未回應。** C8、C9、C11、C12 主方案不變；C11 批准前保留舊樣例的比較標記，批准後才一併整合字典、樣例與角色引用。
- S／E1／多分頁、認證、撤權與瀏覽器政策仍按實際批准狀態處理；沒有新增批准依據，不改成全部已批准。關鍵字搜尋與群組已讀彙總未因本輪補充而納入。
- **中文版 Review（本輪，不是 PM 簽核）：** 文字澄清已直接修正：Cookie 分工、W08 本機保存、非完整離線但保留本機保存義務、H 前後銜接、`logged_out` 欄位、BB 不可連線的狀態摘要、健康範例、JWT 設定使用端、`REALTIME_INTERNAL_URL` 影響、術語與 BA-08／QA-02 交接。契約擴充提案待批准：C13（V1）、C14（V2）。待 PM 決策：V1–V4。R1～R6 與 C8～C12 的既有狀態不變；已回應項目不改回未回應。

| 使用者情境 | 現有候選實際會發生什麼 | 主要推薦行為 | 受影響角色與功能 | 尚待批准的選擇 | 原文／驗收案例連結 |
|---|---|---|---|---|---|
| <a id="group-device-content"></a>G1 裝置已取得歷史後被移除 | 已取得副本不會被伺服器追回；原文要求得知移除後離開路由，未規定抹除副本 | 維持得知撤權後停止顯示不可存取對話，不新增退出後唯讀頁；不強制安全抹除本機副本。離線裝置在得知前可能繼續顯示；不保證刪掉截圖／匯出／下載檔 | FA-05 本機投影；FB-05 路由；QA-03 | 批准此非遠端抹除政策，或另要求「得知後刪除應用程式管理快取」；後者仍不能追回所有副本，與 G2／G3 無連動批准 | [三項政策](contracts/interface-contract.md#group-revocation-policy)、[FB-05](prd/frontend-b.md#fb-05)、[N25](testing/acceptance-matrix.md#ac-n25) |
| <a id="group-pending-content"></a>G2 撤權前已授權、尚未開始交付的服務端內容 | 不採 E1 時，移除者可能在 A18 後很久才收到舊訊息或舊快照；**沒有相對 A18 的固定停止上限。60 秒只是移除紀錄保留窗，不是最大交付延遲，超過 60 秒仍可能開始交付** | 採既有 E1：授權點不變；節點套用撤權即停止該對象該對話的舊內容開始交付；最遲在 A18 提交後超過 S（候選 15 秒）時不再開始交付。窗口內仍可能送；不追回已交給網路的資料 | BB-03 撤權；BB-06 讀取；BA-05／06 遞送；FA-05 同步；QA-03／04 | 批准 E1 的有界延後需求與 S，或明確接受無固定上限的比較方案；E1 內部紀錄／讀取中繼資料等相依須在批准後整合，不宣稱基礎型別已支援 | [E1 完整原文與界線](contracts/interface-contract.md#group-revocation-e1)、[N18](testing/acceptance-matrix.md#ac-n18)、[N26](testing/acceptance-matrix.md#ac-n26) |
| <a id="group-new-queries"></a>G3 撤權後才開始歷史／同步查詢 | A19／A22 拒絕該對話新授權；W14 排除該對話，W16 過濾正文但保留最小自身 W12；其他對話可繼續 | 維持上述過濾／拒絕，不因內容產生於撤權前或持有舊頁面權杖就給新讀取權；沿用每頁授權與各操作錯誤規則，不新增 API | BB-03／05／06／07 授權；BA-06；FA-05；FB-05；QA-03 | 批准維持「新查詢無該群組歷史」，或要求另訂移除前區間讀取權（不是本方案、須另修授權規則）；與 G1 副本獨立 | [操作 5／6](contracts/interface-contract.md#internal-read-bootstrap)、[D1](contracts/interface-contract.md#authorization-boundary)、[N02](testing/acceptance-matrix.md#ac-n02) |
| <a id="session-old-delivery"></a>S1 登出／刷新後，舊連線仍收到舊授權資料 | 未套用撤銷、節點仍新鮮且權杖有效時，舊事件／讀取回應／W18 仍可能開始交付 | 維持 D2：S 候選 15 秒是撤銷後仍可開始交付舊資料的窗口，不只是效能設定；套用撤銷較早則較早停止；撤銷後授權的新資料仍依 D1 禁止 | BA-01／05／06；BB-01；FA-02；QA-02 | 批准有界延後需求與 15 秒候選值，或調整 S；不能把需求批准寫成已達標，也不能把開始交付期限當抵達期限 | [D1–D4](contracts/interface-contract.md#authorization-boundary)、[N13–N17](testing/acceptance-matrix.md#ac-n13) |
| <a id="stale-service-behavior"></a>S2 BB 暫時不可連線／補齊逾時 | 仍新鮮時舊資料可能交付；特定事件補齊逾時放棄即時遞送；不新鮮後連線可保留但只送 W04／W17 | 維持失效狀態表；超過最近完整補齊開始後 S 停止資料交付，恢復先補齊；連線最遲權杖到期關閉。不以保留連線宣稱聊天仍正常 | BA-01／05／06；FA-01／05；BB；QA-02／04 | 批准「暫停交付而非立刻全斷線」與 S／補齊等待值；更短 S 也更早因 BB 中斷暫停資料 | [狀態表](contracts/interface-contract.md#delivery-state-table)、[N04](testing/acceptance-matrix.md#ac-n04)、[N12](testing/acceptance-matrix.md#ac-n12) |
| <a id="multi-tab-session-policy"></a>M1 多分頁刷新、重登或登出 | 每分頁一條 WSS，共用 Cookie；A03 換世代，C5 的同裝置 A02 取代舊工作階段；A04 影響該工作階段的各分頁 | 維持 Web Locks＋BroadcastChannel＋auth_epoch 交接，正常並發只刷新一次；各分頁換自己的連線；同瀏覽器設定檔一帳號，不影響其他裝置 | FB-01／02；FA-02；BB-01；BA-01；QA-02 | 批准 C5 行為副作用、一帳號範圍與每分頁連線，不把 C5 當純內部欄位增加 | [FB 交接](prd/frontend-b.md#fb-multi-tab)、[C5](contracts/interface-contract.md#internal-change-requests)、[N19–N24](testing/acceptance-matrix.md#ac-n19) |
| <a id="multi-tab-activity"></a>M2 前景／背景分頁同時在線，之後關閉或失效 | 前輪尚未定義合併；裝置層最後寫入會使背景分頁覆蓋前景 | 每連線獨立租期，任一有效前景→`foreground`，否則有背景→`background`，皆無→`unknown`。已偵測關閉／套用失效立即移除；未偵測關頁最多計到原租期／權杖到期。W22 只確認本連線，不要求最後一筆 `background` | FA-07；BA-07 聚合；BB-08 消費；QA-02 | 批准 C7 內部連線識別與合併、60 秒候選租期；租期內可能保留已關頁的舊回報；不包含 Web Push 批准 | [C7](contracts/interface-contract.md#activity-merge)、[W21／W22](contracts/interface-contract.md#event-w21)、[N27](testing/acceptance-matrix.md#ac-n27) |
| <a id="refresh-uncertain-policy"></a>M3 A03 結果不明／協調分頁消失 | 前輪依「BB 有無 Cookie 寬限」可能恢復或重登，FB／BB 尚無唯一終點 | **C6：舊 Cookie 無寬限（0 秒）**。先採可用新紀元，否則整個瀏覽器僅一次 A03 恢復；401 或恢復未成功即清除本地認證、停止 WSS、要求 A02。不自動第三次刷新；限速僅在有效 retry_after_ms 存在時計算截止，缺少時按共用規則停止自動定時重試 | FB-02；BB-01；FA-02；QA-02 | 原候選政策與代價仍待明確選定，本輪只修正可省略等待欄位的處理，不改批准狀態 | [C6](contracts/interface-contract.md#refresh-recovery-policy)、[錯誤分流](contracts/interface-contract.md#error-recovery)、[N23](testing/acceptance-matrix.md#ac-n23) |
| <a id="browser-support-policy"></a>B1 瀏覽器缺少協調／可見性能力 | 前輪只有能力前提，沒有具體退路 | HTTPS 同來源頂層頁、Web Locks、BroadcastChannel、可用共享儲存／Cookie、WebSocket／本機同步儲存、Page Visibility 都須可用；缺少就提示不支援，不啟用登入／聊天。執行中失去能力停止該分頁 WSS／自動刷新，不做無鎖單分頁降級 | FB-02／07；FA-01／07；QA-02／06 | 批准能力不足即不支援的政策，並登錄具體瀏覽器／版本清單；無原生應用程式／PWA 擴充 | [支援前提](prd/frontend-b.md#fb-browser-support)、[Web 範圍](#decision-rwd)、[N28](testing/acceptance-matrix.md#ac-n28) |
| <a id="review-identity"></a>R3 登入後 W02 公開身分 | validateAccess 比較原文只提供內部 subject_id，C1 只加位置，不能據此產生可信 user_id | C8 在同一次 BB 驗證回覆增加 user_id，W02 名稱不變、不加 JWT 宣告假設 | BB-01；BA-01；FA-01；QA-01 | 是否採 C8 最小內部欄位；本輪未批准 | [C8](contracts/interface-contract.md#public-identity-handoff)、[AC-R03](testing/acceptance-matrix.md#ac-r03) |
| <a id="review-attachments"></a>R4 收件者看附件／擁有者上傳 | 已有 C9 中繼資料與 C10 PUT／A21 就緒具體方案；前輪尚未綁定就緒與物件版本，簽署網址也不是一次性 | 保留 C9；C10 補每嘗試獨立物件鍵、簽入僅建立前置條件、A21 綁定核驗世代／中繼資料，A22 只簽已核驗世代；版本不可用就失敗，不改送最新版本 | FA-06；FB-03；BB-07；DO-02；QA-04 | **已有具體方案、待批准**：C9 既有欄位與補足後完整 C10 的內部中繼資料／必要標頭／版本交付規則；不另增 A／W API 或可續傳上傳能力 | [C9](contracts/interface-contract.md#attachment-handoff)、[C10](contracts/interface-contract.md#signed-upload-contract)、[AC-R04](testing/acceptance-matrix.md#ac-r04) |
| <a id="review-order-pagination"></a>R5 各端排序與 REST 首頁 | order_key 只有字串型別，REST `limit` 無確定預設／上限 | C11 固定20位 ASCII 數字＋UUID 次排序；C12 候選 `limit` 預設20、最大50；首次省略游標／`before` | BB-05／06；FA-05；FB-04；QA-01／03 | 是否採 C11 編碼與 C12 數值／驗證錯誤適用範圍；原示意樣例保留比較狀態，未量測 | [排序／分頁](contracts/interface-contract.md#ordering-pagination)、[AC-R05](testing/acceptance-matrix.md#ac-r05) |
| <a id="review-auth-layer"></a>V1 內部服務身分驗證失敗 | 內部操作只回單一 `UNAUTHENTICATED`；呼叫端無法分辨呼叫者服務身分失敗與使用者工作階段失效，可能把平台／服務憑證問題當成使用者登出 | C13：內部錯誤封套 `details.auth_layer:"service_identity"\|"user_session"`；只用於 `UNAUTHENTICATED`：可信回應且 `user_session` 才轉為 W17 `UNAUTHENTICATED` 並關閉該連線；`service_identity`／缺少分層的 `UNAUTHENTICATED` 及非 HINE 封套按依賴失敗回 W17 `DEPENDENCY_UNAVAILABLE`，不登出、不刷新，並告警；其他錯誤碼照原分流 | BA-08；BB-01；FA-01／FB-02 消費；DO-04 告警；QA-02 | 是否採 C13 內部欄位；不新增公開錯誤碼 | [C13](contracts/interface-contract.md#internal-auth-layer)、[錯誤分流](contracts/interface-contract.md#error-recovery)、[AC-R09](testing/acceptance-matrix.md#ac-r09) |
| <a id="decision-unread-count"></a>V2 聊天清單未讀數 | `unread_count` 只有型別；未定義範圍、自己訊息、已讀依據、使用者或裝置層級，各端可能算出不同數字 | C14：BB 以呼叫者使用者計算他人所發、已提交回條尚非 `read` 的可讀訊息數；逐訊息已讀、不改成累積式；主要候選為再次查詢時更新：其他裝置在下一次 A11（進入／返回清單）、A12（開啟對話）或 W14（首次登入／游標重設）成功後收斂，查詢前允許偏高的舊值，不新增事件；本機加減採[合併規則 C14-M](contracts/interface-contract.md#unread-merge)：只套用可證明未含於基準的變化（本裝置在基準回應後送出且 `changed:true` 的已讀；W14 基準後經 W16 取得的新訊息），以 `message_id` 去重，不明確的留到下一次查詢；對話串新訊息提示是本機計數 | BB-05；FB-05；FA-04；QA-06 | 是否採 C14；是否接受其他裝置延遲到下次查詢才更新；本機合併選 **C14-M**（主要候選；下一次查詢前可能偏高或偏低，以 A11／A12 為基準後到達的新訊息不加一）或 **C14-S**（只顯示最近查詢值，連本裝置已讀也延後到下一次查詢才反映於徽章）。替代方案：另批准讓讀者自身的其他裝置也收到 W10（C4 觀察者變更），**只適用於一對一對話**；群組目前不發 W10（群組彙總未納入），只改 C4 觀察者不能解決群組未讀同步，群組需另立事件或群組回條投影決策；是否改採「讀到某則即之前全部已讀」（會改回條語義，本輪不推薦） | [C14](contracts/interface-contract.md#unread-count)、[AC-R10](testing/acceptance-matrix.md#ac-r10) |
| <a id="review-read-visibility"></a>V3 已讀可見判定 | 50%／500 ms 未定義觀察單位與分母；超長訊息、200% 縮放、虛擬鍵盤時可能永遠無法成立；模態／隱藏是否累計未定 | 以訊息泡泡為單位、分母為該泡泡在有效可視區內可能的最大交集 min(泡泡寬, 可視區寬)×min(泡泡高, 可視區高)，不代表讀完全文；前提中斷即歸零；模態覆蓋或頁面隱藏停止累計；自己的訊息不送 W09 | FA-08；QA-06；BA-04／BB-05 | 批准 50%、500 ms、分母規則與歸零規則；數值未量測 | [已讀判定](ui/web-rwd.md#rwd-read-rule)、[REQ-20 詳細驗收](testing/acceptance-matrix.md#req-20-detail) |
| <a id="review-web-input-routing"></a>V4 鍵盤判別、根路徑與清單搜尋 | 鍵盤無法判別時沒有規則；`/` 行為未定義；「搜尋」可能被理解為找人 | 鍵盤只依能力訊號判斷，無法判別時 Enter 換行＋送出按鈕＋Ctrl／⌘+Enter；`/` 初始化中顯示載入，之後取代導向 `/login` 或 `/chats`；搜尋只篩選本機已載入的 A08／A11 項目，不擴張 A07 | FA-08；FB-04／05／07；DO-06；QA-06 | 批准三項候選行為；不新增後端 API；關鍵字找人仍不在範圍 | [鍵盤](ui/web-rwd.md#rwd-keyboard)、[根路徑](ui/web-rwd.md#rwd-root-route)、[本機篩選](ui/web-rwd.md#rwd-local-filter) |

<a id="spec-config-measure"></a>
### 規格目標、候選配置、實際量測結果

**可以先批准需求，之後再驗證是否達標。** 「未量測」不是沒有需求的理由；下列全部尚未量測，本輪不執行產品測試或壓測。批准任何一列也不代表已實作、部署或達標。

| 規格目標（待批准） | 候選配置／政策 | 實際量測結果 |
|---|---|---|
| S1：工作階段撤銷後超過 S，不再開始交付舊授權資料 | `INVALIDATION_STALE_SECONDS = 15 秒`；增加 S 同時延長舊授權資料窗口 | 未量測；N13–N17 只是條件 |
| G2：E1 群組待送內容採相同開始交付上限 | 推薦同一 S=15 秒；前提是批准並整合 E1，不是現有基礎型別的既得保證 | 未量測；N26 是需求，非結果 |
| S2：BB 中斷不能無限沿用舊權威；事件補齊失敗走同步 | 輪詢 5 秒，須小於 S；單事件補齊等待 1000 毫秒。輪詢加補齊是清理時間，不替代 D2 上限 | 未量測 |
| G2 比較方案：只盡力減少群組舊事件 | 不採 E1 的移除紀錄保留窗 60 秒；**不是交付延遲上限** | 無固定停止上限可宣稱；N18 未執行 |
| M2：其他分頁不能延長某分頁的前景租期 | `ACTIVITY_LEASE_SECONDS = 60 秒`，且不超過權杖到期；W22 到期前由本連線更新 | 未量測；關頁偵測時間未實測 |
| M3：結果不明不無限輪替／重播舊 Cookie | 舊 Cookie 寬限 0 秒；每次不明刷新全瀏覽器最多 1 次恢復；每次 A03 候選等待 10 秒；`auth.request` 候選等 1 秒 | 未量測；不保證網路中斷可無感恢復 |
| 遺失的群組事件由既有事件流恢復，不改 ACK／游標 | 沿用前景核對候選 10 秒；不宣稱背景瀏覽器有同樣排程時限 | 未量測 |
| B1：只有滿足必要能力的瀏覽器列為支援 | 能力門檻已提出；版本清單待 PM／QA 登錄 | 無相容性實測結果 |
| V3：只在實際可見時判已讀，超長訊息與縮放時仍可成立 | 可見面積 ÷ 最大可能交集 min(泡泡寬, 可視區寬)×min(泡泡高, 可視區高) ≥ 50%、連續 500 ms、中斷歸零 | 未量測；REQ-20 正反案例未執行 |

**技術方案清單（前輪候選保留，不在本輪重選）：**
- `api`／`realtime` 分開部署；`publishCommitted` → Redis Pub/Sub；C1–C4 與 SQL 鎖／計數器／輪詢沿用[技術附錄](contracts/interface-contract.md#internal-transaction-order)。
- G2 若批准 E1，群組紀錄與同步中繼資料等[相依交接](contracts/interface-contract.md#group-revocation-e1)要在整合唯一原文時一併完成；不能只批准效果就當作技術已完成。
- GCP 的計費／通知時機、並行上限、實例數、權杖時效、成本與推播工作程序觸發依[既有適用條件](#runtime-conditions)決定；本輪不填入虛構量測。
- 技術棧仍以 TypeScript 為候選，需組員本人回報經驗／課程限制；Artillery 仍待後續獲授權的試跑與預算確認，本輪不執行。

<a id="proposal-notify-topology"></a>
### 通知路徑與 `api`／`realtime` 部署單元（合併提案）

- **提案主責：** 後端 A 與後端 B 共同提案。BA 負責 `realtime` 端的通知處理、遞送閘門、輪詢與 `publishCommitted`；BB 負責失效紀錄、交易順序、`readSessionInvalidations` 與工作階段綁定檢查。維運負責內部網路與服務身分，QA 負責[候選驗收案例](testing/acceptance-matrix.md#ac-n01)。
- **主要推薦方案：**
  1. **部署單元：** `api` 與 `realtime` 分開部署（同一儲存庫、兩個部署單元）；`api` 可有 M 個實例，`realtime` 可有 N 個實例。推播工作程序與 `api` 屬同一部署單元，候選觸發方式為定期輪詢待處理的推播意圖；它在 Cloud Run 上的執行條件見 [GCP 方案的適用條件](#runtime-conditions)。
  2. **內部呼叫：** 私有網路 HTTP（`POST /internal/v1/<operation>`），應用程式驗證呼叫者的服務身分。
  3. **通知傳遞：** 後端 B 提交成功後，呼叫任一 `realtime` 實例的 [`publishCommitted`](contracts/interface-contract.md#internal-publish-committed)，由該實例發布到 Redis Pub/Sub，所有實例各自遞送或清理。呼叫時機是回應前單次嘗試或回應後非同步，依執行環境在回應後是否仍配置 CPU 而定（[T1](contracts/interface-contract.md#internal-transaction-order)）。W05／W08／W09 產生的事件仍由處理請求的 `realtime` 實例直接發布。
  4. **正確性不依賴通知：** 群組撤權由提交時決定的收件者與既有事件流保證；工作階段失效由新的持久化失效紀錄、交易內工作階段檢查、遞送閘門、輪詢與存取權杖到期保證。規範見[契約候選小節](contracts/interface-contract.md#internal-notify-invalidation)。
- **替代方案：** 同程序部署：`api`、`realtime` 兩個模組在同一程序，N 個相同實例。內部操作改為函式呼叫，`publishCommitted` 仍經 Redis 分發到其他實例；授權失效機制完全相同。適合技術棧決定只用一種後端語言，且維運希望只維運一個服務的情況。採用時須修改 `HealthResponse.service` 的 `api`／`realtime` 區分，以及部署設定表的機密分離（同一程序會同時持有 `DATABASE_URL`、`REDIS_URL` 與 JWT 簽章金鑰）。另外，任何後端變更的部署都會替換承載 WSS 的實例：新連線導向新修訂版，舊連線最晚在請求逾時或實例關閉時結束（平台會讓處理中的請求有時間完成，但例外情況可能提前送出 SIGTERM）。這對重連量的影響取決於部署頻率，未量測。
- **候選比較：**

  | 候選 | 如何到達多個實例 | 優點 | 缺點 | 結論 |
  |---|---|---|---|---|
  | 同程序模組交接 | 仍需 Redis Pub/Sub | 沒有內部網路呼叫與呼叫者驗證；少一次內部網路往返（延遲差異未量測） | 需修改 HealthResponse 與機密分離；任何後端部署都會觸發 WSS 遷移；BA、BB 必須同語言 | 替代方案 |
  | 內部呼叫 `realtime`，再由 `realtime` 分發 | 任一實例發布到 Redis | 維持 Redis 只由 BA 使用、資料庫與 JWT 金鑰只在 BB；沿用 `getDevicePresence` 本來就需要的 BB→BA 方向 | 多一個內部端點、內部 URL 與服務身分設定；成功回覆只代表單一實例已發布 | 主方案 |
  | 後端 B 取得受限的 Redis 發布能力 | BB 直接發布 | 少一段呼叫 | BB 需持有 Redis 憑證，打破現有機密分離；能否只允許發布特定頻道，取決於託管 Redis 是否支援 ACL（未確認） | 不採用 |
  | 既有持久化資料驅動通知 | 各節點輪詢 | 不會遺失 | 群組事件的額外延遲上限約為一個輪詢間隔加查詢時間，縮短間隔會增加每個節點的查詢量（未量測）；群組事件延遲目標尚未定義；事件流是每使用者的，節點還需要另一個全域變更來源 | 在群組事件延遲目標定義前，不作為主要傳遞方式；只用於工作階段失效的補齊 |

- **推薦依據：**
  - 0.4 比較原文以兩個服務為前提：`HealthResponse.service` 區分 `api`／`realtime`；部署設定讓 `DATABASE_URL` 與 JWT 簽章金鑰只給 BB、`REDIS_URL` 只給 BA；內部錯誤已包含網路邊界所需的 `OUTCOME_UNCONFIRMED`。分開部署不需要修改這些內容，不表示本輪已批准部署。
  - `getDevicePresence` 本來就要求 BB 呼叫 BA；`publishCommitted` 沿用同一個 BB→BA 通道。
  - 只部署 `api` 時不會替換 `realtime` 實例，WSS 連線不需遷移。
  - 撤銷後新授權內容依 D1 阻止；舊授權內容另看 S1／G2。不採 E1 時群組舊內容無相對 A18 固定停止上限，推薦 E1 才提出相同 S 的需求；不能用「正確性不依賴通知」掩蓋這個產品差異。
- **尚未確認的前提：**
  - 執行平台提供可由應用程式驗證的服務身分憑證。在 GCP 主方案下是 Google 簽發的 ID 權杖；因為兩個服務都要接收公開流量，無法只用平台的服務層級存取控制保護 `/internal/*`，必須由程式驗證。
  - A03 每次更新都寫入一筆失效紀錄，並經單列計數器序列化。寫入頻率取決於存取權杖時效與活躍裝置數，兩者都未定案，負載也未量測。
  - 同瀏覽器多分頁交接、C6 無寬限恢復與 C7 活動合併均已提出單一主方案，待上方 M1–M3 批准；支援能力政策見 B1，具體版本清單仍待登錄。
  - 群組本機已取得、服務端尚未交付、撤權後新查詢分別依 G1／G2／G3，不能再以同一歷史可見性選項代替三項。
  - 候選設定值（輪詢 5 秒、新鮮期限 15 秒、補齊等待 1000 毫秒、通知重試 3 次且總計 5 秒內）都未經量測。W21 需先補齊失效紀錄，會讓每次 W21 多一次對後端 B 的讀取（可合併），負載未量測。撤銷前資料的工作階段上限等於 `INVALIDATION_STALE_SECONDS`，此值同時決定延遲生效的最長時間與後端 B 短暫不可連線時多久停止交付，需一併取捨。
  - C5 讓同一帳號同一裝置只保留一個有效工作階段；同一瀏覽器在另一分頁重新登入會撤銷原分頁的工作階段，產品上是否接受需與多分頁方案一併確認。
- **成本、維運、學習與交付影響：**
  - BB：新增失效紀錄表與計數器、T1–T4 交易順序、`readSessionInvalidations`、工作階段綁定檢查、提交後通知與重試。
  - BA：遞送閘門、輪詢迴圈、`publishCommitted` 端點、通知去重、群組移除紀錄、W01 註冊競態檢查。
  - 維運：兩個服務的內部 URL、服務身分與呼叫者允許清單、公開入口排除 `/internal/*`、注入候選設定。
  - QA：要執行通知遺失案例，需要能攔截 `publishCommitted` 與丟棄 Pub/Sub 訊息的測試手段。
  - 學習：內部服務身分驗證、PostgreSQL 列鎖順序。
- **影響的文件與工作：** 共同契約 §5 候選小節與 §6 候選設定；架構 §3、§6、§7、§8、§9；BA-01、BA-05、BA-07；BB-01、BB-03、BB-04、BB-05；DO-01、DO-02；QA-02、QA-04；FA-02；FB-02 與 FB 多分頁方案；驗收矩陣候選案例。
- **PM 需要批准：** 見本節開頭的批准清單。

<a id="proposal-runtime-platform"></a>
### GCP 執行環境與託管服務

- **提案主責：** 維運提出環境與成本假設；BA、BB 確認服務需求；QA 確認壓測環境需求；PM 批准成本上限。
- **主要推薦方案：**
  - **運算：** Cloud Run 上的兩個服務 `api` 與 `realtime`，同一區域。各服務的計費模式、最少實例數與並行上限依下方[適用條件](#runtime-conditions)選定；不假設設定最少執行個體就能保證背景工作。
  - **資料與儲存：** Cloud SQL for PostgreSQL、Memorystore for Redis、GCS、Secret Manager；以 Direct VPC egress 或 Serverless VPC Access 連到私有位址。
  - **入口：** 外部 HTTPS Load Balancer 綁定 `hine.run.place` 與代管憑證，`/api/v1` 轉到 `api`、`/ws/v1` 轉到 `realtime`、候選 UI 路由轉到 Web 靜態資產；`/internal/*` 不轉送。
  - **內部呼叫：** 兩個服務各用獨立服務帳號，呼叫時附上 Google 簽發的 ID 權杖，由應用程式驗證受眾與呼叫者帳號。
  - **監控與日誌：** Managed Service for Prometheus 的 Cloud Run 附屬容器蒐集指標，以 Grafana 查詢；Cloud Run 標準輸出進入 Cloud Logging。
  - **交付：** GitHub Actions 建置容器映像並推送到 Artifact Registry 後部署；候選以 Workload Identity Federation 授權，不存放長期金鑰。
  - **環境：** 至少一個受控測試環境與一個正式環境；是否以不同 GCP 專案隔離由維運提案。
- **替代方案：** Compute Engine 代管執行個體群組執行容器，自行架設 Prometheus／Grafana。沒有平台請求逾時與依請求計費的限制，但作業系統更新、擴展與監控都要自行維運。
- **推薦依據：**
  - Cloud Run 支援 WebSocket，每個連線視為一個長時間請求，受服務請求逾時限制，上限 60 分鐘；有任何開啟中 WebSocket 的實例都視為活動中，以執行個體為準的方式計費（[WebSocket](https://docs.cloud.google.com/run/docs/triggering/websockets)、[請求逾時](https://docs.cloud.google.com/run/docs/configuring/request-timeout)）。HINE 的 A03 本來就會以新連線取代舊連線，只要存取權杖最長時效不超過請求逾時，平台逾時就不會額外切斷連線。
  - Cloud Run 可設定以執行個體為準的計費在請求以外持續配置 CPU（[計費設定](https://docs.cloud.google.com/run/docs/configuring/billing-settings)），符合 Redis 訂閱與輪詢的需求；官方文件也建議以 Memorystore 的 Redis Pub/Sub 在實例間同步 WebSocket 資料，與本專案既有方向一致。
  - Cloud Run 支援以服務帳號與 ID 權杖進行服務間驗證（[取得 ID 權杖](https://docs.cloud.google.com/docs/authentication/get-id-token)）；Managed Service for Prometheus 提供 Cloud Run 附屬容器（[Prometheus 附屬容器](https://docs.cloud.google.com/stackdriver/docs/managed-prometheus/cloudrun-sidecar)）。
  - 本方案不需要 Kubernetes 或自管 VM，重連不需要黏性工作階段，與架構文件的約束一致。

  <a id="runtime-conditions"></a>
  **Cloud Run 適用條件（依官方文件，數值須在批准時確認）：**

  | 條件 | 官方文件內容 | 對 HINE 的要求 |
  |---|---|---|
  | 每實例並行請求上限與實際採用值 | 上限可設到 1,000。以 `gcloud` 或 Terraform 新建服務時，預設為 vCPU 數 × 80；主控台預設 80。設定值只是上限，CPU 使用率高時，平台可能少送請求並改為擴展實例（[並行](https://docs.cloud.google.com/run/docs/about-concurrency)） | `realtime` 必須明確設定並行上限；採用值由壓測決定，不預設為 1,000 |
  | 連線與內部請求共用並行名額 | 每條 WebSocket 都是一個長時間請求（[WebSocket](https://docs.cloud.google.com/run/docs/triggering/websockets)） | `realtime` 的並行需求是 WSS 連線數加上同時進行的內部請求（`publishCommitted`、`getDevicePresence`）。所需實例數至少是「需求 ÷ 採用上限」向上取整，再加上部署與實例替換期間的容量餘裕。10,000 ÷ 1,000 = 10 只是理論下限 |
  | WebSocket 請求逾時與預期重連 | 預設 5 分鐘、上限 60 分鐘，到時平台關閉連線，用戶端須自行重連（[請求逾時](https://docs.cloud.google.com/run/docs/configuring/request-timeout)、[WebSocket](https://docs.cloud.google.com/run/docs/triggering/websockets)） | 明確設定為不短於存取權杖最長時效。預期的重連來源：逾時、A03 換線、部署新修訂版、實例替換或重啟，都走 FA 既有的重連與 W15 補回 |
  | API 回應後的 CPU | 以請求為準的計費只在處理請求時配置 CPU；以執行個體為準的計費在實例整個生命週期配置 CPU，可在回應後執行背景工作。有任何開啟中 WebSocket 的實例視為處理中（[計費設定](https://docs.cloud.google.com/run/docs/configuring/billing-settings)、[WebSocket](https://docs.cloud.google.com/run/docs/triggering/websockets)） | `api` 採以請求為準時，`publishCommitted` 使用回應前模式；回應後模式與推播工作程序都需要以執行個體為準的計費。`realtime` 有連線時就有 CPU；沒有連線且採以請求為準時，訂閱與輪詢可能停頓，恢復時節點不新鮮、會先補齊（[狀態表](contracts/interface-contract.md#delivery-state-table)第 7、8 列），只影響延遲，不影響授權正確性 |
  | 實例停止與持久化恢復 | 閒置實例可隨時關閉，包括最少執行個體保留的實例；最少執行個體是盡力維持的目標，可能隨時重啟或暫時低於設定。關閉前先送 SIGTERM，10 秒後送 SIGKILL；例外情況下，處理中的實例也可能收到 SIGTERM（[容器契約](https://docs.cloud.google.com/run/docs/container-contract)、[最少實例](https://docs.cloud.google.com/run/docs/configuring/min-instances)） | 背景工作不依賴某個實例持續存在。推播意圖已持久化於 PostgreSQL，以領取期限讓任何實例接手未完成的意圖；`realtime` 收到 SIGTERM 後停止接受 W01，並盡力關閉連線；未送出的通知由事件流與失效紀錄補回。推播工作程序是否改用官方建議的 Cloud Tasks 等觸發方式，待維運評估 |
  | 以執行個體為準的計費的記憶體 | 至少 512 MiB（[計費設定](https://docs.cloud.google.com/run/docs/configuring/billing-settings)） | 規格估算時納入 |
  | 端對端 HTTP/2 | WebSocket 服務不要啟用（[WebSocket](https://docs.cloud.google.com/run/docs/triggering/websockets)） | `realtime` 不啟用 |
- **尚未確認的前提：**
  - 存取權杖最長時效尚未定案；若超過 60 分鐘，`realtime` 連線會被平台切斷並重連（正確性不受影響，但多一次 W01 與 W15）。
  - 採用的並行上限、實例數與容量餘裕都需要壓測決定。
  - Memorystore 與 Cloud SQL 的最小可用規格是否在預算內。
  - 推播工作程序採定期輪詢或其他觸發方式（例如 Cloud Tasks）。
  - `realtime` 部署新修訂版時，新連線導向新修訂版，舊連線最晚在請求逾時或實例關閉時結束；部署頻率對重連量的影響未量測。
- **成本、維運、學習與交付影響：** `realtime` 常駐實例、Cloud SQL 與 Memorystore 都是持續計費的資源；金額由維運以 GCP 定價計算工具依選定規格估算，本文件不提供數字。維運上不需要管理作業系統；學習重點是 IAM、VPC 輸出流量、Load Balancer 與 Cloud Run 設定。交付面需要在 GitHub Actions 加入映像建置與部署工作。
- **影響的文件與工作：** DO-01～DO-05、架構 §7 與 §11、共同契約[候選設定](contracts/interface-contract.md#deployment-config-candidates)、`infra/gcp/`、`.github/workflows/`。
- **需要補充的資訊：** 可用的 GCP 帳單額度或課程提供的抵用額度、區域、存取權杖時效、展示與測試期間需要常駐的時段。
- **PM 需要批准：** 運算與託管服務組合；`api`、`realtime` 各自的計費模式；環境數量；維運估算後的月費上限；最少實例數。

<a id="proposal-tech-stack"></a>
### 前後端框架與程式語言

- **提案主責：** PM 彙整；前端 A／B 提供前端的團隊適用性依據，後端 A／B 提供後端依據，維運確認 CI 與容器建置可行。
- **主要推薦方案：** 全端 TypeScript。前端 React＋Vite；後端 Node.js LTS，`api` 使用一個 HTTP 框架（候選 Fastify），`realtime` 使用 `ws` 函式庫；PostgreSQL 遷移工具由 BB 在批准前從 TypeScript 生態中提出。A 系列與 W 系列的承載資料型別在前後端共用一份定義。
- **替代方案：** 前端 TypeScript，後端 Python（例如 FastAPI）。型別無法直接共用，需要從同一份結構描述產生兩邊的型別。
- **推薦依據：**
  - Web 用戶端本來就使用 JavaScript／TypeScript；後端也用 TypeScript 時，四個開發角色使用同一語言，A01–A25 與 W01–W22 的型別可以共用，減少前後端欄位不一致。
  - 部署單元採分開或同程序都能使用同一語言；同程序替代方案則要求後端只用一種語言。
  - 若負載測試採用 Artillery，壓測腳本的 JavaScript 處理程式可以重用訊框格式的建構邏輯。
- **尚未確認的前提：**
  - 組員對 TypeScript、React、Node.js 的實際經驗未知，須由本人回報；本提案不假設。
  - 課程是否指定語言或框架未知；Notion 上的「Django」字樣是否來自課程要求需確認。
  - Node.js 單一 `realtime` 實例能承載的連線數未量測，須由壓測確認。
- **成本、維運、學習與交付影響：** 學習成本取決於組員現有經驗（未知）。前後端共用 npm 工具鏈，CI 只需一套安裝與建置流程。
- **影響的文件與工作：** `frontend/app/`、`backend/`（含 `backend/common/`）的目錄結構；CI 工作流程；單元測試工具；容器映像。
- **需要補充的資訊：** 各開發角色對候選語言與框架的實際經驗（本人回報）、課程是否有語言限制。
- **PM 需要批准：** 語言基線（全端 TypeScript 或替代方案）；前端框架。後端 HTTP 框架、WebSocket 函式庫與遷移工具由 BA、BB 依上述資訊提出後定案。

<a id="proposal-load-tool"></a>
### 負載測試工具

- **提案主責：** QA 提案；維運提供壓力產生器環境；BA 提供 WSS 情境。
- **主要推薦方案：** Artillery 的 WebSocket 引擎（[官方說明](https://www.artillery.io/docs/reference/engines/websocket)），加上自訂 JavaScript 處理程式，負責建立 HINE 訊框（UUID、`correlation_id`）與計算延遲。情境依既有規劃：
  1. 1,000 → 5,000 → 10,000 條連線，每條完成 W01／W02 並維持 W03／W04 心跳。
  2. W05→W06 ACK 延遲，以 `correlation_id` 配對。
  3. 跨節點的 W07 遞送延遲：傳送端與接收端使用不同連線，以接收時間計算。
  4. 大量重連後以 W15 補回。

  結果依 [DO-05](prd/devops.md#do-05) 記錄環境。
- **替代方案：** JMeter 加 WebSocket Samplers 外掛。JMeter 本身不支援 WebSocket，需安裝該外掛；外掛的請求／回應取樣器可以等待對應的回應訊框。適合 QA 成員已熟悉 JMeter 的情況。
- **推薦依據：**
  - Artillery 原生支援 WebSocket，測試設定是純文字檔，可以在 PR 中審查，並以 CLI 在 CI 執行。
  - HINE 的每個訊框都需要產生 UUID 與配對 `correlation_id`，Artillery 的 JavaScript 處理程式可以直接完成；若技術棧採用 TypeScript，也與開發語言一致。
  - JMeter 需要第三方外掛，測試計畫是 `.jmx` XML，在 PR 中較難審查。
- **尚未確認的前提：**
  - Artillery 內建指標不包含以 `correlation_id` 配對的 ACK 延遲，需要自訂程式碼；須以小規模試跑確認可行。
  - 單台壓力產生器能維持的連線數未量測，產生器數量須依試跑決定。
  - 在 GCP 上需以多台產生器各自執行並合併結果；Artillery 內建的分散式執行是否支援 GCP 未確認。
  - 壓力產生器不得與受測系統共用主機。
- **成本、維運、學習與交付影響：** 壓力產生器 VM 的費用由維運估算；學習成本是 Artillery 設定與 JavaScript 處理程式。
- **影響的文件與工作：** `tests/load/`、[QA-05](prd/qa.md#qa-05)、[DO-05](prd/devops.md#do-05)、[REQ-18](testing/acceptance-matrix.md#req-18)。
- **需要補充的資訊：** QA 成員對 Artillery 或 JMeter 的經驗、壓力產生器的預算。
- **PM 需要批准：** 工具選擇；壓力產生器環境的預算。10,000 連線是測試階段，不是容量目標。

## 決策治理

在授權決策正式記錄前，候選內容仍未批准，不得視為正式營運值或既定政策實作。記錄決策負責人、日期、選項、理由，以及所需的契約／PRD 修訂。僅更新本登錄表不會修訂 API／事件 ID、標準資料、ACK／游標／同步語意，也不構成批准。

本輪交叉審查只授權局部文件修訂，不是上述或 S／E1／多分頁產品政策的簽核；無明確批准依據者繼續待批准。真正批准時只記錄實際項目、範圍、相依與依據，不捏造日期或其他成員同意；尚未整合完標示「行為已批准、契約待整合」，不得提前宣稱可依完整介面開發。文件批准亦不等於產品實作授權。

本輪範圍澄清：FB-04 僅用[公開 ID 查詢](contracts/interface-contract.md#contact-id-lookup)，關鍵字搜尋未納入；群組彙總仍依原待決列，不阻擋一對一；[本地持久保存](contracts/interface-contract.md#local-persistence-boundary)是既有重試／回條／同步義務，不是新增完整離線應用程式／PWA，也不選定新儲存技術。
