# HINE UI 改版設計（Telegram 式手感，HINE 品牌）

- 日期：2026-10-17（v2.2：同日依程式碼審查、獨立 Review 與使用者 6 項決策修訂）
- 分支：`feature/ui-refresh`
- 狀態：v1 已由使用者逐段確認；v2.1 依實際程式碼補強 P0／P1；v2.2 落實使用者對 §13 的決策，並依契約查證修正排序鍵（R10）。
- 範圍：前端視覺與互動流程重構，保留既有後端契約、持久化語意、授權邊界與資料一致性

## 0. 修訂摘要

| 編號 | 修訂 | 原因（證據） |
|---|---|---|
| R1 | 對話清單在**已載入範圍內**依各對話最新一則訊息的伺服器時間 `created_at`（只升不降）排序，並明示限制〔v2.2 由 `order_key` 改為 `created_at`，見 R10〕 | A11 依隨機 `conversation_id` 排序（`backend/api/src/hine_api/conversations.py:55-59`、`domain.py:18-19`）；清單重新載入一律回到第一頁（`frontend/app/src/ContactsPage.tsx:41-44`），且每次背景同步成功（約每 10 秒）都會觸發（`chat.ts:271`、`api.ts:5`）；本機訊息會暫時清空或過舊（`chat.ts:100,104-111,117`、`repository.ts:34-42`）|
| R2 | 進場動畫只用於尾端新增訊息；`ReadObserver` 不計入動畫未完成的泡泡；聊天室不做 opacity 過場；固定日期改為捲動區外的浮動膠囊 | 已讀量測只用 `getBoundingClientRect`，不看 opacity（`read-observer.ts:42`）；祖先的 opacity 過場不會出現在泡泡的 `getAnimations()`；遮擋演算法只保留最大區塊，捲動區內的遮擋物會造成漏讀（`read-observer.ts:33-36`）|
| R3 | 名稱與頭像 ID 改為依帳號分區、可取消、有並行上限、具每位使用者版本號的記憶體快取 | 一對一 `membership_version` 恆為 null（`chat.ts:21`）；改名與換頭像沒有推播（`profiles.py:35-61`）；頭像可見性取決於聯絡人與共同對話（`domain.py:98-104`）；現行取名稱為無上限 N+1（`ChatView.tsx:47`）|
| R4 | 保留連線狀態文字、`.message-meta` 狀態文字、`.chat-header`、路由標題 | CI 驗收依賴（`tests/browser/browser_acceptance.py:509,604`）|
| R5 | 搜尋只比對名稱與對話標題 | `docs/ui/web-rwd.md:46` |
| R6 | 導覽：寬版保留常駐窄圖示欄，窄版為頂部列＋☰ 選單〔v2.2 使用者已確認，取代 v1「寬版改為 ☰」〕 | `docs/ui/web-rwd.md:36-39` 的 2026-10-01 PM 決議要求寬版「導覽與內容並列」 |
| R7 | ☰ 選單與建群組使用原生 `<dialog>`、關閉即卸載；建群組掛在外殼層級；✎ 浮動按鈕在 Phase 4 才加入 | `aria-modal` 未卸載會永久暫停已讀（`read-observer.ts:29`）；未完成意圖須在重新整理後還原（`GroupsPage.tsx:32-37`）；兩個「建立群組」按鈕並存會使 CI 定位衝突（`browser_acceptance.py:705`）|
| R8 | 移除「頭像位元組 LRU」層 | 現有 `Avatar` 每列自取並在卸載時釋放已足夠，額外快取沒有對應需求 |
| R9 | 新增 IME、767／768、Esc 焦點返回、訊息 DOM 不變式等 CI 檢查，並以不會假通過的方式量測 | 這些行為目前只在一次性證據中出現（`docs/testing/evidence/product-browser.json`）|
| R10 | 跨對話排序不得使用 `order_key` | 契約 C11 規定 `order_key`「只在同一對話比較……不當作時間戳記」（`docs/contracts/interface-contract.md:670`）；雖然目前實作取自全域序列 `nextval('message_order')`（`messages.py:99`、`002_domain.sql:17`），但這是未承諾的實作細節。改用契約保證的 `created_at`（伺服器產生的 ISO-8601 UTC，`interface-contract.md:101`；毫秒精度，`support.py:23-24`）|
| R11 | 清單保留供 `review-shell-native.ts` 定位的掛點：`.list-item`、`data-conversation-id`、標題 `strong`、`.unread`、載入中才出現的 `.chat-list [role="status"]`、`.actions` 內「載入下一頁」 | `frontend/app/tests/review-shell-native.ts:125-135,217-228` |
| R12 | 群組管理頁以 `key={conversationId}` 隔離實例，並讓卸載後的變更請求不再導覽；以 CI 瀏覽器回歸檢查證明 | `GroupsPage.tsx:98-99` 載入回覆可覆蓋新頁；`:96` `memberIntent` 只以使用者 ID 為鍵，跨群組沿用冪等鍵；`:107` 舊實例在退出群組後仍會 `onNavigate('/chats')` |

## 1. 目標與決策（v1 已確認）

| 項目 | 決定 |
|---|---|
| 參考對象 | Telegram 的版面與互動手感，不照抄外觀 |
| 品牌 | 沿用 HINE 品牌並精緻化：深青綠主色、H 對話泡泡標誌、標語「讓每一次對話，更靠近。」 |
| 主要裝置 | 桌面優先；手機（<768px）維持好用但不做完整精修 |
| 範圍方案 | 方案 A：視覺與動畫、對話清單、聊天室、導覽、建群組改為勾選聯絡人；個人檔案／聯絡人／群組管理維持獨立頁面只換外觀 |
| 導覽（v2.2 取代 v1「寬版 ☰」） | 寬版常駐窄圖示欄、窄版頂部列＋☰ 選單；理由：符合 `web-rwd.md:36-39` PM 決議，且接近 Telegram Desktop 左側欄（2026-10-17 使用者確認） |
| 不做 | 深色模式、側邊滑出面板、自動載入較早訊息、後端或 API 變更、訊息虛擬化 |

## 2. 責任邊界

**允許修改**：React 元件、CSS 與設計 token、前端導覽與互動、純展示資料推導、前端測試、`browser_acceptance.py` 的操作步驟與定位，以及 §7.3 所述 `read-observer.ts` 的保守化修改。

**不得修改**：REST、WebSocket、PostgreSQL schema／migration、Redis 語意、JWT／Session 權威邏輯、IndexedDB store 與記錄結構、已讀與離線同步語意、未讀數語意、`ChatController` 的公開 API。

不改後端就無法達成的需求，列入第 12 節「設計限制」，並依第 13 節「決策紀錄」另開 Issue。

## 3. 必須保留的既有行為

- 路由與權限檢查：`/login`、`/register`、`/chats`、`/chats/{id}`、`/contacts`、`/profile`、`/groups/{id}/manage`。
- 單一操作分頁鎖、工作階段刷新與登出、能力不足阻擋畫面。
- 768px 單一斷點，CSS 統一寫成 `(width < 768px)`（目前 `Shell.css:113` 與 `Chat.css:65` 寫法不同）。
- 輸入規則：Enter 傳送、Shift+Enter 換行、Ctrl／⌘+Enter 傳送、輸入法組字中 Enter 不送出、文字 1–4096 code points。
- 已讀判定：他人訊息、最大可能交集的 50%、連續 500ms，遮罩或頁面隱藏時不計。
- 草稿、捲動錨點、「載入較早訊息」、跳至最新（`chat.jumpLatest`，重新取得最新頁）、原意圖重試、撤權撤離、附件流程。
- 未讀數只取 A11 回傳值；群組不顯示已讀人數。
- 建群組的冪等鍵與原意圖保存（`GroupCreationIntentStore`）。
- 訊息 DOM 不變式：每則已持久化訊息恰好一個 `[data-message-id]`（UUID、位於泡泡本體）；`data-read-eligible` 不變；`.message-scroller` 內沒有 `[data-read-occlusion]`；非訊息元素不帶 `data-message-id`。
- 保留的定位：`.chat-room`、`.chat-header small[role=status]`（文字沿用 `CONNECTION_LABEL`）、`.chat-composer textarea`／`#chat-draft`、`.send-button`、`.message-meta`（含狀態文字）、`.chat-list`、`.member-list li`、`.narrow-back`、`.app-nav`（窄版頂部列，維持 sticky）、`navigation "主要導覽"`、按鈕名稱「聊天」「聯絡人」「個人檔案」「登出」「群組資訊」「前往群組管理」「移除」。
- 匯出名稱不變：`GroupCreationIntentStore`、`AvatarSaveRecovery`、`ContactLookupLifetime`、`fetchAvatarBytes`、`AttachmentRecovery`、`usePagedList`、`Avatar`。

## 4. 視覺系統（v1 已確認）

### 4.1 配色 token

| Token | 值 | 用途 |
|---|---|---|
| `--brand-900` | `#0f3d35` | 焦點外框、深色文字底 |
| `--brand-700` | `#1b6558` | 主色：主要按鈕、未讀徽章、已讀勾勾、選取 |
| `--brand-500` | `#2f8a76` | hover |
| `--brand-100` | `#dff1e8` | 自己的泡泡 |
| `--brand-50` | `#eef6f1` | 選取列底色 |
| `--surface` | `#ffffff` | 對方泡泡、卡片 |
| `--canvas` | `#e9efe9` | 聊天背景 |
| `--text`／`--muted`／`--line`／`--danger` | `#18312e`／`#60716a`／`#dce5de`／`#a62d3b` | 文字、次要文字、分隔線、錯誤 |
| `--accent-1`…`--accent-6` | `#1b6558`、`#7a4fb5`、`#b5532f`、`#2f6fb5`、`#9a7a12`、`#b03a6b` | 頭像底色與群組寄件者名稱 |

文字與背景組合對比至少 4.5:1；`--accent-*` 白字或白底使用時，於 Phase 1 以本機截圖與對比計算確認。

### 4.2 品牌元素

- 泡泡圓角 16px，自己的右下角、對方的左下角收尖為 4px；連續訊息只有最後一則收尖。
- 聊天背景：`--canvas` 加低對比 CSS 圖樣（不新增圖檔）。
- 未選對話時右欄顯示 H 標誌與標語。
- 登入、註冊、阻擋畫面套用同一套品牌樣式。

### 4.3 字型、間距、動態

- Inter＋Noto Sans TC；清單名稱 15px／600、預覽 14px、時間 12px；間距 4px 倍數。
- `--motion-fast: 150ms`、`--motion-base: 220ms`，緩出曲線。
- `prefers-reduced-motion: reduce`：關閉 transition、animation 與 WAAPI 動畫（目前 `Shell.css:143` 未關 animation）。
- 捲動區不用 `scroll-behavior: smooth`；保留 `overflow-anchor: none`（`Chat.css:9`）。

## 5. 版面與導覽〔修訂：R6〕

### 5.1 寬版（≥768px）

- **常駐窄圖示欄**（約 72px，`.app-nav`，`<nav aria-label="主要導覽">`）：上方品牌按鈕「HINE 聊天首頁」；圖示按鈕「聊天」「聯絡人」「個人檔案」（可見文字為 tooltip，無障礙名稱即按鈕文字）；Phase 4 加入「建立群組」；底部「登出」。滿足 `web-rwd.md:36-39` 的「導覽與內容並列」，並接近 Telegram Desktop 的左側欄。
- **聊天路由**：圖示欄＋對話清單（約 340px，300–400px）＋聊天室。未選對話時聊天室位置顯示品牌空畫面。
- **聯絡人、個人檔案、群組管理**：圖示欄＋頁面內容。
- 對話清單頂部：搜尋框；清單 h1「聊天」（visually-hidden，供路由焦點）。

### 5.2 窄版（<768px）

- `.app-nav` 變為 sticky 頂部列（帶 `data-read-occlusion` 的效果由 `.app-nav` 既有遮擋規則提供），內含 ☰（「開啟選單」）與品牌按鈕；所有受保護路由都有此頂部列。
- ☰ 開啟 **☰ 選單**：原生 `<dialog>`，`showModal()` 並送出 `hine-overlay-change`；內含 `<nav aria-label="主要導覽">` 與相同項目。Esc、點遮罩或選擇項目後關閉並**卸載**；焦點於 effect cleanup 中先 `close()` 再還給 ☰，若 ☰ 已不存在則聚焦路由標題。選單開啟期間已讀暫停屬預期。
- 清單與聊天室以 `translateX` 切換；畫面外的面板加 `inert`；容器 `overflow: clip`；過場不保留舊聊天室 DOM。保留 `.narrow-back`「← 返回聊天清單」。

### 5.3 路由焦點

每個受保護路由恰好一個 `[data-route-heading]` 可聚焦標題；`App.tsx:60` 改為聚焦此元素。`/chats` 為清單 h1；`/chats/{id}` 為聊天室 h1（清單 h1 不帶屬性）；錯誤頁 h1 亦帶屬性；空狀態維持 h2。

## 6. 對話清單〔修訂：P0-1、P0-3〕

### 6.1 資料來源

| 資料 | 來源 | 規則 |
|---|---|---|
| 清單成員、分頁、未讀 | A11（`usePagedList`，行為不變） | 每頁 20 筆、重新載入回第一頁、游標錯誤從頭載入 |
| 一對一對象 | 依序：`snapshot.messages[id]` 中非自己寄件者 → `snapshot.details[id].members` → 既有 `chat.refreshConversation(id)` | 不直接呼叫 A12 |
| 名稱、頭像 ID | §6.4 使用者摘要快取 | — |
| 最後訊息 | 目前 `snapshot.messages[id]` 最後一則 | 不快取內文 |
| 排序鍵 | §6.2 | 每對話最新 `created_at`，只升不降 |

`refreshConversation` 會重寫本機分區並重新發布，因此只在前兩種來源都沒有對象時呼叫，佇列上限 4、只為可見列呼叫；`RepositoryCancelled` 與 `UNAUTHENTICATED`（資料庫尚未開啟或工作階段更替）視為取消、不顯示錯誤，於下一次清單重新載入或列重新可見時再試，不自動迴圈重試。

### 6.2 排序

- 鍵：每個對話目前見過的最新一則訊息的 `created_at`（`Date.parse` 後的毫秒值），只增不減。**不使用 `order_key`**：契約只保證同一對話內可比較（R10）。
- 鍵表為模組層級、依 `ownerPartition` 分區；owner 改變時清除；對話被撤權時刪除。
- 排序：有鍵者依鍵由新到舊，同鍵依 A11 位置；無鍵者其後並維持 A11 順序。
- 重新排序的時機：只有某對話的鍵前進（收到或送出並已持久化新訊息）時，該對話才移動；沒有新訊息時，背景同步、token 刷新與暫時清空都不改變順序。等待中的意圖沒有伺服器時間，持久化後才上移。
- **已知限制**：
  1. 只排序已載入的對話（R1）；不宣稱未載入對話的活動順序。完整最新活動排序另開 Issue（§13 第 2 項）。
  2. 頁面重新載入或重新登入時鍵表為空，清單會依序以 A11 順序 → 一對一訊息就緒 → 群組驗證完成重排，最多兩次；同一頁面期間不會因暫時清空而沉底。
  3. 排序後，第 2 頁以後在下一次重新載入時被收回的既有行為更容易察覺。
  4. `created_at` 由伺服器時鐘產生；多個 API 實例之間若有時鐘偏差，兩個對話在相差極短時間內收到訊息時的先後可能相反。只影響顯示順序。

### 6.3 列的呈現

- 頭像、名稱、預覽、時間、未讀徽章（`aria-label="N 則伺服器查詢未讀"` 不變）。
- 預覽：自己「你：」、群組他人「名稱：」；圖片「📷 圖片」、檔案「📄 檔案」；空白折疊為單一空格；無訊息為「—」。
- 時間顯示用 `created_at`（今天 `HH:mm`、昨天、7 天內星期、更早 `M/D`、跨年 `YYYY/M/D`，24 小時制 `hourCycle: 'h23'`）。
- 撤權隱藏：對話出現在 `snapshot.denied` 時隱藏；另以依 owner 分區的模組層級集合記錄，保留到下一次 A11 重新載入完成（`disconnect()` 會清空 `observedDenied`，`chat.ts:117`）。
- 骨架列只在清單沒有項目且載入中時顯示。
- 搜尋比對名稱與對話標題，標示「只篩選已載入項目」。
- Phase 2–3 期間沿用現有清單內「＋ 建立群組」；Phase 4 改為 ✎ 浮動按鈕。
- 定位掛點（R11）：每列為 `button.list-item[data-conversation-id]`；標題在列內 `strong`（群組為 A11 `title` 原文）；未讀徽章 `.unread`，文字為伺服器值；`.chat-list` 內唯一的 `role="status"` 只在載入中存在（搜尋提示不用 `role="status"`）；分頁按鈕在 `.actions` 內，文字「載入下一頁」。

### 6.4 使用者摘要快取（P0-3）

| 項目 | 規則 |
|---|---|
| Key | `ownerPartition(user_id, device_id)` ＋ 使用者 ID；僅記憶體 |
| 內容 | `display_name`、`avatar_attachment_id`、取得時間、頭像是否過期 |
| owner 改變 | 整份清除、中止所有請求、遞增 epoch |
| 同 owner token 刷新 | 保留；進行中請求若被 session epoch 拒絕，當作取消 |
| TTL | 5 分鐘；開啟聊天室時對已過期成員重新取得 |
| 頭像過期觸發 | 某群組 `membership_version` 由 n 增為 m（只標記該群組成員）；聯絡人增刪（只標記該使用者）；自己儲存個人檔案時以結果直接更新自己 |
| 不作為觸發 | `hine-conversations-changed`（每次背景同步都會發出）、token 刷新時 `details` 暫時清空 |
| 亂序防護 | 每位使用者一個版本號，`put` 與標記過期時遞增；回覆只在 epoch、owner、該使用者版本號都未變時寫入 |
| 失敗 | 不快取、不往外拋；渲染時退回顯示 ID 或首字 |
| 取消 | 每個 epoch 一個 `AbortController`；清除時中止；同 key 進行中請求共用 |
| 並行 | 上限 4；只為可見列與目前聊天室成員取資料 |

`ChatView` 取名稱改用此快取，取代無上限的 `Promise.all`（`ChatView.tsx:47`）；自己的名稱也經由快取取得（A07 允許查自己），群組資訊不再顯示自己的 ID。☰ 選單與圖示欄的自身名稱、頭像也來自此快取。

## 7. 聊天室〔修訂：P0-2、R4〕

### 7.1 頂部列

- h1（`#chat-title`、`data-route-heading`）只放名稱；頭像在 h1 外。
- 副標題：一對一在線「線上」；群組「N 位成員」。
- `.chat-header small[role=status]` 常駐顯示 `CONNECTION_LABEL`（就緒為「即時連線」），非就緒改警示色。
- 「群組資訊」為圖示按鈕，可存取名稱「群組資訊」，全頁唯一。

### 7.2 訊息

- 分組：同一寄件者、5 分鐘內、同一天的連續訊息為一組；只改 class，不新增外層容器。
- 群組他人訊息：每組第一則顯示寄件者名稱（`--accent-N`），組末則顯示寄件者頭像。
- 日期分隔：清單內一般 `<li role="separator">`，**不 sticky、不帶 data 屬性**，key 為 `date:YYYY-MM-DD`。
- **浮動日期膠囊**：捲動區**外**的獨立元件，帶 `data-read-occlusion`、`aria-hidden="true"`；自帶 state，以 rAF 節流的 scroll 監聽計算頂端訊息日期，只在文字或「是否在最新」改變時更新；在最新位置時以 `hidden` 移除 client rects。
- 時間與狀態放在 `.message-meta`；圖示 `aria-hidden`，狀態文字以 visually-hidden 保留於 textContent：

| 狀態 | 圖示 | 文字 |
|---|---|---|
| 等待傳送 | 🕓 | 等待傳送 |
| 已持久化、核對中 | 🕓 | 已持久保存，正在核對訊息 |
| 伺服器已保存 | ✓ | 已持久保存 |
| 已送達 | ✓✓（灰） | 已送達 |
| 已讀（僅一對一） | ✓✓（主色） | 已讀 |
| 結果不明 | ⚠ | 結果尚未確認 |
| 未傳送 | ⚠ | 未傳送 |

### 7.3 動畫與已讀隔離（P0-2）

- 動畫基準 `baseline`：聊天室授權後第一次渲染時設為目前訊息 ID；`!authorized`（切換聊天室、重連時 `openChat` 先清空目前對話，`chat.ts:341`）時重設為 null。
- 只有「基準存在、且附加在基準最後一則之後」的訊息播放進場動畫；一次超過 3 則（例如離線補回）不播；等待中轉為已持久化的訊息不播。
- 動畫：WAAPI，在既有 layout effect 中 `restoreAnchor()` 之後對泡泡本體執行 opacity 0→1、translateY 8px→0、150ms、`fill: 'none'`；reduced-motion 時不執行。
- `ReadObserver` 保守化：泡泡只要有 `playState !== 'finished'` 的動畫，該幀不計入並歸零計時；只會延後、不會提早已讀。
- **聊天室及其祖先不得使用 opacity、scale、`translateY` 過場**；寬版切換聊天室不做過場；窄版只用 `translateX`。
- 不在 margin、height、padding 加 transition。

### 7.4 捲動與輸入

- 「跳至最新」只保留一個：捲動區外的圓形浮動按鈕（帶 `data-read-occlusion`，名稱「跳至最新」），在非最新位置或有新訊息時顯示，呼叫既有 `latest()`；移除捲動區內的 `.jump-latest`。新訊息數另以 visually-hidden 的 `role="status"` 朗讀（「N 則新訊息 · 不代表未讀數」）。
- 「載入較早訊息」保留為頂部膠囊按鈕。
- 輸入列：📎（名稱不變）、`#chat-draft`（label「撰寫訊息」）、`.send-button`（可見 ➤，名稱「傳送」）；字數超過 3,800 才顯示計數；整體保留 `data-read-occlusion`；鍵盤處理不變。
- 訊息時間使用模組層級重用的 `Intl.DateTimeFormat`（`hourCycle: 'h23'`）。

## 8. 建立群組〔修訂：R7〕

- Phase 4 才加入：寬版圖示欄「建立群組」、☰ 選單「建立群組」、清單 ✎ 浮動按鈕（名稱「建立群組」）；同時移除清單內舊的「＋ 建立群組」。
- 元件掛在外殼層級；有未完成意圖時自動開啟（沿用 `GroupsPage.tsx:32-37`）。
- 原生 `<dialog name="建立群組">`，`showModal()`、`hine-overlay-change`、關閉即卸載並還原焦點。
- 步驟 1：聯絡人勾選清單（載入更多）、已選標籤、「已選 N／49」、達上限停用；「以公開 ID 加入」需 A07 查詢成功並顯示名稱後才加入。
- 步驟 2：「群組名稱」＋「建立群組」。
- 沿用 `GroupCreationIntentStore`（冪等鍵、原意圖重試／核對、結束原意圖、重新整理還原、有意圖時鎖定輸入）；名稱不可空白、不 trim；成員以去重後的 ID 計算。
- 選取規則以作用在 `string[]` 的純函式實作，避免可變物件不觸發重繪。
- 群組管理頁（R12）：`App` 以 `key={route.conversationId}` 渲染 `GroupsPage`，切換群組時重建實例（舊載入回覆不會寫入新實例，`memberIntent` 也不跨群組沿用）；`mutate` 在實例卸載後不再呼叫 `onNavigate`（`chat.withdraw` 照常完成）。CI 回歸檢查：攔截並延遲非群組路由 `/groups/{一對一ID}/manage` 的 A12 回應，於其未回覆前導覽到 `/groups/{群組ID}/manage`，放行後新頁仍顯示群組標題且沒有「這不是群組對話。」。

## 9. 無障礙

- ☰ 選單、建群組、群組資訊、附件檢視器皆為原生 `<dialog>`：焦點限制、Esc 關閉、關閉後焦點回觸發元素（觸發元素不存在時聚焦路由標題）、不聚焦已卸載節點。
- 純圖示按鈕皆有可存取名稱（見 §3 保留清單，另加「開啟選單」「HINE 聊天首頁」「建立群組」「跳至最新」）。
- 狀態圖示附文字；焦點外框可見；觸控目標至少 44px；保留「跳至主要內容」。
- 窄版畫面外的面板 `inert`，Tab 不會進入。

## 10. 效能

- 先量測再最佳化：CI 驗收中加入只記錄、不卡關的指標（§11）。
- 預先納入的低風險項：重用 `Intl.DateTimeFormat`；時間軸與清單推導以 `useMemo` 依輸入計算；使用者摘要快取去重與並行上限。
- 不做虛擬化（100 則復原驗收要求 100 個 `[data-message-id]` 同時存在，`browser_acceptance.py:648-669`）。
- `App` 目前因每次 `publish` 整體重繪（`App.tsx:25`、`chat.ts:100`）；是否調整訂閱方式，依基準結果另議，不在本次預設範圍。

## 11. 測試與驗收

- **單元測試**（bun:test，無 DOM）：清單推導、排序鍵、時間軸、狀態對應、進場判定（含基準為 null）、`bubbleMeasurable`、使用者摘要快取（去重、並行、reset、失敗不拋、TTL、per-user 版本號亂序、owner 切換）、群組選取；靜態渲染驗證訊息 DOM 不變式與 `.message-meta` 文字。
- **既有測試**全數通過；typecheck、正式建置通過。
- **CI 瀏覽器驗收**（Chrome、Edge）：各 Phase 只更新與新版 UI 對應的定位與操作；與已移除元素綁定的檢查改為檢查取代它的新元素並維持同等要求。新增檢查必須能抓到失敗：
  - IME：組字中 Enter 後至少等 1 秒，IndexedDB 意圖數、`.pending-message` 數不變，草稿未清空。
  - 767／768：以元素與 viewport 的幾何交集判定可見，不用 `is_visible`；畫面外面板 `inert`。
  - 動畫：訊息到達前注入 MutationObserver，於插入後的下一個 rAF 記錄泡泡動畫數；reduced-motion 時為 0，並以未開 reduced-motion 的正向對照證明量測有效。
  - 其餘：☰ 與群組資訊 Esc 焦點返回、訊息 DOM 不變式、選單關閉後已讀照常送出、往上捲時新訊息計數、切換聊天室後錨點還原。
  - 新增檢查插在 `:790` 之後、`:793` 之前；結束時將視窗還原為原本的 390×844，使後續既有步驟條件不變。
- **本機實測**：Docker＋臨時帳號，390／767／768／1280 截圖與鍵盤操作；完成後刪除臨時帳號並停止容器。

## 12. 設計限制

| 限制 | 原因 | 影響 |
|---|---|---|
| 無法對全部對話依最新活動排序 | A11 只依 `conversation_id` 排序；契約未定義活動排序；`order_key` 不可跨對話比較 | 只在已載入的對話內排序；完整需求另開 Issue |
| 初次載入時清單最多重排兩次 | 鍵表為記憶體；群組要等首次同步驗證（`chat.ts:100,116`） | 進入頁面後短暫重排 |
| 跨 API 實例時鐘偏差 | `created_at` 為各實例的資料庫時鐘 | 相近時間的兩個對話可能先後相反 |
| 第 2 頁以後在重新載入時被收回 | 既有 `usePagedList` 行為 | 排序後更明顯 |
| 名稱與頭像變更沒有即時推播 | 沒有 profile 事件 | 最長 5 分鐘或重新開啟聊天室後更新 |
| 群組在驗證前沒有預覽 | `publish()` 對未驗證群組輸出空訊息（`chat.ts:100`） | 預覽暫顯「—」，位置由鍵表維持 |

## 13. 決策紀錄（2026-10-17 使用者確認）

1. **寬版導覽**：採寬版常駐窄圖示欄、窄版 ☰ 側邊選單（§5）。取代 v1「寬版改為 ☰」。
2. **伺服器端最新活動排序**：本分支不修改 A11；另開 GitHub Issue 依共同介面流程提議。前端依 §6.2 以 `created_at` 在已載入範圍內排序，`order_key` 不跨對話比較（R10）。
3. **#7 修正的分支歸屬**：將 `fa37230` 以非破壞方式移到 `fix/attachment-error-message`（從 `origin/main` 建立並 cherry-pick，原提交保留在備份分支）；`feature/ui-refresh` 最終只含 UI 改版。需要改寫本分支歷史的操作先經使用者確認。
4. **GroupsPage 競態**：Phase 4 依 §8 R12 修正，並以 CI 瀏覽器回歸檢查證明，不以「改一行」視為已解決。
5. **`frontend/app/tests/review-shell-native.ts`**：同步更新選擇器，維持既有斷言語意（R11）。此腳本在 repo 內沒有執行入口，只能以 typecheck 驗證可編譯，不宣稱其通過。
6. **CI**：每個 Phase 推送 `feature/ui-refresh` 觸發 GitHub Actions，以遠端結果為準；不推 main、不 merge、不開最終 PR、不 force push、不部署。
