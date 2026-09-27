#!/usr/bin/env bash
#
# One-time setup on the shared app server, run as the deploy user (no sudo):
#   bash <(curl -fsSL https://raw.githubusercontent.com/selamet/pars-studio-api/main/scripts/setup-server.sh)
# Clones the repo under /opt/apps, seeds .env and installs the maintenance cron.
# The host must already have Docker and a system Caddy (see deploy/Caddyfile.snippet).
set -euo pipefail

APP_DIR=${APP_DIR:-/opt/apps/pars-studio-api}
REPO=https://github.com/selamet/pars-studio-api.git

command -v docker >/dev/null || { echo "Docker is required." >&2; exit 1; }

if [[ ! -d "$APP_DIR/.git" ]]; then
  echo ">>> Cloning into $APP_DIR"
  git clone --quiet "$REPO" "$APP_DIR"
fi
if [[ ! -f "$APP_DIR/.env" ]]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  chmod 600 "$APP_DIR/.env"
  echo "!!! Fill in $APP_DIR/.env before running scripts/deploy.sh"
fi

echo ">>> Maintenance cron"
APP_DIR="$APP_DIR" bash "$APP_DIR/scripts/install-cron.sh"

cat <<MSG
>>> Done. Remaining steps:
  1. Edit $APP_DIR/.env (see docs/deploy.md for production values).
  2. $APP_DIR/scripts/deploy.sh
  3. As root: append deploy/Caddyfile.snippet to /etc/caddy/Caddyfile and reload caddy.
MSG
