#!/usr/bin/env bash
set -euo pipefail

base_url="${KEYCLOAK_BASE_URL:-http://127.0.0.1:9091/auth}"
realm_template="${1:-keycloak/realm/arena-realm.template.json}"
: "${KEYCLOAK_ADMIN_USER:?KEYCLOAK_ADMIN_USER is required}"
: "${KEYCLOAK_ADMIN_PASSWORD:?KEYCLOAK_ADMIN_PASSWORD is required}"
: "${KEYCLOAK_BFF_SECRET:?KEYCLOAK_BFF_SECRET is required}"
test -f "$realm_template"
command -v jq >/dev/null

temporary_realm="$(mktemp)"
trap 'rm -f "$temporary_realm"' EXIT
jq --arg secret "$KEYCLOAK_BFF_SECRET" '
  (.clients[] | select(.clientId == "arena-bff") | .secret) = $secret
' "$realm_template" > "$temporary_realm"

for attempt in $(seq 1 60); do
  curl -fsS "$base_url/realms/master/.well-known/openid-configuration" >/dev/null && break
  [[ "$attempt" -eq 60 ]] && { echo "Keycloak did not become ready" >&2; exit 1; }
  sleep 5
done

token="$(curl -fsS -X POST "$base_url/realms/master/protocol/openid-connect/token" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode client_id=admin-cli \
  --data-urlencode "username=$KEYCLOAK_ADMIN_USER" \
  --data-urlencode "password=$KEYCLOAK_ADMIN_PASSWORD" \
  --data-urlencode grant_type=password | jq -r .access_token)"
test -n "$token"
test "$token" != null

status="$(curl -sS -o /dev/null -w '%{http_code}' "$base_url/admin/realms/arena" -H "Authorization: Bearer $token")"
if [[ "$status" == 404 ]]; then
  curl -fsS -X POST "$base_url/admin/realms" \
    -H "Authorization: Bearer $token" -H 'Content-Type: application/json' \
    --data-binary @"$temporary_realm" >/dev/null
  echo "Created ArenaOps realm"
elif [[ "$status" == 200 ]]; then
  echo "ArenaOps realm already exists; bootstrap will not overwrite it"
else
  echo "Unexpected Keycloak realm lookup response: HTTP $status" >&2
  exit 1
fi

client_uuid="$(curl -fsS "$base_url/admin/realms/arena/clients?clientId=arena-bff" \
  -H "Authorization: Bearer $token" | jq -r '.[0].id')"
service_user_id="$(curl -fsS "$base_url/admin/realms/arena/clients/$client_uuid/service-account-user" \
  -H "Authorization: Bearer $token" | jq -r .id)"
realm_management_id="$(curl -fsS "$base_url/admin/realms/arena/clients?clientId=realm-management" \
  -H "Authorization: Bearer $token" | jq -r '.[0].id')"
roles="$(curl -fsS "$base_url/admin/realms/arena/clients/$realm_management_id/roles" \
  -H "Authorization: Bearer $token" | jq '[.[] | select(.name == "manage-users" or .name == "view-users" or .name == "view-realm")]')"
curl -fsS -X POST "$base_url/admin/realms/arena/users/$service_user_id/role-mappings/clients/$realm_management_id" \
  -H "Authorization: Bearer $token" -H 'Content-Type: application/json' --data "$roles" >/dev/null
echo "ArenaOps Keycloak service-account roles are configured"
