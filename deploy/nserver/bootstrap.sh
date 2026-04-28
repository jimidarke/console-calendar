#!/usr/bin/env bash
# Idempotent bootstrap for cal-quickadd on nserver.
#
# What this does:
#   1. Validates .env presence (deploy/nserver/.env)
#   2. docker compose up -d --build
#   3. Health-checks /health
#
# What this does NOT do:
#   - Run interactive Google OAuth. For first run, copy credentials.json into
#     deploy/nserver/config/, then either run setup_oauth.py locally and copy
#     the resulting token.json into config/, or after first start run
#     `docker exec -it cal-quickadd python /tmp/refresh_oauth.py` to mint.
#   - Configure the external reverse proxy / DNS (already wired up on nserver)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEPLOY_DIR="$REPO_ROOT/deploy/nserver"

cd "$DEPLOY_DIR"

if [[ ! -f .env ]]; then
  echo "ERROR: $DEPLOY_DIR/.env missing. Copy .env.example and fill in." >&2
  exit 1
fi

mkdir -p "$DEPLOY_DIR/config"
if [[ ! -f config/credentials.json ]]; then
  echo "WARNING: $DEPLOY_DIR/config/credentials.json missing." >&2
  echo "         Place your Google OAuth client credentials there before first run." >&2
fi

echo "==> Building and starting cal-quickadd container..."
docker compose -f docker-compose.yml up -d --build

echo "==> Waiting for /health..."
for i in {1..15}; do
  if curl -fsS --max-time 2 http://127.0.0.1:8419/health >/dev/null 2>&1; then
    echo "    cal-quickadd is healthy."
    exit 0
  fi
  sleep 1
done

echo "ERROR: cal-quickadd did not become healthy within 15s. Check 'docker logs cal-quickadd'." >&2
exit 1
