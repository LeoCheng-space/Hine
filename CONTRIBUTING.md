<a id="contributing-to-hine"></a>
# HINE 協作指南

此流程刻意保持簡單，方便仍在學習 Git 的組員使用。

<a id="daily-workflow"></a>
## 日常工作流程

1. 從 `main` 更新本機儲存庫。
2. 為單一工作建立新分支。
3. 完成變更。
4. 使用清楚的訊息提交。
5. 推送分支。
6. 建立合併請求（PR）。
7. 等待審查與持續整合檢查。
8. 僅在批准後合併。

<a id="branch-naming"></a>
## 分支命名

使用以下任一格式：

- `feature/<short-name>`
- `fix/<short-name>`
- `docs/<short-name>`
- `chore/<short-name>`

範例：

- `feature/chat-ui`
- `feature/websocket-heartbeat`
- `fix/login-token-expiry`
- `docs/api-contract`

<a id="important-rules"></a>
## 重要規則

- 不得直接推送至 `main`。
- 不得強制推送共用分支。
- 開始新工作前，先拉取最新的 `main`。
- 每個分支只處理一項工作。
- 不得盲目接受所有變更來解決合併衝突。
- 不得提交密碼、API 金鑰、權杖、憑證或使用者私密資料。

<a id="pull-request-checklist"></a>
## 合併請求檢查清單

建立合併請求前，確認：

- 程式碼可在本機執行。
- 相關測試通過。
- 已移除除錯程式碼與暫存檔。
- 已記錄 API／WebSocket／資料庫變更。
- 不含機密資訊。
- 合併請求說明了變更內容與驗證方式。

<a id="commit-message-examples"></a>
## 提交訊息範例

- `feat: 新增 WebSocket 重連處理`
- `fix: 防止重複寫入訊息`
- `docs: 新增 REST API 契約`
- `test: 新增訊息同步整合測試`
- `chore: 更新 GitHub Actions 工作流程`
