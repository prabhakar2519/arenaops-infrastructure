#!/usr/bin/env bash
set -euo pipefail
set +x
umask 077
# shellcheck source=scripts/common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
load_environment
cd "$root_dir"
if [[ "$ARENA_ENV" != dev && "$root_dir" != "$ARENAOPS_TARGET" ]]; then
  echo 'Unexpected deployment directory' >&2
  exit 1
fi
# Runs from the final target after the deployment copy, before Keycloak starts.
"$root_dir/scripts/normalize-theme-permissions.sh"
# External networks must exist before any Compose configuration/run/up command.
"$root_dir/scripts/ensure-networks.sh" "$ARENA_ENV"
if [[ "$ARENA_ENV" != dev ]]; then
  "$root_dir/scripts/ensure-networks.sh" edge
fi
compose config --quiet
# Validate proxy before making infrastructure changes. No ports are published by run.
if [[ "$ARENA_ENV" != dev ]]; then
  docker compose --env-file /dev/null -p arenaops-edge -f "$root_dir/docker/docker-compose.edge.yaml" run --rm --no-deps caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null
fi
compose up -d --wait --wait-timeout 360 postgres
# Recreate only Keycloak so cached fallback themes are discarded on redeployment.
compose up -d --no-deps --force-recreate --wait --wait-timeout 360 keycloak
# Compose exec uses the image's runtime user (UID 1000), never root overrides.
compose exec -T keycloak sh -ec '
  test -r /opt/keycloak/themes/arena-login/login/theme.properties
  test -r /opt/keycloak/themes/arena-login/login/login.ftl
'
"$root_dir/scripts/bootstrap-keycloak.sh" "$root_dir/keycloak/realm/arena-realm.$ARENA_ENV.template.json"
if [[ "$ARENA_ENV" != dev ]]; then
  "$root_dir/scripts/apply-edge.sh"
  install -d -m 0750 "$root_dir/state"
  date -u +'%Y-%m-%dT%H:%M:%SZ' > "$root_dir/state/$ARENA_ENV-infrastructure-applied"
fi
echo "$ARENA_ENV infrastructure applied"
