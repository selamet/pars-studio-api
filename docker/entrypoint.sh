#!/usr/bin/env sh
# Runs migrations before the web process starts; other commands run as-is.
set -e

if [ "$1" = "gunicorn" ]; then
  python manage.py migrate --noinput
fi

exec "$@"
