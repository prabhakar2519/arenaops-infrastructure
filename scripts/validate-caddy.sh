#!/usr/bin/env bash
set -euo pipefail
root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for realm in arena-sit arena; do
  docker run --rm --network none -e ARENAOPS_DOMAIN=example.invalid -e KC_REALM="$realm" \
    -v "$root_dir/docker/Caddyfile:/etc/caddy/Caddyfile:ro" \
    caddy:2.8-alpine caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
  # Exercise the actual routing locally inside a disposable isolated container.
  # HTTP avoids issuing TLS certificates; no ports are published to the host.
  docker run --rm -i --network none --entrypoint sh \
    -e ARENAOPS_DOMAIN=http://127.0.0.1:8080 -e KC_REALM="$realm" \
    -v "$root_dir/docker/Caddyfile:/etc/caddy/Caddyfile:ro" caddy:2.8-alpine -s <<'TEST'
set -eu
caddy run --config /etc/caddy/Caddyfile --adapter caddyfile >/tmp/caddy.log 2>&1 &
pid=$!
trap 'kill "$pid" 2>/dev/null || true' EXIT
for attempt in 1 2 3 4 5; do
  if wget -q -O /dev/null http://127.0.0.1:2019/config/ 2>/dev/null; then break; fi
  sleep 1
done
check() {
  status="$(wget -S -O /dev/null "http://127.0.0.1:8080$1" 2>&1 | sed -n 's/.*HTTP\/1.1 \([0-9]*\).*/\1/p' | head -n 1)"
  if [ "$status" != "$2" ]; then echo "Unexpected status for $1: $status (expected $2)" >&2; exit 1; fi
}
for path in /auth /auth/admin /auth/admin/ /auth/admin/master/console/ /auth/realms/master /auth/realms/master/protocol/openid-connect/token /auth/realms/other/protocol/openid-connect/auth; do
  check "$path" 404
done
# Missing upstreams return 502, demonstrating these paths reach proxy handlers.
check "/auth/realms/$KC_REALM/.well-known/openid-configuration" 502
check /auth/resources/test/theme.css 502
check /api/test 502
check / 502
echo "Caddy route protection passed for $KC_REALM"
TEST
done
