# Deploying the API

The API runs on its own Hetzner server behind Caddy. PostgreSQL and Redis are
provided by the separate `laboflush-stack` host and reached over TLS:

| Piece | Where |
| --- | --- |
| `api.studiospars.com` | This server (`91.98.233.170`): Caddy → gunicorn/Django + task worker (Docker Compose) |
| PostgreSQL | `database.selamet.dev:5432` via PgBouncer (transaction pooling, `sslmode=verify-full`) |
| Redis (optional, unused today) | `redis.selamet.dev:6379/6380`, TLS |
| Media | Cloudflare R2 (`R2_*` variables) |
| Frontend | Vercel (`studiospars.com`), talks to the API with a cookie on `.studiospars.com` |

## One-time setup

1. **DNS**: `A api → 91.98.233.170` (no proxy; Caddy obtains the certificate itself).
2. **Database**: on the laboflush host the `pars_studio` database and `pars_studio_app`
   role already exist. Read the connection string:

   ```bash
   ssh selamet@database.selamet.dev 'sudo cat /opt/laboflush/secrets/apps/pars_studio.conn'
   ```

   Make sure it ends with `?sslmode=verify-full`. The `btree_gist` extension
   (needed in phase 5) must be created once by a superuser:
   `CREATE EXTENSION IF NOT EXISTS btree_gist;` on `pars_studio`.
3. **Server**: fresh Ubuntu 24.04, then as root:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/selamet/pars-studio-api/main/scripts/setup-server.sh | sudo DEPLOY_USER=<your-user> bash
   ```

   This installs Docker, opens 22/80/443 in ufw, enables fail2ban and
   unattended upgrades, clones the repo to `/opt/pars-studio-api`, seeds
   `.env` from `.env.example` and installs the maintenance timers.
4. **Environment**: edit `/opt/pars-studio-api/.env`. Production values:

   | Variable | Value |
   | --- | --- |
   | `DEBUG` | `false` |
   | `SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
   | `ALLOWED_HOSTS` | `api.studiospars.com` |
   | `API_DOMAIN` / `ACME_EMAIL` | `api.studiospars.com` / a real inbox |
   | `DATABASE_URL` | the PgBouncer string from step 2 |
   | `DATABASE_POOLED` | `true` |
   | `FRONTEND_URL` | `https://studiospars.com` |
   | `CORS_ALLOWED_ORIGINS` | `https://studiospars.com,https://www.studiospars.com` |
   | `CSRF_TRUSTED_ORIGINS` | `https://studiospars.com,https://www.studiospars.com,https://api.studiospars.com` |
   | `COOKIE_DOMAIN` | `.studiospars.com` |
   | `EMAIL_URL` | `smtp+ssl://resend:<RESEND_API_KEY>@smtp.resend.com:465` |
   | `GOOGLE_CLIENT_ID/SECRET` | OAuth client with redirect URI `https://api.studiospars.com/accounts/google/login/callback/` |
   | `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` | live keys; webhook endpoint `https://api.studiospars.com/api/v1/stripe/webhook` |
   | `R2_*` | account id, token, the two bucket names, public bucket domain |

5. **First deploy**:

   ```bash
   /opt/pars-studio-api/scripts/deploy.sh
   docker compose -f /opt/pars-studio-api/compose.yaml exec web python manage.py createsuperuser
   curl -s https://api.studiospars.com/healthz     # {"status":"ok"}
   ```

6. **Vercel**: set `NEXT_PUBLIC_API_URL=https://api.studiospars.com` and
   `NEXT_PUBLIC_MEDIA_HOST=<R2 public domain>` on the frontend project and redeploy.

## Updating

```bash
/opt/pars-studio-api/scripts/deploy.sh          # main
/opt/pars-studio-api/scripts/deploy.sh v1.2.0   # or any ref
```

The script pulls, rebuilds, restarts (`web` runs `migrate` before gunicorn)
and waits for `/healthz`. Roll back by deploying the previous ref.

## Operations

- Logs: `docker compose logs -f web worker caddy`
- Django shell: `docker compose exec web python manage.py shell`
- Timers: `systemctl list-timers 'pars-api-*'` (expire pending orders every 10 min,
  prune task results nightly)
- The worker container delivers emails and runs fulfilment; if it is down,
  tasks queue up in the database and run when it returns.
