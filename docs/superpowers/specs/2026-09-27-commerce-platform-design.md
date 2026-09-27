# Pars Studio Commerce Platform — Architecture Design

**Date:** 2026-09-27
**Status:** Approved (conversational), implementation split into five phases
**Repos:** `pars-studio-api` (this repo, Django), `pars-studio-v2` (Next.js frontend), `laboflush-stack` (VPS infra)

## 1. Goal

Turn the Pars Studio site (a landing page plus a free-form booking form) into a
store where customers create an account, add products to a cart and pay online.
Three product families are sold:

| Family | Nature | Fulfilment |
| --- | --- | --- |
| Beats | Digital goods with several license tiers per beat | Signed download links after payment |
| Mastering / Mixing | Services on customer-provided audio | Customer uploads source, studio uploads result, status workflow |
| Studio time | A dated time slot in a room | Reservation confirmed on payment |

The studio staff manage everything (products, licenses, orders, reservations,
customers) from the Django admin. No custom admin frontend is built.

Out of scope for now: subscriptions/packages, multi-currency, guest checkout
(may be added later), coupons.

## 2. Decisions

| Topic | Decision | Why |
| --- | --- | --- |
| Backend | Django 6.x, Django REST Framework, `drf-spectacular` | Batteries included: ORM, admin, auth, migrations |
| Frontend | Existing Next.js 14 app stays; talks to Django over HTTPS | The landing page (Three.js, GSAP) is already built and deployed on Vercel |
| Repo layout | Separate repos | Different deploy targets and toolchains; OpenAPI schema is the contract |
| Auth | `django-allauth` headless (browser client): email + password with verification, Google sign-in; HttpOnly session cookie on `.studiospars.com` | No token storage in the browser; CSRF handled by Django |
| Payments | Stripe Checkout (hosted page) + webhooks; currency USD | Zero card data on our side; Stripe account is a non-Turkish entity |
| Cart | Client-side (Next.js, persisted in localStorage); server validates at checkout | Fewer endpoints; the server is the source of truth for price and availability |
| Admin UI | Django admin themed with `django-unfold` | Full CRUD for free |
| Files | Cloudflare R2 via `django-storages` (S3 API); private bucket; presigned URLs | Free egress, S3 compatible |
| Background jobs | Django Tasks framework with `django-tasks` database backend and a worker container | No Redis/Celery needed at this scale |
| Email | Django SMTP backend through Resend SMTP | Reuses the existing Resend account and verified domain |
| Hosting | Docker Compose on the existing Hetzner VPS (`laboflush-stack`), Caddy as TLS reverse proxy, Postgres from the same stack | Cheapest, most flexible; DB already there |
| Database | PostgreSQL 16, database `pars_studio` (already provisioned). Django connects to the `postgres` container directly over the Docker network, not through PgBouncer | Avoids transaction-pooling limitations |

## 3. System overview

```
 Browser ── studiospars.com (Next.js on Vercel)
    │            │  fetch(credentials: include)
    │            ▼
    │       api.studiospars.com ── Caddy (TLS) ── gunicorn/Django ── Postgres
    │                                              │        │
    │                                              │        └── Django Tasks worker (emails, fulfilment)
    │                                              └── Cloudflare R2 (beat files, uploads, deliverables)
    └── checkout.stripe.com ── Stripe ── webhook ──► api.studiospars.com/api/v1/stripe/webhook
```

Cookie domain is `.studiospars.com` so the session set by the API is sent by the
browser on requests from the Next.js origin. CORS allows only the site origin
with credentials. Locally, Next.js runs on `localhost:3000` and Django on
`localhost:8000`; cookies ignore ports so the same flow works unchanged.

## 4. Django project layout

```
config/            settings (env-driven), urls, asgi/wsgi
apps/core/         TimeStampedModel, email helpers, health endpoint
apps/accounts/     custom User (email login), allauth config, /me endpoint
apps/catalog/      Beat, BeatLicense, ServiceProduct, StudioRate
apps/orders/       Order, OrderItem, Payment, checkout endpoint, Stripe webhook, fulfilment
apps/downloads/    DownloadGrant, signed download endpoint
apps/services/     ServiceOrder workflow, customer uploads, deliverables
apps/bookings/     Reservation, availability, slot holds
docs/              this spec, per-phase plans
```

All API routes live under `/api/v1/`. allauth headless routes live under
`/_allauth/browser/v1/` (fixed by the library). The OpenAPI schema is served at
`/api/schema/` and the frontend generates TypeScript types from it.

## 5. Data model

### accounts
- **User**: `email` (unique, login field), `first_name`, `last_name`, `is_staff`, `is_active`, `date_joined`. No username.

### catalog
- **Beat**: `title`, `slug`, `bpm`, `key`, `genre`, `tags[]`, `description`, `cover` (image), `preview` (tagged MP3, public), `status` (`draft`/`published`/`sold_exclusive`), `published_at`.
- **BeatLicense**: FK `beat`, `tier` (`mp3_lease`/`wav_lease`/`trackout`/`exclusive`), `price_usd`, `is_active`, `terms` (text), and the deliverable files: `mp3_file`, `wav_file`, `stems_zip` (each optional, private storage). A beat has at most one license per tier. When an `exclusive` license is sold the beat becomes `sold_exclusive` and all its licenses stop being purchasable.
- **ServiceProduct**: `name`, `slug`, `kind` (`mastering`/`mixing`), `price_usd`, `turnaround_days`, `included_revisions`, `max_stems`, `description`, `is_active`.
- **StudioRate**: `service_type` (`recording`/`vocal`/`production`), `hourly_price_usd`, `is_active`. Used to price reservations.

### orders
- **Order**: `number` (human readable, e.g. `PS-2026-000123`), FK `user`, `status` (`pending`/`paid`/`failed`/`cancelled`/`refunded`), `currency` (`USD`), `subtotal`, `total`, `stripe_checkout_session_id`, `stripe_payment_intent_id`, `paid_at`, `customer_email` snapshot, `locale`.
- **OrderItem**: FK `order`, `item_type` (`beat_license`/`service`/`booking`), generic reference to the sold thing (`beat_license`, `service_product`, `reservation` nullable FKs; exactly one set), `title` snapshot, `unit_price`, `quantity` (always 1 for beats and bookings), `line_total`.
- **Payment**: FK `order`, `provider` (`stripe`), `provider_event_id` (unique, webhook idempotency), `type` (`checkout_completed`/`refund`), `amount`, `raw` (JSON), `created_at`.

### downloads
- **DownloadGrant**: FK `order_item`, FK `user`, `file_kind` (`mp3`/`wav`/`stems`), `download_count`, `max_downloads` (default 10), `expires_at` (default 30 days, renewable by admin). The endpoint returns a presigned R2 URL valid for 15 minutes.

### services
- **ServiceOrder**: OneToOne `order_item`, FK `user`, FK `service_product`, `status` (`awaiting_files`/`received`/`in_progress`/`delivered`/`revision_requested`/`completed`), `notes` (customer brief), `reference_links`, `revisions_used`, `due_at`.
- **ServiceFile**: FK `service_order`, `direction` (`customer_upload`/`studio_deliverable`), `file` (private), `original_name`, `size`, `uploaded_by`.
- **ServiceEvent**: FK `service_order`, `from_status`, `to_status`, `message`, `actor`. Audit trail shown to the customer.

### bookings
- **Reservation**: fields ported from the current `reservations` table (`customer_name`, `customer_email`, `customer_phone`, `artist_name`, `service_type`, `session_date`, `start_time`, `duration_hours`, `project_description`, `reference_links`, `status`, `admin_notes`, `locale`), plus FK `user` (nullable for legacy rows), `hold_expires_at`, `price_usd`, FK `order_item` (nullable). Status set: `hold`/`pending_payment`/`confirmed`/`cancelled`/`completed`/`expired`.
- The existing exclusion constraint (no overlapping `[start, start+duration)` on the same date for live statuses) is kept as a Django `ExclusionConstraint`. Live statuses are `hold`, `pending_payment`, `confirmed`.
- No data migration is needed: both the Neon and VPS databases contain zero reservations as of 2026-09-27.

## 6. Key flows

### Sign-up / sign-in
1. Next.js calls allauth headless endpoints (`/_allauth/browser/v1/auth/signup`, `/login`, `/provider/redirect` for Google, `/password/reset`).
2. Email verification is mandatory before checkout. allauth sends the verification email via Django's email backend (a background task).
3. `GET /api/v1/me` returns the current user or 401.

### Checkout
1. Next.js `POST /api/v1/checkout` with `{ items: [{type, id, ...}], locale }`. Requires an authenticated, verified user.
2. Server validates every line: license active and beat purchasable, service active, reservation slot still free (it creates a `hold` reservation for booking lines with a 15 minute `hold_expires_at`). Prices come from the database, never from the client.
3. Server creates `Order(pending)` + items, then a Stripe Checkout Session with the line items, `client_reference_id = order.number`, `metadata.order_id`, `success_url = site/{locale}/checkout/success?order=…`, `cancel_url = site/{locale}/cart`. Session `expires_at` is 30 minutes.
4. Response `{ checkout_url }`; the browser is redirected to Stripe.
5. Webhook `checkout.session.completed` (signature verified) → idempotent by `provider_event_id` → `Order.status = paid`, `paid_at` set → enqueue `fulfil_order(order_id)`.
6. `fulfil_order` per item type: beat license → create `DownloadGrant`s and, for `exclusive`, mark the beat `sold_exclusive`; service → create `ServiceOrder(awaiting_files)`; booking → reservation `confirmed`. Then send the order confirmation email (customer) and a notification (studio).
7. `checkout.session.expired` / `async_payment_failed` → order `cancelled`/`failed`, booking holds released. A periodic task also expires stale `hold` reservations and pending orders.
8. `GET /api/v1/orders/` and `/api/v1/orders/{number}/` for the customer's "My orders" page.

### Service order
1. After payment the customer sees the service order in `awaiting_files` and uploads sources via `POST /api/v1/service-orders/{id}/files/` (direct-to-R2 presigned PUT, then a confirm call). Status → `received`, studio notified.
2. Studio works from the admin: changes status, uploads deliverables. Each transition writes a `ServiceEvent` and emails the customer.
3. Customer can request a revision while `revisions_used < included_revisions`; otherwise a new service purchase is required.

### Booking
1. Next.js booking page fetches availability from `GET /api/v1/bookings/availability?date=…&service_type=…` and prices from `GET /api/v1/catalog/studio-rates/`.
2. Chosen slot is added to the cart as a booking line and flows through checkout (hold → pending_payment → confirmed).
3. Studio manages reservations in the admin (replaces the current Next.js admin). ICS export stays as an API endpoint.

## 7. Cross-cutting

- **Settings** via `django-environ`; single `config/settings.py` with `DEBUG`-driven switches, secrets only from env. `.env.example` documents every variable.
- **Security**: `SESSION_COOKIE_SECURE`, `SameSite=Lax`, `CSRF_TRUSTED_ORIGINS` = site origins, `SECURE_PROXY_SSL_HEADER` behind Caddy, DRF throttling on auth and checkout, Stripe webhook signature verification, presigned URLs only for files the user owns.
- **Errors**: DRF exception handler returns `{ "detail": …, "code": … }`; validation errors keep DRF's field map. Checkout returns `409` with the offending line when a beat/slot is no longer available.
- **Observability**: Sentry SDK (DSN optional), structured request logging, `/healthz` for Caddy/uptime checks.
- **Testing**: `pytest-django`, factories per app, tests run against Postgres in CI (GitHub Actions service container). Stripe calls are mocked; webhook tests use signed fixture payloads.
- **Tooling**: `uv` for dependencies, `ruff` for lint + format, pre-commit optional.
- **Deploy**: multi-stage Dockerfile (uv → slim runtime), `compose.yaml` with `web` (gunicorn) and `worker` (`manage.py db_worker`) attached to the external `laboflush_lfnet` network. Migrations run in the container entrypoint. Static files via WhiteNoise. Caddy in `laboflush-stack` gains a `443` listener and `api.studiospars.com` site block (separate PR in that repo); `ufw allow 443/tcp`.
- **Frontend contract**: `openapi-typescript` generates `src/lib/api/schema.d.ts` in `pars-studio-v2` from `/api/schema/`; a thin `apiFetch` wrapper adds `credentials: 'include'` and the CSRF header.

## 8. Phases

Each phase is a GitHub issue, a branch named after the issue (`PSA-<n>` in this
repo, `PSW-<n>` in the frontend repo), and a pull request merged before the next
phase starts.

1. **Foundation & accounts** — project skeleton, settings, custom User, allauth headless (email + Google), DRF + OpenAPI, Unfold admin, health endpoint, Docker + compose, CI, deploy to VPS. Frontend: API client, sign-in/sign-up/verify/reset pages, account page, navbar auth state.
2. **Catalog & beats** — catalog models, R2 storage, admin (inline licenses, file uploads, cover/preview), public read API. Frontend: beats listing with player, beat detail with license picker, services page.
3. **Cart, checkout & Stripe** — orders models, checkout endpoint, Stripe Checkout + webhooks, fulfilment task, download grants, emails. Frontend: cart drawer, checkout redirect, success page, "My orders" and downloads.
4. **Service orders** — ServiceOrder workflow, direct-to-R2 uploads, deliverables, admin actions, status emails. Frontend: service order page with upload and timeline.
5. **Bookings & payment** — Reservation model with hold/expiry, availability API, booking priced through StudioRate and paid via checkout, ICS endpoint, admin. Frontend: booking page switched to the API, cart integration; remove the old Next.js admin, auth and `/api/reservations` routes and the direct database access.

## 9. Open items to confirm with the studio (do not block phase 1)

- Exact license tier names, prices and what files each tier includes.
- Studio hourly prices per service type and whether a deposit (instead of full payment) is preferred for long sessions.
- Service turnaround and included revision counts.
- Refund policy text for the checkout page.
