#!/bin/bash
# =============================================================================
# Twenty CRM — Start ngrok Tunnel
# =============================================================================
# Launches ngrok, auto-configures SERVER_URL, and restarts containers.
# Usage: bash scripts/tunnel-start.sh
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$REPO_ROOT/packages/twenty-docker/.env"
PID_FILE="$REPO_ROOT/.ngrok.pid"

info()  { echo "=> $*"; }
ok()    { echo "   done: $*"; }
fail()  { echo "   FAIL: $*"; exit 1; }

# --------------- prerequisites ---------------
if ! command -v ngrok &>/dev/null; then
  fail "ngrok not installed. Get it at https://ngrok.com/download"
fi

if ! command -v jq &>/dev/null; then
  fail "jq not installed. Install it: brew install jq"
fi

if [ ! -f "$ENV_FILE" ]; then
  fail ".env not found at $ENV_FILE. Run 'make up' first."
fi

# --------------- check docker ---------------
info "Checking Twenty is running..."
if ! docker compose -f "$REPO_ROOT/packages/twenty-docker/docker-compose.yml" ps 2>/dev/null | grep -q "server.*Up"; then
  fail "Twenty server is not running. Run 'make up' first."
fi
ok "Twenty is running"

# --------------- kill existing ngrok on 3000 ---------------
if [ -f "$PID_FILE" ]; then
  OLD_PID=$(cat "$PID_FILE" 2>/dev/null || true)
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    info "Stopping existing ngrok (PID $OLD_PID)..."
    kill "$OLD_PID" 2>/dev/null || true
    sleep 1
  fi
  rm -f "$PID_FILE"
fi

# Also kill any ngrok process bound to port 3000
EXISTING=$(lsof -ti:4040 2>/dev/null | xargs -I{} ps -p {} -o pid=,command= 2>/dev/null | grep "ngrok http 3000" | awk '{print $1}' || true)
if [ -n "$EXISTING" ]; then
  info "Killing stale ngrok process..."
  kill $EXISTING 2>/dev/null || true
  sleep 1
fi

# --------------- launch ngrok ---------------
info "Starting ngrok tunnel to localhost:3000..."
nohup ngrok http 3000 --log=stdout > /dev/null 2>&1 &
NGROK_PID=$!
echo "$NGROK_PID" > "$PID_FILE"

# --------------- wait for tunnel URL ---------------
info "Waiting for ngrok tunnel..."
TUNNEL_URL=""
for i in $(seq 1 30); do
  TUNNEL_URL=$(curl -s http://localhost:4040/api/tunnels 2>/dev/null | jq -r '.tunnels[0].public_url' 2>/dev/null || true)
  if [ "$TUNNEL_URL" != "null" ] && [ -n "$TUNNEL_URL" ]; then
    break
  fi
  sleep 1
done

if [ -z "$TUNNEL_URL" ] || [ "$TUNNEL_URL" = "null" ]; then
  fail "ngrok did not register a tunnel within 30 seconds"
fi

ok "Tunnel URL: $TUNNEL_URL"

# --------------- update SERVER_URL in .env ---------------
info "Updating SERVER_URL in .env..."
cp "$ENV_FILE" "${ENV_FILE}.bak"

if grep -q "^SERVER_URL=" "$ENV_FILE"; then
  sed -i.bak-tmp "s|^SERVER_URL=.*|SERVER_URL=$TUNNEL_URL|" "$ENV_FILE"
  rm -f "${ENV_FILE}.bak-tmp"
else
  echo "SERVER_URL=$TUNNEL_URL" >> "$ENV_FILE"
fi

ok "SERVER_URL updated"

# --------------- recreate server + worker with new env ---------------
info "Recreating server and worker containers with new SERVER_URL..."
docker compose -f "$REPO_ROOT/packages/twenty-docker/docker-compose.yml" up -d --force-recreate server worker

# --------------- wait for healthy ---------------
info "Waiting for server to be healthy..."
for i in $(seq 1 30); do
  if docker compose -f "$REPO_ROOT/packages/twenty-docker/docker-compose.yml" ps 2>/dev/null | grep -q "server.*healthy"; then
    break
  fi
  sleep 2
done

# --------------- done ---------------
echo ""
echo "============================================"
echo "  Tunnel ready!"
echo "  URL: $TUNNEL_URL"
echo "============================================"
echo ""
echo "  Access from any device: $TUNNEL_URL"
echo "  Stop tunnel: make tunnel-stop"
echo ""
