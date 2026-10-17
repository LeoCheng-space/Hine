# HINE UI Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 以 Telegram 式版面與互動手感重構 HINE Web 前端，保留 HINE 品牌，且不改變任何後端契約、持久化、授權、已讀或同步語意。

**Architecture:** 新增不依賴 React 的純邏輯模組（`chat-presentation.ts`、`user-directory.ts`、`group-selection.ts`）承擔排序、分組、狀態對應、快取與選取規則，先以 bun:test 驗證；React 元件只負責呈現與互動。`ChatController`、`SessionController`、`repository.ts` 的公開 API 與資料流不變；唯一的行為修改是 `ReadObserver` 對未完成動畫的保守化。

**Tech Stack:** React 19.3、TypeScript 7.0、Bun 1.4.2（bun:test，無 DOM 環境；以 `renderToStaticMarkup` 做靜態渲染測試）、原生 CSS、Playwright 1.63（`tests/browser/browser_acceptance.py`，CI Chrome／Edge headed）。

**Spec:** `docs/superpowers/specs/2026-10-17-ui-refresh-design.md`（v2.3）。spec §13 決策已由使用者確認（2026-10-17）：寬版圖示欄＋窄版 ☰；排序用 `created_at`（Issue #11 追蹤伺服器端排序）；#7 移出本分支（PR #10）；GroupsPage 以回歸檢查證明；同步 `review-shell-native.ts`；每個 Phase 推送功能分支跑 CI。v2.3 依第二次獨立審查修正（R8、R12–R14）。

## Global Constraints

- 不修改：REST、WebSocket、PostgreSQL schema／migration、Redis、JWT／Session 權威邏輯、IndexedDB store 與記錄結構、已讀／同步／未讀語意、`ChatController` 公開 API。
- 768px 單一斷點，CSS 統一寫成 `@media (width < 768px)`。
- 訊息 DOM 不變式：每則已持久化訊息恰好一個 `[data-message-id]`（UUID、在泡泡本體）；`.message-scroller` 內沒有 `[data-read-occlusion]`；非訊息元素不帶 `data-message-id`。
- 保留定位與名稱：`.chat-room`、`.chat-header small[role=status]`（文字為 `CONNECTION_LABEL`）、`.chat-composer textarea`／`#chat-draft`、`.send-button`、`.message-meta`（含狀態文字）、`.chat-list`、`.member-list li`、`.narrow-back`、`.app-nav`（窄版 sticky）、`navigation "主要導覽"`、按鈕「聊天」「聯絡人」「個人檔案」「登出」「群組資訊」「前往群組管理」「移除」。
- 匯出名稱不變：`GroupCreationIntentStore`、`AvatarSaveRecovery`、`ContactLookupLifetime`、`fetchAvatarBytes`、`AttachmentRecovery`、`usePagedList`、`Avatar`。
- 聊天室與其祖先不得有 opacity、scale、translateY 過場。
- 不新增 npm 或 Python 依賴；不做訊息虛擬化。
- 每個 Phase 改到哪個 UI，就在同一 Phase 更新依賴它的驗收步驟；只改定位與操作，不刪除、跳過或降低任何 `check(...)`。
- 每個 Phase 的完成條件：三個前端命令 exit 0；推送 `feature/ui-refresh` 後 GitHub Actions `Repository Checks` 8／8 jobs 成功（以遠端 run 為準，記錄 run URL）；本機截圖證據記錄於該 Phase 的提交訊息或回報。第一次推送前，#7 分支整理（spec §13 第 3 項）必須完成。
- 提交身分：`git -c user.name='Leo' -c user.email='126685053+LeoCheng-space@users.noreply.github.com' commit …`，不修改使用者 Git 設定。

前端三命令（於 `frontend/app/` 執行）：

```bash
~/.bun/bin/bun run typecheck
HINE_CASEFOLD_PYTHON=python3.12 ~/.bun/bin/bun run test
PUBLIC_ORIGIN=https://localhost:8443 ~/.bun/bin/bun run build
```

---

## File Structure

| 檔案 | 動作 | 責任 |
|---|---|---|
| `frontend/app/src/chat-presentation.ts` | 新增 | 清單時間、預覽、排序鍵表、撤權記憶、排序、頭像配色、時間軸、日期標籤、狀態對應、進場判定 |
| `frontend/app/src/chat-presentation.test.ts` | 新增 | 上述單元測試 |
| `frontend/app/src/user-directory.ts` | 新增 | 依 owner 分區的使用者摘要快取 |
| `frontend/app/src/user-directory.test.ts` | 新增 | 快取單元測試 |
| `frontend/app/src/avatar-cache.ts`、`avatar-cache.test.ts` | 新增 | 依 owner 分區的頭像物件 URL 快取 |
| `frontend/app/src/group-selection.ts`、`group-selection.test.ts` | 新增 | 建群組成員選取純函式 |
| `frontend/app/src/AppMenu.tsx` | 新增 | 窄版 ☰ 選單 |
| `frontend/app/src/ChatList.tsx` | 新增（自 `App.tsx:13-23` 移出） | 對話清單 |
| `frontend/app/src/MessageRow.tsx`、`message-row.test.tsx` | 新增 | 訊息列、待送列、日期分隔、浮動日期膠囊；DOM 不變式測試 |
| `frontend/app/src/read-observer.ts`、`read-observer.test.ts` | 修改 | `bubbleMeasurable` |
| `frontend/app/src/App.tsx` | 修改 | 外殼、圖示欄、窄版頂部列、路由焦點、聊天路由只閘門聊天室（R13）、建群組掛載 |
| `frontend/app/src/ChatView.tsx` | 修改 | 頂部列、時間軸、浮動按鈕、輸入列、名稱快取、進場動畫 |
| `frontend/app/src/GroupsPage.tsx` | 修改 | 兩步建群組對話框、管理頁外觀、卸載後不導覽（R12） |
| `AccountPages.tsx`、`ContactsPage.tsx`（`Avatar` 改用頭像快取，匯出不變）、`ProfilePage.tsx`、`AttachmentViewer.tsx` | 修改 | 外觀、`data-route-heading`、快取接線；行為不變 |
| `Shell.css`、`Chat.css` | 修改 | token、版面、動畫、reduced-motion |
| `tests/browser/browser_acceptance.py` | 修改 | 各 Phase 定位更新；Phase 5 新增檢查與效能記錄 |
| `frontend/app/tests/review-shell-native.ts` | 修改（Phase 2、4） | 同步選擇器，斷言語意不變；無執行入口，只以 typecheck 驗證 |
| `docs/CHANGELOG.md`、`docs/ui/web-rwd.md` | 修改（Phase 5） | 記錄 |

---

## Phase 1：Design Tokens / App Shell

**目標**：設計 token、寬版圖示欄、窄版頂部列與 ☰ 選單、路由焦點、登入與阻擋頁樣式。清單與聊天室內容暫不改。

**依賴**：無。

**潛在失效模式**：選單關閉未卸載使已讀永久暫停；Esc 後焦點落到 body；窄版頂部列不再 sticky；圖示欄按鈕名稱改變使既有驗收失敗；路由焦點落到錯誤元素。

**完成條件**：三命令 exit 0；CI 8／8，其中 `{tag}_login_reached_authenticated_shell`、`responsive_mobile_navigation_is_sticky`、`responsive_mobile_shell_has_no_horizontal_overflow`、`real_ui_logout_received_committed_http_204` 通過；本機 1280／768／767／390 截圖無水平溢出；鍵盤開關 ☰ 後焦點回到 ☰。

**建議提交**：Task 1.1、1.2、1.3、1.4 各一個提交。

### Task 1.1：設計 token、reduced-motion、斷點寫法

**Files:** Modify `frontend/app/src/Shell.css`、`frontend/app/src/Chat.css`

**Interfaces:** Produces CSS 變數 `--brand-900/700/500/100/50`、`--surface`、`--canvas`、`--text`、`--muted`、`--line`、`--danger`、`--accent-1…6`、`--motion-fast`、`--motion-base`、`--ease-out`、`--radius-bubble`、`--radius-tail`；既有 `--accent`、`--accent-soft` 改為別名。

- [ ] **Step 1：`Shell.css` 的 `:root` 加入 token**

```css
:root {
  --brand-900: #0f3d35; --brand-700: #1b6558; --brand-500: #2f8a76; --brand-100: #dff1e8; --brand-50: #eef6f1;
  --surface: #ffffff; --canvas: #e9efe9; --text: #18312e; --muted: #60716a; --line: #dce5de; --danger: #a62d3b;
  --accent-1: #1b6558; --accent-2: #7a4fb5; --accent-3: #b5532f; --accent-4: #2f6fb5; --accent-5: #9a7a12; --accent-6: #b03a6b;
  --motion-fast: 150ms; --motion-base: 220ms; --ease-out: cubic-bezier(.2,.8,.2,1);
  --radius-bubble: 16px; --radius-tail: 4px;
  --accent: var(--brand-700); --accent-soft: var(--brand-50);
}
```

- [ ] **Step 2：以下列規則取代 `Shell.css:143` 的 reduced-motion 規則**

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { transition: none !important; animation: none !important; scroll-behavior: auto !important; }
}
```

- [ ] **Step 3：`Shell.css` 的 `@media (max-width: 767px)` 改為 `@media (width < 768px)`。**
- [ ] **Step 4：Run 三命令。** Expected：exit 0，測試數與修改前相同。
- [ ] **Step 5：Commit** `style: add HINE design tokens and full reduced-motion`

### Task 1.2：路由焦點 `data-route-heading`

**Files:** Modify `App.tsx:22,60,68`、`AccountPages.tsx:27`、`ContactsPage.tsx:185`、`ProfilePage.tsx:88`、`GroupsPage.tsx:113`、`ChatView.tsx:100`

**Interfaces:** Produces 每個路由恰好一個 `[data-route-heading]`（`tabIndex={-1}`）。

- [ ] **Step 1：`App.tsx:60` 改為**

```tsx
useEffect(() => { if (allowedKey === key || route?.kind === 'login' || route?.kind === 'register') document.querySelector<HTMLElement>('[data-route-heading]')?.focus(); }, [path, allowedKey]);
```

- [ ] **Step 2：加上屬性**：登入／註冊頁 h1；聯絡人、個人檔案、群組管理頁 h1；錯誤頁 h1（`App.tsx:68`）；清單 h1 只在 `route.kind === 'chats'` 時帶；聊天室 `#chat-title` 帶。`ChatView` 空狀態維持 h2，不帶。
- [ ] **Step 3：Run 三命令；本機以鍵盤進入 `/contacts`、`/profile`、`/chats/{id}`、`/chats`，`document.activeElement` 為該頁的 `[data-route-heading]`。**
- [ ] **Step 4：Commit** `refactor: focus route headings explicitly`

### Task 1.3：寬版圖示欄、窄版頂部列與 ☰ 選單

**Files:**
- Create: `frontend/app/src/AppMenu.tsx`
- Modify: `frontend/app/src/App.tsx:74`、`Shell.css`、`tests/browser/browser_acceptance.py:793-798`

**Interfaces:**
- Produces: `export function AppMenu({ open, items, onClose, triggerRef }: { open: boolean; items: { label: string; onSelect: () => void }[]; onClose: () => void; triggerRef: RefObject<HTMLButtonElement | null> })`。`open=false` 時回傳 null。
- Produces: 外殼 `.app-nav` 單一元素：寬版為圖示欄（含 `<nav aria-label="主要導覽">`）、窄版為 sticky 頂部列（含 ☰「開啟選單」與品牌按鈕，`<nav>` 移入選單）。

- [ ] **Step 1：`AppMenu.tsx`**（焦點在 cleanup 中先 `close()` 再還原，比照 `GroupsPage.tsx:74-79`）

```tsx
import { useEffect, useRef, type RefObject } from 'react';
export function AppMenu({ open, items, onClose, triggerRef }: { open: boolean; items: { label: string; onSelect: () => void }[]; onClose: () => void; triggerRef: RefObject<HTMLButtonElement | null> }) {
  const dialog = useRef<HTMLDialogElement>(null), first = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return; const element = dialog.current; if (!element) return;
    element.showModal(); first.current?.focus(); window.dispatchEvent(new Event('hine-overlay-change'));
    return () => {
      element.close(); window.dispatchEvent(new Event('hine-overlay-change'));
      const trigger = triggerRef.current;
      if (trigger?.isConnected && trigger.offsetParent !== null) trigger.focus();
      else document.querySelector<HTMLElement>('[data-route-heading]')?.focus();
    };
  }, [open, triggerRef]);
  if (!open) return null;
  return <dialog ref={dialog} className="app-menu" aria-label="選單" onCancel={event => { event.preventDefault(); onClose(); }} onClick={event => { if (event.target === dialog.current) onClose(); }}>
    <nav aria-label="主要導覽" className="app-menu-panel"><ul>
      {items.map((item, index) => <li key={item.label}><button ref={index === 0 ? first : undefined} type="button" onClick={() => { onClose(); item.onSelect(); }}>{item.label}</button></li>)}
    </ul></nav>
  </dialog>;
}
```

- [ ] **Step 2：`App.tsx` 外殼**：以 `matchMedia('(width < 768px)')` 的 state（監聽 `change`）決定窄版。寬版 `.app-nav` 內為 `<nav aria-label="主要導覽">`：品牌按鈕（`aria-label="HINE 聊天首頁"`）、「聊天」「聯絡人」「個人檔案」按鈕（圖示 `<span aria-hidden="true">`＋visually-hidden 文字，`title` 為同名提示；可存取名稱必須恰為文字，`browser_acceptance.py:282` 以 `exact=True` 比對）、底部「登出」。窄版 `.app-nav` 內為 ☰（`ref={menuButton}`、`aria-label="開啟選單"`、`aria-haspopup="dialog"`）與品牌按鈕，並渲染 `<AppMenu open={menuOpen} items={[聊天, 個人檔案, 聯絡人, 登出]} …/>`。登出沿用 `App.tsx:74` 既有處理器。保留「跳至主要內容」、`.session-notice`。
- [ ] **Step 3：`Shell.css`**：`.app-shell` 寬版 `grid-template-columns: 72px 1fr`；`.app-nav` 寬版 `position: sticky; top: 0; height: 100dvh`，窄版 `position: sticky; top: 0; z-index: 10`；`.app-menu::backdrop` 半透明；`.app-menu-panel` 寬 280px、自左滑入（`@starting-style { transform: translateX(-100%) }`、`transition: transform var(--motion-base) var(--ease-out)`）；修正 `Shell.css:64-65,124-125` 寫死的 68／109px 高度為以變數 `--app-nav-height` 計算。
- [ ] **Step 4：更新驗收**（只改 `:795` 的定位，條件不變；其他使用「主要導覽」的步驟都在寬版執行，不需修改）：

```python
async def main_nav(page):
    menu_button = page.get_by_role("button", name="開啟選單", exact=True)
    if await menu_button.is_visible():
        await menu_button.click()
        menu = page.get_by_role("dialog", name="選單")
        await menu.wait_for(state="visible")
        return menu.get_by_role("navigation", name="主要導覽")
    return page.get_by_role("navigation", name="主要導覽")
```

`:795` 改為 `await (await main_nav(page_a)).get_by_role("button", name="登出", exact=True).click()`（保留外層 `expect_response`）。

- [ ] **Step 5：Run 三命令；本機 Docker 截圖 1280／768／767／390；390 時以鍵盤 Tab 到 ☰、Enter 開啟、Esc 關閉，確認焦點回到 ☰。推送後 CI 8／8。**
- [ ] **Step 6：Commit** `feat: Telegram-style shell with icon rail and mobile menu`

### Task 1.4：登入、註冊、阻擋畫面樣式

**Files:** Modify `AccountPages.tsx`、`App.tsx:61-63`、`Shell.css`

- [ ] **Step 1**：只改 class 與 CSS；label、按鈕文字、註冊頁唯一的 `role="status"` 不變。
- [ ] **Step 2**：Run 三命令；CI 中 `{tag}_registration_completed_in_real_ui` 通過。
- [ ] **Step 3：Commit** `style: apply HINE brand to account and status pages`

---

## Phase 2：Chat List

**目標**：對話清單顯示頭像、名稱、預覽、時間、未讀；已載入範圍內穩定排序；名稱與頭像經 `UserDirectory`。

**依賴**：Phase 1。

**潛在失效模式**：重排或沉底；跨帳號顯示舊名稱；撤權列重新出現；請求風暴；骨架閃爍；`refreshConversation` 迴圈重試。

**完成條件**：Task 2.1、2.2、2.2b 測試通過；三命令 exit 0；CI 8／8；本機 25 個對話：首次載入時 `/users/`、`/conversations/{id}`、`/attachments/…/download` 同時進行中請求各 ≤4（DevTools Network 截圖）；**沒有新訊息時**，等待兩次背景同步（約 20 秒）列順序不變；**由另一帳號對某個已載入但不在首位的對話送 1 則**後，該對話移到首位，其他列相對順序不變（前後截圖）；切換對話時清單不重建（Task 2.4 Step 3）。

**建議提交**：Task 2.1、2.2、2.2b、2.3、2.4 各一個提交。

### Task 2.1：清單推導（`chat-presentation.ts` 第一部分）

**Files:** Create `frontend/app/src/chat-presentation.ts`；Test `frontend/app/src/chat-presentation.test.ts`

**Interfaces:**
- Produces: `formatListTime(iso: string, now: Date): string`；`previewText(message: MessageView | undefined, kind: 'direct' | 'group', me: string, nameOf: (userId: string) => string): string`；`class ActivityBook`（`observe(id, createdAt?: string)`、`drop`、`get(id): number | undefined`）；`activityBookFor(owner: string): ActivityBook`；`class DeniedMemory`（`hide(id)`、`has(id)`、`clear()`）；`deniedMemoryFor(owner: string): DeniedMemory`；`sortConversations<T extends { id: string }>(items: T[], book: ActivityBook): T[]`；`accentIndex(id: string): 1 | 2 | 3 | 4 | 5 | 6`；內部 `dayStart(date: Date): number`。跨對話排序**不使用 `order_key`**（契約 C11 只保證同一對話內可比較）。

- [ ] **Step 1：寫失敗測試**

```ts
import { expect, test } from 'bun:test';
import { ActivityBook, DeniedMemory, accentIndex, activityBookFor, deniedMemoryFor, formatListTime, previewText, sortConversations } from './chat-presentation';
import type { MessageView } from './types';

const now = new Date(2026, 9, 17, 15, 0);
const at = (y: number, m: number, d: number, h = 9, min = 5) => new Date(y, m - 1, d, h, min).toISOString();
function text(id: string, sender: string, body: string, order: string): MessageView {
  return { id, event_id: id, conversation_id: 'c', sender_id: sender, created_at: at(2026, 10, 17), order_key: order, receipt: null, type: 'text', text: body };
}
test('list time shows 24-hour clock today, 昨天, weekday within a week, then dates', () => {
  expect(formatListTime(at(2026, 10, 17, 0, 5), now)).toBe('00:05');
  expect(formatListTime(at(2026, 10, 17, 9, 5), now)).toBe('09:05');
  expect(formatListTime(at(2026, 10, 16), now)).toBe('昨天');
  expect(formatListTime(at(2026, 10, 12), now)).toBe('週一');
  expect(formatListTime(at(2026, 10, 9), now)).toBe('10/9');
  expect(formatListTime(at(2025, 12, 31), now)).toBe('2025/12/31');
});
test('preview prefixes own and group senders, folds whitespace and labels attachments', () => {
  const nameOf = (id: string) => (id === 'ann' ? 'Ann' : id);
  expect(previewText(undefined, 'direct', 'me', nameOf)).toBe('—');
  expect(previewText(text('1', 'me', '你好', '1'), 'direct', 'me', nameOf)).toBe('你：你好');
  expect(previewText(text('1', 'ann', '嗨', '1'), 'direct', 'me', nameOf)).toBe('嗨');
  expect(previewText(text('1', 'ann', '嗨', '1'), 'group', 'me', nameOf)).toBe('Ann：嗨');
  expect(previewText(text('1', 'ann', '第一行\n  第二行', '1'), 'direct', 'me', nameOf)).toBe('第一行 第二行');
  const image = { ...text('2', 'ann', '', '2'), type: 'image', attachment_id: 'a' } as unknown as MessageView;
  const file = { ...text('3', 'ann', '', '3'), type: 'file', attachment_id: 'f' } as unknown as MessageView;
  expect(previewText(image, 'direct', 'me', nameOf)).toBe('📷 圖片');
  expect(previewText(file, 'group', 'me', nameOf)).toBe('Ann：📄 檔案');
});
test('activity only moves forward and survives temporarily empty snapshots', () => {
  const book = new ActivityBook();
  book.observe('c', '2026-10-17T01:00:05.000Z');
  book.observe('c', undefined);
  book.observe('c', '2026-10-17T01:00:03.000Z');
  expect(book.get('c')).toBe(Date.parse('2026-10-17T01:00:05.000Z'));
  book.drop('c');
  expect(book.get('c')).toBeUndefined();
});
test('unparseable timestamps are ignored', () => {
  const book = new ActivityBook();
  book.observe('c', 'not-a-time');
  expect(book.get('c')).toBeUndefined();
});
test('sorting puts conversations with activity first, newest first, and keeps A11 order otherwise', () => {
  const book = new ActivityBook();
  book.observe('b', '2026-10-17T01:00:02.000Z');
  book.observe('d', '2026-10-17T01:00:09.000Z');
  expect(sortConversations([{ id: 'a' }, { id: 'b' }, { id: 'c' }, { id: 'd' }], book).map(item => item.id)).toEqual(['d', 'b', 'a', 'c']);
});
test('a new message moves only its conversation and equal times keep A11 order', () => {
  const book = new ActivityBook(), items = [{ id: 'a' }, { id: 'b' }, { id: 'c' }];
  for (const id of ['a', 'b', 'c']) book.observe(id, '2026-10-17T01:00:00.000Z');
  expect(sortConversations(items, book).map(item => item.id)).toEqual(['a', 'b', 'c']);
  book.observe('c', '2026-10-17T01:00:01.000Z');
  expect(sortConversations(items, book).map(item => item.id)).toEqual(['c', 'a', 'b']);
});
test('activity books and denied memories are isolated per owner', () => {
  activityBookFor('["u1","d1"]').observe('c', '2026-10-17T01:00:00.000Z');
  deniedMemoryFor('["u1","d1"]').hide('g');
  expect(activityBookFor('["u2","d2"]').get('c')).toBeUndefined();
  expect(deniedMemoryFor('["u2","d2"]').has('g')).toBe(false);
  expect(activityBookFor('["u1","d1"]').get('c')).toBeUndefined();
});
test('denied memory hides until the next completed list reload', () => {
  const memory = new DeniedMemory();
  memory.hide('g');
  expect(memory.has('g')).toBe(true);
  memory.clear();
  expect(memory.has('g')).toBe(false);
});
test('accent index is deterministic and within one to six', () => {
  expect(accentIndex('user-a')).toBe(accentIndex('user-a'));
  for (const id of ['a', 'b', 'c', 'dd', 'eee', '中文']) { expect(accentIndex(id)).toBeGreaterThanOrEqual(1); expect(accentIndex(id)).toBeLessThanOrEqual(6); }
});
```

- [ ] **Step 2：Run** `~/.bun/bin/bun test src/chat-presentation.test.ts`。Expected：FAIL（`Cannot find module './chat-presentation'`）。
- [ ] **Step 3：實作**

```ts
import type { MessageView } from './types';

const clock = new Intl.DateTimeFormat('zh-TW', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
const WEEKDAY = ['週日', '週一', '週二', '週三', '週四', '週五', '週六'];
export function dayStart(value: Date): number { return new Date(value.getFullYear(), value.getMonth(), value.getDate()).getTime(); }
function daysBetween(earlier: Date, later: Date): number { return Math.round((dayStart(later) - dayStart(earlier)) / 86_400_000); }
export function formatListTime(iso: string, now: Date): string {
  const value = new Date(iso), days = daysBetween(value, now);
  if (days <= 0) return clock.format(value);
  if (days === 1) return '昨天';
  if (days < 7) return WEEKDAY[value.getDay()];
  if (value.getFullYear() === now.getFullYear()) return `${value.getMonth() + 1}/${value.getDate()}`;
  return `${value.getFullYear()}/${value.getMonth() + 1}/${value.getDate()}`;
}
export function previewText(message: MessageView | undefined, kind: 'direct' | 'group', me: string, nameOf: (userId: string) => string): string {
  if (!message) return '—';
  const body = message.type === 'text' ? message.text.replace(/\s+/g, ' ').trim() : message.type === 'image' ? '📷 圖片' : '📄 檔案';
  if (message.sender_id === me) return `你：${body}`;
  return kind === 'group' ? `${nameOf(message.sender_id)}：${body}` : body;
}
export class ActivityBook {
  private readonly times = new Map<string, number>();
  observe(conversationId: string, createdAt: string | undefined): void {
    if (createdAt === undefined) return;
    const value = Date.parse(createdAt); if (Number.isNaN(value)) return;
    const current = this.times.get(conversationId);
    if (current === undefined || value > current) this.times.set(conversationId, value);
  }
  drop(conversationId: string): void { this.times.delete(conversationId); }
  get(conversationId: string): number | undefined { return this.times.get(conversationId); }
}
export class DeniedMemory {
  private readonly ids = new Set<string>();
  hide(conversationId: string): void { this.ids.add(conversationId); }
  has(conversationId: string): boolean { return this.ids.has(conversationId); }
  clear(): void { this.ids.clear(); }
}
let scopedOwner: string | null = null, scopedBook = new ActivityBook(), scopedDenied = new DeniedMemory();
function scope(owner: string): void { if (owner !== scopedOwner) { scopedOwner = owner; scopedBook = new ActivityBook(); scopedDenied = new DeniedMemory(); } }
export function activityBookFor(owner: string): ActivityBook { scope(owner); return scopedBook; }
export function deniedMemoryFor(owner: string): DeniedMemory { scope(owner); return scopedDenied; }
export function sortConversations<T extends { id: string }>(items: T[], keys: ActivityBook): T[] {
  return items.map((item, index) => ({ item, index, key: keys.get(item.id) }))
    .sort((a, b) => {
      if (a.key !== undefined && b.key !== undefined && a.key !== b.key) return a.key > b.key ? -1 : 1;
      if ((a.key === undefined) !== (b.key === undefined)) return a.key === undefined ? 1 : -1;
      return a.index - b.index;
    }).map(entry => entry.item);
}
export function accentIndex(id: string): 1 | 2 | 3 | 4 | 5 | 6 {
  let hash = 0x811c9dc5;
  for (const char of id) hash = Math.imul(hash ^ char.codePointAt(0)!, 0x01000193) >>> 0;
  return (hash % 6 + 1) as 1 | 2 | 3 | 4 | 5 | 6;
}
```

- [ ] **Step 4：Run** 同 Step 2。Expected：9 pass。
- [ ] **Step 5：Commit** `feat: derive chat list presentation state`

### Task 2.2：使用者摘要快取（`user-directory.ts`）

**Files:** Create `frontend/app/src/user-directory.ts`；Test `frontend/app/src/user-directory.test.ts`

**Interfaces:**
- Produces: `interface DirectoryEntry { displayName: string; avatarId: string | null; fetchedAt: number; avatarStale: boolean }`；`interface DirectoryDeps { fetchSummary(userId: string, signal: AbortSignal): Promise<{ display_name: string; avatar_attachment_id: string | null }>; now(): number; accept(): boolean }`；`class UserDirectory`：`get(userId)`、`ensure(userId): Promise<void>`（永不 reject）、`put(userId, summary)`（未被 `accept()` 時不寫入）、`markAvatarsStale(userIds: string[])`、`observeMembership(groupId: string, version: number | null, memberIds: string[])`、`reset()`、箭頭屬性 `subscribe`、`getVersion`；`directoryFor(session: SessionController): UserDirectory`。
- 呼叫規則：`ensure` 只在 effect 中依使用者 ID 集合呼叫，不在 render 中呼叫。

- [ ] **Step 1：寫失敗測試**

```ts
import { expect, test } from 'bun:test';
import { UserDirectory, directoryFor } from './user-directory';
import type { SessionController } from './session';

type Summary = { display_name: string; avatar_attachment_id: string | null };
function deferred<T>() { let resolve!: (value: T) => void, reject!: (error: unknown) => void; const promise = new Promise<T>((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; }
function harness(options: { concurrency?: number; accept?: () => boolean } = {}) {
  const calls: { id: string; signal: AbortSignal; done: ReturnType<typeof deferred<Summary>> }[] = [];
  let time = 0;
  const directory = new UserDirectory({ fetchSummary: (id, signal) => { const done = deferred<Summary>(); calls.push({ id, signal, done }); return done.promise; }, now: () => time, accept: options.accept ?? (() => true) }, { ttlMs: 300_000, concurrency: options.concurrency ?? 4, failureBackoffMs: 30_000 });
  return { directory, calls, advance: (ms: number) => { time += ms; } };
}
const flush = () => new Promise(resolve => setTimeout(resolve, 0));

test('concurrent ensures for one user share a single request', async () => {
  const { directory, calls } = harness();
  void directory.ensure('u'); void directory.ensure('u'); await flush();
  expect(calls.length).toBe(1);
});
test('no more than the configured number of requests run at once', async () => {
  const { directory, calls } = harness({ concurrency: 4 });
  for (const id of ['a', 'b', 'c', 'd', 'e', 'f']) void directory.ensure(id);
  await flush(); expect(calls.length).toBe(4);
  calls[0].done.resolve({ display_name: 'A', avatar_attachment_id: null }); await flush();
  expect(calls.length).toBe(5);
});
test('reset aborts requests, discards late responses and settles queued work', async () => {
  const { directory, calls } = harness({ concurrency: 1 });
  const running = directory.ensure('u'), queued = directory.ensure('v'); await flush();
  directory.reset();
  expect(calls[0].signal.aborted).toBe(true);
  await queued;
  calls[0].done.resolve({ display_name: 'Old account', avatar_attachment_id: 'old' }); await running;
  expect(directory.get('u')).toBeUndefined();
});
test('failures resolve quietly, are not cached and back off before retrying', async () => {
  const { directory, calls, advance } = harness();
  const first = directory.ensure('u'); await flush();
  calls[0].done.reject(new Error('DEPENDENCY_UNAVAILABLE'));
  await first;
  expect(directory.get('u')).toBeUndefined();
  await directory.ensure('u'); expect(calls.length).toBe(1);
  advance(30_001); void directory.ensure('u'); await flush();
  expect(calls.length).toBe(2);
});
test('a newer put is not overwritten by an older in-flight response', async () => {
  const { directory, calls } = harness();
  const first = directory.ensure('me'); await flush();
  directory.put('me', { display_name: 'New name', avatar_attachment_id: null });
  calls[0].done.resolve({ display_name: 'Old name', avatar_attachment_id: null }); await first;
  expect(directory.get('me')?.displayName).toBe('New name');
});
test('an in-flight request made stale by a version change is replaced, not reused', async () => {
  const { directory, calls } = harness();
  const old = directory.ensure('u'); await flush();
  directory.markAvatarsStale(['u']);
  const fresh = directory.ensure('u'); await flush();
  expect(calls.length).toBe(2);
  calls[0].done.resolve({ display_name: 'Ann', avatar_attachment_id: 'old' }); await old;
  expect(directory.get('u')).toBeUndefined();
  calls[1].done.resolve({ display_name: 'Ann', avatar_attachment_id: 'new' }); await fresh;
  expect(directory.get('u')?.avatarId).toBe('new');
});
test('marking avatars stale forces a refetch that clears the stale flag', async () => {
  const { directory, calls } = harness();
  const first = directory.ensure('u'); await flush();
  calls[0].done.resolve({ display_name: 'Ann', avatar_attachment_id: 'x' }); await first;
  await directory.ensure('u'); expect(calls.length).toBe(1);
  directory.markAvatarsStale(['u']);
  expect(directory.get('u')?.avatarStale).toBe(true);
  const again = directory.ensure('u'); await flush();
  calls[1].done.resolve({ display_name: 'Ann', avatar_attachment_id: 'y' }); await again;
  expect(directory.get('u')).toMatchObject({ avatarId: 'y', avatarStale: false });
});
test('fresh entries are reused and expired entries are revalidated', async () => {
  const { directory, calls, advance } = harness();
  const first = directory.ensure('u'); await flush();
  calls[0].done.resolve({ display_name: 'Ann', avatar_attachment_id: null }); await first;
  await directory.ensure('u'); expect(calls.length).toBe(1);
  advance(300_001); void directory.ensure('u'); await flush();
  expect(calls.length).toBe(2);
});
test('responses and puts are discarded when the owner is no longer accepted', async () => {
  let accepted = true;
  const { directory, calls } = harness({ accept: () => accepted });
  const first = directory.ensure('u'); await flush();
  accepted = false;
  calls[0].done.resolve({ display_name: 'Ann', avatar_attachment_id: null }); await first;
  directory.put('v', { display_name: 'Leaked', avatar_attachment_id: 'a' });
  expect(directory.get('u')).toBeUndefined();
  expect(directory.get('v')).toBeUndefined();
});
test('a group membership version increase marks only that group members stale', async () => {
  const { directory, calls } = harness();
  for (const id of ['a', 'b', 'c']) { const done = directory.ensure(id); await flush(); calls.at(-1)!.done.resolve({ display_name: id, avatar_attachment_id: null }); await done; }
  directory.observeMembership('g', 3, ['a', 'b']);
  expect(directory.get('a')?.avatarStale).toBe(false);
  directory.observeMembership('g', 3, ['a', 'b']);
  directory.observeMembership('g', null, ['a', 'b']);
  expect(directory.get('a')?.avatarStale).toBe(false);
  directory.observeMembership('g', 4, ['a', 'b']);
  expect(directory.get('a')?.avatarStale).toBe(true);
  expect(directory.get('b')?.avatarStale).toBe(true);
  expect(directory.get('c')?.avatarStale).toBe(false);
});
test('subscribe works when passed unbound', () => {
  const { directory } = harness();
  const { subscribe, getVersion } = directory;
  const unsubscribe = subscribe(() => {});
  expect(typeof getVersion()).toBe('number');
  unsubscribe();
});
test('switching account resets the directory and ignores the old account response', async () => {
  let snapshot = { context: { state: 'authenticated', user_id: 'A', device_id: 'd' } };
  const listeners = new Set<() => void>(), pending: ReturnType<typeof deferred<{ data: Summary }>>[] = [];
  const session = { getSnapshot: () => snapshot, subscribe: (listener: () => void) => { listeners.add(listener); return () => listeners.delete(listener); }, request: () => { const done = deferred<{ data: Summary }>(); pending.push(done); return done.promise; } } as unknown as SessionController;
  const first = directoryFor(session);
  const loading = first.ensure('x'); await flush();
  snapshot = { context: { state: 'authenticated', user_id: 'B', device_id: 'd' } };
  for (const listener of listeners) listener();
  pending[0].resolve({ data: { display_name: 'From A', avatar_attachment_id: null } }); await loading;
  first.put('y', { display_name: 'A view of y', avatar_attachment_id: 'a' });
  const second = directoryFor(session);
  expect(second).not.toBe(first);
  expect(first.get('x')).toBeUndefined();
  expect(first.get('y')).toBeUndefined();
  expect(second.get('x')).toBeUndefined();
  expect(second.get('y')).toBeUndefined();
});
```

- [ ] **Step 2：Run** `~/.bun/bin/bun test src/user-directory.test.ts`。Expected：FAIL（模組不存在）。
- [ ] **Step 3：實作**

```ts
import { ownerPartition } from './api';
import type { SessionController } from './session';
import type { UserSummary } from './types';

export interface DirectoryEntry { displayName: string; avatarId: string | null; fetchedAt: number; avatarStale: boolean }
type Summary = { display_name: string; avatar_attachment_id: string | null };
export interface DirectoryDeps { fetchSummary(userId: string, signal: AbortSignal): Promise<Summary>; now(): number; accept(): boolean }
interface Job { run(): void; cancel(): void }

export class UserDirectory {
  private entries = new Map<string, DirectoryEntry>();
  private versions = new Map<string, number>();
  private failedAt = new Map<string, number>();
  private memberships = new Map<string, number>();
  private inflight = new Map<string, { version: number; promise: Promise<void> }>();
  private queue: Job[] = [];
  private running = 0;
  private epoch = 0;
  private abort = new AbortController();
  private listeners = new Set<() => void>();
  private version = 0;
  private readonly ttl: number;
  private readonly limit: number;
  private readonly backoff: number;
  constructor(private readonly deps: DirectoryDeps, options: { ttlMs?: number; concurrency?: number; failureBackoffMs?: number } = {}) {
    this.ttl = options.ttlMs ?? 300_000; this.limit = options.concurrency ?? 4; this.backoff = options.failureBackoffMs ?? 30_000;
  }
  subscribe = (listener: () => void): (() => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  getVersion = (): number => this.version;
  get(userId: string): DirectoryEntry | undefined { return this.entries.get(userId); }
  private changed(): void { this.version++; for (const listener of this.listeners) listener(); }
  private versionOf(userId: string): number { return this.versions.get(userId) ?? 0; }
  private bump(userId: string): void { this.versions.set(userId, this.versionOf(userId) + 1); }
  ensure(userId: string): Promise<void> {
    const entry = this.entries.get(userId), now = this.deps.now();
    if (entry && !entry.avatarStale && now - entry.fetchedAt <= this.ttl) return Promise.resolve();
    const failed = this.failedAt.get(userId);
    if (failed !== undefined && now - failed <= this.backoff) return Promise.resolve();
    const version = this.versionOf(userId), existing = this.inflight.get(userId);
    if (existing && existing.version === version) return existing.promise;
    const epoch = this.epoch, signal = this.abort.signal;
    const work = new Promise<void>(resolve => {
      const run = (): void => {
        this.running++;
        this.deps.fetchSummary(userId, signal).then(summary => {
          if (epoch !== this.epoch || this.versionOf(userId) !== version || !this.deps.accept()) return;
          this.failedAt.delete(userId); this.store(userId, summary);
        }, () => { if (epoch === this.epoch) this.failedAt.set(userId, this.deps.now()); })
          .finally(() => { this.running--; resolve(); this.pump(); });
      };
      this.queue.push({ run, cancel: resolve });
      this.pump();
    });
    const tracked = work.finally(() => { if (this.inflight.get(userId)?.promise === tracked) this.inflight.delete(userId); });
    this.inflight.set(userId, { version, promise: tracked });
    return tracked;
  }
  private pump(): void { while (this.running < this.limit && this.queue.length) this.queue.shift()!.run(); }
  private store(userId: string, summary: Summary): void { this.entries.set(userId, { displayName: summary.display_name, avatarId: summary.avatar_attachment_id, fetchedAt: this.deps.now(), avatarStale: false }); this.changed(); }
  put(userId: string, summary: Summary): void { if (!this.deps.accept()) return; this.bump(userId); this.failedAt.delete(userId); this.store(userId, summary); }
  markAvatarsStale(userIds: string[]): void {
    let changed = false;
    for (const id of userIds) { const entry = this.entries.get(id); this.bump(id); if (entry && !entry.avatarStale) { this.entries.set(id, { ...entry, avatarStale: true }); changed = true; } }
    if (changed) this.changed();
  }
  observeMembership(groupId: string, version: number | null, memberIds: string[]): void {
    if (version === null) return;
    const previous = this.memberships.get(groupId);
    this.memberships.set(groupId, version);
    if (previous !== undefined && version > previous) this.markAvatarsStale(memberIds);
  }
  reset(): void {
    this.epoch++; this.abort.abort(); this.abort = new AbortController();
    for (const job of this.queue) job.cancel();
    this.queue = []; this.entries.clear(); this.versions.clear(); this.failedAt.clear(); this.memberships.clear(); this.inflight.clear(); this.changed();
  }
}

let current: { owner: string; directory: UserDirectory; unsubscribe: () => void } | null = null;
export function directoryFor(session: SessionController): UserDirectory {
  const context = session.getSnapshot().context, owner = ownerPartition(context.user_id, context.device_id);
  if (current?.owner === owner) return current.directory;
  current?.unsubscribe(); current?.directory.reset();
  const accept = (): boolean => { const now = session.getSnapshot().context; return now.state === 'authenticated' && ownerPartition(now.user_id, now.device_id) === owner; };
  const directory = new UserDirectory({ fetchSummary: async (id, signal) => (await session.request<UserSummary>(`/users/${encodeURIComponent(id)}`, { signal })).data, now: () => Date.now(), accept });
  const unsubscribe = session.subscribe(() => { const now = session.getSnapshot().context; if (ownerPartition(now.user_id, now.device_id) !== owner) directory.reset(); });
  current = { owner, directory, unsubscribe };
  return directory;
}
```

- [ ] **Step 4：Run** 同 Step 2。Expected：13 pass。
- [ ] **Step 5：Commit** `feat: add owner-scoped user summary cache`

### Task 2.2b：頭像位元組快取（`avatar-cache.ts`）

**Files:** Create `frontend/app/src/avatar-cache.ts`、`frontend/app/src/avatar-cache.test.ts`；Modify `frontend/app/src/ContactsPage.tsx:95-119`（`Avatar` 改用快取；匯出名稱與 props 不變）

**Interfaces:**
- Produces: `interface AvatarDeps { load(attachmentId: string, signal: AbortSignal): Promise<Blob>; createURL(blob: Blob): string; revokeURL(url: string): void; accept(): boolean }`；`class AvatarCache`：`acquire(attachmentId): Promise<string | null>`（永不 reject；失敗回 null 且不快取）、`release(attachmentId)`、`reset()`（中止下載、撤銷全部 URL、所有未完成的 `acquire` 以 null 結算）；`avatarCacheFor(session, load): AvatarCache`（owner 改變時 `reset` 舊實例；`load` 由呼叫端注入，避免 `avatar-cache.ts` 反向 import `ContactsPage.tsx`）。

- [ ] **Step 1：寫失敗測試**

```ts
import { expect, test } from 'bun:test';
import { AvatarCache } from './avatar-cache';

function deferred<T>() { let resolve!: (value: T) => void, reject!: (error: unknown) => void; const promise = new Promise<T>((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; }
function harness(options: { idleLimit?: number; concurrency?: number } = {}) {
  const loads: { id: string; signal: AbortSignal; done: ReturnType<typeof deferred<Blob>> }[] = [], revoked: string[] = [];
  let next = 0;
  const cache = new AvatarCache({ load: (id, signal) => { const done = deferred<Blob>(); loads.push({ id, signal, done }); return done.promise; }, createURL: () => `blob:${++next}`, revokeURL: url => { revoked.push(url); }, accept: () => true }, { idleLimit: options.idleLimit ?? 48, concurrency: options.concurrency ?? 4 });
  return { cache, loads, revoked };
}
const flush = () => new Promise(resolve => setTimeout(resolve, 0));
const blob = () => new Blob(['x']);

test('concurrent acquires share one download and one object URL', async () => {
  const { cache, loads } = harness();
  const a = cache.acquire('p'), b = cache.acquire('p'); await flush();
  expect(loads.length).toBe(1);
  loads[0].done.resolve(blob());
  expect(await a).toBe('blob:1'); expect(await b).toBe('blob:1');
});
test('a released avatar is reused without downloading again', async () => {
  const { cache, loads } = harness();
  const first = cache.acquire('p'); await flush(); loads[0].done.resolve(blob()); await first;
  cache.release('p');
  expect(await cache.acquire('p')).toBe('blob:1');
  expect(loads.length).toBe(1);
});
test('idle avatars beyond the limit are revoked oldest first; in-use ones are kept', async () => {
  const { cache, loads, revoked } = harness({ idleLimit: 1 });
  for (const id of ['a', 'b', 'c']) { const done = cache.acquire(id); await flush(); loads.at(-1)!.done.resolve(blob()); await done; }
  cache.release('a'); cache.release('b');
  expect(revoked).toEqual(['blob:1']);
  expect(await cache.acquire('c')).toBe('blob:3');
});
test('failures are not cached and resolve to null', async () => {
  const { cache, loads } = harness();
  const first = cache.acquire('p'); await flush(); loads[0].done.reject(new Error('expired'));
  expect(await first).toBeNull();
  cache.release('p');
  void cache.acquire('p'); await flush();
  expect(loads.length).toBe(2);
});
test('no more than the configured number of downloads run at once', async () => {
  const { cache, loads } = harness({ concurrency: 2 });
  for (const id of ['a', 'b', 'c']) void cache.acquire(id);
  await flush(); expect(loads.length).toBe(2);
  loads[0].done.resolve(blob()); await flush();
  expect(loads.length).toBe(3);
});
test('reset aborts downloads, revokes every URL and settles pending acquires with null', async () => {
  const { cache, loads, revoked } = harness();
  const held = cache.acquire('a'); await flush(); loads[0].done.resolve(blob()); await held;
  const pending = cache.acquire('b'); await flush();
  cache.reset();
  expect(loads[1].signal.aborted).toBe(true);
  expect(await pending).toBeNull();
  expect(revoked).toEqual(['blob:1']);
  loads[1].done.resolve(blob()); await flush();
  expect(revoked.length).toBe(1);
});
```

- [ ] **Step 2：Run** `~/.bun/bin/bun test src/avatar-cache.test.ts`。Expected：FAIL（模組不存在）。
- [ ] **Step 3：實作**

```ts
import { ownerPartition } from './api';
import type { SessionController } from './session';

export interface AvatarDeps { load(attachmentId: string, signal: AbortSignal): Promise<Blob>; createURL(blob: Blob): string; revokeURL(url: string): void; accept(): boolean }
interface Entry { refs: number; url: string | null; promise: Promise<string | null>; settle(value: string | null): void }

export class AvatarCache {
  private entries = new Map<string, Entry>();
  private idle: string[] = [];
  private queue: { run(): void }[] = [];
  private running = 0;
  private epoch = 0;
  private abort = new AbortController();
  private readonly idleLimit: number;
  private readonly limit: number;
  constructor(private readonly deps: AvatarDeps, options: { idleLimit?: number; concurrency?: number } = {}) { this.idleLimit = options.idleLimit ?? 48; this.limit = options.concurrency ?? 4; }
  acquire(attachmentId: string): Promise<string | null> {
    const existing = this.entries.get(attachmentId);
    if (existing) { existing.refs++; this.idle = this.idle.filter(id => id !== attachmentId); return existing.promise; }
    const epoch = this.epoch, signal = this.abort.signal;
    let settle!: (value: string | null) => void;
    const entry: Entry = { refs: 1, url: null, promise: new Promise<string | null>(resolve => { settle = resolve; }), settle: value => settle(value) };
    this.entries.set(attachmentId, entry);
    this.queue.push({ run: () => {
      if (this.entries.get(attachmentId) !== entry) { entry.settle(null); return; }
      this.running++;
      this.deps.load(attachmentId, signal).then(blob => {
        if (epoch !== this.epoch || !this.deps.accept() || this.entries.get(attachmentId) !== entry) { entry.settle(null); return; }
        entry.url = this.deps.createURL(blob); entry.settle(entry.url);
      }, () => { if (this.entries.get(attachmentId) === entry) this.entries.delete(attachmentId); entry.settle(null); })
        .finally(() => { this.running--; this.pump(); });
    } });
    this.pump();
    return entry.promise;
  }
  release(attachmentId: string): void {
    const entry = this.entries.get(attachmentId); if (!entry || entry.refs === 0) return;
    entry.refs--; if (entry.refs > 0) return;
    if (entry.url === null) { this.entries.delete(attachmentId); return; }
    this.idle.push(attachmentId);
    while (this.idle.length > this.idleLimit) {
      const oldest = this.idle.shift()!, evicted = this.entries.get(oldest);
      this.entries.delete(oldest); if (evicted?.url) this.deps.revokeURL(evicted.url);
    }
  }
  private pump(): void { while (this.running < this.limit && this.queue.length) this.queue.shift()!.run(); }
  reset(): void {
    this.epoch++; this.abort.abort(); this.abort = new AbortController();
    for (const entry of this.entries.values()) { if (entry.url) this.deps.revokeURL(entry.url); entry.settle(null); }
    this.queue = []; this.entries.clear(); this.idle = [];
  }
}

let current: { owner: string; cache: AvatarCache; unsubscribe: () => void } | null = null;
export function avatarCacheFor(session: SessionController, load: (attachmentId: string, signal: AbortSignal) => Promise<Blob>): AvatarCache {
  const context = session.getSnapshot().context, owner = ownerPartition(context.user_id, context.device_id);
  if (current?.owner === owner) return current.cache;
  current?.unsubscribe(); current?.cache.reset();
  const accept = (): boolean => { const now = session.getSnapshot().context; return now.state === 'authenticated' && ownerPartition(now.user_id, now.device_id) === owner; };
  const cache = new AvatarCache({ load, createURL: blob => URL.createObjectURL(blob), revokeURL: url => URL.revokeObjectURL(url), accept });
  const unsubscribe = session.subscribe(() => { const now = session.getSnapshot().context; if (ownerPartition(now.user_id, now.device_id) !== owner) cache.reset(); });
  current = { owner, cache, unsubscribe };
  return cache;
}
```

`ContactsPage.tsx` 提供下載函式（沿用現行 `downloadAttachment` 與 `fetchAvatarBytes`，30 秒逾時與現行 `:104` 相同）：

```ts
function loadAvatar(session: SessionController) {
  return async (attachmentId: string, signal: AbortSignal): Promise<Blob> => {
    const child = new AbortController(), stop = (): void => child.abort();
    signal.addEventListener('abort', stop, { once: true }); const timeout = setTimeout(stop, 30_000);
    try { return await fetchAvatarBytes(await downloadAttachment(session, attachmentId), fetch, child.signal); }
    finally { clearTimeout(timeout); signal.removeEventListener('abort', stop); }
  };
}
```

- [ ] **Step 4：`Avatar` 改用快取**（props、外層 `span.avatar`、`aria-label`、`alt`、首字後備不變）：

```tsx
useEffect(() => {
  if (!attachmentId || session.getSnapshot().context.state !== 'authenticated') { setUrl(null); setFailed(false); return; }
  const cache = avatarCacheFor(session, loadAvatar(session)); let active = true; setUrl(null); setFailed(false);
  void cache.acquire(attachmentId).then(value => { if (!active) return; if (value) setUrl(value); else setFailed(true); });
  return () => { active = false; cache.release(attachmentId); };
}, [session, attachmentId]);
```

- [ ] **Step 5：Run** Step 2 與三命令。Expected：6 pass；既有測試全數通過。
- [ ] **Step 6：Commit** `feat: share owner-scoped avatar downloads`

### Task 2.3：`ChatList.tsx`

**Files:** Create `frontend/app/src/ChatList.tsx`（移出 `App.tsx:13-23`）；Modify `App.tsx`、`ContactsPage.tsx:176`、`ProfilePage.tsx:82`、`Shell.css`

**Interfaces:**
- Consumes: Task 2.1、2.2、2.2b 全部匯出；`usePagedList`、`Avatar`、`CreateGroup`（Phase 2 仍為現行 inline 版本）；`chat.getSnapshot()`、`chat.subscribe`、`chat.refreshConversation`。
- Produces: `export function ChatList({ session, chat, path, onNavigate }: { session: SessionController; chat: ChatController; path: string; onNavigate: (path: string) => void })`；根元素 `className="list-panel chat-list"`；`<ul className="item-list" aria-label="對話清單">`；未讀徽章 `aria-label="N 則伺服器查詢未讀"`。

- [ ] **Step 1：排序與撤權接線**

```tsx
const snapshot = useSyncExternalStore(chat.subscribe, chat.getSnapshot);
const context = session.getSnapshot().context, owner = ownerPartition(context.user_id, context.device_id);
const book = activityBookFor(owner), denied = deniedMemoryFor(owner);
for (const id of snapshot.denied) { book.drop(id); denied.hide(id); }
for (const item of list.items) book.observe(item.id, snapshot.messages[item.id]?.at(-1)?.created_at);
const visible = useMemo(() => sortConversations(list.items.filter(item => !denied.has(item.id)), book), [list.items, snapshot.messages, snapshot.denied]);
```

`usePagedList` 的重新載入完成時（`list.busy` 由 true 轉 false 且沒有 `list.error`）呼叫 `denied.clear()`。

- [ ] **Step 2：一對一對象與名稱**：列以 `IntersectionObserver`（root 為清單捲動容器）回報可見後：對象 = `snapshot.messages[id]` 中第一個 `sender_id !== me` 的寄件者 → 否則 `snapshot.details[id]?.members` 中非自己 → 否則放入上限 4 的佇列呼叫 `chat.refreshConversation(id)`；錯誤若為 `RepositoryCancelled` 或 `code === 'UNAUTHENTICATED'` 靜默略過，其他錯誤只記在該列並顯示 ID；每個對話在一次清單載入週期內最多呼叫一次。需要名稱的使用者 ID（可見列的對象、群組預覽寄件者）在 render 中算成**排序後以逗號連接的字串**，`useEffect(() => { for (const id of ids.split(',').filter(Boolean)) void directory.ensure(id); }, [ids, directory])`，不在 render 中呼叫 `ensure`。以 `useSyncExternalStore(directory.subscribe, directory.getVersion)` 觸發重繪。
- [ ] **Step 3：列內容**：`Avatar`（`directory.get(peer)?.avatarId`，`avatarStale` 時顯示首字）、名稱（目錄名稱 → 對象 ID → 「一對一對話」；群組用 A11 標題原文）、`previewText`、`formatListTime(last.created_at, now)`、未讀徽章；`now` 每分鐘更新一次的 state。定位掛點（spec R11）：列為 `<button className="list-item" data-conversation-id={item.id}>`，名稱放在列內唯一的 `<strong>`，未讀徽章 `<span className="unread" aria-label="N 則伺服器查詢未讀">N</span>`（0 時不渲染）。
- [ ] **Step 4：搜尋、骨架、空狀態**：搜尋比對名稱與標題，提示文字「只篩選已載入項目」（一般 `<p>`，**不用** `role="status"`）；`list.items.length === 0 && list.busy` 才顯示骨架；載入中狀態沿用 `.chat-list` 內唯一的 `role="status"`，載入完成即移除；「載入下一頁」按鈕維持在 `.actions` 內；空狀態按鈕「到聯絡人開始聊天」；Phase 2 保留現行 `CreateGroup` 於清單頂部。
- [ ] **Step 4a：同步 `review-shell-native.ts`**：`:126` 改為 `button.dataset.conversationId === id`；`:228` 改為 `[...document.querySelectorAll<HTMLElement>('.chat-list [data-conversation-id]')].map(element => element.dataset.conversationId)`；`:130` 改為群組列 `strong` 等於 A11 `title`、一對一列 `strong` 非空（腳本的情境只建立群組，群組斷言不變）；`:254,259` 依賴的 `.chat-list .item-list` 保留不改。其他斷言（`.unread`、`role="status"`、「載入下一頁」、游標、去重、舊 owner 隔離）不變。此腳本無執行入口，以 typecheck 確認可編譯；回報時明示未實際執行。
- [ ] **Step 5：快取失效接線**：ChatList 與 ChatView 在 `snapshot.details` 變化的 effect 中，對每個群組呼叫 `directory.observeMembership(id, detail.membership_version, detail.members.map(m => m.user_id))`（上次版本存在快取實例內，不用元件 ref）；`ContactsPage.tsx:176` 聯絡人增刪後 `markAvatarsStale([selected.id])`；`GroupsPage` 變更成功後 `markAvatarsStale(detail.members.map(m => m.user_id))`；`ProfilePage.tsx:82` 在**送出請求前**取得 `const directory = directoryFor(session)`，成功後 `directory.put(result.data.id, result.data)`（`put` 內再做 owner 檢查）。
- [ ] **Step 6：Run 三命令；CI 8／8；本機 25 個對話依完成條件驗證並截圖。**
- [ ] **Step 7：Commit** `feat: Telegram-style chat list with stable ordering`

### Task 2.4：聊天路由保留清單實例、自身資訊（spec R13、§6.4）

**Files:** Modify `frontend/app/src/App.tsx:67-74`、`Shell.css`

- [ ] **Step 1：權限閘門只包聊天室**：`route.kind` 為 `chats` 或 `chat` 且沒有 `routeError` 時，不論 `allowedKey`，都渲染同一個 `<section className="split-page chats-page …">`，`ChatList` 位於固定位置；`.chat-detail` 內：`allowedKey === key` 時渲染現行 `.narrow-back` 與 `Chat`，否則渲染 `<p role="status">正在確認頁面權限…</p>`。`routeError` 錯誤頁、其他路由的整頁閘門、`App.tsx:40-59` 的 effect 全部不變。
- [ ] **Step 2：自身資訊**：圖示欄底部與 ☰ 選單頂部顯示自己的頭像與名稱，來源為 `directory.get(me)`（effect 中 `ensure(me)`），沒有資料時顯示首字「H」。
- [ ] **Step 3：驗證**：三命令；本機在寬版從對話 A 點到對話 B，清單捲動位置不變、Network 面板沒有重新發出清單列的 `/users/`、`/attachments/…/download` 請求（截圖）；直接開 `/chats/{無權限 ID}` 仍顯示「無法存取此頁面」。推送後 CI 8／8。
- [ ] **Step 4：Commit** `feat: keep the chat list mounted while switching conversations`

---

## Phase 3：Chat View

**目標**：聊天室頂部列、時間軸（分組、日期分隔）、狀態圖示、浮動日期膠囊、浮動「跳至最新」、新輸入列、名稱快取、尾端進場動畫。

**依賴**：Phase 1、Task 2.1、Task 2.2。

**潛在失效模式**：已讀提早或漏判；錨點漂移；重連或補回時大量動畫；`data-message-id` 重複或非 UUID；`.message-meta` 文字消失；「跳至最新」名稱重複造成定位衝突；浮動膠囊造成全室重繪。

**完成條件**：Task 3.1–3.3 測試通過；三命令 exit 0；CI 8／8，其中 `visible_recipient_read_observer_commits_read_receipt`、`physical_reload_restores_draft_from_indexeddb`、`recipient_offline_to_100_dom_and_idb_recovery`（≤5000ms）、`genuine_reload_replays_same_unconfirmed_c1_to_same_single_m1` 通過；本機確認離線補回 3 則以上時沒有進場動畫（DevTools Animations 面板截圖）。

**建議提交**：Task 3.1、3.2、3.3、3.4 各一個提交。

### Task 3.1：時間軸、狀態、進場判定（`chat-presentation.ts` 第二部分）

**Files:** Modify `chat-presentation.ts`、`chat-presentation.test.ts`

**Interfaces:**
- Produces: `dateLabel(value: Date, now: Date): string`；`type TimelineItem = { kind: 'date'; key: string; label: string } | { kind: 'message'; message: MessageView; groupStart: boolean; groupEnd: boolean }`；`buildTimeline(messages: MessageView[], now: Date): TimelineItem[]`；`type StatusIcon = 'clock' | 'check' | 'double' | 'double-read' | 'warn'`；`messageStatus(message, kind)`；`intentStatus(status: SendIntent['status'])`；`entryAnimationIds(baseline: readonly string[] | null, next: readonly string[], replaced: ReadonlySet<string>): string[]`；`MAX_ENTRY_ANIMATIONS = 3`。

- [ ] **Step 1：寫失敗測試**（附加到 `chat-presentation.test.ts`；新增 import 與輔助函式）

```ts
import { buildTimeline, entryAnimationIds, intentStatus, messageStatus } from './chat-presentation';

function at2(id: string, sender: string, iso: string, order: string): MessageView { return { id, event_id: id, conversation_id: 'c', sender_id: sender, created_at: iso, order_key: order, receipt: null, type: 'text', text: id }; }
test('timeline groups one sender within five minutes on the same day', () => {
  const items = buildTimeline([
    at2('m1', 'ann', new Date(2026, 9, 16, 23, 58).toISOString(), '1'),
    at2('m2', 'ann', new Date(2026, 9, 17, 0, 1).toISOString(), '2'),
    at2('m3', 'ann', new Date(2026, 9, 17, 0, 4).toISOString(), '3'),
    at2('m4', 'bob', new Date(2026, 9, 17, 0, 5).toISOString(), '4'),
    at2('m5', 'bob', new Date(2026, 9, 17, 0, 11).toISOString(), '5'),
  ], new Date(2026, 9, 17, 12, 0));
  expect(items.map(item => item.kind === 'date' ? `${item.key}|${item.label}` : `${item.message.id}:${+item.groupStart}${+item.groupEnd}`)).toEqual([
    'date:2026-10-16|昨天', 'm1:11', 'date:2026-10-17|今天', 'm2:10', 'm3:01', 'm4:11', 'm5:11',
  ]);
});
test('date keys are not message ids and stay stable when history is prepended', () => {
  const now = new Date(2026, 9, 17, 12, 0), iso = new Date(2026, 9, 17, 9, 0).toISOString();
  const keys = (list: MessageView[]) => buildTimeline(list, now).filter(item => item.kind === 'date').map(item => item.key);
  expect(keys([at2('m1', 'a', iso, '1'), at2('m2', 'a', iso, '2')])).toEqual(keys([at2('m2', 'a', iso, '2')]));
  for (const key of keys([at2('m2', 'a', iso, '2')])) expect(key.startsWith('date:')).toBe(true);
});
test('status text matches the existing message meta wording', () => {
  const base = at2('m', 'me', new Date().toISOString(), '1');
  const receipt = (status: 'delivered' | 'read') => ({ kind: 'direct' as const, message_id: 'm', recipient_id: 'b', status, updated_at: base.created_at });
  expect(messageStatus(base, 'direct')).toEqual({ icon: 'check', text: '已持久保存' });
  expect(messageStatus({ ...base, receipt: receipt('delivered') }, 'direct')).toEqual({ icon: 'double', text: '已送達' });
  expect(messageStatus({ ...base, receipt: receipt('read') }, 'direct')).toEqual({ icon: 'double-read', text: '已讀' });
  expect(messageStatus(base, 'group')).toEqual({ icon: 'check', text: '已持久保存' });
  expect(intentStatus('pending')).toEqual({ icon: 'clock', text: '等待傳送' });
  expect(intentStatus('persisted')).toEqual({ icon: 'clock', text: '已持久保存，正在核對訊息' });
  expect(intentStatus('unknown')).toEqual({ icon: 'warn', text: '結果尚未確認' });
  expect(intentStatus('rejected')).toEqual({ icon: 'warn', text: '未傳送' });
});
test('only a few messages appended after an established baseline animate', () => {
  expect(entryAnimationIds(null, ['a', 'b'], new Set())).toEqual([]);
  expect(entryAnimationIds([], ['a'], new Set())).toEqual([]);
  expect(entryAnimationIds(['b', 'c'], ['a', 'b', 'c'], new Set())).toEqual([]);
  expect(entryAnimationIds(['a', 'b'], ['a', 'b', 'c', 'd'], new Set())).toEqual(['c', 'd']);
  expect(entryAnimationIds(['a', 'b'], ['a', 'b', 'c'], new Set(['c']))).toEqual([]);
  expect(entryAnimationIds(['x'], ['a', 'b'], new Set())).toEqual([]);
  expect(entryAnimationIds(['a'], ['a', 'b', 'c', 'd', 'e'], new Set())).toEqual([]);
});
```

- [ ] **Step 2：Run** `~/.bun/bin/bun test src/chat-presentation.test.ts`。Expected：FAIL（未匯出）。
- [ ] **Step 3：實作**（附加；檔頭加 `import type { SendIntent } from './repository';`）

```ts
const GROUP_WINDOW_MS = 5 * 60_000;
export const MAX_ENTRY_ANIMATIONS = 3;
function dateKey(value: Date): string { return `date:${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`; }
export function dateLabel(value: Date, now: Date): string {
  const days = daysBetween(value, now);
  if (days <= 0) return '今天';
  if (days === 1) return '昨天';
  return value.getFullYear() === now.getFullYear() ? `${value.getMonth() + 1}月${value.getDate()}日` : `${value.getFullYear()}年${value.getMonth() + 1}月${value.getDate()}日`;
}
export type TimelineItem = { kind: 'date'; key: string; label: string } | { kind: 'message'; message: MessageView; groupStart: boolean; groupEnd: boolean };
export function buildTimeline(messages: MessageView[], now: Date): TimelineItem[] {
  const items: TimelineItem[] = []; let previous: MessageView | null = null, lastDay = '';
  for (const message of messages) {
    const created = new Date(message.created_at), day = dateKey(created);
    if (day !== lastDay) { items.push({ kind: 'date', key: day, label: dateLabel(created, now) }); lastDay = day; previous = null; }
    const joins = previous !== null && previous.sender_id === message.sender_id && Date.parse(message.created_at) - Date.parse(previous.created_at) <= GROUP_WINDOW_MS;
    const last = items.at(-1);
    if (joins && last?.kind === 'message') last.groupEnd = false;
    items.push({ kind: 'message', message, groupStart: !joins, groupEnd: true });
    previous = message;
  }
  return items;
}
export type StatusIcon = 'clock' | 'check' | 'double' | 'double-read' | 'warn';
export function messageStatus(message: MessageView, kind: 'direct' | 'group'): { icon: StatusIcon; text: string } {
  if (kind === 'direct' && message.receipt) return message.receipt.status === 'read' ? { icon: 'double-read', text: '已讀' } : { icon: 'double', text: '已送達' };
  return { icon: 'check', text: '已持久保存' };
}
export function intentStatus(status: SendIntent['status']): { icon: StatusIcon; text: string } {
  if (status === 'persisted') return { icon: 'clock', text: '已持久保存，正在核對訊息' };
  if (status === 'rejected') return { icon: 'warn', text: '未傳送' };
  if (status === 'unknown') return { icon: 'warn', text: '結果尚未確認' };
  return { icon: 'clock', text: '等待傳送' };
}
export function entryAnimationIds(baseline: readonly string[] | null, next: readonly string[], replaced: ReadonlySet<string>): string[] {
  if (!baseline?.length) return [];
  const index = next.indexOf(baseline[baseline.length - 1]); if (index < 0) return [];
  const known = new Set(baseline);
  const entering = next.slice(index + 1).filter(id => !known.has(id) && !replaced.has(id));
  return entering.length > MAX_ENTRY_ANIMATIONS ? [] : entering;
}
```

- [ ] **Step 4：Run** 同 Step 2。Expected：全部 pass。
- [ ] **Step 5：Commit** `feat: build chat timeline and status presentation`

### Task 3.2：`ReadObserver` 不計入未完成動畫

**Files:** Modify `read-observer.ts:42`、`read-observer.test.ts`

**Interfaces:** Produces `export function bubbleMeasurable(bubble: { getAnimations?: () => { playState: string }[] }): boolean`

- [ ] **Step 1：寫失敗測試**（附加到 `read-observer.test.ts`）

```ts
import { bubbleMeasurable } from './read-observer';
test('a bubble with an unfinished animation is not measured for read', () => {
  expect(bubbleMeasurable({ getAnimations: () => [{ playState: 'running' }] })).toBe(false);
  expect(bubbleMeasurable({ getAnimations: () => [{ playState: 'paused' }] })).toBe(false);
  expect(bubbleMeasurable({ getAnimations: () => [{ playState: 'finished' }] })).toBe(true);
  expect(bubbleMeasurable({ getAnimations: () => [] })).toBe(true);
  expect(bubbleMeasurable({})).toBe(true);
});
```

- [ ] **Step 2：Run** `~/.bun/bin/bun test src/read-observer.test.ts`。Expected：FAIL（未匯出）。
- [ ] **Step 3：實作**

```ts
export function bubbleMeasurable(bubble:{getAnimations?:()=>{playState:string}[]}):boolean {return !(bubble.getAnimations?.()??[]).some(animation=>animation.playState==='running'||animation.playState==='paused');}
```

`read-observer.ts:42` 改為：

```ts
const eligible=permitted&&bubble.dataset.readEligible==='true'&&bubbleMeasurable(bubble)&&visibleRatio(bubble.getBoundingClientRect(),visible)>=0.5;
```

- [ ] **Step 4：Run** 同 Step 2。Expected：既有 4 個與新 1 個全部 pass。
- [ ] **Step 5：Commit** `fix: ignore animating bubbles when measuring reads`

### Task 3.3：`MessageRow.tsx`、浮動日期膠囊與 DOM 不變式

**Files:** Create `frontend/app/src/MessageRow.tsx`、`frontend/app/src/message-row.test.tsx`；Modify `ChatView.tsx:100`

**Interfaces:**
- Produces: `MessageRow({ item, own, kind, readEligible, senderName, accent, avatar, children })`、`IntentRow({ intent, connectionReady, onRetry, children })`、`DateSeparator({ label })`、`DatePill({ scroller, messages, now })`。

- [ ] **Step 1：寫失敗測試**

```tsx
import { expect, test } from 'bun:test';
import { renderToStaticMarkup } from 'react-dom/server';
import { DateSeparator, MessageRow } from './MessageRow';
import type { MessageView } from './types';

const id = '9f1c2b0e-1d2c-4e5f-8a9b-0c1d2e3f4a5b';
const message: MessageView = { id, event_id: '9f1c2b0e-1d2c-4e5f-8a9b-0c1d2e3f4a5c', conversation_id: 'c', sender_id: 'me', created_at: '2026-10-17T01:00:00Z', order_key: '00000000000000000001', receipt: { kind: 'direct', message_id: id, recipient_id: 'b', status: 'read', updated_at: '2026-10-17T01:00:01Z' }, type: 'text', text: '你好' };
test('a message renders exactly one UUID data-message-id and keeps status text in its meta', () => {
  const html = renderToStaticMarkup(<ol><MessageRow item={{ kind: 'message', message, groupStart: true, groupEnd: true }} own kind="direct" readEligible={false} senderName="我" accent={1}><p className="message-text">你好</p></MessageRow></ol>);
  expect(html.match(/data-message-id="/g)?.length).toBe(1);
  expect(html).toContain(`data-message-id="${id}"`);
  expect(html).toContain('data-read-eligible="false"');
  expect(html.slice(html.indexOf('message-meta'))).toContain('已讀');
});
test('date separators never carry message ids or read occlusion', () => {
  const html = renderToStaticMarkup(<ol><DateSeparator label="今天" /></ol>);
  expect(html).not.toContain('data-message-id');
  expect(html).not.toContain('data-read-occlusion');
  expect(html).toContain('今天');
});
```

- [ ] **Step 2：Run** `~/.bun/bin/bun test src/message-row.test.tsx`。Expected：FAIL（模組不存在）。
- [ ] **Step 3：實作 `MessageRow.tsx`**

```tsx
import { useEffect, useRef, useState, type ReactNode, type RefObject } from 'react';
import { dateLabel, intentStatus, messageStatus, type StatusIcon, type TimelineItem } from './chat-presentation';
import type { SendIntent } from './repository';
import type { MessageView } from './types';

const time = new Intl.DateTimeFormat('zh-TW', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
const ICON: Record<StatusIcon, string> = { clock: '🕓', check: '✓', double: '✓✓', 'double-read': '✓✓', warn: '⚠' };
function Status({ icon, text }: { icon: StatusIcon; text: string }) {
  return <span className={`message-status status-${icon}`}><span aria-hidden="true">{ICON[icon]}</span><span className="visually-hidden">{text}</span></span>;
}
export function DateSeparator({ label }: { label: string }) { return <li className="date-separator" role="separator"><span>{label}</span></li>; }
export function MessageRow({ item, own, kind, readEligible, senderName, accent, avatar, children }: { item: Extract<TimelineItem, { kind: 'message' }>; own: boolean; kind: 'direct' | 'group'; readEligible: boolean; senderName: string; accent: number; avatar?: ReactNode; children: ReactNode }) {
  const { message, groupStart, groupEnd } = item, status = own ? messageStatus(message, kind) : null;
  return <li className={`message-row ${own ? 'own' : 'peer'}${groupStart ? ' group-start' : ''}${groupEnd ? ' group-end' : ''}`}>
    {kind === 'group' && !own && <span className="message-avatar" aria-hidden="true">{groupEnd ? avatar : null}</span>}
    <article className="message-bubble" data-message-id={message.id} data-read-eligible={readEligible ? 'true' : 'false'} aria-label={`${own ? '你' : senderName}的訊息`}>
      {kind === 'group' && !own && groupStart && <strong className={`message-sender accent-${accent}`}>{senderName}</strong>}
      {children}
      <footer className="message-meta"><time dateTime={message.created_at}>{time.format(new Date(message.created_at))}</time>{status && <Status {...status} />}</footer>
    </article>
  </li>;
}
export function IntentRow({ intent, connectionReady, onRetry, children }: { intent: SendIntent; connectionReady: boolean; onRetry: () => void; children: ReactNode }) {
  return <li className="message-row own group-start group-end">
    <article className={`message-bubble pending-message${intent.status === 'rejected' ? ' rejected-message' : ''}`} aria-label="你的待確認訊息">
      {children}
      <footer className="message-meta"><Status {...intentStatus(intent.status)} /></footer>
      {intent.error && <p className="intent-error">{intent.error === 'RATE_LIMITED' ? '傳送速度受限，請等待後重試。' : intent.error === 'FORBIDDEN' ? '對話權限已變更。' : '此傳送意圖尚未完成，原內容及識別碼已保留。'}</p>}
      {intent.status !== 'persisted' && <button type="button" disabled={!connectionReady || intent.retryAt !== null && intent.retryAt > Date.now()} onClick={onRetry}>以原意圖重試</button>}
    </article>
  </li>;
}
export function DatePill({ scroller, messages, now }: { scroller: RefObject<HTMLElement | null>; messages: MessageView[]; now: Date }) {
  const [label, setLabel] = useState<string | null>(null);
  const latest = useRef({ messages, now });
  latest.current = { messages, now };
  useEffect(() => {
    const element = scroller.current; if (!element) return; let frame = 0;
    const measure = (): void => {
      frame = 0;
      const top = element.getBoundingClientRect().top, atLatest = element.scrollHeight - element.clientHeight - element.scrollTop <= 48;
      const first = atLatest ? undefined : [...element.querySelectorAll<HTMLElement>('[data-message-id]')].find(node => node.getBoundingClientRect().bottom > top);
      const message = first ? latest.current.messages.find(item => item.id === first.dataset.messageId) : undefined;
      const next = !message ? null : dateLabel(new Date(message.created_at), latest.current.now);
      setLabel(current => (current === next ? current : next));
    };
    const onScroll = (): void => { if (!frame) frame = requestAnimationFrame(measure); };
    element.addEventListener('scroll', onScroll, { passive: true }); onScroll();
    return () => { element.removeEventListener('scroll', onScroll); if (frame) cancelAnimationFrame(frame); };
  }, [scroller]);
  return <div className="date-pill" data-read-occlusion aria-hidden="true" hidden={label === null}>{label}</div>;
}
```

- [ ] **Step 4：`ChatView.tsx` 改用**：`const timeline = useMemo(() => buildTimeline(messages, now), [messages, now]);`（`now` 為每分鐘更新的 state）；`timeline.map` 依 `kind` 渲染 `DateSeparator` 或 `MessageRow`（附件仍以 `AttachmentTile` 作為 children；群組他人訊息的 `avatar` 為 `<Avatar … />`）；待送意圖改用 `IntentRow`，重試沿用 `chat.retryIntent(intent.clientMessageId).catch(…)`；`<DatePill scroller={scroller} …/>` 放在 `.message-scroller` 之後、`.chat-room` 之內。
- [ ] **Step 5：Run 三命令。** Expected：全部 pass。
- [ ] **Step 6：Commit** `refactor: render chat timeline with stable message DOM`

### Task 3.4：頂部列、跳至最新、輸入列、名稱快取、進場動畫

**Files:** Modify `ChatView.tsx`、`Chat.css`

- [ ] **Step 1：頂部列**：`#chat-title` 只放名稱並帶 `data-route-heading`；頭像在 h1 外；副標題（一對一 `snapshot.presence[peer]==='online'` 為「線上」、群組「N 位成員」）；`<small role="status">{CONNECTION_LABEL[snapshot.connection]}</small>` 常駐；「群組資訊」為圖示按鈕，內含 visually-hidden 文字「群組資訊」。保留 `.chat-header` class 與 `data-read-occlusion`。
- [ ] **Step 2：跳至最新**：刪除捲動區內 `.history-control` 的「跳至最新」按鈕（保留「載入較早訊息」）；取代 `.new-message-prompt` 為捲動區外的 `<button className="jump-latest-fab" data-read-occlusion aria-label="跳至最新" hidden={atLatest && newCount === 0} onClick={latest}>↓{newCount > 0 && <span aria-hidden="true">{newCount}</span>}</button>`，另放 `<p className="visually-hidden" role="status">{newCount > 0 ? `${newCount} 則新訊息 · 不代表未讀數` : ''}</p>`。`atLatest` 為 state，初值 `true`；在 `captureAnchor`（捲動）與 `ChatView.tsx:60-64` 的 layout effect 結尾都以 `scrollHeight - clientHeight - scrollTop <= 48` 重新計算，只在值改變時 set（不會捲動的短聊天室也為 true）。
- [ ] **Step 3：輸入列**：保留 `form.chat-composer[data-read-occlusion]`、`#chat-draft`、label「撰寫訊息」、`.attachment-button` 的 `aria-label`、`.send-button`（可見 ➤，visually-hidden「傳送」）；字數計數 `[...draft].length > 3800` 才顯示。鍵盤處理器不改。
- [ ] **Step 4：名稱**：以 `const directory = directoryFor(session)` 取代 `ChatView.tsx:47`；`useSyncExternalStore(directory.subscribe, directory.getVersion)`；成員 ID（含自己）排序後以逗號連接成字串，`useEffect` 依該字串對每位 `void directory.ensure(id)`（不在 render 中呼叫）；`names[id]` 改為 `directory.get(id)?.displayName ?? (id === me ? '你' : id)`；`GroupInfoDialog` 的 `names` 同樣來源。
- [ ] **Step 5：進場動畫**：新增 `const animationBaseline = useRef<string[] | null>(null)` 與 `const shownIntents = useRef<Set<string>>(new Set())`；在 `ChatView.tsx:60-64` 的 layout effect 中，`if (!authorized) { animationBaseline.current = null; return; }` 放在最前；`restoreAnchor()` 之後：

```ts
const replaced=new Set(messages.filter(message=>message.client_message_id&&shownIntents.current.has(message.client_message_id)).map(message=>message.id));
if(!matchMedia('(prefers-reduced-motion: reduce)').matches)for(const id of entryAnimationIds(animationBaseline.current,ids,replaced)){scroller.current?.querySelector<HTMLElement>(`[data-message-id="${CSS.escape(id)}"]`)?.animate([{opacity:0,transform:'translateY(8px)'},{opacity:1,transform:'none'}],{duration:150,easing:'cubic-bezier(.2,.8,.2,1)',fill:'none'});}
animationBaseline.current=ids;shownIntents.current=new Set(pending.map(intent=>intent.clientMessageId));
```

- [ ] **Step 6：`Chat.css`**：泡泡 token、`group-start`／`group-end` 圓角與間距（不加 transition）、`.date-separator`、`.date-pill`（absolute 於 `.chat-room` 內、位於頂部列下方）、`.jump-latest-fab`、輸入列；加入 `.jump-latest-fab[hidden], .date-pill[hidden] { display: none !important; }`；聊天室與祖先不加 opacity／scale／translateY／translateX 過場。
- [ ] **Step 7：Run 三命令；推送後 CI 8／8；本機截圖與 Animations 面板確認。**
- [ ] **Step 8：Commit** `feat: Telegram-style chat room with read-safe motion`

---

## Phase 4：Group Creation

**目標**：建群組改為外殼層級兩步對話框；加入 ✎ 浮動按鈕、圖示欄與選單項目；移除舊的清單內建群組表單。

**依賴**：Phase 1、Phase 2（`UserDirectory`、清單）。

**潛在失效模式**：超過 49 人或重複 ID；結果不明時另建一群；未完成意圖重新整理後遺失；對話框關閉未卸載；多個「建立群組」按鈕使定位衝突。

**完成條件**：Task 4.1 測試通過；三命令 exit 0；CI 8／8，`group_creation_preserves_original_title_members_and_intent`、新增的 `group_creation_resolved_member_name_before_adding` 與 `group_leave_response_after_navigation_does_not_redirect` 通過，且後者有一次「修正前失敗」的 CI run 證據；本機在建立請求送出後立刻重新整理，對話框自動開啟並鎖定原名稱與成員、之後 token 刷新不再自動開啟（截圖）。

**建議提交**：Task 4.1、4.2 各一個提交；Task 4.3 兩個提交（先檢查、後修正）。

### Task 4.1：成員選取規則

**Files:** Create `frontend/app/src/group-selection.ts`、`group-selection.test.ts`

**Interfaces:** Produces `GROUP_OTHER_MEMBER_LIMIT = 49`；`type AddResult = 'added' | 'duplicate' | 'self' | 'full'`；`addMember(selected: readonly string[], id: string, self: string): { selected: string[]; result: AddResult }`；`removeMember(selected: readonly string[], id: string): string[]`；`groupPayload(title: string, selected: readonly string[]): GroupCreatePayload`。

- [ ] **Step 1：寫失敗測試**

```ts
import { expect, test } from 'bun:test';
import { GROUP_OTHER_MEMBER_LIMIT, addMember, groupPayload, removeMember } from './group-selection';

test('adding ignores self and duplicates and keeps insertion order', () => {
  let selected: string[] = [];
  expect(addMember(selected, 'me', 'me').result).toBe('self');
  ({ selected } = addMember(selected, 'a', 'me'));
  expect(addMember(selected, 'a', 'me').result).toBe('duplicate');
  ({ selected } = addMember(selected, 'b', 'me'));
  expect(selected).toEqual(['a', 'b']);
});
test('selection stops at forty-nine other members and frees a slot on removal', () => {
  let selected: string[] = [];
  for (let i = 0; i < GROUP_OTHER_MEMBER_LIMIT; i++) ({ selected } = addMember(selected, `u${i}`, 'me'));
  expect(addMember(selected, 'extra', 'me').result).toBe('full');
  selected = removeMember(selected, 'u0');
  expect(addMember(selected, 'extra', 'me').result).toBe('added');
});
test('adding returns a new array so React state updates', () => {
  const before = ['a'];
  const { selected } = addMember(before, 'b', 'me');
  expect(selected).not.toBe(before);
  expect(before).toEqual(['a']);
});
test('payload keeps the exact title and selected ids', () => {
  expect(groupPayload(' 讀書會 ', ['a', 'b'])).toEqual({ title: ' 讀書會 ', member_ids: ['a', 'b'] });
});
```

- [ ] **Step 2：Run** `~/.bun/bin/bun test src/group-selection.test.ts`。Expected：FAIL。
- [ ] **Step 3：實作**

```ts
import type { GroupCreatePayload } from './GroupsPage';
export const GROUP_OTHER_MEMBER_LIMIT = 49;
export type AddResult = 'added' | 'duplicate' | 'self' | 'full';
export function addMember(selected: readonly string[], id: string, self: string): { selected: string[]; result: AddResult } {
  if (id === self) return { selected: [...selected], result: 'self' };
  if (selected.includes(id)) return { selected: [...selected], result: 'duplicate' };
  if (selected.length >= GROUP_OTHER_MEMBER_LIMIT) return { selected: [...selected], result: 'full' };
  return { selected: [...selected, id], result: 'added' };
}
export function removeMember(selected: readonly string[], id: string): string[] { return selected.filter(item => item !== id); }
export function groupPayload(title: string, selected: readonly string[]): GroupCreatePayload { return { title, member_ids: [...selected] }; }
```

- [ ] **Step 4：Run** 同 Step 2。Expected：4 pass。
- [ ] **Step 5：Commit** `feat: add group member selection rules`

### Task 4.2：建群組對話框與入口

**Files:** Modify `GroupsPage.tsx`（`CreateGroup`）、`App.tsx`、`ChatList.tsx`、`Shell.css`、`tests/browser/browser_acceptance.py:704-711`

- [ ] **Step 1**：`CreateGroup` 改為受控 `open`／`onClose`／`triggerRef` 的原生 `<dialog aria-label="建立群組">`（`showModal`、`hine-overlay-change`、cleanup 中 `close()` 後還原焦點，觸發元素不存在時聚焦路由標題）；掛在 `App` 外殼；掛載時 `store.read()` 有未完成意圖且模組層級 `autoOpened` 集合沒有此 owner 時，自動開啟並把 owner 加入集合（每次頁面載入、每個 owner 只自動開啟一次；token 刷新造成的外殼重建不再自動開啟）；有意圖時鎖定輸入（現行 `GroupsPage.tsx:32-37,62-64`）。
- [ ] **Step 2**：步驟 1：`usePagedList(session, 'contacts', …)` 列出聯絡人（勾選框 label 為名稱）、「載入下一頁」；已選標籤區 `.selected-members`；「已選 N／49」；達上限停用未勾選項。「以公開 ID 加入」（label 文字即此）＋「加入」按鈕：**送出前**取得 `const directory = directoryFor(session)`，`session.request<UserSummary>('/users/{id}')` 成功且 owner 未變時才 `addMember` 並 `directory.put(id, data)`（`put` 內再做 owner 檢查），失敗顯示既有 `describeError`。「下一步」進入步驟 2：label「群組名稱」、按鈕「建立群組」。送出沿用現行 `submit`：`store.begin(groupPayload(title, selected))`、`idempotencyKey`、`store.confirm`、owner 檢查、錯誤處理。
- [ ] **Step 3：入口**：寬版圖示欄加「建立群組」；窄版選單 items 加「建立群組」；清單右下 ✎（`aria-label="建立群組"`，`.chat-list` 內）；移除清單內舊表單。
- [ ] **Step 4：更新驗收**（`:704-711`；SQL 斷言 `:713-719` 不變，並新增一個 check）：

```python
await page_a.locator(".chat-list").get_by_role("button", name="建立群組", exact=True).click()
dialog = page_a.get_by_role("dialog", name="建立群組")
lookup_pattern = f"**/api/v1/users/{ids[1]}"
lookup_gate = asyncio.Event()
async def hold_lookup(route):
    await lookup_gate.wait()
    await route.continue_()
await page_a.route(lookup_pattern, hold_lookup)
try:
    await dialog.get_by_label("以公開 ID 加入").fill(ids[1])
    async with page_a.expect_request(lookup_pattern):
        await dialog.get_by_role("button", name="加入", exact=True).click()
    absent_before_lookup = await dialog.locator(".selected-members li").count() == 0
    async with page_a.expect_response(lookup_pattern):
        lookup_gate.set()
finally:
    lookup_gate.set()
    await page_a.unroute(lookup_pattern, hold_lookup)
chosen = dialog.locator(".selected-members").get_by_text(names[1], exact=True)
await chosen.wait_for(state="visible")
check(test_record, "group_creation_resolved_member_name_before_adding", absent_before_lookup and await chosen.count() == 1)
await dialog.get_by_text("已選 1／49", exact=True).wait_for(state="visible")
await dialog.get_by_role("button", name="下一步", exact=True).click()
await dialog.get_by_label("群組名稱").fill(group_title)
await dialog.get_by_role("button", name="建立群組", exact=True).click()
```

- [ ] **Step 5：Run 三命令；CI 8／8；本機重新整理還原驗證並截圖。**
- [ ] **Step 6：Commit** `feat: create groups by picking contacts`

### Task 4.3：群組管理頁卸載後不再導覽（spec R12）

**Files:** Modify `tests/browser/browser_acceptance.py`（`:779` 群組移除完成之後、`:780` 建立 page_c 之前）、`GroupsPage.tsx:94-113`。**不修改** `App.tsx:72`（App 的路由 key 已含 `path`，`key` 無作用）。

- [ ] **Step 1：先寫回歸檢查**（應用內導覽沿用 `router.ts:18-19` 的 `popstate`；最後一位管理員不能退出，所以先把 Bob 設為管理員）：

```python
async def spa_go(page, path):
    await page.evaluate("p => { history.pushState(null, '', p); dispatchEvent(new PopStateEvent('popstate')); }", path)

temp_title = "Leave race " + secrets.token_hex(3)
await spa_go(page_a, "/chats")
await page_a.locator(".chat-list").get_by_role("button", name="建立群組", exact=True).click()
temp_dialog = page_a.get_by_role("dialog", name="建立群組")
await temp_dialog.get_by_label("以公開 ID 加入").fill(ids[1])
await temp_dialog.get_by_role("button", name="加入", exact=True).click()
await temp_dialog.locator(".selected-members").get_by_text(names[1], exact=True).wait_for(state="visible")
await temp_dialog.get_by_role("button", name="下一步", exact=True).click()
await temp_dialog.get_by_label("群組名稱").fill(temp_title)
await temp_dialog.get_by_role("button", name="建立群組", exact=True).click()
await page_a.wait_for_url(re.compile(r"/chats/[^/]+$"))
temp_group_id = unquote(page_a.url.rstrip("/").rsplit("/", 1)[-1])
await spa_go(page_a, f"/groups/{quote(temp_group_id, safe='')}/manage")
bob_row = page_a.locator(".member-list li", has_text=ids[1])
await bob_row.get_by_role("button", name="設為管理員", exact=True).click()
await bob_row.get_by_role("button", name="改為成員", exact=True).wait_for(state="visible")
is_leave = lambda r: (r.request if hasattr(r, "request") else r).method == "DELETE" and r.url.endswith(f"/members/{ids[0]}")
leave_gate = asyncio.Event()
async def hold_leave(route):
    if route.request.method == "DELETE":
        await leave_gate.wait()
    await route.continue_()
leave_pattern = f"**/members/{ids[0]}"
await page_a.route(leave_pattern, hold_leave)
try:
    async with page_a.expect_request(is_leave):
        await page_a.get_by_role("button", name="退出群組", exact=True).click()
    await spa_go(page_a, "/contacts")
    await page_a.wait_for_url(re.compile(r"/contacts$"))
    async with page_a.expect_response(is_leave) as leave_info:
        leave_gate.set()
    leave_status = (await leave_info.value).status
    await page_a.wait_for_timeout(1000)
    stayed = page_a.url.endswith("/contacts")
finally:
    leave_gate.set()
    await page_a.unroute(leave_pattern, hold_leave)
async with components.sql() as conn:
    still_member = await conn.fetchval("SELECT count(*) FROM memberships WHERE conversation_id=$1 AND user_id=$2 AND active", temp_group_id, ids[0])
check(test_record, "group_leave_response_after_navigation_does_not_redirect", leave_status == 204 and still_member == 0 and stayed)
```

`quote`／`unquote`、`re`、`secrets`、`asyncio` 依腳本既有 import 補齊（只用標準函式庫）；退出群組若有確認步驟，依實際 UI 補上點擊。結束時 page_a 位於 `/contacts`；後續 `:780` 起的步驟不依賴 page_a 的路由（`:793` 登出只用導覽）。

- [ ] **Step 2：只提交檢查並推送**，確認 CI 中此 check 為 false（`GroupsPage.tsx:107` 會把使用者導回 `/chats`），記錄失敗 run URL。若意外通過，代表檢查無效：停止並重新設計，不進入 Step 3。
- [ ] **Step 3：修正**：`GroupsPage` 加 `const alive = useRef(false); useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);`；`mutate` 中退出成功後照常 `await chat.withdraw(conversationId)`，再 `if (alive.current) onNavigate('/chats')`；`:112` 的撤權導覽同樣先檢查 `alive.current`。
- [ ] **Step 4**：管理頁套用新樣式，保留 `.member-list li` 內的成員使用者 ID 文字（`:759` 以 `has_text=ids[1]` 篩選）、「移除」「設為管理員」「改為成員」「退出群組」「前往群組管理」名稱、`data-route-heading`。
- [ ] **Step 5：Run 三命令；推送後 CI 8／8，且此 check 為 true。**
- [ ] **Step 6：Commit**（Step 1–2：`test: catch navigation after leaving an unmounted group page`；Step 3–4：`fix: stop group management from navigating after unmount`）

---

## Phase 5：CI / Browser Acceptance

**目標**：補上 CI 目前未把關的行為、加入效能基準、同步文件。

**依賴**：Phase 1–4。

**潛在失效模式**：新檢查假通過；headed 雜訊造成不穩；視窗尺寸改變影響後續既有步驟；`timings_ms` 被覆蓋。

**完成條件**：CI 8／8，所有新增 check 通過且 artifact JSON 含 `perf`；正向對照證明動畫量測有效；文件已更新。

**建議提交**：Task 5.1、5.2、5.3 各一個提交。

### Task 5.1：新增行為檢查

插入位置：`browser_acceptance.py` Task 4.3 檢查之後、`:780`（建立 page_c）之前。此時 page_c（與 page_a 同帳號）尚未存在，不會代替 page_a 送出已讀。開始時記錄目前 viewport（390×844），結束時還原。page_a 先以 `spa_go` 進入 `/chats/{direct_id}`（已有 100 則以上訊息，可捲動）；page_b（Bob）也進入同一聊天室並負責送出訊息。

| Check | 操作 | 條件（必須能抓到失敗） |
|---|---|---|
| `message_dom_invariants` | page_a 位於一對一聊天室 | 所有 `[data-message-id]` 值符合 UUID 正規表示式且不重複；`.message-scroller [data-read-occlusion]` 數量為 0 |
| `entry_animation_positive_control` | page_a 位於最新位置；送出前 `page.evaluate` 安裝 MutationObserver：節點插入後下一個 rAF 記錄其中每個 `[data-message-id]` 的 ID 與 `getAnimations().length`；page_b 送 1 則已知文字，並由 page_a 的 IndexedDB 取得其 message ID | 記錄中**有該 ID**，且其動畫數 ≥1 |
| `reduced_motion_no_entry_animation` | `page_a.emulate_media(reduced_motion="reduce")` 後重複上一列 | 記錄中**有該 ID**，且其動畫數為 0；之後 `emulate_media(reduced_motion="no-preference")` |
| `closed_menu_does_not_block_reads` | 390 寬度下 page_a 開啟再以 Esc 關閉 ☰；`page_a.bring_to_front()`；page_b 送 1 則 | 關閉後 `[aria-modal="true"],dialog[open]` 皆 `getClientRects().length===0`；SQL 該訊息對 Alice 的回條在 15 秒內變為 `read` |
| `menu_escape_returns_focus` | 開啟 ☰ 後按 Esc | `document.activeElement` 的可存取名稱為「開啟選單」 |
| `group_info_escape_returns_focus` | page_a 進入原群組聊天室，開啟群組資訊後按 Esc | `document.activeElement` 的可存取名稱為「群組資訊」 |
| `ime_composition_enter_does_not_send` | page_a 回一對一聊天室；以 CDP `Input.imeSetComposition` 輸入組字文字後按 Enter，等待 1000ms | IndexedDB intents 數（沿用 `indexed_db_state`）、`.pending-message` 數、`[data-message-id]` 數皆不變；`#chat-draft` 值仍含組字文字；之後 `Input.insertText` 完成組字並 Ctrl+Enter，intents 恰好增加 1 |
| `layout_767_single_column` / `layout_768_two_columns` | 分別設 767×900、768×900，位於 `/chats/{direct_id}` | 以 `getBoundingClientRect` 與 viewport 交集判定：767 時 `.chat-list` 與 `.chat-room` 恰一個交集面積 >0，另一個 `getClientRects().length===0`；768 時兩者交集面積皆 >0；兩者 `document.scrollingElement.scrollWidth <= innerWidth` |
| `new_message_count_while_scrolled_up` | 390 寬度，一對一聊天室往上捲到頂；page_b 送 2 則 | 「跳至最新」按鈕可見且顯示 2；點擊後 `scrollHeight-clientHeight-scrollTop<=48` 且按鈕隱藏 |
| `anchor_restored_after_room_switch` | 一對一聊天室往上捲並等 IndexedDB 錨點寫入；切到群組再切回 | 300ms 後捲動區頂端第一個 `[data-message-id]` 等於儲存的 messageId，offset 差 ≤1px |

- [ ] **Step 1**：依上表以腳本既有的 `check`、`wait_visible`、`components.sql()`、`indexed_db_state` 實作。
- [ ] **Step 2**：推送；CI 8／8。
- [ ] **Step 3：Commit** `test: guard IME, breakpoints, focus and read-safe motion in CI`

### Task 5.2：效能基準（只記錄）

- [ ] **Step 1**：`browser_acceptance.py:674` 由 `test_record["timings_ms"] = {...}` 改為 `test_record.setdefault("timings_ms", {}).update({...})`。
- [ ] **Step 2**：於群組建立（`:719`）之後、群組資訊（`:735`）之前（此時為寬版、page_a 有一對一與群組兩個聊天室）加入：

```python
async def perf_sample(page, label, action, repeats=3):
    cdp = await page.context.new_cdp_session(page)
    try:
        await cdp.send("Performance.enable")
        samples = []
        for _ in range(repeats):
            before = {m["name"]: m["value"] for m in (await cdp.send("Performance.getMetrics"))["metrics"]}
            started = time.monotonic()
            await action()
            await page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
            after = {m["name"]: m["value"] for m in (await cdp.send("Performance.getMetrics"))["metrics"]}
            samples.append({"elapsed_ms": (time.monotonic() - started) * 1000, **{k: after[k] - before[k] for k in ("ScriptDuration", "TaskDuration", "LayoutCount", "RecalcStyleCount")}})
        median = lambda key: sorted(sample[key] for sample in samples)[len(samples) // 2]
        test_record.setdefault("perf", {})[label] = {key: round(median(key), 4) for key in samples[0]}
    finally:
        await cdp.detach()
```

情境：在一對一與群組之間切換 10 次（點擊清單列後等待目標 `[data-message-id]` 可見）；composer `keyboard.type` 50 字；另記錄 `document.getElementsByTagName('*').length` 與 `[data-message-id]` 數量。不設門檻、不呼叫 `check`。

- [ ] **Step 3**：推送；CI 8／8；下載 artifact 確認 `perf` 欄位。需要基準比較時，對 `main` 在同一 workflow 跑一次並保存。
- [ ] **Step 4：Commit** `test: record UI performance baselines in browser acceptance`

### Task 5.3：文件與手動驗證腳本

- [ ] **Step 1**：`docs/CHANGELOG.md` 新增條目：改版內容、保留行為、設計限制、CI run 連結與本機截圖說明。
- [ ] **Step 2**：`docs/ui/web-rwd.md`：記錄寬版圖示欄＋窄版 ☰（屬既有「導覽與內容並列」的實作細節，不改驗收條件）、reduced-motion 與 768 寫法。
- [ ] **Step 3**：確認 `review-shell-native.ts` 沒有殘留舊 UI 選擇器（Phase 2 Step 4a 已改；Phase 4 移除清單內舊建群組表單後再檢查一次）；typecheck 通過；回報中明示此腳本未實際執行。
- [ ] **Step 4**：本機 Docker 實測（390／767／768／1280、鍵盤操作、一對一、三人群組、建群組、附件錯誤提示）；完成後刪除臨時帳號、停止容器。
- [ ] **Step 5：Commit** `docs: record UI refresh behaviour and verification`

---

## Failure Analysis

| 情境 | 失效 | 使用者看到 | 資料／狀態風險 | 預防 | 恢復 | 驗證 |
|---|---|---|---|---|---|---|
| 非同步回覆亂序 | 舊名稱覆蓋新名稱；舊群組管理頁退出請求回來後把已離開的使用者導回清單 | 錯誤名稱；突然跳頁 | 無（`chat.withdraw` 照常） | 每位使用者版本號＋epoch＋owner；過期進行中請求不沿用；`GroupsPage` 卸載後不導覽 | 下一次 `ensure` | Task 2.2「newer put」「replaced, not reused」測試；Task 4.3 CI 回歸檢查（含修正前失敗證據） |
| 快取過期 | 名稱或頭像過舊 | 最長 5 分鐘舊值 | 無 | TTL、開啟聊天室重新驗證、範圍化的頭像過期 | TTL 到期重抓 | Task 2.2 TTL 測試 |
| Session 切換 | 舊帳號資料顯示在新帳號 | 他人名稱或頭像 | 隱私外洩 | `directoryFor` owner 重設、abort、`accept()`；session epoch 第二道防線 | 新帳號重新取得 | Task 2.2「switching account」測試；CI 換帳號流程 |
| Token 刷新 | 清單重排、快取被清 | 列順序跳動 | 無 | 鍵表與目錄同 owner 保留 | — | Task 2.3 背景同步前後截圖 |
| 跨對話排序依據錯誤 | 以 `order_key` 跨對話比較 | 契約變動後順序錯亂 | 無（呈現） | 只用 `created_at`（R10） | — | Task 2.1 測試；程式碼審查 |
| 收到新訊息 | 未上移或其他列跟著跳動 | 列位置不合預期 | 無 | 只移動鍵前進的對話；同鍵依 A11 | — | Task 2.1「moves only its conversation」測試；Phase 2 截圖 |
| 權限撤銷 | 撤權對話重新出現 | 不應看見的標題 | 隱私 | `snapshot.denied` 與 owner 範圍 `DeniedMemory` 至下次 A11 完成；預覽不快取內文 | A11 重新載入 | Task 2.1 測試；CI 群組移除流程 |
| IndexedDB 不可用 | 聊天停止 | 既有提示 | 無新增 | 不改持久化 | 既有 | 既有測試 |
| 網路中斷 | 群組預覽清空 | 預覽「—」，位置不變 | 無 | 鍵表保留 | 同步後恢復 | 本機離線驗證 |
| WebSocket 重連 | 補回訊息大量動畫 | 閃爍 | 無 | `!authorized` 時基準歸 null；一次 >3 則不播 | — | Task 3.1 測試；Phase 3 Animations 截圖 |
| 訊息結果不明 | 圖示誤顯示成功 | ✓ 而非 ⚠ | 使用者誤判 | `intentStatus('unknown')` | 既有原意圖重試 | Task 3.1 測試；CI 既有 C1 重播檢查 |
| 群組建立結果不明 | 重複建立 | 兩個群組 | 重複資料 | 沿用意圖保存與冪等鍵；自動開啟 | 原意圖重試／核對 | CI 既有群組建立檢查；Phase 4 重新整理還原截圖 |
| 動畫與已讀競爭 | 透明或位移中被計為已讀 | 錯誤已讀 | 已讀語意 | 只動尾端少量新訊息；`bubbleMeasurable`；聊天室無 opacity 過場；reduced-motion 不播 | — | Task 3.2 測試；CI 動畫正向對照與 reduced-motion |
| 日期分隔遮擋 | 提早或漏掉已讀 | 已讀不準 | 已讀語意 | 列表分隔無遮擋屬性；浮動膠囊在捲動區外 | — | Task 3.3 測試；CI `message_dom_invariants` |
| 選單關閉未卸載 | 已讀永久暫停 | 對方看不到已讀 | 回條不送 | 關閉即卸載 | 重新整理 | CI `closed_menu_does_not_block_reads`（Bob 送、Alice 讀，無同帳號第二視窗） |
| 頁面切換的未完成請求 | 卸載後寫入、請求風暴 | 錯誤資料或延遲 | 無 | AbortController、共享 promise、並行 4、`refreshConversation` 每週期一次 | — | Task 2.2 測試；Phase 2 DevTools 截圖 |
| 名稱查詢持續失敗 | 每次按鍵都重送 `/users/` | 延遲、伺服器負載 | 無 | 失敗 30 秒退避；`ensure` 只在 effect 中依 ID 集合呼叫 | 30 秒後重試 | Task 2.2「back off」測試 |
| 帳號切換時的延遲寫入 | 甲帳號看到的頭像 ID 寫入乙帳號快取 | 乙看到不該看到的頭像 | 隱私 | 請求前取得快取實例；`put` 檢查 `accept()`；owner 切換時 `reset` | 新 owner 重新取得 | Task 2.2「puts are discarded」「switching account」測試 |
| 頭像下載風暴或洩漏 | 每次切換聊天室重抓全部頭像；物件 URL 不釋放；跨帳號顯示 | 閃爍、記憶體成長 | 隱私（跨帳號） | 頭像快取共用下載、參照數、閒置 LRU 48、並行 4、owner 切換撤銷；清單在切換對話時不重建（R13） | — | Task 2.2b 測試；Task 2.4 Network 截圖 |
| 未完成建群組意圖反覆彈出 | token 刷新重建外殼後再次自動開啟模態 | 對話框反覆出現、已讀暫停 | 回條延後 | 每次頁面載入每個 owner 只自動開啟一次 | 使用者關閉 | Phase 4 本機 token 刷新截圖 |
| 窄版面板滑動 | 滑入中的泡泡被當成可見 | 提早已讀 | 已讀語意 | 窄版不做滑動過場（R14），沿用 `display` 切換 | — | 程式碼審查；CI `layout_767_single_column` |

## Test Matrix

| 類別 | 項目 | 預期 | Phase |
|---|---|---|---|
| Unit | 清單時間 | 00:05、09:05、昨天、週一、10/9、2025/12/31 | 2 |
| Unit | 預覽 | 你：、名稱：、📷／📄、空白折疊、「—」 | 2 |
| Unit | 活動時間鍵、撤權記憶、排序 | 只升不降；無效時間忽略；新訊息只移動該對話；owner 隔離；清除 | 2 |
| Unit | 使用者摘要快取 | 去重、並行 ≤4、reset 中止與結算、失敗不拋與 30 秒退避、版本號亂序、過期請求不沿用、`put` owner 檢查、群組成員版本追蹤、TTL、owner 切換、未綁定 subscribe | 2 |
| Unit | 頭像快取 | 共用下載、釋放後重用、閒置 LRU 撤銷、失敗不快取、並行上限、reset 撤銷並結算 | 2 |
| Unit | 時間軸 | 分組、跨日、key 穩定 | 3 |
| Unit | 狀態對應 | 文字與現行相同 | 3 |
| Unit | 進場判定 | 基準 null、往前加入、pending→persisted、>3 則不播 | 3 |
| Unit | `bubbleMeasurable` | running／paused 不計入 | 3 |
| Unit（靜態渲染） | 訊息 DOM 不變式 | 單一 UUID、meta 狀態文字、分隔無遮擋 | 3 |
| Unit | 群組選取 | 排除自己、去重、49 上限、新陣列、payload | 4 |
| Integration（CI） | 註冊、登入、登出、換帳號、另一裝置存續 | 既有 check 通過 | 1–4 |
| Integration（CI） | 一對一傳訊、已讀回條、草稿重載、C1 重播 | 既有 check 通過 | 3 |
| Integration（CI） | 離線補回 100 則 | ≤5000ms | 3 |
| Integration（CI） | 群組建立、群組資訊、移除成員 | 既有 check＋名稱解析 | 4 |
| Integration（本機） | 附件錯誤提示 | 服務錯誤＋場景結尾 | 5 |
| Browser（CI Chrome／Edge） | 390／767／768／1280 | 既有 390 檢查；新增 767／768 幾何判定 | 1、5 |
| Browser | 焦點 | ☰、群組資訊 Esc 返回；路由標題 | 1、5 |
| Browser | Reduced Motion | 正向對照 ≥1、reduce 時 0 | 5 |
| Browser | 捲動與已讀 | 選單關閉後已讀；新訊息計數；錨點還原 | 5 |
| Browser | IME | 組字 Enter 不產生意圖 | 5 |
| Browser | 效能 | `perf` 寫入 artifact | 5 |
