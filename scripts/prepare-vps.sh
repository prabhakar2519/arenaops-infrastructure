#!/usr/bin/env bash
set -euo pipefail

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required. Install Docker Engine from the official Docker repository before continuing." >&2
  exit 1
fi
docker compose version >/dev/null

deployment_user="${SUDO_USER:-$USER}"
install -d -o "$deployment_user" -g "$deployment_user" -m 0750 \
  /opt/arenaops/infra /opt/arenaops/app /opt/arenaops/config /opt/arenaops/state
docker network inspect arenaops >/dev/null 2>&1 || docker network create arenaops >/dev/null

echo "VPS directories and the arenaops Docker network are ready."
echo "Create /opt/arenaops/config/infra.env and app.env with mode 0600 before applying infrastructure."
