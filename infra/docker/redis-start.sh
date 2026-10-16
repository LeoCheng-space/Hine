#!/bin/sh
set -eu
umask 077
password=$(cat /run/secrets/redis_password)
[ "${#password}" -eq 64 ] || { echo 'Redis secret must be64hex characters' >&2; exit 1; }
case "$password" in *[!0-9a-f]*) echo 'Redis secret must be lowercase hexadecimal' >&2; exit 1 ;; esac
# Keep each bootstrap config in a fresh private runtime directory. /tmp is sticky
# and the config remains redis-owned there between container restarts.
config_dir=$(mktemp -d /run/hine-redis.XXXXXX)
config=$config_dir/redis.conf
printf '%s\n' 'bind 0.0.0.0' 'protected-mode yes' 'port 6379' \
    'dir /data' 'appendonly yes' 'appendfsync everysec' \
    "requirepass $password" > "$config"
chown redis:redis "$config" "$config_dir"
chmod 600 "$config"
unset password
exec /usr/local/bin/docker-entrypoint.sh redis-server "$config"
