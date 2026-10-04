# Development environment and deployment handoff

This is the DO-owned environment, not an implementation of BB or the frontend. The binding requirements remain the [deployment configuration contract](../contracts/interface-contract.md#deployment-config) and [DO PRD](../prd/devops.md). The default stack actually contains PostgreSQL17 and Redis7; the optional `realtime` profile builds the BA sources. There is deliberately no dummy API service, fake frontend, or nonexistent HINE image.

**Evidence status:** these commands are the reproducible operator workflow, not a claim that this checkout has been launched. No Docker daemon/VM launch, DNS change, certificate issuance, GCP/GCS setup, SSH deployment, release approval, production rollback, or cloud modification was performed while authoring these files. A public marketing site, including an existing nginx-served site, is not evidence that this Caddy configuration or the chat API is deployed. Parent verification records actual local checks separately. BB/FA/FB artifacts and member confirmations are still prerequisites for product and production acceptance. Main branch protection is deferred, not silently enabled.

## 1. Shared local Docker environment

Prerequisites: Docker Engine/Desktop with a functioning daemon, Compose v2 with `--wait` and JSON `config` support, a POSIX shell, and OpenSSL. Linux containers are required. Python3 is needed only for infrastructure tests/production preflight. No global Python package installation is required. Development uses upstream `postgres:17-alpine` and `redis:7-alpine`; production releases must record the exact resolved image digests, not assume that a mutable major tag is a release identifier.

Run at the repository root:

```sh
sh infra/scripts/init-dev.sh
docker compose config --quiet
docker compose up -d --wait --wait-timeout 120
docker compose ps
```

`init-dev.sh` generates four distinct256-bit random hex credentials and a Redis connection URI under `.secrets/` (directory0700, files0600), creates `.env` with mode0600 **and runtime UID/GID matching the actual BA secret-file owner**, and never prints credentials. It preserves existing secrets and `.env`; rejects empty/nonhex credentials, inconsistent Redis URL/password pairs, mixed BA secret ownership, and symlink targets rather than replacing them. `.env`, `.secrets/`, and `.backups/` must remain ignored/untracked. Do not commit or send those files in chat. The secret files are consumed through Compose file secrets, which are bind mounts, **not encrypted secret storage**. Protect the VM filesystem/backups and operator access accordingly.

The default stack publishes **no host ports**. Its `backend` network is `internal: true`; PostgreSQL and Redis use named persistent volumes. PostgreSQL is authoritative storage; Redis AOF persistence helps development restarts but does not make Pub/Sub messages a durable queue or message authority.

Check actual authenticated data services without exposing passwords in command arguments:

```sh
docker compose exec -T postgres sh -ec 'export PGPASSWORD="$(cat /run/secrets/postgres_password)"; psql -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -X -v ON_ERROR_STOP=1 -c "SELECT 1"'
docker compose exec -T redis sh -ec 'export REDISCLI_AUTH="$(cat /run/secrets/redis_password)"; redis-cli --no-auth-warning ping'
```

Expected successful results are PostgreSQL `1` and Redis `PONG`. `pg_isready` checks server availability; the explicit SQL command additionally checks the provisioned password/database. PostgreSQL initialization credentials apply only when its data volume is empty: changing `.secrets/postgres_password` does not rotate the already-existing database password. Coordinate an explicit BB/DO rotation; do not regenerate credentials after losing secret files and pretend old data is accessible.

### Intentional host-local access

Only if a developer needs host access:

```sh
docker compose -f docker-compose.yml -f infra/docker/compose.dev.yml up -d --wait --wait-timeout 120
```

This opt-in override binds PostgreSQL5432, Redis6379, and (when its profile is selected) BA8081 **only to127.0.0.1**, never all interfaces. Port collisions fail normally; use the default private stack if those ports are occupied. BA's `/internal/*` and `/health/*` share8081 and are consequently reachable by local processes only under this explicit development override. Never include it in production. Development access is not public TLS/WSS acceptance.

### Stop, restart, and persistence

```sh
docker compose stop
docker compose start
docker compose down
docker compose up -d --wait --wait-timeout 120
```

`stop` retains containers and data; `down` removes containers/network, **not named volumes**. Keep `COMPOSE_PROJECT_NAME=hine-dev` and the same checkout configuration to reconnect to the same volumes. Do not use `down --volumes`, `docker volume prune`, or `docker system prune --volumes` on data you need. When using an override/provider/profile, use the same `-f`/profile options on subsequent commands.

## 2. Optional BA and real BB integration

The Dockerfile is `backend/realtime/Dockerfile`, listen port8081, entrypoint `python -m hine_realtime`; BA requires Python3.12+, `aiohttp==3.14.3` and `redis==8.1.0` as owned/pinned by BA. Its build context is limited to `backend/realtime/`; repository-root secrets, dumps, virtualenv and `.omp` are not sent to Docker. No JWT issuer, audience, or signing key is injected into BA.

```sh
docker compose --profile realtime up -d --build realtime
# Liveness only; this is NOT proof of dependency readiness or a working chat.
docker compose exec -T realtime python -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8081/health/live").status)'
```

Without a real `api:8080` provider, BA readiness is expected to fail/return503 and its container health is unhealthy; no fake BB/auth/persistence fallback is provided. Do **not** use `--wait` and call that deployment successful while BB is absent. Actual integration requires BB's real provider and internal operations, including session invalidation polling, alongside BA. All BB/BA internal operations remain `/internal/v1/<operation>`, JSON envelope and bearer credentials per contract.

Operator-provisioned BA settings:

| Setting | Injected value/source |
|---|---|
| `HINE_ENV` | `development`; production overlay forces `production` |
| `REALTIME_HOST` / `REALTIME_PORT` | `0.0.0.0` / `8081` inside its private container |
| `API_INTERNAL_URL` | `http://api:8080`; dev may override for a **real reachable** BB |
| `REDIS_URL_SECRET_REF` | `/run/secrets/redis_url`, content `redis://:<generated hex>@redis:6379/0` |
| `INTERNAL_CALLER_TOKEN_SECRET_REF` | `/run/secrets/realtime_internal_token`, BA outbound credential |
| `INTERNAL_ALLOWED_CALLERS` | JSON `{"api":"/run/secrets/api_internal_token"}`; only BB may call BA publish/presence |
| `HEARTBEAT_INTERVAL_SECONDS` / `HEARTBEAT_TIMEOUT_SECONDS` | `30` / `90` |
| `INVALIDATION_POLL_SECONDS` / `INVALIDATION_STALE_SECONDS` | `5` / `15` |
| `NOTICE_CATCHUP_HOLD_MS` / `SYNC_PAGE_LIMIT` | `1000` / `100` |

Compose file secrets preserve host file ownership/mode; the `uid/gid/mode` fields do not remap a bind-mounted file's ownership. BA has `cap_drop: ALL` and `no-new-privileges`: even UID0 cannot bypass owner-only permissions without `DAC_OVERRIDE`. For a newly generated `.env`, `init-dev.sh` sets `HINE_RUNTIME_UID`/`HINE_RUNTIME_GID` from the actual secret-file owner. An existing `.env` is intentionally preserved, including explicit production IDs: inspect and correct legacy/moved-secret mismatches before selecting the BA profile; never assume rerunning init repairs a stale UID0 setting. On Linux, `stat -c '%u %g' .secrets/redis_url` gives the required IDs; set both in `.env` or export both when operating. All three BA secret files must share an owner. For rootless Docker, reconcile actual mapped ownership explicitly; do not weaken files to world-readable. The upstream PostgreSQL entrypoint reads its file secret during privileged initialization; the Redis wrapper reads its secret before dropping to the upstream `redis` runtime user. Passwords are not placed in Redis argv or inspectable Compose environment; Redis's temporary config is0600 and owned by its runtime user.

A real BB provider must supply `api` on `backend`, listening8080, with no published ports; a real readiness healthcheck; its own source/build or approved release image; DB URI/credentials and only-BB JWT signing settings; and the reciprocal BA settings:

- `REALTIME_INTERNAL_URL=http://realtime:8081`.
- `INTERNAL_CALLER_TOKEN_SECRET_REF=/run/secrets/api_internal_token` (API outbound).
- `INTERNAL_ALLOWED_CALLERS={"realtime":"/run/secrets/realtime_internal_token"}` (API inbound).
- Mount the two existing internal secret definitions and DB password/URI as required by **BB's actual secret-reading implementation**, not invented environment support. `DATABASE_URL` is sensitive; any generated URI must remain in a protected file/secret reference, not a checked-in provider or plaintext inspectable environment.
- Inject the contract's BB limits and BB-only `JWT_ISSUER`, `JWT_AUDIENCE`, signing-key reference. `INVALIDATION_RETENTION_SECONDS` remains a BB/PM decision and must be at least the actual maximum access-token lifetime; DO does not invent that lifetime. GCS settings become necessary only when attachment storage is enabled.
- If enabled GCS operations require outbound connectivity, BB may additionally join an operator-defined egress network. This does not allow host ports or a public `/internal` route. DB/Redis/BA stay only on `backend`.

For an actually available BB provider, local integration uses:

```sh
# Absolute path to the real BB-owned file; no sample fake provider is delivered.
export API_PROVIDER_COMPOSE=/absolute/path/to/approved-api.compose.yml
docker compose -f docker-compose.yml -f "$API_PROVIDER_COMPOSE" --profile realtime up -d --build --wait --wait-timeout 120
```

This command is conditional on the real artifact; it is not part of the default PG/Redis startup guarantee. Paths in overlay files resolve relative to the first/root Compose file, so provider build contexts/bind sources should be absolute or explicitly root-relative.

## 3. Real PostgreSQL backup and restore

Backups contain private user data. Archive destination permissions are0600; keep `.backups/`0700, encrypt copies off-host using the operator's approved tooling, and restrict retention/access. No remote/cloud backup was configured here. A backup is not proven recoverable until restored and checked against BB's real schema/data.

```sh
mkdir -p .backups
chmod 700 .backups
sh infra/scripts/backup-postgres.sh .backups/hine-before-change.dump
```

This uses the PostgreSQL17 container's actual `pg_dump` custom format, fails on Docker/server/dump/validation errors, validates with `pg_restore --list`, and atomically publishes without overwriting an existing archive. It neither logs nor passes the password in argv. Retrying the same filename fails rather than silently replacing your backup.

Restore is **destructive for objects represented in the archive**. A custom dump of a full application database restores those objects; it does not promise to delete unrelated objects created after that dump. Only trust operator-generated archives (restore SQL is executable). Stop all writers, including host BB sessions, and take a new backup first:

```sh
docker compose --profile realtime stop realtime
# If a real BB provider is in use, stop api with the identical provider Compose options.
sh infra/scripts/restore-postgres.sh --confirm-destructive .backups/hine-before-change.dump
```

There is no automatic database drop/recreation or silent create-target fallback. Restore refuses absent/symlink/empty archives, running `api`/`realtime`, active DB clients, unsafe/system DB names, target mismatch, and unreadable archives. It uses the configured existing `POSTGRES_DB`/`POSTGRES_USER`, authenticated TCP connection, `pg_restore --clean --if-exists --exit-on-error --single-transaction --no-owner --no-acl`. PostgreSQL permission/SQL errors are real failures and the restore transaction rolls back. A lost transport response around commit can leave the outcome unknown: keep writers stopped and inspect the real target before retrying; a command failure is not proof that no changes committed. Quiesce **all** clients externally; the active-client check is not a distributed lock against a new client connecting later. After a successful commit, BB must validate schema/migrations, representative records, C1/M1 idempotence and event/session streams before writers restart. Do not restart automatically after failure.

## 4. Production handoff: real artifacts required

Target architecture: one approved GCP Compute Engine VM, Compose, one `api` and one `realtime`, private PostgreSQL/Redis, and a Caddy Web entrypoint. GCS attachment infrastructure is separately BB/DO-owned. This repository does **not** provision a VM, change live DNS, replace the observed marketing host, or fabricate release/member approval. Firewall provisioning must permit public TCP80/443 only (plus separately approved restricted operator SSH), never5432/6379/8080/8081. Host Compose isolation cannot prove that a cloud firewall or unrelated host daemon is safe; the operator must provide its firewall review evidence.

Prerequisites before using production commands:

1. Approved domain `hine.run.place`, responsible ACME email, approved VM DNS addresses, actual VM access/authorization and firewall review. Caddy's edge network is required for certificate issuance; persistence lives in `caddy_data`/`caddy_config`.
2. Real BB provider described above, actual release image already loaded/pulled locally (preflight never pulls an arbitrary BB tag), or available source context/Dockerfile; approved frontend build directory containing nonempty `index.html`. Build the frontend using its owner-provided commands and configured `API_BASE_URL=https://hine.run.place/api/v1`, `WS_URL=wss://hine.run.place/ws/v1`, and approved origin. DO does not generate a placeholder `index.html`.
3. Provision separate production credentials on the VM. `init-dev.sh` creates credentials only in the current checkout; use a dedicated production checkout and securely move its generated `.secrets` contents to the protected production secret directory **before** first data initialization. Never reuse dev secrets or point production at dev volumes. JWT signing/GCS credentials come from their actual owners, not this generator. Preserve existing production DB credentials and secret references across releases.
4. Keep `.env` present/protected in the checkout (its nonsecret defaults can remain); production wrapper settings come from the exported operator environment. Example values below are configuration instructions, not claims those artifacts exist:

```sh
export HINE_ENV=production
export COMPOSE_PROJECT_NAME=hine-production
export HINE_SECRET_DIR=/srv/hine/secrets
export API_PROVIDER_COMPOSE=/srv/hine/releases/current/api.compose.yml
export WEB_ROOT=/srv/hine/releases/current/web
export HINE_DOMAIN=hine.run.place
export ACME_EMAIL=your-approved-operator-email
export HINE_EXPECTED_IP=your-approved-vm-public-ip
# Set matching secret-owner IDs if BA does not run as root.
# export HINE_RUNTIME_UID=1000 HINE_RUNTIME_GID=1000

sh infra/scripts/preflight.sh --local
sh infra/scripts/stack.sh up -d --build --wait --wait-timeout 120
sh infra/scripts/stack.sh ps
sh infra/scripts/preflight.sh --public
```

Replace the operator values with approved real ones; launch preflight explicitly fails on missing artifacts. `stack.sh` consistently combines the root Compose file, real BB provider, then `infra/docker/compose.production.yml`, enabling both profiles. No fake `api` is delivered: the production overlay intentionally depends on the real provider's `api`. The wrapper validates isolation and the actual frontend build before `up`/`start`. For `stop`, `down`, `ps`, `logs`, `config`, backup and restore, a broken/missing frontend directory does **not** block recovery: keep `WEB_ROOT` set to the same absolute release path for Compose interpolation, the existing provider/project configuration and production secrets intact. These operations do not launch or mount the frontend. No dev loopback override is included.

`stack.sh down` uses a positive argument allowlist **before prerequisites or any Docker call**: only the five service names (`caddy`, `api`, `realtime`, `postgres`, `redis`), `--remove-orphans`, and a nonnegative integer timeout (`-t 10`, `-t10`, `--timeout 10`, `--timeout=10`) are accepted. All unknown flags and every volume-deletion spelling/alias/cluster are refused, including `-v`, `-v=true`, `-vt10`, `--volume` and `--volumes`. Omit other raw Compose flags in this safety wrapper.

`--local` requires a real Docker daemon and validates artifacts, resolved Compose topology, locally available BB image when not building, and the actual Caddy parser in a short-lived container. It does not start the stack, acquire certificates, or report public acceptance. `--public` repeats local checks, observes actual private `/health/ready` for both services, then performs **read-only** DNS/HTTP/TLS/REST/WSS probes. It requires `HINE_EXPECTED_IP` (comma-separated approved addresses); all DNS answers must exactly match those approved addresses. It fails on redirect/certificate/frontend/API/WS/isolation failures and prints no response bodies or tokens. A101 WebSocket upgrade is not W01/W02 authentication or product E2E; run the QA-owned real product tooling separately.

### Exact public Caddy behavior

- Automatic HTTP-to-HTTPS redirect and normal publicly verified certificates for the configured approved domain.
- `/api/v1` and `/api/v1/*` proxy unchanged to `api:8080`.
- **Exact** `/ws/v1` proxies unchanged to `realtime:8081`, including WebSocket Upgrade. `/ws/v1/` and other `/ws/*` are404, never a SPA fallback.
- `/internal`, `/internal/*`, `/health`, `/health/*` always receive controlled404 at the public entrypoint; they are not forwarded upstream. API/WS errors cannot be rewritten to frontend HTML. Other reserved API/WS routes are404.
- Only `/`, `/login`, `/register`, `/contacts`, `/chats`, `/chats/{conversation_id}`, `/profile`, `/groups/{conversation_id}/manage` get the actual SPA shell. Existing build assets are served normally. Unknown UI paths return404. Auth guards and root `replace` redirect are frontend-owned; serving a shell is not proof of guarded content behavior.
- Caddy's admin API is disabled. No access log is enabled because raw URLs/query strings can contain sensitive values; product services must independently preserve the shared log privacy rules.

### Operational stop, backup, restore, and rollback

With the same exported production environment:

```sh
sh infra/scripts/backup-postgres.sh --production /protected/backups/hine-before-release.dump
sh infra/scripts/stack.sh stop caddy api realtime
# Start only the existing private data services if they were stopped.
sh infra/scripts/stack.sh up -d postgres redis
sh infra/scripts/restore-postgres.sh --production --confirm-destructive /protected/backups/hine-before-release.dump
# Validate real BB schema/data before restarting writers.
sh infra/scripts/stack.sh up -d --build --wait --wait-timeout 120
sh infra/scripts/preflight.sh --public
# Non-destructive full stop/removal; persistent named volumes remain:
sh infra/scripts/stack.sh down
```

Backup directory must already exist with restricted permissions. A schema rollback is only possible if BB confirms compatibility or provides an actual tested migration/restore procedure. For an application-only rollback, keep the prior approved API image/source, BA source/image, frontend build, provider configuration, image digests and secret references. Stop caddy/api/realtime, select the prior real release paths, keep the same production project name/data volumes, run `--local`, then `up --wait` and `--public`. **Do not** promise rolling back code reverses committed data/migrations. If restore is required, follow the explicit destructive command with quiesced writers and BB validation; restore/release rollback was not exercised here. Release artifacts must not include `.secrets` or private dumps.

## 5. Parent/local verification commands

Workers do not run tests/builds/lint/formatters mid-flight. Behavioral tests exercise actual credential generation/reruns/symlink refusal, backup no-clobber, restore destructive guards, missing-artifact failures, production isolation and RFC6455 upgrade validation. No test provider is delivered as the real product.

```sh
python3 -m unittest discover -s infra/tests -p 'test_*.py'
sh -n infra/scripts/init-dev.sh infra/scripts/common.sh infra/scripts/backup-postgres.sh infra/scripts/restore-postgres.sh infra/scripts/preflight.sh infra/scripts/stack.sh infra/docker/redis-start.sh
docker compose config --quiet
docker compose -f docker-compose.yml -f infra/docker/compose.dev.yml --profile realtime config --quiet
```

The Docker startup/authenticated smoke and real dump/restore commands above require an available daemon; document them as **not performed** if unavailable. Production preflight remains blocked until real BB/frontend/release/VM prerequisites exist. No performance/capacity results or successful cloud deployment are claimed.

Upstream references: [Compose secrets](https://docs.docker.com/compose/how-tos/use-secrets/), [Compose networks](https://docs.docker.com/reference/compose-file/networks/), [Caddy route patterns](https://caddyserver.com/docs/caddyfile/patterns), [Caddy route ordering](https://caddyserver.com/docs/caddyfile/directives/route), [PostgreSQL pg_dump](https://www.postgresql.org/docs/17/app-pgdump.html), [PostgreSQL pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html).
