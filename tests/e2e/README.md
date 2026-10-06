<a id="e2e-tests"></a>
# 端對端測試

登入、聯絡人、傳訊、群聊、上傳、重連與離線同步等端對端使用流程。
瀏覽器 E2E 與協定負載測試分開記錄；瀏覽器驗收對象為 Chrome／Edge 桌面版及 Android Chrome，並記錄實測版本。

## 可執行協定串接檢查（不等於瀏覽器 E2E）

共用唯一一套 [`../load/protocol.py`](../load/protocol.py)，設定格式／完整命令見
[`../load/README.md`](../load/README.md)。現行 Python／aiohttp 工具依使用者跨角色補完指示維護，
不代表特定組員已核准；本目錄不另建第二套框架。

```sh
.venv/bin/python tests/load/protocol.py e2e --config .local/qa-users.json
.venv/bin/python tests/load/protocol.py e2e --config .local/qa-users.json \
  --reconnect --state .local/qa-sync.sqlite
.venv/bin/python -m unittest discover -s tests/e2e -p 'test_protocol_tool.py'
```

第一個命令需要真實 BB A02（或已提供 AccessSession）、A13、A19，
以及真實 BA W01–W07／W17 與正式持久化／Redis；第二個另需 W13–W16
的完整快照／事件流。工具不提供假 server／product mock，不輸出帳密或訊息本文。
`test_protocol_tool.py` 只保護工具的證據判讀：ACK 不得代替收件成功、C1 不外洩、
M1／本文／order_key 一致、歷史去重與排序、同步邊界／游標原子保存及重播去重；
這些 oracle 單元測試不能當產品 E2E。

## 真實瀏覽器另行驗收

協定 CLI 只量收件 W07 與 QA 自己的 SQLite 同步投影，**本工具**
不提供瀏覽器儲存、UI 呈現、Web Lock 或 Page Visibility 證據。
實際 React Web 與 PostgreSQL API 已提供；父工作另以真實 Chrome 檢查，
結果／尚未執行的正式 VM、Edge、Android Chrome、GCS 案例見[驗收矩陣](../../docs/testing/acceptance-matrix.md)。
不得因 CLI exit0 填「瀏覽器送達／已讀／呈現通過」；工具不發 W08/W09。另記錄：

- Chrome／Edge 桌面版與 Android Chrome 的實測版本、資料集、VM／網路。
- 使用兩個隔離瀏覽器設定檔登入兩帳戶，單操作分頁／Web Lock 與工作階段錯誤分流。
- 寄件送出→收件實際保存／呈現時間；原本文、同一 M1、排序、ACK 遺失重試不重複。
- 斷線／重新整理後持久識別資訊、待送意圖和保存游標；恢復 ≤100 則時實際呈現耗時。
- 本機持久化後才 W08；實際符合 V3 可見條件後才 W09；IME、RWD、路由／權限案例。

實測結果按環境／場景分列，不把協定、oracle 測試或 BA 記憶體 authority
當作瀏覽器／PostgreSQL／正式部署驗收。
