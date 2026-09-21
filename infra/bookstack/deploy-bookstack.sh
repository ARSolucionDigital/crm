#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
deploy_dir="${DEPLOY_DIR:-/opt/twenty-crm}"
compose_file="${COMPOSE_FILE:-$script_dir/bookstack.compose.yml}"
env_file="${ENV_FILE:-$deploy_dir/.env.bookstack}"
[[ -f "$compose_file" && -f "$env_file" ]] || { echo "BookStack managed files are missing" >&2; exit 1; }
env_value() {
  sed -n "s/^${1}=//p" "$env_file" | head -1
}
set_env_value() {
  key="$1"
  value="$2"
  temporary_file="$(mktemp)"
  awk -v key="$key" -v value="$value" \
    'BEGIN { prefix = key "=" } $0 ~ ("^" prefix) { print prefix value; found=1; next } { print } END { if (!found) print prefix value }' \
    "$env_file" > "$temporary_file"
  chmod 600 "$temporary_file"
  mv "$temporary_file" "$env_file"
}
state_file="$deploy_dir/.bookstack-deploy-state"
previous_bookstack_image="$(sed -n 's/^active_bookstack_image=//p' "$state_file" 2>/dev/null | head -1)"
previous_mariadb_image="$(sed -n 's/^active_mariadb_image=//p' "$state_file" 2>/dev/null | head -1)"
bookstack_image="${BOOKSTACK_IMAGE:-$(env_value BOOKSTACK_IMAGE)}"
mariadb_image="${MARIADB_IMAGE:-$(env_value MARIADB_IMAGE)}"
[[ -n "$bookstack_image" && -n "$mariadb_image" ]] || { echo "Pinned BookStack and MariaDB images are required" >&2; exit 1; }
"$script_dir/backup-bookstack.sh"
compose=(docker compose --env-file "$env_file" -f "$compose_file")
"${compose[@]}" pull bookstack bookstack-db
printf 'previous_bookstack_image=%s\nprevious_mariadb_image=%s\nactive_bookstack_image=%s\nactive_mariadb_image=%s\n' \
  "$previous_bookstack_image" "$previous_mariadb_image" "$bookstack_image" "$mariadb_image" > "$state_file"
set_env_value BOOKSTACK_IMAGE "$bookstack_image"
set_env_value MARIADB_IMAGE "$mariadb_image"
"${compose[@]}" up -d --remove-orphans bookstack bookstack-db
app_url="$(env_value APP_URL)"
[[ -n "$app_url" ]] || { echo "APP_URL is required in $env_file" >&2; exit 1; }
curl --fail --silent --max-time 30 "$app_url" >/dev/null
echo "BookStack is healthy"
