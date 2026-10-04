#!/usr/bin/env bash
set -euo pipefail
set +x
root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root_dir"
for script in scripts/*.sh; do bash -n "$script"; done
jq empty keycloak/realm/*.json
python3 -m unittest discover -s tests -v
