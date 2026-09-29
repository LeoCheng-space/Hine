# HINE-IC-0.4 — DevOps 角色 PRD

**版本：** HINE-IC-0.4  
**狀態：** 待產品核准  
**來源：** [歷史來源：HINE-IC-0.4 role PRDs](../HINE-IC-0.4-role-prds.md); 唯一現行介面規格依據為 [共同介面契約](../contracts/interface-contract.md).  
**角色目的：** 負責主機路由、設定／secret 綁定、交付流程、監控及可重現的驗證環境。本 PRD 規定未來行為與驗收要求，不代表已實作或已完成測試。
**必讀／串接時查閱：** [共同介面契約](../contracts/interface-contract.md)、[驗收矩陣](../testing/acceptance-matrix.md)；各功能串接見下方 Trace／Handoff。 [返回文件導覽](../README.md)。

## 範圍

- **範圍內：** host routing, configuration/secret bindings, delivery pipeline, monitoring, and repeatable verification environment; the role-specific feature cards below.
- **範圍外：** 其他角色所負責的範圍；亦不得變更共用 API／event IDs、正式資料、ACK、Cursor 或同步語意。共用欄位型別、envelope、錯誤與限制均以共同介面契約為準。
- **共用 Web 行為：** 遵循 [Web / RWD specification](../ui/web-rwd.md#web-rwd); 不得另訂 breakpoint 或重複定義版面規則。

## 功能索引

- [DO-01 — 網域、TLS、入口與路由](#do-01)
- [DO-02 — 型別化環境設定與 secret 管理](#do-02)
- [DO-03 — GitHub Actions 交付](#do-03)
- [DO-04 — 健康檢查、監控、警示與日誌隱私](#do-04)
- [DO-05 — 可重現的效能驗證環境](#do-05)
- [DO-06 — Web 資產與受保護深層路由 fallback](#do-06)

## 角色目的與責任界線

提供指定的主機路由、設定／secret 綁定、交付流程、監控及可重現的驗證環境。GCP 運算架構尚未選定，不得假設使用 Kubernetes。

<a id="do-01"></a>
### DO-01 — Domain, TLS, ingress, and routes
**Trace:** [REQ-17 Infrastructure, health probes, and CI delivery](../testing/acceptance-matrix.md#req-17); [共同介面契約部署／健康設定](../contracts/interface-contract.md#deployment-config), public REST `/api/v1` and WSS `/ws/v1` routes.
- **Precondition:** Approved domain and target environment.
- **Normal flow:** Route public HTTPS REST `/api/v1` and WSS `/ws/v1` under `hine.run.place`; keep probes internal.
- **Failure flow:** TLS, routing, or required dependency failure prevents readiness/deployment acceptance.
- **Acceptance:** Single public contract; internal health is not exposed as user API. Web-shell refresh fallback is limited to approved UI paths and preserves API/WSS routes.
- **Handoff:** [BA-01](backend-a.md#ba-01)/[BB-01](backend-b.md#bb-01) ports/health behavior; [QA-05](qa.md#qa-05) smoke specification.

<a id="do-02"></a>
### DO-02 — Typed environment and secret management
**Trace:** [REQ-17 Infrastructure, health probes, and CI delivery](../testing/acceptance-matrix.md#req-17); [部署設定登錄](../contracts/interface-contract.md#deployment-config).
- **Precondition:** Approved environment inventory and least-privilege ownership.
- **Normal flow:** Inject typed config and secret references per service/environment; only BB receives JWT signing authority; protect GCS and push provider credentials.
- **Failure flow:** Missing required config fails closed or readiness; never substitute fake credentials or log secret material.
- **Acceptance:** Each setting has service owner, sensitivity, requirement, and missing-value behavior. Secret values do not enter PRDs/logs.
- **Handoff:** [BA-01](backend-a.md#ba-01)/[BB-01](backend-b.md#bb-01) required config; [QA-05](qa.md#qa-05) test matrix.

<a id="do-03"></a>
### DO-03 — GitHub Actions delivery
**Trace:** [REQ-17 Infrastructure, health probes, and CI delivery](../testing/acceptance-matrix.md#req-17); [部署設定與健康檢查](../contracts/interface-contract.md#deployment-config).
- **Precondition:** Approved quality gates and controlled deployment environment.
- **Normal flow:** PR checks → controlled test deployment → health/REST/WSS smoke → authorized production promotion with recoverable version.
- **Failure flow:** Missing config or failed check stops promotion and retains traceable artifact/version.
- **Acceptance:** GitHub Actions is the CI/CD baseline (not GitLab); pipeline specification identifies inputs, outputs, approvals, and rollback artifact. This PRD does not claim it is implemented.
- **Handoff:** Build/runtime needs with [BA-01](backend-a.md#ba-01), [BB-01](backend-b.md#bb-01), [FA-01](frontend-a.md#fa-01), [FB-01](frontend-b.md#fb-01), PM, and [QA-05](qa.md#qa-05).

<a id="do-04"></a>
### DO-04 — Health, monitoring, alerting, and log privacy
**Trace:** [REQ-16 Unified errors and privacy protection](../testing/acceptance-matrix.md#req-16), [REQ-17 Infrastructure, health probes, and CI delivery](../testing/acceptance-matrix.md#req-17); [HealthResponse](../contracts/interface-contract.md#data-dictionary), [`/health/live` and `/health/ready`](../contracts/interface-contract.md#deployment-config).
- **Precondition:** BA/BB expose health and non-sensitive metrics.
- **Normal flow:** Distinguish liveness from dependency readiness; monitor ACK, live delivery, recovery, activity expiry, and push failures.
- **Failure flow:** Missing config reason is diagnosable (e.g. CONFIG_MISSING) without exposing secrets, body, token, or high-cardinality public user-ID labels.
- **Acceptance:** Dependency failure returns unready/503; logs and metric labels remain privacy-safe.
- **Handoff:** [BA-08](backend-a.md#ba-08)/[BB-08](backend-b.md#bb-08) health dependencies; [QA-05](qa.md#qa-05) alert thresholds and acceptance.

<a id="do-05"></a>
### DO-05 — Reproducible performance-verification environment
**Trace:** [REQ-18 Performance validation and capacity boundaries](../testing/acceptance-matrix.md#req-18); [approved operational configuration](../contracts/interface-contract.md#deployment-config).
- **Precondition:** QA workload and PM thresholds are specified.
- **Normal flow:** Record software version, compute/resource, network, DB pool, Redis, and config references needed to reproduce a run.
- **Failure flow:** Incomparable environments do not share capacity conclusions; untested scale is never reported passed.
- **Acceptance:** Environment description is sufficient to reproduce future measurements; no performance result is claimed in this spec.
- **Handoff:** Reproducible environment record to [QA-05](qa.md#qa-05).

<a id="do-06"></a>
### DO-06 — Web assets and protected deep-route fallback
**Trace:** [REQ-21 Web deep links and authorized route return](../testing/acceptance-matrix.md#req-21); [FB-07](frontend-b.md#fb-07) route ownership, [FA-05](frontend-a.md#fa-05) chat route behavior, [A12](../contracts/interface-contract.md#api-a12), [A13](../contracts/interface-contract.md#api-a13), `/api/v1` and `/ws/v1` routing.
- **Precondition:** Approved Web asset build and known UI route namespace.
- **Normal flow:** Serve the same Web project assets and allow refresh/deep-link fallback only for the listed candidate UI route patterns: `/login`, `/register`, `/contacts`, `/chats`, `/chats/{conversation_id}`, `/profile`, and `/groups/{conversation_id}/manage`. Retain `/api/v1` REST and `/ws/v1` WSS routing as separate backend routes.
- **Failure flow:** Never rewrite `/api/v1` or `/ws/v1` paths or failures to the Web shell. Unknown UI routes show controlled not-found state; protected routes wait for authorization and do not disclose content.
- **Acceptance:** Refresh/direct navigation to each listed UI route reaches the same auth guard and authorized route return; the Web-shell fallback is restricted to those UI route patterns, and API/WSS paths and status behavior remain unchanged.
- **Handoff:** [FB-07](frontend-b.md#fb-07) route namespace; [BA-01](backend-a.md#ba-01)/[BB-03](backend-b.md#bb-03) origin/ingress; [QA-06](qa.md#qa-06) deep-link matrix.

## 決策與共用參照

- [響應式 Web 行為](../ui/web-rwd.md#web-rwd)
- [決策：Web Push 範圍](../decisions.md#decision-web-push)
- [決策：響應式 Web 版面](../decisions.md#decision-rwd)
- [返回文件導覽](../README.md)
