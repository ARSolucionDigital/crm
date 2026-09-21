#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
deploy_dir="${DEPLOY_DIR:-/opt/twenty-crm}"
compose_file="${COMPOSE_FILE:-$script_dir/bookstack.compose.yml}"
env_file="${ENV_FILE:-$deploy_dir/.env.bookstack}"
backup_dir="${BACKUP_DIR:-$deploy_dir/backups/bookstack}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
[[ -f "$compose_file" && -f "$env_file" ]] || { echo "BookStack managed files are missing" >&2; exit 1; }
env_value() {
  sed -n "s/^${1}=//p" "$env_file" | head -1
}
mkdir -p "$backup_dir"
compose=(docker compose --env-file "$env_file" -f "$compose_file")
db_user="$(env_value DB_USERNAME)"; db_user="${db_user:-bookstack}"
db_password="$(env_value DB_PASSWORD)"
db_database="$(env_value DB_DATABASE)"; db_database="${db_database:-bookstack}"
[[ -n "$db_password" ]] || { echo "DB_PASSWORD is required in $env_file" >&2; exit 1; }
"${compose[@]}" exec -T bookstack-db mariadb-dump -u"$db_user" -p"$db_password" "$db_database" | gzip > "$backup_dir/mariadb_${timestamp}.sql.gz"
volume="$("${compose[@]}" config --volumes | awk '/^bookstack-data$/{print; exit}')"
project="$("${compose[@]}" config --format json | sed -n 's/^[[:space:]]*"name": "\([^"]*\)",$/\1/p' | head -1)"
volume_name="${project}_${volume}"
[[ -n "$volume_name" ]] || { echo "Could not resolve Docker volume for $volume" >&2; exit 1; }
docker volume inspect "$volume_name" >/dev/null || { echo "Docker volume does not exist: $volume_name" >&2; exit 1; }
docker run --rm -v "${volume_name}:/source:ro" -v "$backup_dir:/backup" alpine:3.20 sh -c "tar czf /backup/config_${timestamp}.tar.gz -C /source ."
echo "BookStack backup created in $backup_dir"
