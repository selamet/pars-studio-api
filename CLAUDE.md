# pars-studio-api

Django 6 REST backend for Pars Studio (beats, mastering services, studio
bookings, Stripe checkout). Frontend lives in `../pars-studio-v2` (Next.js).
Architecture spec: `docs/superpowers/specs/2026-09-27-commerce-platform-design.md`.

## Conventions
- Talk to the user in Turkish; code, comments, docs and commit messages in English.
- Task tracking: GitHub issues in this repo. Branch = `PSA-<issue>`; commit
  format `PSA-<issue>-<type>: <summary>` (`feat`, `fix`, `core`, `chore`,
  `refactor`, `test`, `docs`). PR body ends with `Closes #<issue>`.
- No AI attribution lines in commits or PRs.
- One phase per issue/branch/PR; merge before starting the next.

## Tooling
- `uv sync` installs; `uv run manage.py <cmd>`; `uv run pytest`; `uv run ruff check . && uv run ruff format .`
- Settings are env-driven (`django-environ`); copy `.env.example` to `.env`.
- Local Postgres: `docker compose -f compose.dev.yaml up -d db`.
- Tests run against Postgres (needed for the exclusion constraint and JSON fields).

## Layout
- `config/` settings, urls, asgi/wsgi
- `apps/<domain>/` one Django app per bounded context (see spec §4)
- API under `/api/v1/`, allauth headless under `/_allauth/browser/v1/`, schema at `/api/schema/`
