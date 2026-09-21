#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
deploy_dir="${DEPLOY_DIR:-/opt/twenty-crm}"
compose_file="${COMPOSE_FILE:-$script_dir/twenty.compose.yml}"
env_file="${ENV_FILE:-$deploy_dir/.env}"
state_file="$deploy_dir/.twenty-deploy-state"
[[ -f "$state_file" ]] || { echo "No deployment state found" >&2; exit 1; }
previous_reference="$(sed -n 's/^previous_reference=//p' "$state_file" | head -1)"
[[ -n "$previous_reference" ]] || { echo "No previous image reference found" >&2; exit 1; }
env_value() {
  sed -n "s/^${1}=//p" "$env_file" | head -1
}

export IMAGE_REFERENCE="$previous_reference"
compose=(docker compose --env-file "$env_file" -f "$compose_file")
"${compose[@]}" pull server worker
"${compose[@]}" up -d --remove-orphans server worker
twenty_port="$(env_value TWENTY_PORT)"; twenty_port="${twenty_port:-3000}"
curl --fail --silent --max-time 30 "http://127.0.0.1:${twenty_port}/healthz" >/dev/null
echo "Twenty rolled back to $previous_reference"
