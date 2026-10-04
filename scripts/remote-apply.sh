#!/usr/bin/env bash
set -euo pipefail
set +x
umask 077
environment="${1:?Environment required}"
case "$environment" in sit|prod) ;; *) exit 1 ;; esac
[[ -d /dev/shm && -w /dev/shm ]] || { echo '/dev/shm is required' >&2; exit 1; }
runtime_dir="$(mktemp -d /dev/shm/arenaops-infra.XXXXXX)"
trap 'rm -rf "$runtime_dir"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP
export ARENAOPS_INFRA_ENV_FILE="$runtime_dir/runtime.env"
cat > "$ARENAOPS_INFRA_ENV_FILE"
chmod 600 "$ARENAOPS_INFRA_ENV_FILE"
# shellcheck source=scripts/common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
load_environment
[[ "$ARENA_ENV" == "$environment" && "$root_dir" == "$ARENAOPS_TARGET" ]] || { echo 'Deployment environment mismatch' >&2; exit 1; }
exec_script="$root_dir/scripts/apply-infrastructure.sh"
"$exec_script"
