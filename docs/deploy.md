# Deploying to the VPS

The API runs as two containers (`web`, `worker`) on the same Hetzner server as
`laboflush-stack`, attached to its Docker network so PostgreSQL is reachable as
`postgres:5432` and Caddy can proxy to `pars-api:8000`.

## One-time setup

1. **DNS**: `A api.studiospars.com → 46.62.206.65`.
2. **Caddy** (in `laboflush-stack`): publish `443`, add the site block

   ```
   api.studiospars.com {
       reverse_proxy pars-api:8000
   }
   ```

   and `ufw allow 443/tcp`. Redeploy the stack.
3. **Database**: `pars_studio` and role `pars_studio_app` already exist
   (`/opt/laboflush/scripts/new-app.sh pars_studio`). Read the password from
   `/opt/laboflush/secrets/apps/pars_studio.conn` and build the internal URL
   `postgres://pars_studio_app:<pass>@postgres:5432/pars_studio`.
   The `btree_gist` extension (phase 5) must be created once by a superuser.
4. **Checkout and env**:

   ```bash
   sudo mkdir -p /opt/pars-studio-api && sudo chown $USER /opt/pars-studio-api
   git clone https://github.com/selamet/pars-studio-api.git /opt/pars-studio-api
   cp /opt/pars-studio-api/.env.example /opt/pars-studio-api/.env   # then fill it in
   ```

   Production values: `DEBUG=false`, `ALLOWED_HOSTS=api.studiospars.com`,
   `FRONTEND_URL=https://studiospars.com`,
   `CORS_ALLOWED_ORIGINS=https://studiospars.com,https://www.studiospars.com`,
   `CSRF_TRUSTED_ORIGINS=https://studiospars.com,https://www.studiospars.com,https://api.studiospars.com`,
   `COOKIE_DOMAIN=.studiospars.com`, `EMAIL_URL=smtp+ssl://resend:<key>@smtp.resend.com:465`.

## Deploy / update

```bash
cd /opt/pars-studio-api
git pull --ff-only
docker compose build
docker compose up -d          # entrypoint runs migrations before gunicorn starts
docker compose logs -f web
curl -s https://api.studiospars.com/healthz
```

First deploy only: `docker compose exec web python manage.py createsuperuser`.

## Background worker

`worker` runs `manage.py db_worker` and processes emails and fulfilment tasks
stored in the database. Prune old results occasionally:
`docker compose exec web python manage.py prune_db_task_results --min-age-days 30`.
