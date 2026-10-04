#!/bin/sh
set -eu
umask 077
. "$(dirname -- "$0")/common.sh"
mode=development
if [ "${1:-}" = --production ]; then mode=production; shift; fi
[ "$#" -eq 1 ] || fail 'usage: backup-postgres.sh [--production] NEW_ARCHIVE_PATH'
output=$1
case "$output" in /*) ;; *) output="$PWD/$output" ;; esac
[ ! -e "$output" ] && [ ! -L "$output" ] || fail 'backup output already exists; never overwrite an archive'
[ -d "$(dirname -- "$output")" ] || fail 'backup output directory does not exist'
configure_stack "$mode"
require_docker
[ -f "$ROOT/.env" ] || fail 'run init-dev.sh or provision the protected .env first'
temporary=$(mktemp "$output.tmp.XXXXXX")
trap 'rm -f "$temporary"' EXIT HUP INT TERM
compose exec -T postgres sh -ec '
    export PGPASSWORD="$(cat /run/secrets/postgres_password)"
    exec pg_dump --host=127.0.0.1 --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --format=custom --no-owner --no-acl
' > "$temporary" || fail 'pg_dump failed; no archive was published'
[ -s "$temporary" ] || fail 'pg_dump produced an empty archive'
compose exec -T postgres pg_restore --list < "$temporary" >/dev/null || fail 'archive validation failed; no archive was published'
# Same-directory hard link provides an atomic no-clobber publish even if another
# process creates the target after the initial existence check.
ln "$temporary" "$output" || fail 'cannot publish archive without overwriting; temporary archive removed'
printf 'Backup archived: %s (protect and test-restore this file; it contains private data)\n' "$output"
