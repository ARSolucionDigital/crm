#!/bin/bash
# =============================================================================
# Twenty CRM — Stop ngrok Tunnel
# =============================================================================
# Kills ngrok, restores SERVER_URL to localhost, and restarts containers.
# Usage: bash scripts/tunnel-stop.sh
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$REPO_ROOT/packages/twenty-docker/.env"
PID_FILE="$REPO_ROOT/.ngrok.pid"

info()  { echo "=> $*"; }
ok()    { echo "   done: $*"; }
fail()  { echo "   FAIL: $*"; exit 1; }

# --------------- kill ngrok ---------------
if [ -f "$PID_FILE" ]; then
  NGROK_PID=$(cat "$PID_FILE" 2>/dev/null || true)
  if [ -n "$NGROK_PID" ] && kill -0 "$NGROK_PID" 2>/dev/null; then
    info "Stopping ngrok (PID $NGROK_PID)..."
    kill "$NGROK_PID" 2>/dev/null || true
    sleep 1
  fi
  rm -f "$PID_FILE"
  ok "ngrok stopped"
else
  info "No ngrok PID file found, checking for running process..."
  EXISTING=$(lsof -ti:4040 2>/dev/null | xargs -I{} ps -p {} -o pid=,command= 2>/dev/null | grep "ngrok" | awk '{print $1}' || true)
  if [ -n "$EXISTING" ]; then
    kill $EXISTING 2>/dev/null || true
    sleep 1
    ok "ngrok process killed"
  else
    ok "No ngrok process found"
  fi
fi

# --------------- restore SERVER_URL ---------------
if [ ! -f "$ENV_FILE" ]; then
  fail ".env not found at $ENV_FILE"
fi

info "Restoring SERVER_URL to localhost..."
if grep -q "^SERVER_URL=" "$ENV_FILE"; then
  sed -i.bak-tmp "s|^SERVER_URL=.*|SERVER_URL=http://localhost:3000|" "$ENV_FILE"
  rm -f "${ENV_FILE}.bak-tmp"
  ok "SERVER_URL restored to http://localhost:3000"
else
  echo "SERVER_URL=http://localhost:3000" >> "$ENV_FILE"
  ok "SERVER_URL added as http://localhost:3000"
fi

# --------------- recreate server + worker with restored env ---------------
info "Recreating server and worker containers with localhost URL..."
docker compose -f "$REPO_ROOT/packages/twenty-docker/docker-compose.yml" up -d --force-recreate server worker

ok "Tunnel closed. Twenty is back on localhost:3000"
