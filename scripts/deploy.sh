#!/usr/bin/env bash
#
# Pull the latest ref, rebuild the image and restart the stack. Run on the
# server from anywhere:  /opt/apps/pars-studio-api/scripts/deploy.sh [git-ref]
set -euo pipefail

APP_DIR=${APP_DIR:-/opt/apps/pars-studio-api}
REF=${1:-main}
cd "$APP_DIR"
WEB_PORT=$(grep -E '^WEB_PORT=' .env | cut -d= -f2 || true)
WEB_PORT=${WEB_PORT:-8108}

echo ">>> Fetching $REF"
git fetch --quiet origin
git checkout --quiet "$REF"
git pull --quiet --ff-only origin "$REF" 2>/dev/null || true

echo ">>> Building image"
docker compose build --pull web

echo ">>> Starting (migrations run in the web entrypoint)"
docker compose up -d --remove-orphans

echo ">>> Waiting for health on 127.0.0.1:$WEB_PORT"
for _ in $(seq 1 45); do
  if curl -fsS "http://127.0.0.1:$WEB_PORT/healthz" >/dev/null 2>&1; then
    echo ">>> Healthy"
    docker image prune -f >/dev/null
    exit 0
  fi
  sleep 2
done
echo "!!! web did not become healthy; recent logs:" >&2
docker compose logs --tail=50 web >&2
exit 1
