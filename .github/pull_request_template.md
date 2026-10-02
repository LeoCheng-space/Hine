<a id="summary"></a>
## 摘要

說明此合併請求的變更內容。

<a id="related-task--issue"></a>
## 相關工作／議題

附上相關議題或工作的連結。

<a id="how-to-test"></a>
## 驗證方式

說明審查者應如何驗證此變更。

<a id="interface-impact"></a>
## 共同介面影響

無跨模組影響時填「無，僅模組內實作」，不需介面專項批准。有影響時依[共同變更流程](../CONTRIBUTING.md#interface-changes)說明：

- 受影響介面 ID、原格式／行為與新格式／行為、變更原因。
- 提供方與直接受影響的消費方；共同確認紀錄。
- 同步的契約／範例／驗收／實作，以及相關 PR 依賴與共同切換方式。
- 已執行的驗證與未取得的證據；文件檢查不代表產品串接通過。
- 核對 W05 六階段與唯一 BB 5/s burst10 產品 quota：C1 後／持久化前只判新合法 intent；列 quota exhausted 的五個結果、拒絕無持久化／C1映射／W06。BA transport/frame defense 另屬防護，不重現 canonical／產品 quota。BB 發通知前驗 IDs，BA 對 authenticated BB notice 僅結構驗證；EntityID 矩陣包含 A06 非 null／A10 且保留 A06 null，其他 PM 邊界不變。
- 分開記錄 PM 政策確認與直接受影響成員確認；沒有實際證據不替 FA／FB／BA／BB 宣稱已確認。文件／CI 檢查不代表產品測試通過，未執行產品情境須明列「尚未產品驗證」。


<a id="checklist"></a>
## 檢查清單

- [ ] 我已在本機測試此變更。
- [ ] 我未提交機密或私密資料。
- [ ] 我已更新相關文件／規格。
- [ ] 已記錄 API／WebSocket／資料庫變更。
- [ ] 共同介面有變更時，受影響提供方／消費方已共同確認，相關定義與切換方式已同步；無變更已明列。
- [ ] 我已移除除錯程式碼與暫存檔。
- [ ] 持續整合檢查通過。
