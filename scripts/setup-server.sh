#!/usr/bin/env bash
#
# First-boot setup for the API server (Ubuntu 24.04). Run once as root:
#   curl -fsSL https://raw.githubusercontent.com/selamet/pars-studio-api/main/scripts/setup-server.sh | sudo bash
# Idempotent: safe to re-run.
set -euo pipefail

APP_DIR=/opt/pars-studio-api
REPO=https://github.com/selamet/pars-studio-api.git
DEPLOY_USER=${DEPLOY_USER:-${SUDO_USER:-deploy}}

echo ">>> Packages, firewall, fail2ban, unattended upgrades"
apt-get update -qq
apt-get install -y -qq ca-certificates curl git ufw fail2ban unattended-upgrades
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
ufw allow 80/tcp comment 'HTTP (ACME + redirect)'
ufw allow 443/tcp comment 'HTTPS'
ufw allow 443/udp comment 'HTTP/3'
ufw --force enable
systemctl enable --now fail2ban
dpkg-reconfigure -f noninteractive unattended-upgrades

if ! command -v docker >/dev/null; then
  echo ">>> Docker"
  curl -fsSL https://get.docker.com | sh
fi
usermod -aG docker "$DEPLOY_USER" || true

echo ">>> Application checkout at $APP_DIR"
if [[ ! -d "$APP_DIR/.git" ]]; then
  git clone "$REPO" "$APP_DIR"
fi
chown -R "$DEPLOY_USER":"$DEPLOY_USER" "$APP_DIR"
if [[ ! -f "$APP_DIR/.env" ]]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  chmod 600 "$APP_DIR/.env"
  echo "!!! Fill in $APP_DIR/.env before running scripts/deploy.sh"
fi

echo ">>> Maintenance timers"
cp "$APP_DIR"/deploy/systemd/*.service "$APP_DIR"/deploy/systemd/*.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now pars-api-expire-orders.timer pars-api-prune-tasks.timer

echo ">>> Done. Next: edit $APP_DIR/.env, then run $APP_DIR/scripts/deploy.sh"
