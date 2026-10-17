#!/bin/sh
# Creates ROOT/.env once from .env.example with the actual runtime secret owner IDs; never rewrites it.
set -eu
umask 077
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
fail() { printf 'init-env: %s\n' "$*" >&2; exit 1; }
[ "$#" -eq 2 ] || fail 'usage: sh infra/scripts/init-env.sh RUNTIME_UID RUNTIME_GID'
for value in "$1" "$2"; do
    case "$value" in ""|*[!0-9]*) fail 'runtime IDs must be numeric' ;; esac
done
[ ! -L "$ROOT/.env" ] || fail '.env must not be a symlink'
if [ ! -e "$ROOT/.env" ]; then
    (set -C
        while IFS= read -r line || [ -n "$line" ]; do
            case "$line" in
                HINE_RUNTIME_UID=*) printf 'HINE_RUNTIME_UID=%s\n' "$1" ;;
                HINE_RUNTIME_GID=*) printf 'HINE_RUNTIME_GID=%s\n' "$2" ;;
                *) printf '%s\n' "$line" ;;
            esac
        done < "$ROOT/.env.example" > "$ROOT/.env"
    ) || fail 'could not create .env without overwriting'
fi
[ -f "$ROOT/.env" ] || fail '.env must be a regular file'
chmod 600 "$ROOT/.env"
