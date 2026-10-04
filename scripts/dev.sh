#!/usr/bin/env bash
set -euo pipefail
set +x
export ARENAOPS_INFRA_ENV_FILE="${ARENAOPS_INFRA_ENV_FILE:-$(cd "$(dirname "$0")/.." && pwd)/.env}"
# shellcheck source=scripts/common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
load_environment
[[ "$ARENA_ENV" == dev ]] || { echo 'dev.sh only accepts ARENA_ENV=dev' >&2; exit 1; }
case "${1:-}" in
  start) exec "$root_dir/scripts/apply-infrastructure.sh" ;;
  stop) compose down ;;
  reset) [[ "${2:-}" == DELETE_DEV_DATA ]] || { echo 'Destructive reset requires DELETE_DEV_DATA' >&2; exit 1; }; compose down --volumes ;;
  logs) compose logs -f ;;
  *) echo 'Usage: dev.sh start|stop|logs|reset DELETE_DEV_DATA' >&2; exit 1 ;;
esac
