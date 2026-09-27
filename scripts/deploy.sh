#!/usr/bin/env bash
#
# Pull the latest main, rebuild the image and restart the stack. Run on the
# server from anywhere:  /opt/pars-studio-api/scripts/deploy.sh [git-ref]
set -euo pipefail

APP_DIR=${APP_DIR:-/opt/pars-studio-api}
REF=${1:-main}
cd "$APP_DIR"

echo ">>> Fetching $REF"
git fetch --quiet origin
git checkout --quiet "$REF"
git pull --quiet --ff-only origin "$REF" || true

echo ">>> Building image"
docker compose build --pull web

echo ">>> Starting (migrations run in the web entrypoint)"
docker compose up -d --remove-orphans

echo ">>> Waiting for health"
for _ in $(seq 1 30); do
  if docker compose exec -T web curl -fsS http://127.0.0.1:8000/healthz >/dev/null 2>&1; then
    echo ">>> Healthy"
    docker image prune -f >/dev/null
    exit 0
  fi
  sleep 2
done
echo "!!! web did not become healthy; recent logs:" >&2
docker compose logs --tail=50 web >&2
exit 1
