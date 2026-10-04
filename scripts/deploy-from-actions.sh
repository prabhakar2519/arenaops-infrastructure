#!/usr/bin/env bash
# SSH commands intentionally expand validated runner target paths locally.
# shellcheck disable=SC2029
set -euo pipefail
set +x
umask 077
case "$TARGET_ENVIRONMENT" in sit) export ARENA_ENV=sit ;; production) export ARENA_ENV=prod ;; *) exit 1 ;; esac
: "${VPS_HOST:?VPS_HOST is required}"
: "${VPS_USERNAME:?VPS_USERNAME is required}"
: "${VPS_SSH_KEY:?VPS_SSH_KEY is required}"
: "${VPS_SSH_HOST_KEY:?Pinned SSH host key is required}"
runtime_dir="$(mktemp -d /dev/shm/arenaops-runner.XXXXXX)"
trap 'rm -rf "$runtime_dir"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP
printf '%s\n' "$VPS_SSH_KEY" > "$runtime_dir/key"
printf '%s\n' "$VPS_SSH_HOST_KEY" > "$runtime_dir/known_hosts"
python3 scripts/write-runtime-env.py "$runtime_dir/runtime.env"
# Fail before connecting if configuration is incomplete. Export output is discarded.
python3 scripts/config.py "$runtime_dir/runtime.env" > /dev/null
ssh_options=(-i "$runtime_dir/key" -o BatchMode=yes -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$runtime_dir/known_hosts")
remote="$VPS_USERNAME@$VPS_HOST"
staging="/tmp/arenaops-$ARENA_ENV-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"
# Only repository configuration is written to disk; secrets travel over SSH stdin.
tar -czf - docker keycloak scripts | ssh "${ssh_options[@]}" "$remote" \
  "set -eu; umask 077; mkdir -p '$staging'; tar -xzf - -C '$staging'"
ssh "${ssh_options[@]}" "$remote" \
  "bash '$staging/scripts/prepare-vps.sh' '$ARENA_ENV'" || \
  ssh "${ssh_options[@]}" "$remote" "sudo -n bash '$staging/scripts/prepare-vps.sh' '$ARENA_ENV'"
ssh "${ssh_options[@]}" "$remote" \
  "set -eu; cp -a '$staging/docker' '$staging/keycloak' '$staging/scripts' '/opt/arenaops/$ARENA_ENV/'; rm -rf '$staging'"
ssh "${ssh_options[@]}" "$remote" \
  "bash '/opt/arenaops/$ARENA_ENV/scripts/remote-apply.sh' '$ARENA_ENV'" < "$runtime_dir/runtime.env"
