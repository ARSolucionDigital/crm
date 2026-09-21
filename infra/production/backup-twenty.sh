#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
deploy_dir="${DEPLOY_DIR:-/opt/twenty-crm}"
compose_file="${COMPOSE_FILE:-$script_dir/twenty.compose.yml}"
env_file="${ENV_FILE:-$deploy_dir/.env}"
backup_dir="${BACKUP_DIR:-$deploy_dir/backups/twenty}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"

[[ -f "$compose_file" ]] || { echo "Missing Compose file: $compose_file" >&2; exit 1; }
[[ -f "$env_file" ]] || { echo "Missing env file: $env_file" >&2; exit 1; }
env_value() {
  sed -n "s/^${1}=//p" "$env_file" | head -1
}
mkdir -p "$backup_dir"

compose=(docker compose --env-file "$env_file" -f "$compose_file")
pg_user="$(env_value PG_DATABASE_USER)"; pg_user="${pg_user:-postgres}"
pg_database="$(env_value PG_DATABASE_NAME)"; pg_database="${pg_database:-default}"
"${compose[@]}" exec -T db pg_dump -U "$pg_user" -d "$pg_database" | gzip > "$backup_dir/postgres_${timestamp}.sql.gz"

volume="$("${compose[@]}" config --volumes | awk '/^db-data$/{print; exit}')"
project="$("${compose[@]}" config --format json | sed -n 's/^[[:space:]]*"name": "\([^"]*\)",$/\1/p' | head -1)"
volume_name="${project}_${volume}"
[[ -n "$volume_name" ]] || { echo "Could not resolve Docker volume for $volume" >&2; exit 1; }
docker volume inspect "$volume_name" >/dev/null || { echo "Docker volume does not exist: $volume_name" >&2; exit 1; }
docker run --rm -v "${volume_name}:/source:ro" -v "$backup_dir:/backup" alpine:3.20 sh -c "tar czf /backup/db-volume_${timestamp}.tar.gz -C /source ."

echo "Twenty backup created in $backup_dir"
