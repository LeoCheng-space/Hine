# HINE-IC-0.4 — Web / RWD 規格

**狀態：**HINE-IC-0.4 獨立 Web/RWD 規格，待產品核准。已確認的平台配置與提議中的版面及互動規則分開標示。本文件是目前的 Web/RWD 規格來源；整合角色草稿為歷史文件。本文描述行為規格，不代表已實作或驗證。

[HINE 文件導覽圖](../README.md) · [介面契約](../contracts/interface-contract.md) · [角色 PRD](../README.md) · [決策紀錄](../decisions.md)

<a id="web-rwd"></a>
## Web / RWD 共用 UI 規格

### [CONFIRMED] Web delivery model and shared runtime

- HINE is one Web application used in desktop, tablet, and mobile browsers; this scope does not infer a native App or PWA.
- Frontend A and Frontend B are feature areas in the same Web project, not separate desktop/mobile clients. They share one SessionContext owner (FB), public REST API, WSS events/models, and one app-scoped WSS owner (FA).
- Responsive layout is presentation only: it does not create another login/session, socket, account SyncCursor, or business API. BA/BB do not expose duplicated desktop/mobile APIs or schemas.

### [PROPOSED] Responsive page and shared-component rules

This is one reviewable candidate layout, not an approved design. The width bands below are defined only here; all later references use the band names.

| Available Web viewport width | Layout band |
|---|---|
| `320 <= w < 768` CSS px | Narrow |
| `768 <= w < 1200` CSS px | Medium |
| `w >= 1200` CSS px | Wide |

Candidate UI-only routes are `/login`, `/register`, `/contacts`, `/chats`, `/chats/{conversation_id}`, `/profile`, and `/groups/{conversation_id}/manage`. They add no backend route or API. Login/register are public; protected routes wait for authorization and disclose no protected content before it. After login, return only to an authorized requested UI route. Browser back/forward restores the prior UI route/state; direct deep links and refresh enter the same guard/return flow. Image/file preview is an in-app surface opened from an authorized page, not a new route in this candidate.

| Page family | Narrow | Medium | Wide |
|---|---|---|---|
| Login and registration | One full-height, single-column form surface; form and submit action remain visible while scrolling. | Centered form surface with compact brand/header area and one-column fields. | Two columns: brand/information pane and readable-width form pane; form remains the primary action area. |
| Contacts/directory | One surface with header, search/filter, and full-height contact list; selecting a contact opens its detail as a drill-in with back action. | App navigation rail beside contacts content; selected contact details occupy a second content pane when selected. | App navigation, contacts list, and selected contact details are three persistent panes. |
| Chat list (`/chats`) | One surface with conversation list/search; selecting a conversation navigates to its thread. | App navigation rail plus chat list/content area; no empty third pane is required. | App navigation, conversation list, and thread are three panes once a conversation is selected. |
| Chat thread and composer | Thread is the sole content surface with explicit back-to-list action; composer stays above the virtual keyboard and within the visible viewport. | Chat list and thread are the two chat panes; composer is fixed to the thread's visible bottom. | Chat list and thread remain side by side; composer stays in the thread's visible bottom region. |
| Profile/avatar | One-column profile form with avatar preview and explicit save/cancel actions. | App navigation rail beside a centered, readable-width profile form with avatar preview. | App navigation and profile form; avatar preview/actions occupy a contextual side pane. |
| Group management | One section at a time in a single surface; section selection drills into details with back action and persistent save/cancel actions. | App navigation rail, group-management section list, and active section content in two work panes. | App navigation, section list, and active settings/member content are three panes. |
| Image/file preview | Full-screen viewer with top close/action bar; metadata/details open as a dismissible bottom sheet. | Viewer in the content area with collapsible details panel. | Centered constrained viewer with persistent metadata/details side panel. |

- **Shared forms and controls:** Every field has a programmatic and visible label. Validation messages identify the field and corrective action; invalid submission focuses the first invalid field. Submit, disabled, loading, success, empty, and error states are distinct. Empty/error surfaces offer an appropriate next action (for example, create/search, retry, or return). Toasts are non-blocking, announced accessibly, and never replace inline validation or critical recovery.
- **Touch, focus, and overlays [candidate]:** Minimum touch target is 44 CSS px, pending approval. On narrow, modal content uses an edge-to-edge sheet/dialog and navigation drawers use a full-height drawer; on medium/wide, dialogs are centered and navigation/context drawers are docked or side panels. A modal/drawer traps focus only while modal, Escape closes the topmost dismissible overlay, close returns focus to its trigger, and route changes place focus at the new page heading. Keep visible keyboard focus and logical tab order.
- **Content bounds:** Text uses `overflow-wrap:anywhere` where needed; media, metadata, and file names have `max-width:100%` and cannot widen the page or chat thread. Images remain inspectable within the viewer bounds; signed storage URLs are never displayed as UI text.
- **Navigation and return:** The listed route patterns are the candidate allowlist for Web-shell fallback. Keep browser history meaningful for route entry, chat selection, and preview open/close; do not intercept normal back/forward. This is UI routing only: no route change creates another login/session, WSS, SyncCursor, or business API.

### [PROPOSED] FA chat input, scroll, and read behavior

- Physical keyboard behavior is width-independent: Enter sends and Shift+Enter inserts a newline. With a soft keyboard, Enter inserts a newline and an explicit Send button submits. Set an IME-composing guard on `compositionstart`; suppress Enter-to-send while the guard or `event.isComposing` is true, and consume the Enter used to commit composition as composition input, not as send. Release the guard on `compositionend`; composition Enter MUST NOT submit.
- Track `visualViewport` height/offset so the composer remains visible above the virtual keyboard without losing draft, thread, or focus. Resizing/orientation preserves each conversation's draft and pending C1 state.
- Preserve the reading anchor as `message_id` plus its pixel offset through resize/orientation and when older history is prepended. Do not force scroll to bottom during history browsing. Auto-follow a new message only when the user is within a candidate 48 CSS px of the bottom; otherwise preserve position and show an unread count / Jump to latest action.
- W08 may be sent after durable local receipt independent of read state. Candidate W09 eligibility requires a visible browser, that conversation active, and the actual message intersecting at least 50% continuously for 500 ms. These visibility thresholds are proposed pending product/QA approval; thread open or W08 alone never establishes read.

### [PROPOSED] Web push scope

A23/A24 and `DeviceTokenStatus.platform` remain `ios|android`; they do not define browser subscription/provider payloads. Any Web Push provider, subscription lifecycle, permission, foreground suppression, and service-worker behavior require an explicit product/provider contract and approval. This PRD defines governance and acceptance only: do not ship fake browser-push behavior or infer native App/PWA support from the existing push-token API.
