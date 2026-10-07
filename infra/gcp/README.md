# HINE GCP Environment

更新日期：2026-10-07

## 目前環境

HINE 目前部署於 Google Cloud Platform。

- GCP Project：`HINEproject`
- Domain：`hine.run.place`
- Web Server：GCP Compute Engine
- Database Server：GCP Compute Engine
- Database：PostgreSQL 16
- Web Server：Nginx
- TLS：Let's Encrypt

## 架構

目前開發／整合環境採 Web 與 Database 分離：

```text
Internet
   |
   | HTTPS
   v
hine.run.place
   |
   v
Web Server
   |
   | GCP VPC Private Network
   v
PostgreSQL Server
