<a id="backend-api"></a>
# 後端 API

## Runtime and configuration

The API is a real `aiohttp` service on port 8080. From the repository root, start the bundled product profile (PostgreSQL, API, and BA realtime):

```sh
sh infra/scripts/init-dev.sh
docker compose --profile product --profile realtime up -d --build --wait --wait-timeout 120
docker compose ps
```

`init-dev.sh` creates/preserves owner-only files in `.secrets/` and `.env`; it starts no service and does not invent production credentials. Docker Compose requires a running Docker daemon and Compose v2. The API image uses Python 3.12, installs the pinned `backend/api/requirements.txt`, copies migrations and the BA protocol package, and starts `python -m hine_api`. Development/test runtime applies migrations on database connection; staging/production runtime verifies the migration set and never applies DDL automatically.

Required API settings are injected by the root `docker-compose.yml`: `HINE_ENV`, HTTPS `PUBLIC_ORIGIN`, `DATABASE_URL_SECRET_REF`, `JWT_ISSUER`, `JWT_AUDIENCE`, `JWT_SIGNING_KEY_SECRET_REF`, `REALTIME_INTERNAL_URL`, `INTERNAL_CALLER_TOKEN_SECRET_REF`, `INTERNAL_ALLOWED_CALLERS`, `SYNC_PAGE_LIMIT`, `SYNC_SCAN_LIMIT`, and `INVALIDATION_RETENTION_SECONDS`. The environment accepts a PostgreSQL URI from `DATABASE_URL` when no secret reference is provided; the reference takes precedence and reads the named file. The bundled profile mounts `.secrets/database_url`. The initializer derives that URI from `POSTGRES_USER`, `POSTGRES_DB`, and `postgres_password`; preserve it with the existing database credentials. It rejects disagreement rather than rotating a live database password. JWT signing-key file must contain at least 32 UTF-8 bytes. Internal caller tokens are distinct and at least 32 bytes. Production access-token lifetime defaults to 900 seconds; invalidation retention must be at least that lifetime.

`TRUSTED_PROXY_NETWORKS` is optional and defaults to no trusted proxies; development therefore uses the socket peer for rate-limit identity. Only when the TCP peer belongs to a configured CIDR, exactly one valid `X-Hine-Client-IP` value is considered; other forwarded client-IP headers are ignored. Production Compose requires explicit `TRUSTED_PROXY_NETWORKS`. Supply only operator-verified isolated proxy CIDR(s), ensure clients cannot connect from those ranges, and configure the proxy to strip/replace incoming copies of the header. Never use a broad/client-reachable CIDR or treat this header as authentication.

For development, an explicit migration can be run with `docker compose --profile product run --build --rm --no-deps api python -m hine_api migrate`. Production migrations must use the guarded wrapper, after backing up/quiescing writers and starting PostgreSQL/Redis:

```sh
sh infra/scripts/stack.sh up -d postgres redis
sh infra/scripts/stack.sh migrate
```

Production `stack.sh migrate` takes no arguments, requires the full production environment and passing local preflight, then builds/runs the API migration command. The running production API only verifies the ordered, checksum-recorded SQL set under a schema-scoped advisory lock; it never auto-applies production DDL. Migrations do not drop the database. Liveness (`/health/live`) is process-only; readiness (`/health/ready`) requires valid configuration, PostgreSQL, and schema readiness.

## GCS attachments (optional)

No bucket or cloud credential is created by the application or development initializer. To enable real object storage, provision a private bucket and actual signing-capable credentials through the cloud owner. The production-only overlay `infra/docker/compose.gcs.yml` requires an absolute credential-file path and bucket name. Production `stack.sh config` assumes the complete production environment required by `infra/scripts/stack.sh` is already configured (`HINE_ENV`, project name, secret directory, domain, ACME email, and `WEB_ROOT` among other settings); see the [deployment handoff](../../docs/deployment/README.md#5-production-handoff-and-safety-boundary). This overlay does not enable cloud storage in development.

```sh
export GCS_BUCKET=your-real-private-bucket
export GCS_CREDENTIALS_FILE=/srv/hine/secrets/gcs-credentials.json
sh infra/scripts/stack.sh config
```

`stack.sh` automatically adds that overlay in production when `GCS_CREDENTIALS_FILE` is set; the file must exist, be nonempty, and not be a symlink. It is mounted to the API as `GOOGLE_APPLICATION_CREDENTIALS`. Without an explicit key file the SDK can use Application Default Credentials (ADC) where the runtime provides them. The application uses the official Google Cloud Storage SDK, private bucket operations, create-only V4 upload grants, and generation-pinned verification/download/deletion. Signing uses service-account signing when available or the IAM Credentials signer when `GCS_SIGNING_SERVICE_ACCOUNT` is configured; IAM signing requires the actual workload identity/service account to have permission to sign as that account. Do not create or commit a fake credential, and do not enable the overlay until the real bucket, identity, permissions, and egress are ready. Bucket lifecycle, retention, IAM, and backups remain operator responsibilities.

Abandoned object cleanup runs automatically in the API process every 60 seconds. The implementation entry point is `await hine_api.attachments.cleanup_abandoned(runtime, limit=100)` (limit 1–100); there is no standalone cleanup CLI. It first closes eligible database rows in a transaction, then deletes only their pinned object generations. Cleanup failures are retried by a later sweep; they do not reopen a row or authorize deletion of replacement generations.

## Product test prerequisites

The real-process API/product suite requires Python 3.12, both pinned requirement sets, a reachable isolated PostgreSQL database, a reachable real Redis instance, and permission for the DB role to create/drop its per-run schema. The test harness launches a real API process on loopback; domain tests also launch BA against Redis.

From the repository root, install requirements in the active Python environment:

```sh
python3 -m pip install -r backend/api/requirements.txt -r backend/realtime/requirements.txt
```

Supply database settings through a protected JSON environment-reference file (for example, JSON containing `DATABASE_URL_SECRET_REF` pointing to a protected file with the test PostgreSQL URI), and provide its path plus the real Redis URI through a protected environment manager. Set `PYTHONPATH` for the test modules and spawned API:

```sh
export HINE_TEST_API_ENV_REF=/secure/path/product-test-api-env.json
export HINE_TEST_REDIS_URL=redis://:REAL_SECRET@127.0.0.1:6379/0
PYTHONPATH=backend/api/src:backend/realtime/src:tests/product python3 -m unittest discover -s tests/product -p 'test_*.py'
```

Do not use a production database or Redis, and keep the Redis URI out of shell history/process arguments; provide it via a protected environment manager rather than typing a real secret in the command. The test harness's PostgreSQL interface is `HINE_TEST_DATABASE_URL` or `HINE_TEST_API_ENV_REF`; BA tests require `HINE_TEST_REDIS_URL` or a `REDIS_URL`/`REDIS_URL_SECRET_REF` in the API env-reference JSON. The test harness adds `backend/api/src` and `backend/realtime/src` to the spawned API's `PYTHONPATH`. This suite does not prove access to an actual GCS project/bucket; exercising cloud signing/storage requires the real credentials, permissions, bucket, and egress. For HTTP/API routes and client contract, see the repository interface contract. These tests and health endpoints alone are not product-level signup/chat/attachment acceptance.
