# Development environment and deployment handoff

This checkout includes the real API, BA realtime service, and bundled root Compose product profile. The default profile remains PostgreSQL 17 and Redis 7 only; `product` adds the API and `realtime` adds BA. No external API provider compose file or fake API is required. This is an operator workflow, not a claim that a VM, DNS, certificate, GCP project, or GCS bucket has been operated. See the physical limitations at the end.

## 1. Local product stack

Prerequisites: Docker Engine/Desktop with a functioning daemon, Compose v2 (`--wait` and JSON `config` support), POSIX shell, OpenSSL, and Python 3 where infrastructure scripts need it. Run at the repository root:

```sh
sh infra/scripts/init-dev.sh
docker compose config --quiet
docker compose --profile product --profile realtime up -d --build --wait --wait-timeout 120
docker compose ps
```

The root Compose file builds `api` from `backend/api/Dockerfile` and BA from `backend/realtime/Dockerfile`. `init-dev.sh` creates/preserves random development secrets and `.env` with restrictive permissions; it never prints secrets, starts services, creates cloud credentials, or overwrites existing secrets. It derives `.secrets/database_url` from the configured `POSTGRES_USER`, `POSTGRES_DB`, and password file. Do not edit/rotate those independently: initialization rejects URI/password/database disagreement. Existing PostgreSQL volumes retain their initialized DB password. Secret files are host bind-mounted, not encrypted storage; protect the host and backups.

The initializer intentionally accepts only a small `.env` grammar: each nonblank, noncomment physical line must be a single assignment accepted by `infra/scripts/database-reference.py` (optional `export` is accepted as assignment syntax, not executed). Shell expansion and multiline/continued values are not evaluated and unsupported multiline syntax fails closed before secret files are changed. `POSTGRES_USER` and `POSTGRES_DB` must resolve to literal identifier values; inspect the parser before changing database target settings.

Compose's default stack publishes no ports. The internal backend network is isolated. For intentional local database/Redis/BA access only, use the documented `infra/docker/compose.dev.yml` override and bind addresses remain loopback:

```sh
docker compose -f docker-compose.yml -f infra/docker/compose.dev.yml --profile product --profile realtime up -d --build --wait --wait-timeout 120
```

Never use this override in production. Keep the same Compose files/profile/project name to operate the same services and volumes. `stop`, `start`, and `down` retain named volumes; never use volume deletion/prune commands on data you need.

## 2. API, realtime, and trusted proxy

The API container starts `python -m hine_api`. In development/test the API applies migrations when connecting; in staging/production it verifies the already-applied migration set and does **not** apply DDL automatically. For local development, the explicit migration command is:

```sh
docker compose --profile product run --build --rm --no-deps api python -m hine_api migrate
```

For production, back up first and stop all API/BA/writers; ensure the private PostgreSQL/Redis services are running, then use the production wrapper (with the complete production environment below):

```sh
sh infra/scripts/stack.sh up -d postgres redis
sh infra/scripts/stack.sh migrate
```

`stack.sh migrate` takes no arguments, runs production preflight and builds/runs the bundled API image with `python -m hine_api migrate`. Then launch the full stack. It applies ordered, checksum-verified SQL files under an advisory lock and never drops the database.

The API reads its PostgreSQL connection from `/run/secrets/database_url` via `DATABASE_URL_SECRET_REF`. JWT signing key comes from `/run/secrets/jwt_signing_key`; issuer/audience and internal service credentials are distinct settings/secrets. Signing key must be at least 32 bytes. Do not use a placeholder key. API settings also require HTTPS `PUBLIC_ORIGIN`, valid `REALTIME_INTERNAL_URL`, `SYNC_PAGE_LIMIT` 1–100, `SYNC_SCAN_LIMIT` 1–1000, and invalidation retention at least as long as access-token lifetime.

`TRUSTED_PROXY_NETWORKS` is a comma-separated list of strict CIDRs; API defaults to trusting none, and development defaults to the direct TCP peer. Only a socket peer inside a configured network may supply exactly one valid `X-Hine-Client-IP`, used for client-IP rate limits. Production Compose requires this setting: provide only operator-verified, isolated reverse-proxy CIDR(s), ensure clients cannot connect from those ranges, and ensure the proxy strips/replaces incoming copies of the header. Do not invent a broad subnet or trust a client-reachable range. It is never authentication.

Compose secret bind mounts retain host UID/GID/mode; their `uid/gid/mode` options do not remap ownership. The containers drop all capabilities and use `no-new-privileges`; configure `HINE_RUNTIME_UID`/`HINE_RUNTIME_GID` to the actual secret owner when needed. `init-dev.sh` only initializes an absent `.env`; inspect existing values and file owners after moving secrets.

## 3. Optional real GCS attachments

GCS is off unless configured. Provision the real private bucket, workload identity/service account, required bucket access, signing permission, and egress independently. No fake credential/fallback is generated. Production `stack.sh` automatically adds `infra/docker/compose.gcs.yml` only when `GCS_CREDENTIALS_FILE` is set. Example with actual provisioned values:

```sh
export GCS_BUCKET=your-private-bucket
export GCS_CREDENTIALS_FILE=/srv/hine/secrets/gcs-credentials.json
sh infra/scripts/stack.sh config
```

The path must be absolute and refer to a nonempty, non-symlink file. The overlay mounts it as `GOOGLE_APPLICATION_CREDENTIALS`; without a key file, Google SDK ADC must be provided by the runtime. The API uses the official Cloud Storage SDK, signs V4 create-only upload grants and pins verification/download/deletion to object generations. `GCS_SIGNING_SERVICE_ACCOUNT` selects IAM Credentials signing and requires actual IAM sign-blob permission for that service account; otherwise signing uses credentials that implement signing. Do not enable until the real identity can sign and the real private bucket is configured. Bucket lifecycle, retention, IAM, and backups remain operator responsibilities.

Abandoned object cleanup runs automatically in the API process every 60 seconds. The implementation entry point is `await hine_api.attachments.cleanup_abandoned(runtime, limit=100)` (limit 1–100); there is no standalone cleanup CLI. It first closes eligible database rows in a transaction, then deletes only their pinned object generations. Cleanup failures are retried by a later sweep; they do not reopen a row or authorize deletion of replacement generations.

## 4. PostgreSQL backup and restore

Backups contain private user data. Keep `.backups/` mode 0700, archive files mode 0600, encrypt off-host copies using approved tooling, and restrict retention/access. No remote backup is configured. From repository root:

```sh
mkdir -p .backups && chmod 700 .backups
sh infra/scripts/backup-postgres.sh .backups/hine-before-change.dump
```

This uses PostgreSQL 17 `pg_dump` custom format, validates via `pg_restore --list`, and atomically publishes without overwriting an existing archive. It does not put passwords in argv. Restore is destructive for objects in the archive. Stop all writers and take a new backup first:

```sh
docker compose --profile product --profile realtime stop api realtime
sh infra/scripts/restore-postgres.sh --confirm-destructive .backups/hine-before-change.dump
```

Restore operates on the configured existing database and refuses unsafe targets, active clients, absent/symlink/empty archives, and running API/BA. It does not drop/recreate the database or create a fallback target. It uses `pg_restore --clean --if-exists --exit-on-error --single-transaction --no-owner --no-acl`; a transport failure around commit can leave the result unknown, so inspect the real target before retrying. Quiesce external clients too. Restore into a separate, explicitly authorized isolated target to validate recoverability; never point it at production without approval. After restore, use the production migration wrapper if necessary and verify schema/data with product owners before writers resume.

## 5. Production handoff and safety boundary

The intended layout is one approved GCP Compute Engine VM with Compose, one API and one BA instance, private PostgreSQL/Redis, and Caddy as the HTTPS/WSS web entrypoint. Firewall permits public TCP 80/443 only, plus separately approved restricted SSH; never expose 5432/6379/8080/8081. Compose isolation does not prove cloud firewall or host-daemon safety.

Build the real frontend using commands/configuration in the [frontend application README](../../frontend/app/README.md); provide its actual build artifact as `WEB_ROOT` (nonempty `index.html`). The API and BA are built from this checkout. Production secrets must be provisioned and transferred securely to a dedicated production secret directory before initializing the data volume. Never reuse development secrets/volumes. The secret directory must contain `postgres_password`, `redis_password`, `redis_url`, `api_internal_token`, `realtime_internal_token`, `database_url`, and `jwt_signing_key`; credentials and database URI must match the existing DB. Optional GCS uses the overlay procedure above. Preserve all secrets and references across releases.

With approved real domain, ACME email, VM IP, frontend artifact, production secrets, and authorized VM access:

```sh
export HINE_ENV=production
export COMPOSE_PROJECT_NAME=hine-production
export HINE_SECRET_DIR=/srv/hine/secrets
export WEB_ROOT=/srv/hine/releases/current/web
export HINE_DOMAIN=hine.run.place
export ACME_EMAIL=your-approved-operator-email
: "${TRUSTED_PROXY_NETWORKS:?Set actual isolated proxy CIDR(s) before running}"
sh infra/scripts/preflight.sh --local
# For an upgrade: back up PostgreSQL and quiesce all writers first.
sh infra/scripts/stack.sh up -d postgres redis
sh infra/scripts/stack.sh migrate
sh infra/scripts/stack.sh up -d --build --wait --wait-timeout 120
sh infra/scripts/stack.sh ps
sh infra/scripts/preflight.sh --public
```

Use actual approved values, never examples. `stack.sh` combines root Compose with `infra/docker/compose.production.yml`; no external API provider is required. The production wrapper validates isolation and frontend artifact before launch. For recovery commands (`stop`, `down`, `ps`, `logs`, `config`, backup/restore), keep `WEB_ROOT` set for Compose interpolation; a missing frontend artifact must not impede recovery. `stack.sh down` positively allowlists services, `--remove-orphans`, and numeric timeout forms; volume-deletion flags/aliases are refused.

`--local` requires Docker and checks resolved topology, artifacts, local image availability when not building, and Caddy parsing; it does not launch or obtain certificates. `--public` repeats checks, observes private `/health/ready`, then performs read-only DNS/HTTP/TLS/REST/WSS probes against explicitly approved `HINE_EXPECTED_IP` addresses. A WebSocket HTTP upgrade is not W01/W02 authentication or product E2E.

Production Caddy routes `/api/v1` to API and exact `/ws/v1` to BA; `/internal` and `/health` are controlled 404s publicly, only approved SPA routes serve the shell, and Caddy admin API is disabled. Do not publish service ports. For rollback, retain prior real API/BA/frontend artifacts and image digests, keep the same project and data volumes, and do not assume code rollback reverses database migrations. Restore only with stopped writers and an approved isolated target or explicit production authorization.
The actual local PostgreSQL 17.11 dump/atomic restore drill is recorded as PF08 in [native fault evidence](../testing/evidence/product-native-faults.json); it restored an owned isolated clone and verified durable product state. This is local native evidence only, not Docker/VM/cloud restore acceptance, a formal RPO, or GCS backup proof.


No cloud VM login/project/bucket/ADC/signing credentials were available for this documentation work. Therefore VM deployment, cloud firewall, DNS/TLS issuance, real GCS operations, and production backup/restore are physical gates, not claims of execution. Docker daemon/API product tests and browser/Edge/Android execution are separately reported by the integration owner; do not infer them from this manual.

Upstream references: [Compose secrets](https://docs.docker.com/compose/how-tos/use-secrets/), [Compose networks](https://docs.docker.com/reference/compose-file/networks/), [PostgreSQL pg_dump](https://www.postgresql.org/docs/17/app-pgdump.html), [PostgreSQL pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html).
