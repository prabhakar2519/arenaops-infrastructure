#!/usr/bin/env bash
# Validate mounted theme readability without starting Keycloak or publishing ports.
set -euo pipefail
set +x
umask 077
root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fixture="$(mktemp -d)"
trap 'rm -rf "$fixture"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
mkdir -p "$fixture/scripts" "$fixture/keycloak"
cp "$root_dir/scripts/normalize-theme-permissions.sh" "$fixture/scripts/"
cp "$root_dir/keycloak/theme-assets.txt" "$fixture/keycloak/"
cp -a "$root_dir/keycloak/themes" "$fixture/keycloak/"
# Reproduce the deployment umask issue before applying the actual helper.
find "$fixture/keycloak/themes" -type d -exec chmod 700 {} \;
find "$fixture/keycloak/themes" -type f -exec chmod 600 {} \;
bash "$fixture/scripts/normalize-theme-permissions.sh"
# Use the image declared by the infrastructure Compose source, not a root override.
image="$(python3 - "$root_dir/docker/docker-compose.infra.yaml" <<'PY'
import re
import sys
from pathlib import Path
text = Path(sys.argv[1]).read_text()
match = re.search(r'^  keycloak:\n(?:(?!^  \S)[\s\S])*?^    image: (\S+)', text, re.MULTILINE)
if not match:
    raise SystemExit('Cannot find Keycloak image in infrastructure Compose')
print(match.group(1))
PY
)"
docker run --rm --network none --entrypoint sh \
  -v "$fixture/keycloak/themes:/opt/keycloak/themes:ro" "$image" -ec '
    test "$(id -u)" -ne 0
    id
    test -r /opt/keycloak/themes/arena-login/login/theme.properties
    test -r /opt/keycloak/themes/arena-login/login/login.ftl
    test -r /opt/keycloak/themes/arena-login/login/resources/css/arena-login-v3.css
    echo "Static theme assets readable by the Keycloak runtime user"
  '
