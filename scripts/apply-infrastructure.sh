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
compose config --quiet
# Validate proxy before making infrastructure changes. No ports are published by run.
if [[ "$ARENA_ENV" != dev ]]; then
  compose run --rm --no-deps caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null
fi
if [[ "$ARENA_ENV" == dev ]]; then
  docker network inspect "$ARENAOPS_NETWORK" >/dev/null 2>&1 || docker network create "$ARENAOPS_NETWORK" >/dev/null
else
  docker network inspect "$ARENAOPS_NETWORK" >/dev/null
fi
compose up -d --wait --wait-timeout 360 postgres keycloak
"$root_dir/scripts/bootstrap-keycloak.sh" "$root_dir/keycloak/realm/arena-realm.$ARENA_ENV.template.json"
if [[ "$ARENA_ENV" != dev ]]; then
  compose --profile edge up -d --wait --wait-timeout 120 caddy
  install -d -m 0750 "$root_dir/state"
  date -u +'%Y-%m-%dT%H:%M:%SZ' > "$root_dir/state/$ARENA_ENV-infrastructure-applied"
fi
echo "$ARENA_ENV infrastructure applied"
