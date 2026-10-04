#!/usr/bin/env bash
# Pipeline-owned prerequisite networks. Never delete or recreate existing networks.
set -euo pipefail
set +x
case "${1:-}" in
  sit) networks=(arenaops-sit) ;;
  prod) networks=(arenaops-prod) ;;
  edge) networks=(arenaops-sit arenaops-prod) ;;
  dev) networks=(arenaops-dev) ;;
  *) echo 'Usage: ensure-networks.sh sit|prod|edge|dev' >&2; exit 1 ;;
esac
for network in "${networks[@]}"; do
  if ! docker network inspect "$network" >/dev/null 2>&1; then
    # A concurrent bootstrap may create it first. Only tolerate creation failure
    # if the subsequent inspection proves that the network now exists.
    if ! docker network create --driver bridge "$network" >/dev/null; then
      docker network inspect "$network" >/dev/null
    fi
  fi
  docker network inspect "$network" >/dev/null
  echo "Docker network ready: $network"
done
