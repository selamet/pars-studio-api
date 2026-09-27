#!/usr/bin/env bash
# Installs deploy/crontab into the current user's crontab (idempotent, no sudo needed).
set -euo pipefail
APP_DIR=${APP_DIR:-/opt/apps/pars-studio-api}
MARK="# pars-studio-api"
{ crontab -l 2>/dev/null | grep -v "$MARK" | grep -v "pars-studio-api" || true; \
  sed "s|^\([^#]\)|\1|" "$APP_DIR/deploy/crontab" | grep -v '^#' | sed "s|\$| $MARK|"; } | crontab -
echo "Installed:"; crontab -l | grep "$MARK"
