# 基礎設施

HINE 的部署與維運設定。

## 目前開發環境

目前 HINE 開發／整合環境部署於 Google Cloud Platform。

- Web Server：GCP Compute Engine
- Database Server：GCP Compute Engine
- Database：PostgreSQL 16
- Web Server：Nginx
- TLS：Let's Encrypt
- Domain：`hine.run.place`

目前開發環境暫時採 Web 與 PostgreSQL 分離部署，詳細資訊請參考：

- [`infra/gcp/README.md`](./gcp/README.md)

## HINE-IC-0.4 目標架構

課程版目標架構仍採：

```text
Single GCP Compute Engine VM
└─ Docker Compose
   ├─ Web
   ├─ api
   ├─ realtime
   ├─ PostgreSQL
   └─ Redis
