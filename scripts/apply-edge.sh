#!/usr/bin/env bash
# Apply the single shared edge project under a VPS-wide lock; never start a second proxy.
set -euo pipefail
set +x
root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${CADDY_BIND_IP:?CADDY_BIND_IP is required}"
edge_dir=/opt/arenaops/edge
exec 9>"$edge_dir/apply.lock"
flock 9
for network in arenaops-sit arenaops-prod; do docker network inspect "$network" >/dev/null; done
compose_file="$root_dir/docker/docker-compose.edge.yaml"
docker compose --env-file /dev/null -p arenaops-edge -f "$compose_file" config --quiet
docker compose --env-file /dev/null -p arenaops-edge -f "$compose_file" run --rm --no-deps caddy \
  caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null
# Configuration is canonical, not tied to whichever environment applied last.
install -m 0644 "$root_dir/docker/Caddyfile" "$edge_dir/docker/Caddyfile"
install -m 0644 "$compose_file" "$edge_dir/docker/docker-compose.edge.yaml"
docker compose --env-file /dev/null -p arenaops-edge -f "$edge_dir/docker/docker-compose.edge.yaml" \
  up -d --wait --wait-timeout 120 caddy
# A mounted Caddyfile change does not necessarily recreate the container.
docker compose --env-file /dev/null -p arenaops-edge -f "$edge_dir/docker/docker-compose.edge.yaml" \
  exec -T caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
