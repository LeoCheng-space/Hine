# 文件導覽

專案文件依系統職責分類。HINE-IC-0.4 文件方向依 2026-10-01 PM 決議整合；決議為文件政策，不代表已實作或已有測試結果。

## 按角色閱讀

| 角色 | 專屬需求文件 | 職責 | 必讀共用文件 |
|---|---|---|---|
| 前端 A（FA） | [前端 A 需求文件](prd/frontend-a.md) | 聊天介面、應用程式共用 WSS、訊息狀態與同步投影、響應式聊天互動 | [共用介面契約](contracts/interface-contract.md)、[網頁／響應式介面](ui/web-rwd.md#web-rwd)、[驗收矩陣](testing/acceptance-matrix.md) |
| 前端 B（FB） | [前端 B 需求文件](prd/frontend-b.md) | 工作階段與認證權責、聯絡人、個人資料、路由；不含推播權杖用戶端（本版範圍外） | [共用介面契約](contracts/interface-contract.md)、[網頁／響應式介面](ui/web-rwd.md#web-rwd)、[驗收矩陣](testing/acceptance-matrix.md) |
| 後端 A（BA） | [後端 A 需求文件](prd/backend-a.md) | WSS 入口、心跳、暫態在線狀態、事件路由、同步入口 | [共用介面契約](contracts/interface-contract.md)、[驗收矩陣](testing/acceptance-matrix.md)、[PM 決議事項](decisions.md) |
| 後端 B（BB） | [後端 B 需求文件](prd/backend-b.md) | REST、PostgreSQL 權威狀態、授權、持久化事件流與附件；不含推播意圖（本版範圍外） | [共用介面契約](contracts/interface-contract.md)、[PM 決議事項](decisions.md)及[驗收矩陣](testing/acceptance-matrix.md) |
| 維運（DO） | [維運需求文件](prd/devops.md) | 路由、部署設定與密鑰、持續整合／持續交付、健康狀態、監控與交付 | [共用介面契約](contracts/interface-contract.md)、[PM 決議事項](decisions.md)及[驗收矩陣](testing/acceptance-matrix.md) |
| 品質驗證（QA） | [品質驗證需求文件](prd/qa.md) | 未來驗收、契約與隱私檢查、復原、響應式與效能驗證 | [驗收矩陣](testing/acceptance-matrix.md)、[共用介面契約](contracts/interface-contract.md)及[PM 決議事項](decisions.md) |

**各角色必讀順序：** 先讀[系統架構](architecture/README.md)，掌握元件邊界、資料權威與關鍵流程；再讀自己的需求文件，掌握範圍、情境、驗收條件與交接事項；接著依角色文件連結查閱共用契約中的標準介面；最後以[驗收矩陣](testing/acceptance-matrix.md)確認跨角色結果，並以[PM 決議事項](decisions.md)查閱 2026-10-01 的政策決議。前端 A／B 另須閱讀[共用網頁／響應式介面規格](ui/web-rwd.md#web-rwd)。

**整合查找順序：** 先查[共用介面契約](contracts/interface-contract.md)，再查[依需求編列的驗收矩陣](testing/acceptance-matrix.md)、[決策登錄表](decisions.md)及相關角色需求文件。較早的[整合版六角色 0.4 文件](HINE-IC-0.4-role-prds.md)僅作歷史來源保存，不是現行或共同權威來源；現行導覽以六份拆分角色需求文件和獨立契約為準。

**近期開始開發：** 先讀[首輪串接基線](contracts/interface-contract.md#integration-baseline)與[共同介面變更流程](../CONTRIBUTING.md#interface-changes)。PM 已確認 EntityID 上限 128、text 非空且有效範圍 1～4096；權威驗證由後端負責，文字由 BB 在持久化前判定，前端提示只是 UX，不要求各語言重現相同算法。先對齊近期一對一文字路徑；模組內實作自由，其餘介面在相應串接前共同確認，不需一次鎖死整份規格。PM 確認與尚未取得的成員對接確認分別記錄於[分輪決策紀錄](decisions.md#incremental-interface-governance)；尚未產品驗證。


## 按問題查找

- [系統架構與部署拓樸（推播流程本版範圍外）](architecture/README.md)
- [近期串接基線與後端權威長度驗證](contracts/interface-contract.md#integration-baseline)
- [共同修改介面的流程](../CONTRIBUTING.md#interface-changes)
- [關鍵即時流程：連線、傳送、群組事件、附件（推播範圍外）](architecture/README.md#arch-flows)
- [REST API 登錄表 A01–A25](contracts/interface-contract.md#rest-api)（本版提供 A01–A22；A23–A25 僅保留 ID）
- [WebSocket 事件登錄表 W01–W22](contracts/interface-contract.md#websocket-events)（本版提供 W01–W20；W21／W22 僅保留 ID）
- [共用資料字典](contracts/interface-contract.md#data-dictionary)
- [錯誤與重試規則](contracts/interface-contract.md#error-rules)
- [後端 A↔B 內部交接契約](contracts/interface-contract.md#internal-handoffs)
- [授權失效與提交後通知](contracts/interface-contract.md#internal-notify-invalidation)
- [架構決策與 PM 決議](decisions.md#architecture-proposals)
- [部署設定](contracts/interface-contract.md#deployment-config)
- [響應式網頁介面](ui/web-rwd.md#web-rwd)
- [REQ-01–REQ-22 驗收](testing/acceptance-matrix.md#req-01)
- [BA 專用失效分析、故障演練證據與殘餘風險](testing/backend-a-failure-analysis.md)
- [決議紀錄](decisions.md)
- [文件變更紀錄](CHANGELOG.md)

## 來源與狀態

現行 HINE-IC-0.4 規格依 2026-10-01 PM 決議整合；決議不表示已實作、部署或完成測試。較早的整合版[契約](HINE-IC-0.4-contract.md)與[六角色需求文件](HINE-IC-0.4-role-prds.md)僅作歷史來源保存，並非共同權威文件或現行導覽目標。[變更紀錄](CHANGELOG.md)說明來源、增補內容及未變更的介面識別碼。歷史 HINE-IC-0.3 資料唯讀。
