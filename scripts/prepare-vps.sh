#!/usr/bin/env bash
set -euo pipefail
set +x
umask 077
environment="${1:?Usage: prepare-vps.sh sit|prod}"
case "$environment" in sit|prod) ;; *) echo 'Only sit or prod is supported' >&2; exit 1 ;; esac
require_tool() {
  command -v "$1" >/dev/null 2>&1 || { echo "$1 is required on the VPS" >&2; exit 1; }
}
for executable in docker python3 curl jq tar; do require_tool "$executable"; done
docker compose version >/dev/null || { echo 'Docker Compose is required' >&2; exit 1; }
deployment_user="${SUDO_USER:-$(id -un)}"
deployment_group="$(id -gn "$deployment_user")"
install -d -o "$deployment_user" -g "$deployment_group" -m 0750 \
  /opt/arenaops "/opt/arenaops/$environment" "/opt/arenaops/$environment/state"
docker network inspect "arenaops-$environment" >/dev/null 2>&1 || \
  docker network create "arenaops-$environment" >/dev/null
echo "$environment directories and network are ready"
