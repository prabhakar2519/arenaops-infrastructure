#!/usr/bin/env bash
set -euo pipefail
set +x
root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
load_environment() {
  local exports
  exports="$(python3 "$root_dir/scripts/config.py" "${ARENAOPS_INFRA_ENV_FILE:?ARENAOPS_INFRA_ENV_FILE is required}")"
  eval "$exports"
}
compose() {
  # Values are already parsed/exported; an empty env file avoids ambient .env reads.
  local -a files=(-f "$root_dir/docker/docker-compose.infra.yaml")
  if [[ "$ARENA_ENV" == dev ]]; then files+=(-f "$root_dir/docker/docker-compose.dev.yaml"); fi
  docker compose --env-file /dev/null --project-name "$COMPOSE_PROJECT_NAME" \
    "${files[@]}" "$@"
}
