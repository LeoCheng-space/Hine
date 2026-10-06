#!/bin/sh
set -eu
. "$(dirname -- "$0")/common.sh"
[ "$#" -gt 0 ] || fail 'usage: stack.sh config|up|ps|logs|stop|start|down|migrate [Compose arguments]'
command=$1
shift
case "$command" in config|up|ps|logs|stop|start|down|migrate) ;; *) fail 'unsupported stack command' ;; esac
# Reject destructive/unknown down flags before any prerequisites or Docker call.
if [ "$command" = down ]; then validate_down_arguments "$@"; fi
if [ "$command" = migrate ]; then
    [ "$#" -eq 0 ] || fail 'migrate takes no arguments and only applies the API migrations'
fi
configure_stack production
require_docker
# No production cutover with absent release artifacts or published private ports.
case "$command" in
    up|start|migrate) sh "$ROOT/infra/scripts/preflight.sh" --local ;;
esac
if [ "$command" = migrate ]; then
    compose run --build --rm --no-deps api python -m hine_api migrate
else
    compose "$command" "$@"
fi
