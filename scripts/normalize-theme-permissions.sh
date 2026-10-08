#!/usr/bin/env bash
# Only public static theme assets are normalized; runtime/realm secrets stay private.
set -euo pipefail
set +x
umask 077
root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
theme_root="$root_dir/keycloak/themes"
[[ -d "$theme_root" && ! -L "$theme_root" ]] || { echo 'Static theme directory is missing or a symlink' >&2; exit 1; }
# Reject symlinks/special files rather than following them outside the static tree.
[[ -z "$(find "$theme_root" ! -type d ! -type f -print -quit)" ]] || {
  echo 'Static themes must contain only regular files and directories' >&2; exit 1;
}
# The deployment carries an explicit list of repository-owned public assets.
manifest="$root_dir/keycloak/theme-assets.txt"
[[ -s "$manifest" ]] || { echo 'Static theme asset manifest is missing' >&2; exit 1; }
while IFS= read -r file; do
  relative="${file#"$theme_root/"}"
  grep -Fxq -- "$relative" "$manifest" || { echo 'Unlisted file in static theme tree; refusing permission changes' >&2; exit 1; }
done < <(find "$theme_root" -type f -print)
while IFS= read -r asset; do
  [[ "$asset" != /* && "$asset" != *..* && -f "$theme_root/$asset" ]] || { echo 'Invalid or missing listed theme asset' >&2; exit 1; }
done < "$manifest"
for asset in arena-login/login/theme.properties arena-login/login/login.ftl; do
  [[ -f "$theme_root/$asset" ]] || { echo "Required theme asset is missing: $asset" >&2; exit 1; }
done
find "$theme_root" -type d -exec chmod 755 {} \;
find "$theme_root" -type f -exec chmod 644 {} \;
[[ -z "$(find "$theme_root" -type d ! -perm 0755 -print -quit)" ]] || { echo 'Theme directories are not accessible' >&2; exit 1; }
[[ -z "$(find "$theme_root" -type f ! -perm 0644 -print -quit)" ]] || { echo 'Theme files are not readable' >&2; exit 1; }
for asset in arena-login/login/theme.properties arena-login/login/login.ftl; do
  [[ -r "$theme_root/$asset" ]] || { echo "Required theme asset is unreadable: $asset" >&2; exit 1; }
done
echo 'Static Keycloak theme permissions verified: directories 755, files 644'
