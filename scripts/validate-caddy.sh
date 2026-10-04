#!/usr/bin/env bash
set -euo pipefail
root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
docker run --rm --network none -v "$root_dir/docker/Caddyfile:/etc/caddy/Caddyfile:ro" \
  caddy:2.8-alpine caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
# Mock distinct SIT/PROD upstream addresses inside one disposable container.
# No published ports, external network, deployments or certificate requests.
docker run --rm -i --network none --entrypoint sh \
  --add-host sit-keycloak:127.0.0.2 --add-host sit-arena-login:127.0.0.2 --add-host sit-arena-ui:127.0.0.2 \
  --add-host prod-keycloak:127.0.0.3 --add-host prod-arena-login:127.0.0.3 --add-host prod-arena-ui:127.0.0.3 \
  -v "$root_dir/docker/Caddyfile:/etc/caddy/Caddyfile:ro" caddy:2.8-alpine -s <<'TEST'
set -eu
for environment in sit prod; do
  case "$environment" in sit) address=127.0.0.2 ;; prod) address=127.0.0.3 ;; esac
  for endpoint in keycloak:8080 login:7700 ui:80; do
    name="${endpoint%:*}"; port="${endpoint#*:}"
    (
      while true; do
        body="$environment-$name"
        printf 'HTTP/1.1 200 OK\r\nContent-Length: %s\r\nConnection: close\r\n\r\n%s' "${#body}" "$body" |
          nc -l -s "$address" -p "$port" >>"/tmp/$environment-$name.requests"
      done
    ) &
  done
done
sed -e 's/^sit.arenaops.in {/http:\/\/sit.arenaops.in:8081 {/' \
    -e 's/^arenaops.in {/http:\/\/arenaops.in:8081 {/' /etc/caddy/Caddyfile >/tmp/Caddyfile
caddy run --config /tmp/Caddyfile --adapter caddyfile >/tmp/caddy.log 2>&1 &
for attempt in 1 2 3 4 5; do
  if wget -q -O /dev/null http://127.0.0.1:2019/config/ 2>/dev/null; then break; fi
  sleep 1
done
check() {
  host="$1"; path="$2"; expected="$3"
  wget -S -O /tmp/body --header="Host: $host" "http://127.0.0.1:8081$path" >/tmp/response 2>&1 || true
  status="$(sed -n 's/.*HTTP\/1.1 \([0-9]*\).*/\1/p' /tmp/response | head -n 1)"
  if [ "$expected" = 404 ]; then
    [ "$status" = 404 ] || { cat /tmp/response; exit 1; }
  else
    [ "$status" = 200 ] && [ "$(cat /tmp/body)" = "$expected" ] || { cat /tmp/response; cat /tmp/body; exit 1; }
    grep -qi 'X-Content-Type-Options: nosniff' /tmp/response
  fi
}
for environment in sit prod; do
  case "$environment" in sit) host=sit.arenaops.in; realm=arena-sit; other=arena ;; prod) host=arenaops.in; realm=arena; other=arena-sit ;; esac
  check "$host" / "$environment-ui"
  check "$host" /api "$environment-login"
  check "$host" /api/ "$environment-login"
  check "$host" '/api/test?probe=1' "$environment-login"
  grep -q '^GET / HTTP/1.1' "/tmp/$environment-login.requests"
  grep -q '^GET /test?probe=1 HTTP/1.1' "/tmp/$environment-login.requests"
  if grep -q '^GET /api' "/tmp/$environment-login.requests"; then
    echo 'BFF received an unstripped API prefix' >&2; exit 1
  fi
  check "$host" /apiary "$environment-ui"
  check "$host" "/auth/realms/$realm" "$environment-keycloak"
  check "$host" "/auth/realms/$realm/.well-known/openid-configuration" "$environment-keycloak"
  check "$host" /auth/resources/test/theme.css "$environment-keycloak"
  for path in /auth /auth/ /auth/admin /auth/admin/realms /auth/realms/master /auth/realms/master/protocol/openid-connect/token "/auth/realms/$other" "/auth/realms/$other/protocol/openid-connect/auth" /auth/realms/other /auth/health /health /metrics /management; do
    check "$host" "$path" 404
  done
  grep -qi "Host: $host" "/tmp/$environment-keycloak.requests"
  grep -qi "X-Forwarded-Host: $host" "/tmp/$environment-keycloak.requests"
  grep -qi 'X-Forwarded-Proto: http' "/tmp/$environment-keycloak.requests"
done
echo 'Both hostnames: correct distinct upstreams, realm allowlists, private-path blocking, API prefix stripping, security and forwarded headers passed.'
TEST
