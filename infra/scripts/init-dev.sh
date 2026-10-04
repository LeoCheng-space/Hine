#!/bin/sh
set -eu
umask 077
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
fail() { printf 'init-dev: %s\n' "$*" >&2; exit 1; }
[ "$#" -eq 0 ] || fail 'usage: sh infra/scripts/init-dev.sh (creates .env and .secrets in this checkout)'
command -v openssl >/dev/null 2>&1 || fail 'openssl is required for random credentials'
SECRET_DIR="$ROOT/.secrets"
[ ! -L "$SECRET_DIR" ] || fail 'secret directory must not be a symlink'
if [ -e "$SECRET_DIR" ]; then
    [ -d "$SECRET_DIR" ] || fail 'secret path is not a directory'
else
    mkdir -m 700 "$SECRET_DIR"
fi
[ ! -L "$ROOT/.env" ] || fail '.env must not be a symlink'
[ ! -e "$ROOT/.env" ] || [ -f "$ROOT/.env" ] || fail '.env must be a regular file'
# Validate every existing target before changing permissions or creating secrets.
for name in postgres_password redis_password api_internal_token realtime_internal_token redis_url; do
    target="$SECRET_DIR/$name"
    [ ! -L "$target" ] || fail 'secret file must not be a symlink'
    if [ -e "$target" ]; then
        [ -f "$target" ] && [ -s "$target" ] || fail 'existing secret must be a nonempty regular file'
    fi
done
chmod 700 "$SECRET_DIR"
for name in postgres_password redis_password api_internal_token realtime_internal_token; do
    target="$SECRET_DIR/$name"
    if [ ! -e "$target" ]; then
        (set -C; openssl rand -hex 32 > "$target") || fail 'could not create random secret without overwriting'
    fi
    chmod 600 "$target"
    # Hex encoding keeps Redis config and URL syntax safe without escaping.
    value=$(cat "$target")
    [ "${#value}" -eq 64 ] || fail 'existing secret is not the expected64-character hex format'
    case "$value" in *[!0-9a-f]*) fail 'existing secret is not lowercase hexadecimal' ;; esac
done
expected="redis://:$(cat "$SECRET_DIR/redis_password")@redis:6379/0"
if [ -e "$SECRET_DIR/redis_url" ]; then
    [ "$(cat "$SECRET_DIR/redis_url")" = "$expected" ] || fail 'redis_url and redis_password disagree; repair references explicitly, do not rotate a running DB implicitly'
else
    (set -C; printf '%s\n' "$expected" > "$SECRET_DIR/redis_url") || fail 'could not create redis_url without overwriting'
fi
chmod 600 "$SECRET_DIR/redis_url"
# File secrets are bind mounts: capless container root cannot bypass host0600.
# Derive the runtime IDs from the actual secret owner, not an assumed root UID.
owners=$(stat -c '%u %g' "$SECRET_DIR/redis_url" 2>/dev/null || stat -f '%u %g' "$SECRET_DIR/redis_url") || fail 'cannot determine secret ownership'
runtime_uid=${owners%% *}
runtime_gid=${owners#* }
for name in api_internal_token realtime_internal_token; do
    other=$(stat -c '%u %g' "$SECRET_DIR/$name" 2>/dev/null || stat -f '%u %g' "$SECRET_DIR/$name") || fail 'cannot determine secret ownership'
    [ "$other" = "$owners" ] || fail 'BA secret files must share one UID/GID owner'
done
if [ ! -e "$ROOT/.env" ]; then
    (set -C
        while IFS= read -r line || [ -n "$line" ]; do
            case "$line" in
                HINE_RUNTIME_UID=*) printf 'HINE_RUNTIME_UID=%s\n' "$runtime_uid" ;;
                HINE_RUNTIME_GID=*) printf 'HINE_RUNTIME_GID=%s\n' "$runtime_gid" ;;
                *) printf '%s\n' "$line" ;;
            esac
        done < "$ROOT/.env.example" > "$ROOT/.env"
    ) || fail 'could not create .env without overwriting'
fi
chmod 600 "$ROOT/.env"
printf '%s\n' 'Development credentials ready (owner-only files); existing values preserved. No service was started.'
