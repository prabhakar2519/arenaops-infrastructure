#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root_dir"
env_file="/opt/arenaops/config/infra.env"
test -f "$env_file"
set -a
# shellcheck disable=SC1090
source "$env_file"
set +a

docker compose --env-file "$env_file" -f docker/docker-compose.infra.yaml config --quiet
docker compose --env-file "$env_file" -f docker/docker-compose.infra.yaml up -d postgres keycloak caddy
./scripts/bootstrap-keycloak.sh keycloak/realm/arena-realm.template.json
touch /opt/arenaops/state/infrastructure-applied
