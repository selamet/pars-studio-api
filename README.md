# pars-studio-api

Backend for [Pars Studio](https://studiospars.com): a Django 6 REST API that
sells beats (with license tiers), mastering/mixing services and studio time,
with Stripe Checkout payments and a Django admin for the studio team.

The public site is a separate Next.js app (`pars-studio-v2`) that talks to this
API with a session cookie.

## Stack

| Concern | Choice |
| --- | --- |
| Framework | Django 6, Django REST Framework, drf-spectacular |
| Auth | django-allauth (headless): email + password, Google |
| Admin | Django admin + Unfold |
| Payments | Stripe Checkout + webhooks (USD) |
| Files | Cloudflare R2 through django-storages |
| Background jobs | Django Tasks + django-tasks DB backend |
| Database | PostgreSQL 16 |
| Runtime | Docker Compose on a Hetzner VPS behind Caddy |

## Development

```bash
uv sync
cp .env.example .env            # fill in values
docker compose -f compose.dev.yaml up -d db
uv run manage.py migrate
uv run manage.py createsuperuser
uv run manage.py runserver      # http://localhost:8000
```

- Admin: http://localhost:8000/admin/
- OpenAPI schema: http://localhost:8000/api/schema/ (Swagger UI at `/api/docs/`)
- Tests: `uv run pytest`
- Lint/format: `uv run ruff check . && uv run ruff format .`

## Documentation

- Architecture and phase plan: `docs/superpowers/specs/2026-09-27-commerce-platform-design.md`
