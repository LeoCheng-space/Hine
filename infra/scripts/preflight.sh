#!/bin/sh
set -eu
umask 077
. "$(dirname -- "$0")/common.sh"
[ "$#" -eq 1 ] || fail 'usage: preflight.sh --local | --public'
case "$1" in --local|--public) ;; *) fail 'usage: preflight.sh --local | --public' ;; esac
kind=$1
configure_stack production
# Launch artifacts must exist for preflight/up/start, not for stop/data recovery.
[ -f "$WEB_ROOT/index.html" ] && [ -s "$WEB_ROOT/index.html" ] || fail 'WEB_ROOT must contain the real frontend index.html build'
[ -f "$ROOT/.env" ] || fail 'provision the protected .env before preflight'
[ -f "$ROOT/backend/realtime/Dockerfile" ] || fail 'actual BA Dockerfile is missing'
[ -f "$ROOT/backend/api/Dockerfile" ] || fail 'actual BB Dockerfile is missing'
command -v python3 >/dev/null 2>&1 || fail 'Python3 is required for configuration and TLS probes'
require_docker
resolved=$(mktemp)
trap 'rm -f "$resolved"' EXIT HUP INT TERM
compose config --format json > "$resolved" || fail 'production Compose configuration failed'
python3 "$ROOT/infra/scripts/check-compose.py" "$resolved" || fail 'production topology or artifacts are invalid'
api_image=$(python3 -c 'import json,sys; api=json.load(open(sys.argv[1]))["services"]["api"]; print(api.get("image", "") if not api.get("build") else "")' "$resolved")
if [ -n "$api_image" ]; then
    docker image inspect "$api_image" >/dev/null 2>&1 || fail 'approved api image is not available locally; load/pull the real release artifact explicitly'
fi
# Actual shipped proxy parser validates this configuration; no VM/cloud changes.
compose run --rm --no-deps caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile || fail 'Caddy configuration validation failed'
if [ "$kind" = --local ]; then
    printf '%s\n' 'PASS local prerequisites/configuration only. No deployment, DNS, TLS issuance, API readiness, WSS, or product E2E result is implied.'
    exit 0
fi
[ -n "${HINE_EXPECTED_IP:-}" ] || fail 'HINE_EXPECTED_IP is required for a real public DNS check'
# Ready must be observed from inside the private network, not a public health URL.
compose exec -T realtime python -c '
import json, urllib.request
for name, url in (("api", "http://api:8080/health/ready"), ("realtime", "http://127.0.0.1:8081/health/ready")):
    with urllib.request.urlopen(url, timeout=5) as response:
        value = json.load(response)
        if response.status != 200 or value.get("status") != "ok" or value.get("service") != name:
            raise SystemExit("private readiness failed")
print("PASS actual private API and realtime readiness")
' || fail 'real internal services are unavailable or unready'
python3 "$ROOT/infra/scripts/probe-public.py" || fail 'public deployment acceptance failed'
printf '%s\n' 'PASS deployment transport/isolation preflight. Authenticated product smoke/load/browser acceptance remains separate.'
