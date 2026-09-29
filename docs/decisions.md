# HINE-IC-0.4 — 待決策事項

**狀態：** 本表供審閱；列入本表不代表任何項目已獲批准。[共用介面契約](contracts/interface-contract.md)、[角色 PRD](README.md#按角色閱讀)及[Web/RWD 候選規格](ui/web-rwd.md#web-rwd)中標示待批准的內容仍屬提案。本表集中整理尚未定案的政策、成本／影響與相關負責角色，不授權實作，也不表示已有部署行為。

| 決策項目 | 狀態與待選事項 | 決策成本／影響 | 相關負責角色與來源 |
|---|---|---|---|
| <a id="decision-web-push"></a>Web Push 範圍與供應商 | 待決。決定是否納入瀏覽器推播；若納入，須批准供應商、訂閱生命週期、權限、前景抑制規則及交付／驗收契約。A23/A24 維持原生 `ios|android`，本規格未定義瀏覽器 API／事件。 | 需新增供應商整合、瀏覽器權限與訂閱生命週期、service worker／安全／隱私審查、維運密鑰及 QA 測試矩陣；若暫不納入，則只維持原生 token 行為。 | PM 與 [BB](prd/backend-b.md#bb-08)、[FB](prd/frontend-b.md#fb-06)、[DO](prd/devops.md#do-02)、[QA](prd/qa.md#qa-06)；[契約](contracts/interface-contract.md#api-a23)、[Web UI](ui/web-rwd.md#web-rwd)。 |
| <a id="decision-rwd"></a>Web 響應式版面與互動 | 待批准候選版面斷點／頁面配置、路由允許清單、無障礙與觸控規則、輸入／IME、捲動／自動跟隨及已讀可視條件。已確認基線為桌面、平板及手機瀏覽器共用單一 Web app；不推定原生 App／PWA 範圍。 | 決定不同寬度與輸入方式下的前端設計、實作及 QA 範圍；閾值調整會影響已讀狀態與測試涵蓋。 | PM 與 [FA](prd/frontend-a.md#fa-08)、[FB](prd/frontend-b.md#fb-07)、[DO](prd/devops.md#do-06)、[QA](prd/qa.md#qa-06)；[Web/RWD](ui/web-rwd.md#web-rwd)。 |
| <a id="decision-device-id"></a>DeviceID 核發、重用與重新安裝 | 待決。決定重新安裝、切換帳號及遺失本機 DeviceStore 時，伺服器核發與重用 DeviceID 的界線。DeviceID 仍為不透明識別碼，並非憑證。 | 影響帳號／裝置綁定、復原、推播 token 所有權、登出及隱私；不得削弱驗證。 | PM/BB/FB/BA；[A02](contracts/interface-contract.md#api-a02)、[Session 字典](contracts/interface-contract.md#data-dictionary)。 |
| <a id="decision-activity-push"></a>Activity lease 與未知狀態推播受眾 | 待決。決定 lease 時長／更新方式，以及背景或未知狀態裝置是否可收到不含訊息內容的通用提示。W21/W22 及相關政策均為提案。 | 影響即時流量、Redis 不確定狀態處理、推播量、隱私及多裝置驗收；不得將推播視為收件回執。 | PM 與 [FA](prd/frontend-a.md#fa-07)、[BA](prd/backend-a.md#ba-07)、[BB](prd/backend-b.md#bb-08)、[QA](prd/qa.md#qa-02)；[W21](contracts/interface-contract.md#event-w21)、[W22](contracts/interface-contract.md#event-w22)。 |
| <a id="decision-operational-values"></a>營運上限與速率 | 待決。批准同步分頁／掃描上限、上傳大小與 MIME allowlist、heartbeat 間隔／逾時、activity lease、前景同步週期、訊息／登入速率限制及供應商憑證缺漏政策。契約中的數值均為候選值，不是 SLO。 | 影響資源使用上限、使用者體驗／重試、基礎設施容量、濫用防護、readiness 及 QA 門檻。 | PM/DO 與 [BA](prd/backend-a.md#ba-08)、[BB](prd/backend-b.md#bb-07)、[FA](prd/frontend-a.md#fa-07)、[QA](prd/qa.md#qa-05)；[部署設定](contracts/interface-contract.md#deployment-config)。 |
| <a id="decision-group-policy"></a>群組角色、人數與成員政策 | 待決。決定既有 admin/member 與最後一位 admin 不可移除之外的人數及角色規則；目前未定義 ban 操作。 | 影響授權交易、成員 UI、feed 扇出與容量；政策須維持 A14/A16→W11、A15/A17→W20、A18→W12 的對應。 | PM/BB 與 [FB](prd/frontend-b.md#fb-05)、[BA](prd/backend-a.md#ba-05)、[QA](prd/qa.md#qa-04)；[REST](contracts/interface-contract.md#rest-api)、[事件](contracts/interface-contract.md#websocket-events)。 |
| <a id="decision-group-receipts"></a>群組回執可見性 | 待決。決定是否提供群組回執投影，以及其可見對象與彙總政策。 | 影響隱私、扇出、投影語意及用戶端狀態 UI；後端逐收件者回執狀態仍須區別處理。 | PM/BB 與 [BA](prd/backend-a.md#ba-04)、[FA](prd/frontend-a.md#fa-04)、[QA](prd/qa.md#qa-01)；[回執字典](contracts/interface-contract.md#data-dictionary)。 |
| <a id="decision-history-membership"></a>加入前與離開後的歷史訊息 | 待決。定義使用者加入前及移除／離開後的歷史可見規則；現有授權檢查禁止未授權的後續內容存取。 | 影響 A19/A22 授權、snapshot/feed 過濾、保留預期、隱私及遷移／測試案例。 | PM/BB 與 [FA](prd/frontend-a.md#fa-05)、[BA](prd/backend-a.md#ba-06)、[QA](prd/qa.md#qa-03)；[歷史 API](contracts/interface-contract.md#api-a19)、[內部交接](contracts/interface-contract.md#internal-handoffs)。 |
| <a id="decision-attachment-policy"></a>附件限制與支援類型 | 待決。批准檔名、大小、MIME 限制及續期／過期政策；候選 20 MiB 與 allowlist 尚未批准。 | 影響儲存／輸出流量成本、濫用掃描、上傳體驗、signed grant 生命週期及安全／QA 涵蓋。 | PM/BB/DO 與 [FA](prd/frontend-a.md#fa-06)、[FB](prd/frontend-b.md#fb-03)、[QA](prd/qa.md#qa-04)；[A20](contracts/interface-contract.md#api-a20)–[A25](contracts/interface-contract.md#api-a25)。 |
| <a id="decision-historical-slos"></a>歷史效能與重連目標 | 待決。確認先前記錄的目標哪些仍有效；使用前須批准工作負載、環境、門檻及量測方法。 | 影響容量規劃與發佈準則；保留過時目標可能造成錯誤的通過／失敗判斷，移除則須明確替代。 | PM/QA/DO 與 [BA](prd/backend-a.md#ba-08)、[BB](prd/backend-b.md#bb-06)；[驗收 REQ-18](testing/acceptance-matrix.md#req-18)。 |

## 決策治理

在授權決策正式記錄前，候選內容仍未批准，不得視為正式營運值或既定政策實作。記錄決策負責人、日期、選項、理由，以及所需的契約／PRD 修訂。僅更新本登錄表不會修訂 API／事件 ID、標準資料、ACK/Cursor/sync 語意，也不構成批准。
