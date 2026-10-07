# HINE GCP Environment

更新日期：2026-10-07

本文件記錄 HINE 目前已完成的 GCP 開發／整合環境與 PostgreSQL 建置進度。

---

## 1. Domain / DNS

目前網域與 DNS 已完成設定。

| 項目 | 狀態 |
|---|---|
| Domain Provider | `freedomain.one` |
| Domain | ✅ OK |
| DNS | ✅ OK |

目前 HINE 對外服務使用：

- `hine.run.place`
- `www.hine.run.place`

---

## 2. Google Cloud Platform

HINE 目前部署於 Google Cloud Platform。

| 項目 | 狀態 |
|---|---|
| GCP Project | ✅ 已建立 |
| GCP Free Trial / Credit | ✅ US$300 |
| Compute Engine | ✅ 使用中 |
| VPC Private Network | ✅ 使用中 |

目前主要由兩台 VM 組成：

- `hine-web`
- `hine-sql`

---

## 3. hine-web

`hine-web` 為目前 HINE 的 Web / Service 主機。

| 項目 | 狀態 |
|---|---|
| Compute Engine VM | ✅ OK |
| Nginx | ✅ OK |
| Domain 綁定 | ✅ OK |
| SSL / TLS | ✅ OK |
| CA Certificate | ✅ OK |
| HTTPS | ✅ OK |
| HINE Website Service | ✅ OK |

目前網站已可透過 HTTPS 提供服務。

架構：

```text
Internet
   |
   | HTTPS
   v
hine.run.place
   |
   v
hine-web
   |
   └─ Nginx
       └─ HINE Website
```

---

## 4. SSL / Certificate

目前 HTTPS 憑證已完成設定。

| 項目 | 狀態 |
|---|---|
| CA Certificate | ✅ OK |
| SSL / TLS | ✅ OK |
| HTTPS Website | ✅ OK |

所有公開 Web 流量使用 HTTPS。

---

## 5. hine-sql

`hine-sql` 為目前 HINE 的 Database Server。

| 項目 | 狀態 |
|---|---|
| Compute Engine VM | ✅ OK |
| PostgreSQL 16 | ✅ OK |
| Database 建立 | ✅ OK |
| Web → SQL Private Network | ✅ OK |
| PostgreSQL Connection Test | ✅ PASS |

目前 PostgreSQL 已完成第一階段 Schema 建置與整合測試。

---

## 6. PostgreSQL Schema Progress

目前 PostgreSQL 已建立 10 張核心資料表。

| Table | 用途 | 狀態 |
|---|---|---|
| `users` | 使用者帳號 | ✅ 完成 |
| `friendships` | 好友關係 | ✅ 完成 |
| `conversations` | 一對一 / 群組聊天室 | ✅ 完成 |
| `conversation_members` | 聊天室成員與角色 | ✅ 完成 |
| `messages` | 訊息資料 | ✅ 完成 |
| `message_receipts` | Delivered / Read 回條 | ✅ 完成 |
| `devices` | DeviceID / 裝置資料 | ✅ 完成 |
| `sessions` | Login Session | ✅ 完成 |
| `session_invalidations` | Session 失效紀錄 | ✅ 完成 |
| `user_events` | Per-user Event Feed | ✅ 完成 |

目前共 10 Tables。

---

## 7. PostgreSQL Data Flow

目前主要資料關聯如下：

```text
users
 ├─ friendships
 ├─ devices
 │   └─ sessions
 │       └─ session_invalidations
 │
 └─ conversation_members
      └─ conversations
           └─ messages
                ├─ message_receipts
                └─ user_events
```

---

## 8. Message Structure

目前 `messages` 已包含 HINE 訊息核心欄位：

- `client_message_id`
- `message_id`
- `event_id`
- `order_key`
- `conversation_id`
- `sender_id`
- `message_type`
- `content`
- `created_at`

概念對應：

```text
client_message_id = C1
message_id        = M1
event_id          = Event UUID
order_key         = Conversation Ordering Key
```

`order_key` 使用固定 20 位數字字串格式，例如：

```text
00000000000000000001
```

---

## 9. Session / Device

目前已建立：

- `devices`
- `sessions`
- `session_invalidations`

可支援：

- DeviceID
- Login Session
- Session Generation
- Session Expiry
- Logout
- Refresh
- Replace
- Session Invalidation

流程概念：

```text
User
 |
 v
Device
 |
 v
Session
 |
 v
SessionInvalidation
```

---

## 10. Message Receipt

目前已建立：

`message_receipts`

支援：

- `delivered`
- `read`

每個 Message / User 可保存獨立 Receipt 狀態。

概念：

```text
Message M1
   |
   └─ User
       ├─ delivered
       └─ read
```

---

## 11. Per-user Event Feed

目前已建立：

`user_events`

主要欄位包含：

- `position`
- `user_id`
- `event_id`
- `event_type`
- `conversation_id`
- `message_id`
- `payload`
- `created_at`

可作為後續 W15 / W16 同步與補送機制的 PostgreSQL 基礎。

概念：

```text
Redis Pub/Sub
   |
   | 即時通知
   v
Client

如果即時通知遺失：

PostgreSQL user_events
   |
   | W15 / W16
   v
Client 補送
```

Redis 不作為訊息權威儲存。

---

## 12. Database Integration Test

2026-10-07 已完成 PostgreSQL 基礎整合測試。

測試項目：

- User
- Friendship
- Conversation
- Conversation Member
- Message Persistence
- Device
- Session
- Session Invalidation
- Delivered Receipt
- Read Receipt
- Per-user Event Feed
- Event Feed Query

測試結果：

```text
User / Friendship             PASS
Conversation / Membership     PASS
Message Persistence           PASS
Device                        PASS
Session                       PASS
Session Invalidation          PASS
Delivered Receipt             PASS
Read Receipt                  PASS
Per-user Event Feed           PASS
Event Feed Query              PASS
```

目前 PostgreSQL 已可進入 Backend API 串接階段。

---

## 13. Current Architecture

目前實際開發環境：

```text
Internet
   |
   | HTTPS
   v
Domain / DNS
freedomain.one
   |
   v
hine.run.place
   |
   v
hine-web
GCP Compute Engine
   |
   | GCP VPC Private Network
   v
hine-sql
GCP Compute Engine
   |
   v
PostgreSQL 16
```

PostgreSQL 不直接對 Internet 開放。

---

## 14. Current Progress

目前基礎設施完成狀態：

```text
Domain                  ✅ OK
DNS                     ✅ OK

GCP Project             ✅ OK
GCP US$300 Credit       ✅ OK

hine-web VM             ✅ OK
SSL / CA                ✅ OK
HTTPS                   ✅ OK
Website Service         ✅ OK

hine-sql VM             ✅ OK
PostgreSQL              ✅ OK
Database Schema         ✅ OK
Database Integration    ✅ PASS
```

---

## 15. Security

目前基礎安全原則：

- PostgreSQL 不直接對 Internet 開放
- Database Password 不提交 Git
- JWT Secret 不提交 Git
- Internal Service Token 不提交 Git
- `.env` 不提交 Git
- Web 公開入口使用 HTTPS
- PostgreSQL 為主要權威資料來源
- Redis 僅用於即時通知與 Presence

---

## 16. 與 HINE-IC-0.4 目標架構差異

HINE-IC-0.4 的課程版目標架構為：

```text
Single GCP Compute Engine VM
└─ Docker Compose
   ├─ Web
   ├─ api
   ├─ realtime
   ├─ PostgreSQL
   └─ Redis
```

目前實際開發環境則暫時採用：

```text
hine-web
├─ Nginx
├─ Website
├─ 未來 api
└─ 未來 realtime

hine-sql
└─ PostgreSQL
```

也就是目前 PostgreSQL 暫時獨立至第二台 VM。

此設定屬目前開發／整合環境，不代表已修改 HINE-IC-0.4 最終架構決議。

---

## 17. Next Step

下一階段：

```text
PostgreSQL
    ↓
Backend B / API
    ↓
Account / Session
Conversation / Message
    ↓
Backend A / Realtime
    ↓
Redis / WebSocket
    ↓
Frontend Integration
```

後續主要工作：

- Backend API
- Redis
- WebSocket
- GCS Attachment
- Docker Compose
- CI/CD
- Monitoring
