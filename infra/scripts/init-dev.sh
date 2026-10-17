#!/bin/sh
set -eu
umask 077
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
fail() { printf 'init-dev: %s\n' "$*" >&2; exit 1; }
[ "$#" -eq 0 ] || fail 'usage: sh infra/scripts/init-dev.sh (creates .env and .secrets in this checkout)'
SECRET_DIR="$ROOT/.secrets"
[ ! -L "$ROOT/.env" ] || fail '.env must not be a symlink'
[ ! -e "$ROOT/.env" ] || [ -f "$ROOT/.env" ] || fail '.env must be a regular file'
command -v python3 >/dev/null 2>&1 || fail 'Python3 is required to resolve literal database targets'
configuration="$ROOT/.env"
[ -f "$configuration" ] || configuration="$ROOT/.env.example"
targets=$(python3 "$ROOT/infra/scripts/database-reference.py" "$configuration") || fail 'database target configuration is invalid or ambiguous'
sh "$ROOT/infra/scripts/init-secrets.sh" "$SECRET_DIR" "${targets%% *}" "${targets#* }" || fail 'credential initialization failed'
# Derive the runtime IDs from the actual secret owner, not an assumed root UID.
owners=$(stat -c '%u %g' "$SECRET_DIR/redis_url" 2>/dev/null || stat -f '%u %g' "$SECRET_DIR/redis_url") || fail 'cannot determine secret ownership'
sh "$ROOT/infra/scripts/init-env.sh" "${owners%% *}" "${owners#* }" || fail 'could not create .env without overwriting'
printf '%s\n' 'Development credentials ready (owner-only files); existing values preserved. No service was started.'
