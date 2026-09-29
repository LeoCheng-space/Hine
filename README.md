# HINE

HINE is a cross-platform real-time communication system developed as a software engineering final project.

## Project Goals

- Real-time one-to-one and group messaging
- WebSocket-based bidirectional communication
- Message persistence and history
- Offline synchronization and duplicate prevention
- Image and file transfer
- Push notification integration
- CI/CD, monitoring, testing, and load testing

## Repository Structure

```text
Hine/
├── docs/
├── frontend/
├── backend/
├── infra/
├── tests/
└── .github/
```

### Main Areas

- `docs/` — architecture, API, WebSocket, database, deployment, and testing documentation
- `frontend/` — client application
- `backend/api/` — REST API and business data services
- `backend/realtime/` — WebSocket and real-time messaging services
- `backend/common/` — shared backend code
- `infra/` — Docker, GCP, monitoring, and operational scripts
- `tests/` — integration, E2E, and load tests
- `.github/` — GitHub Actions and collaboration templates

## Core Technology Direction

- WebSocket / WSS
- PostgreSQL
- Redis / Redis Pub/Sub
- Google Cloud Storage
- Firebase Cloud Messaging (FCM)
- Apple Push Notification service (APNs)
- Google Cloud Platform
- GitHub Actions
- Prometheus / Grafana
- JMeter or Artillery for load testing

> Frontend and backend frameworks are not locked yet. Any major technology decision should be documented before adoption.

## Collaboration

This repository uses a simple workflow designed for a six-person student team:

1. Pull the latest `main`
2. Create a `feature/<name>` or `fix/<name>` branch
3. Make one focused change
4. Commit and push
5. Open a Pull Request
6. Wait for review and CI
7. Merge only after checks pass

See [CONTRIBUTING.md](CONTRIBUTING.md) for the team workflow.

## Team Areas

- Frontend A — chat UI and real-time interaction
- Frontend B — authentication, contacts, profile, routing
- Backend A — WebSocket and real-time communication
- Backend B — REST API and database
- PM / DevOps — architecture, CI/CD, infrastructure, integration
- QA — integration, E2E, load, regression, and acceptance testing

## 團隊文件入口

請從 [HINE-IC-0.4 文件地圖](docs/README.md) 依角色閱讀。角色 PRD：[Frontend A](docs/prd/frontend-a.md) · [Frontend B](docs/prd/frontend-b.md) · [Backend A](docs/prd/backend-a.md) · [Backend B](docs/prd/backend-b.md) · [DevOps](docs/prd/devops.md) · [QA](docs/prd/qa.md)。
