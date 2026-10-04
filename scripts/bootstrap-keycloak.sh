#!/usr/bin/env bash
set -euo pipefail
set +x
umask 077
exec python3 "$(dirname "${BASH_SOURCE[0]}")/bootstrap-keycloak.py" "${1:?Realm template path is required}"
