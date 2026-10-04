#!/bin/sh
set -eu
umask 077
. "$(dirname -- "$0")/common.sh"
mode=development
if [ "${1:-}" = --production ]; then mode=production; shift; fi
[ "${1:-}" = --confirm-destructive ] || fail 'restore is destructive; usage: restore-postgres.sh [--production] --confirm-destructive ARCHIVE_PATH'
shift
[ "$#" -eq 1 ] || fail 'exactly one archive path is required'
archive=$1
[ -f "$archive" ] && [ -s "$archive" ] && [ ! -L "$archive" ] || fail 'archive must be an existing nonempty regular file, not a symlink'
configure_stack "$mode"
require_docker
[ -f "$ROOT/.env" ] || fail 'the protected .env is missing'
# Refuse live writers, rather than racing them or terminating their connections.
running=$(compose ps --status running --services) || fail 'cannot determine running services'
for service in $running; do
    case "$service" in api|realtime) fail 'stop api and realtime before restoring' ;; esac
done
compose exec -T postgres pg_restore --list < "$archive" >/dev/null || fail 'archive is not readable as a PostgreSQL custom archive'
compose exec -T postgres sh -ec '
    case "$POSTGRES_DB" in ""|postgres|template0|template1|*[!a-zA-Z0-9_]*) echo "unsafe restore database name" >&2; exit 1 ;; esac
    case "$POSTGRES_USER" in ""|*[!a-zA-Z0-9_]*) echo "unsafe restore username" >&2; exit 1 ;; esac
    export PGPASSWORD="$(cat /run/secrets/postgres_password)"
    # Connection must succeed against the already-existing exact target database.
    target=$(psql --host=127.0.0.1 --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" -XAt --set=ON_ERROR_STOP=1 --command="SELECT current_database()")
    [ "$target" = "$POSTGRES_DB" ] || { echo "restore target mismatch" >&2; exit 1; }
    connections=$(psql --host=127.0.0.1 --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" -XAt --set=ON_ERROR_STOP=1 --command="SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND pid <> pg_backend_pid() AND backend_type = '\''client backend'\''")
    [ "$connections" = 0 ] || { echo "restore target still has active clients" >&2; exit 1; }
    exec pg_restore --host=127.0.0.1 --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --clean --if-exists --no-owner --no-acl --exit-on-error --single-transaction
' < "$archive" || fail 'restore command failed; keep writers stopped and verify the target before retrying (SQL errors roll back, but a lost commit response can leave the outcome unknown)'
printf '%s\n' 'Restore committed to the configured existing database. Validate schema/data before restarting writers.'
