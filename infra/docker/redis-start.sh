#!/bin/sh
set -eu
umask 077
password=$(cat /run/secrets/redis_password)
[ "${#password}" -eq 64 ] || { echo 'Redis secret must be64hex characters' >&2; exit 1; }
case "$password" in *[!0-9a-f]*) echo 'Redis secret must be lowercase hexadecimal' >&2; exit 1 ;; esac
# Use a private config file, not an argv secret exposed by docker inspect / ps.
config=/tmp/hine-redis.conf
printf '%s\n' 'bind 0.0.0.0' 'protected-mode yes' 'port 6379' \
    'dir /data' 'appendonly yes' 'appendfsync everysec' \
    "requirepass $password" > "$config"
chown redis:redis "$config"
chmod 600 "$config"
unset password
exec /usr/local/bin/docker-entrypoint.sh redis-server "$config"
