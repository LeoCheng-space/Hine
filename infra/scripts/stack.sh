#!/bin/sh
set -eu
. "$(dirname -- "$0")/common.sh"
[ "$#" -gt 0 ] || fail 'usage: stack.sh config|up|ps|logs|stop|start|down [Compose arguments]'
command=$1
shift
case "$command" in config|up|ps|logs|stop|start|down) ;; *) fail 'unsupported stack command' ;; esac
# Reject destructive/unknown down flags before any prerequisites or Docker call.
if [ "$command" = down ]; then validate_down_arguments "$@"; fi
configure_stack production
require_docker
# No production cutover from an unchecked provider or with published private ports.
case "$command" in
    up|start) sh "$ROOT/infra/scripts/preflight.sh" --local ;;
esac
compose "$command" "$@"
