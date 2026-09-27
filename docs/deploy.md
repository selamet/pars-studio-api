# Deploying the API

The API runs on the shared Hetzner app server behind the host's system Caddy.
PostgreSQL and Redis are provided by the `laboflush-stack` host over TLS.

| Piece | Where |
| --- | --- |
| `api.studiospars.com` | App server `91.98.233.170`, `/opt/apps/pars-studio-api`, Docker Compose (`web` on `127.0.0.1:8108` + `worker`), proxied by `/etc/caddy/Caddyfile` |
| PostgreSQL | `database.selamet.dev:5432` via PgBouncer (transaction pooling, `sslmode=verify-full`, `DATABASE_POOLED=true`) |
| Redis (optional, unused today) | `redis.selamet.dev` |
| Media | Cloudflare R2 (`R2_*`); local `media` volume until configured |
| Frontend | Vercel (`studiospars.com`), `NEXT_PUBLIC_API_URL=https://api.studiospars.com` |

## One-time setup

1. **DNS**: `A api → 91.98.233.170` (done).
2. **Database**: `pars_studio` / `pars_studio_app` exist on the laboflush host and
   `btree_gist` is created. Connection string:
   `ssh selamet@database.selamet.dev 'sudo cat /opt/laboflush/secrets/apps/pars_studio.conn'`
   (make sure it carries `?sslmode=verify-full`).
3. **Checkout + cron** (as the deploy user, no sudo):

   ```bash
   bash <(curl -fsSL https://raw.githubusercontent.com/selamet/pars-studio-api/main/scripts/setup-server.sh)
   ```

4. **Environment**: `/opt/apps/pars-studio-api/.env` — production values:

   | Variable | Value |
   | --- | --- |
   | `DEBUG` | `false` |
   | `SECRET_KEY` | `python3 -c "import secrets; print(secrets.token_urlsafe(50))"` |
   | `ALLOWED_HOSTS` | `api.studiospars.com` |
   | `WEB_PORT` | `8108` |
   | `DATABASE_URL` / `DATABASE_POOLED` | PgBouncer string / `true` |
   | `FRONTEND_URL` | `https://studiospars.com` |
   | `CORS_ALLOWED_ORIGINS` | `https://studiospars.com,https://www.studiospars.com` |
   | `CSRF_TRUSTED_ORIGINS` | `https://studiospars.com,https://www.studiospars.com,https://api.studiospars.com` |
   | `COOKIE_DOMAIN` | `.studiospars.com` |
   | `EMAIL_URL` | `smtp+ssl://resend:<RESEND_API_KEY>@smtp.resend.com:465` |
   | `GOOGLE_CLIENT_ID/SECRET` | OAuth client, redirect URI `https://api.studiospars.com/accounts/google/login/callback/` (Google button appears only when set) |
   | `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` | keys; webhook endpoint `https://api.studiospars.com/api/v1/stripe/webhook` |
   | `R2_*` | account id, token, bucket names, public bucket domain |

5. **Deploy**: `/opt/apps/pars-studio-api/scripts/deploy.sh`, then
   `docker compose exec web python manage.py createsuperuser`.
6. **Caddy** (root): append `deploy/Caddyfile.snippet` to `/etc/caddy/Caddyfile`,
   `sudo caddy validate --config /etc/caddy/Caddyfile && sudo systemctl reload caddy`.
   Then `curl https://api.studiospars.com/healthz` → `{"status":"ok"}`.
7. **Vercel**: `NEXT_PUBLIC_API_URL=https://api.studiospars.com` (and `NEXT_PUBLIC_MEDIA_HOST`
   once R2 exists) on the frontend project; redeploy.

## Updating

```bash
/opt/apps/pars-studio-api/scripts/deploy.sh          # main
/opt/apps/pars-studio-api/scripts/deploy.sh v1.2.0   # any ref
```

Pulls, rebuilds, restarts (`web` runs `migrate` before gunicorn) and waits for
`/healthz`. Roll back by deploying the previous ref.

## Operations

- Logs: `docker compose logs -f web worker` (in the app dir)
- Django shell: `docker compose exec web python manage.py shell`
- Cron (`crontab -l`): pending orders and reservation holds expire every 10 min,
  task results are pruned nightly; output in `cron.log`.
- The worker delivers emails and runs fulfilment; if it is down, tasks queue in
  the database and run when it returns.
