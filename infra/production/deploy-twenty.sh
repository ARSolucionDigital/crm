#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
deploy_dir="${DEPLOY_DIR:-/opt/twenty-crm}"
compose_file="${COMPOSE_FILE:-$script_dir/twenty.compose.yml}"
env_file="${ENV_FILE:-$deploy_dir/.env}"
image_tag="${1:-${IMAGE_TAG:-}}"

[[ "$image_tag" =~ ^[0-9a-f]{40}$ ]] || { echo "Usage: $0 <40-character Git SHA>" >&2; exit 2; }
[[ -f "$compose_file" && -f "$env_file" ]] || { echo "Managed Twenty files are missing" >&2; exit 1; }
command -v docker >/dev/null || { echo "docker is required" >&2; exit 1; }
env_value() {
  sed -n "s/^${1}=//p" "$env_file" | head -1
}

export IMAGE_TAG="$image_tag"
export IMAGE_REFERENCE="${IMAGE_REPOSITORY:?IMAGE_REPOSITORY must be exported by the environment}:$image_tag"
compose=(docker compose --env-file "$env_file" -f "$compose_file")
state_file="$deploy_dir/.twenty-deploy-state"
previous_reference=""
if [[ -f "$state_file" ]]; then
  previous_reference="$(sed -n 's/^active_reference=//p' "$state_file" | head -1)"
fi

"$script_dir/backup-twenty.sh"
"${compose[@]}" pull server worker
printf 'previous_reference=%s\nactive_reference=%s\n' "$previous_reference" "$IMAGE_REFERENCE" > "$state_file"
"${compose[@]}" up -d --remove-orphans server worker
"${compose[@]}" ps

twenty_port="$(env_value TWENTY_PORT)"; twenty_port="${twenty_port:-3000}"
for attempt in $(seq 1 30); do
  if curl --fail --silent --max-time 5 "http://127.0.0.1:${twenty_port}/healthz" >/dev/null; then
    echo "Twenty $image_tag is healthy"
    exit 0
  fi
  sleep 2
done

echo "Twenty did not become healthy; inspect logs and run rollback if needed" >&2
"${compose[@]}" logs --tail=80 server >&2
exit 1
