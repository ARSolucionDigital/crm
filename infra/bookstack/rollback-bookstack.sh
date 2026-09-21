#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
deploy_dir="${DEPLOY_DIR:-/opt/twenty-crm}"
compose_file="${COMPOSE_FILE:-$script_dir/bookstack.compose.yml}"
env_file="${ENV_FILE:-$deploy_dir/.env.bookstack}"
state_file="$deploy_dir/.bookstack-deploy-state"
[[ -f "$state_file" && -f "$env_file" ]] || { echo "BookStack state or env file is missing" >&2; exit 1; }
previous_bookstack_image="$(sed -n 's/^previous_bookstack_image=//p' "$state_file" | head -1)"
previous_mariadb_image="$(sed -n 's/^previous_mariadb_image=//p' "$state_file" | head -1)"
current_bookstack_image="$(sed -n 's/^active_bookstack_image=//p' "$state_file" | head -1)"
current_mariadb_image="$(sed -n 's/^active_mariadb_image=//p' "$state_file" | head -1)"
[[ -n "$previous_bookstack_image" && -n "$previous_mariadb_image" ]] || { echo "No previous BookStack images are recorded" >&2; exit 1; }

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

set_env_value BOOKSTACK_IMAGE "$previous_bookstack_image"
set_env_value MARIADB_IMAGE "$previous_mariadb_image"
compose=(docker compose --env-file "$env_file" -f "$compose_file")
"${compose[@]}" pull bookstack bookstack-db
"${compose[@]}" up -d --remove-orphans bookstack bookstack-db
app_url="$(sed -n 's/^APP_URL=//p' "$env_file" | head -1)"
[[ -n "$app_url" ]] || { echo "APP_URL is required in $env_file" >&2; exit 1; }
curl --fail --silent --max-time 30 "$app_url" >/dev/null
printf 'previous_bookstack_image=%s\nprevious_mariadb_image=%s\nactive_bookstack_image=%s\nactive_mariadb_image=%s\n' \
  "$current_bookstack_image" "$current_mariadb_image" "$previous_bookstack_image" "$previous_mariadb_image" > "$state_file"
echo "BookStack rolled back to the previous approved images"
