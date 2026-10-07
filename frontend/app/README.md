<a id="frontend-app"></a>
# Web 應用程式（FA＋FB）

本目錄交付單一 React／TypeScript 響應式 Web 應用，整合帳戶、路由、聯絡人、個人資料、群組及聊天。主要實作位於 `src/`：`index.tsx`／`App.tsx` 組裝入口與頁面，`session.ts`／`router.ts`／帳戶與資料頁負責 FB，`chat.ts`／`repository.ts`／`ChatView.tsx`／`read-observer.ts`／`attachment-transfer.ts` 負責 FA。契約以 [`docs/contracts/interface-contract.md`](../../docs/contracts/interface-contract.md)、[Web/RWD 規格](../../docs/ui/web-rwd.md)與[前端 PRD](../../docs/prd/frontend-a.md)、[前端 B PRD](../../docs/prd/frontend-b.md)為準。

## 已實作行為

- 單一 SessionController、ChatController、WebSocket；SessionContext 只在記憶體保存 access token。裝置識別資訊依帳號保存於 DeviceStore，不是憑證。
- DeviceStore 登入查找與保存使用 Python3.12／Unicode15.0.0 的完整 casefold；未曾輸入的等價 email 拼法仍綁原伺服器 DeviceID，舊 alias 只遷移識別資訊，不搬動草稿／原 C1 分區。`email-casefold-data.ts` 由 `generate-email-casefold.py` 產生，不使用瀏覽器版本不同的 lowercase／locale／NFKC 代替後端語意。
- 登入、註冊、更新、登出與認證前持有同來源獨占 Web Lock `hine-session`；沒有 Web Locks 時阻止聊天，不提供無鎖退路。
- IndexedDB 以帳號／裝置分區保存訊息投影、SyncCursor、待送 C1、待確認回條、草稿與捲動錨點。投影與游標在同一交易原子提交；待送 intent／回條先保存再送。儲存不可用即停止聊天，沒有記憶體替代持久化。
- 初始化以完整多頁快照暫存，合併同步期間觀察到的即時事件後才切換投影及安裝 H；W08 只有在本機保存成功後才回報。送達、已讀回條單調合併；前景同步、重連與重複事件依既有游標／事件 ID 規則恢復。
- 依目前授權處理撤權／重加入；不把本機資料當伺服器權威。未讀徽章取伺服器最近查詢值。已讀觀察僅適用他人訊息，泡泡最大可視交集達 50% 並連續 500ms；頁面隱藏、遮罩或條件中斷即重置。
- 聊天清單消費既有 `hine-conversations-changed`，以 A11 刷新；一次 in-flight 加合併 trailing refresh，保留伺服器未讀及分頁，舊帳戶／裝置／工作階段／token／已卸載請求不得寫 DOM 或 cache。
- 群組 A12 只在 queued IDB commit 內套用不低於已安裝 metadata version floor 的回覆；floor 與 self-join 授權界線分離，detail cache eviction 不會抹掉比較。已提交的 live／feed metadata 及 staged snapshot replay 都推進同一私有 floor；equal／direct-null 仍可更新未讀，舊成功回覆不假造 unknown outcome／重連。
- 初次 A14 的 fresh self-join 與開啟 A12 交錯時，pending route 只交接至同一 opening identity／epoch／ticket 的最新 join 授權交易；原舊read保持取消，不重試失敗handoff或重發競爭A12。關閉路由、withdraw／self-removal、disconnect／換binding會撤銷intent，不啟動舊房間。
- 附件經 A20／A21 取得及確認 ready 後，瀏覽器直接透過短效 signed URL 與 GCS 傳輸 bytes；展示與下載仍依授權，不將 signed URL 寫入訊息或日誌。
- PUT 非成功或結果不明先核对原 A21；只有原 attempt 確認 `UPLOAD_NOT_READY` 且 grant 尚有效才允許重 PUT，同 bytes／SHA／key／create-only headers。412 不冒稱成功，A21 不明結果不盲目重 PUT，過期 grant 不續期。

## 版本與本機命令

依 `package.json` 固定使用 Bun 1.4.2、React／react-dom 19.3.0、TypeScript 7.0.2、`@types/react`／`@types/react-dom` 19.3.0 與 `@types/bun` 1.4.2。由 `frontend/app/` 執行：

```sh
bun install --frozen-lockfile
PUBLIC_ORIGIN=https://example.invalid bun run build
bun run typecheck
HINE_CASEFOLD_PYTHON=python3.12 bun run test
python3.12 generate-email-casefold.py --check
```

建置需要有效 HTTPS origin 格式的 `PUBLIC_ORIGIN`（僅用於產生同源 `/api/v1`、`/ws/v1` 執行期設定，不含密鑰）；輸出至 `dist/`。Typecheck 與測試不需服務端。瀏覽器產品操作需 HTTPS、同來源 API／WSS、Cookie、IndexedDB、WebSocket、Page Visibility 與 Web Locks；缺少契約要求的能力時不啟用聊天，沒有無鎖退路。正式支援驗收政策列於 B1；僅已實際測試的瀏覽器／版本可宣稱相容。沒有 PWA、原生應用或完整離線模式。

Typecheck 不需服務端；Unicode 回歸／artifact 重生檢查另需 Python3.12 與其 Unicode15.0.0 標準資料，腳本會拒絕不同版本。`HINE_CASEFOLD_PYTHON` 可指向實際 Python3.12 interpreter。不要手動修改生成表或以狹窄字元例外掩蓋完整 canonical email 規則。
