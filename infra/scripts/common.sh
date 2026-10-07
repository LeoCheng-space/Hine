#!/bin/sh
# Sourced by operations scripts; no shell code is loaded from .env.
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
fail() { printf 'hine-ops: %s\n' "$*" >&2; exit 1; }
require_docker() {
    command -v docker >/dev/null 2>&1 || fail 'Docker CLI and Compose plugin are required'
    docker compose version >/dev/null 2>&1 || fail 'Docker Compose v2 plugin is required'
    docker info >/dev/null 2>&1 || fail 'Docker daemon is unavailable or access is denied'
}
configure_stack() {
    MODE=$1
    case "$MODE" in
        development) ;;
        production)
            [ -n "${WEB_ROOT:-}" ] || fail 'WEB_ROOT is required as the configured absolute release path (it need not exist for recovery)'
            case "$WEB_ROOT" in /*) ;; *) fail 'WEB_ROOT must be an absolute path' ;; esac
            [ "${HINE_ENV:-}" = production ] || fail 'production commands require HINE_ENV=production'
            [ -n "${COMPOSE_PROJECT_NAME:-}" ] && [ "$COMPOSE_PROJECT_NAME" != hine-dev ] || fail 'set a distinct stable production COMPOSE_PROJECT_NAME (not hine-dev)'
            [ -n "${HINE_SECRET_DIR:-}" ] || fail 'HINE_SECRET_DIR must name provisioned production secrets'
            case "$HINE_SECRET_DIR" in /*) ;; *) fail 'production HINE_SECRET_DIR must be absolute' ;; esac
            [ -n "${HINE_DOMAIN:-}" ] || fail 'HINE_DOMAIN is required'
            case "$HINE_DOMAIN" in *[!a-zA-Z0-9.-]*|.*|*.) fail 'HINE_DOMAIN must be a DNS hostname without scheme or port' ;; esac
            [ -n "${ACME_EMAIL:-}" ] || fail 'ACME_EMAIL is required'
            for name in postgres_password redis_password redis_url api_internal_token realtime_internal_token database_url jwt_signing_key; do
                [ -f "$HINE_SECRET_DIR/$name" ] && [ -s "$HINE_SECRET_DIR/$name" ] || fail "required production secret file missing: $name"
                [ ! -L "$HINE_SECRET_DIR/$name" ] || fail 'production secret files must not be symlinks'
            done
            if [ -n "${GCS_CREDENTIALS_FILE:-}" ]; then
                case "$GCS_CREDENTIALS_FILE" in /*) ;; *) fail 'GCS_CREDENTIALS_FILE must be absolute' ;; esac
                [ -f "$GCS_CREDENTIALS_FILE" ] && [ -s "$GCS_CREDENTIALS_FILE" ] || fail 'provision the actual GCS signing credential file'
                [ ! -L "$GCS_CREDENTIALS_FILE" ] || fail 'GCS signing credential must not be a symlink'
            fi
            ;;
        *) fail 'unknown stack mode' ;;
    esac
}
validate_down_arguments() {
    # A positive allowlist prevents aliases, short-option clusters and =values
    # from enabling volume deletion through Compose's option parser.
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --remove-orphans|caddy|api|realtime|postgres|redis) shift ;;
            -t|--timeout)
                [ "$#" -ge 2 ] || fail 'unsafe down argument: timeout requires a nonnegative integer'
                case "$2" in ""|*[!0-9]*) fail 'unsafe down argument: timeout requires a nonnegative integer' ;; esac
                shift 2
                ;;
            --timeout=*)
                timeout=${1#--timeout=}
                case "$timeout" in ""|*[!0-9]*) fail 'unsafe down argument: timeout requires a nonnegative integer' ;; esac
                shift
                ;;
            -t[0-9]*)
                timeout=${1#-t}
                case "$timeout" in *[!0-9]*) fail 'unsafe down argument: timeout requires a nonnegative integer' ;; esac
                shift
                ;;
            *) fail 'unsafe down argument: only service names, --remove-orphans and integer timeout options are permitted; volume deletion is forbidden' ;;
        esac
    done
}
compose() {
    if [ "$MODE" = production ]; then
        if [ -n "${GCS_CREDENTIALS_FILE:-}" ]; then
            set -- -f "$ROOT/infra/docker/compose.gcs.yml" "$@"
        fi
        docker compose --project-directory "$ROOT" --env-file "$ROOT/.env" \
            -f "$ROOT/docker-compose.yml" \
            -f "$ROOT/infra/docker/compose.production.yml" \
            --profile product --profile realtime --profile production "$@"
    else
        docker compose --project-directory "$ROOT" --env-file "$ROOT/.env" \
            -f "$ROOT/docker-compose.yml" "$@"
    fi
}
