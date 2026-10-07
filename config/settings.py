"""
Django settings for the Pars Studio API.

Every deployment-specific value comes from the environment (see `.env.example`).
The same module serves development and production; `DEBUG` flips the
security-related defaults.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CORS_ALLOWED_ORIGINS=(list, ["http://localhost:3000"]),
    CSRF_TRUSTED_ORIGINS=(list, ["http://localhost:3000"]),
    COOKIE_DOMAIN=(str, ""),
    FRONTEND_URL=(str, "http://localhost:3000"),
    API_URL=(str, "http://localhost:8000"),
    EMAIL_URL=(str, "consolemail://"),
    RESEND_API_KEY=(str, ""),
    EMAIL_HOST=(str, ""),
    EMAIL_PORT=(int, 465),
    EMAIL_HOST_USER=(str, ""),
    EMAIL_HOST_PASSWORD=(str, ""),
    EMAIL_USE_SSL=(bool, True),
    EMAIL_USE_TLS=(bool, False),
    DEFAULT_FROM_EMAIL=(str, "Pars Studio <noreply@studiospars.com>"),
    STUDIO_NOTIFICATION_EMAIL=(str, "parsstudiosofficial@gmail.com"),
    GOOGLE_CLIENT_ID=(str, ""),
    GOOGLE_CLIENT_SECRET=(str, ""),
    TASKS_BACKEND=(str, "django_tasks_db.DatabaseBackend"),
    SENTRY_DSN=(str, ""),
    LOG_LEVEL=(str, "INFO"),
    R2_ACCOUNT_ID=(str, ""),
    R2_ACCESS_KEY_ID=(str, ""),
    R2_SECRET_ACCESS_KEY=(str, ""),
    R2_BUCKET_PUBLIC=(str, ""),
    R2_BUCKET_PRIVATE=(str, ""),
    R2_PUBLIC_DOMAIN=(str, ""),
    PRESIGNED_URL_TTL=(int, 900),
    STRIPE_SECRET_KEY=(str, ""),
    STRIPE_WEBHOOK_SECRET=(str, ""),
    CHECKOUT_SESSION_TTL_MINUTES=(int, 30),
    DOWNLOAD_GRANT_DAYS=(int, 30),
    DOWNLOAD_MAX_PER_GRANT=(int, 10),
    DATABASE_POOLED=(bool, False),
    SERVICE_UPLOAD_MAX_MB=(int, 2048),
)
environ.Env.read_env(BASE_DIR / ".env")

# --- Core -------------------------------------------------------------------

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
# Loopback names are always allowed so the container health check (curl on
# 127.0.0.1) and the host reverse proxy work without listing them per deploy.
ALLOWED_HOSTS = list(dict.fromkeys([*env("ALLOWED_HOSTS"), "127.0.0.1", "localhost"]))
FRONTEND_URL = env("FRONTEND_URL").rstrip("/")
# Public origin of this API; studio emails link to its admin.
API_URL = env("API_URL").rstrip("/")

INSTALLED_APPS = [
    # Unfold must precede django.contrib.admin.
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "django.contrib.postgres",
    # Third party
    "rest_framework",
    "drf_spectacular",
    "corsheaders",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.headless",
    "django_tasks_db",
    "django_filters",
    # Project
    "apps.core",
    "apps.accounts",
    "apps.catalog",
    "apps.orders",
    "apps.downloads",
    "apps.services",
    "apps.bookings",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
SITE_ID = 1

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --- Database ---------------------------------------------------------------

DATABASES = {
    "default": {
        **env.db("DATABASE_URL", default="postgres://pars:pars@localhost:5432/pars_studio"),
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
    }
}
# Production talks to PgBouncer in transaction-pooling mode: no server-side
# cursors and no server-side prepared statements (psycopg would otherwise
# prepare after five executions and hit a different backend next time).
if env("DATABASE_POOLED"):
    DISABLE_SERVER_SIDE_CURSORS = True
    DATABASES["default"].setdefault("OPTIONS", {})["prepare_threshold"] = None
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Auth -------------------------------------------------------------------

AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# allauth (headless only: the Next.js app renders every screen)
ACCOUNT_ADAPTER = "apps.accounts.adapter.AccountAdapter"
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_EMAIL_VERIFICATION_BY_CODE_ENABLED = False
# Clicking the verification link (in the same browser) signs the user in right away.
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
ACCOUNT_EMAIL_SUBJECT_PREFIX = "Pars Studio — "
ACCOUNT_LOGOUT_ON_PASSWORD_CHANGE = False
ACCOUNT_RATE_LIMITS = {
    "login_failed": "10/m/ip,5/5m/key",
    "signup": "20/m/ip",
    "reset_password": "20/m/ip,5/m/key",
    "confirm_email": "1/3m/key",
}

# Google sign-in only exists when credentials are configured; the frontend hides
# the button when the provider is absent from the headless config.
if env("GOOGLE_CLIENT_ID"):
    INSTALLED_APPS.insert(
        INSTALLED_APPS.index("allauth.headless"), "allauth.socialaccount.providers.google"
    )

SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "APPS": [
            {
                "client_id": env("GOOGLE_CLIENT_ID"),
                "secret": env("GOOGLE_CLIENT_SECRET"),
                "key": "",
            }
        ],
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
        "EMAIL_AUTHENTICATION": True,
    }
}

HEADLESS_ONLY = True
HEADLESS_CLIENTS = ("browser",)
HEADLESS_SERVE_SPECIFICATION = True
# Links placed in emails point at the Next.js app, which calls the API back.
HEADLESS_FRONTEND_URLS = {
    "account_confirm_email": f"{FRONTEND_URL}/account/verify-email/{{key}}",
    "account_reset_password": f"{FRONTEND_URL}/account/password/reset",
    "account_reset_password_from_key": f"{FRONTEND_URL}/account/password/reset/key/{{key}}",
    "account_signup": f"{FRONTEND_URL}/account/signup",
    "socialaccount_login_error": f"{FRONTEND_URL}/account/provider/callback",
}

# --- Sessions, CSRF, CORS ---------------------------------------------------

_cookie_domain = env("COOKIE_DOMAIN") or None
SESSION_COOKIE_DOMAIN = _cookie_domain
CSRF_COOKIE_DOMAIN = _cookie_domain
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
# The frontend reads the CSRF cookie to send it back as a header.
CSRF_COOKIE_HTTPONLY = False
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = 60 * 60 * 24 * 30
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")

CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True
    SECURE_SSL_REDIRECT = False  # Caddy terminates TLS and redirects HTTP itself.
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_REFERRER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "DENY"

# --- REST framework ---------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 24,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"]
    + (["rest_framework.renderers.BrowsableAPIRenderer"] if DEBUG else []),
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "120/min",
        "user": "600/min",
        "checkout": "10/min",
    },
    "EXCEPTION_HANDLER": "apps.core.exceptions.exception_handler",
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Pars Studio API",
    "DESCRIPTION": "Beats, mastering services and studio bookings for Pars Studio.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/v1",
    "COMPONENT_SPLIT_REQUEST": True,
}

# --- Admin (Unfold) ---------------------------------------------------------

UNFOLD = {
    "SITE_TITLE": "Pars Studio",
    "SITE_HEADER": "Pars Studio",
    "SITE_SYMBOL": "graphic_eq",
    "SITE_URL": FRONTEND_URL,
    "SHOW_HISTORY": True,
    "COLORS": {
        # Brass-gold accent that matches the storefront.
        "primary": {
            "50": "252 247 234",
            "100": "247 236 204",
            "200": "239 218 156",
            "300": "229 196 105",
            "400": "218 172 62",
            "500": "196 146 40",
            "600": "163 116 30",
            "700": "128 89 26",
            "800": "102 71 25",
            "900": "84 59 23",
            "950": "48 32 10",
        },
    },
}

# --- Email, tasks -----------------------------------------------------------

# Email, in order of precedence: Resend HTTPS API (RESEND_API_KEY; works where SMTP
# ports are blocked), discrete SMTP variables (EMAIL_HOST), or an EMAIL_URL.
# Django 6.1+ wants MAILERS.
if env("RESEND_API_KEY"):
    _email_backend = "apps.core.mail.ResendEmailBackend"
    _email_options = {"api_key": env("RESEND_API_KEY")}
elif env("EMAIL_HOST"):
    _email_backend = "django.core.mail.backends.smtp.EmailBackend"
    _email_options = {
        "host": env("EMAIL_HOST"),
        "port": env("EMAIL_PORT"),
        "username": env("EMAIL_HOST_USER"),
        "password": env("EMAIL_HOST_PASSWORD"),
        "use_ssl": env("EMAIL_USE_SSL"),
        "use_tls": env("EMAIL_USE_TLS"),
    }
else:
    _email = env.email("EMAIL_URL")
    _email_backend = _email["EMAIL_BACKEND"]
    _email_options = {
        "host": _email.get("EMAIL_HOST"),
        "port": _email.get("EMAIL_PORT"),
        "username": _email.get("EMAIL_HOST_USER"),
        "password": _email.get("EMAIL_HOST_PASSWORD"),
        "use_ssl": _email.get("EMAIL_USE_SSL"),
        "use_tls": _email.get("EMAIL_USE_TLS"),
        "file_path": _email.get("EMAIL_FILE_PATH"),
    }
MAILERS = {
    "default": {
        "BACKEND": _email_backend,
        "OPTIONS": {key: value for key, value in _email_options.items() if value},
    }
}
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL")
SERVER_EMAIL = DEFAULT_FROM_EMAIL
STUDIO_NOTIFICATION_EMAIL = env("STUDIO_NOTIFICATION_EMAIL")

TASKS = {
    "default": {
        "BACKEND": env("TASKS_BACKEND"),
        "QUEUES": ["default"],
    }
}

# --- Commerce ---------------------------------------------------------------

STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET")
CHECKOUT_SESSION_TTL_MINUTES = env("CHECKOUT_SESSION_TTL_MINUTES")
DOWNLOAD_GRANT_DAYS = env("DOWNLOAD_GRANT_DAYS")
DOWNLOAD_MAX_PER_GRANT = env("DOWNLOAD_MAX_PER_GRANT")
CURRENCY = "USD"
SERVICE_UPLOAD_MAX_MB = env("SERVICE_UPLOAD_MAX_MB")
SERVICE_UPLOAD_EXTENSIONS = ("wav", "aif", "aiff", "flac", "mp3", "zip")

# --- I18n, static, media ----------------------------------------------------

LANGUAGE_CODE = "en"
LANGUAGES = [("en", "English"), ("tr", "Türkçe")]
TIME_ZONE = "Europe/Istanbul"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Two media buckets: `public` (covers, previews) is served straight from R2's
# public domain; `private` (license files, uploads, deliverables) is only ever
# reached through short-lived presigned URLs. Without R2 credentials both fall
# back to the local filesystem so development needs no cloud account.
R2_ACCOUNT_ID = env("R2_ACCOUNT_ID")
PRESIGNED_URL_TTL = env("PRESIGNED_URL_TTL")
USE_R2 = bool(R2_ACCOUNT_ID and env("R2_ACCESS_KEY_ID"))

if USE_R2:
    _r2_common = {
        "access_key": env("R2_ACCESS_KEY_ID"),
        "secret_key": env("R2_SECRET_ACCESS_KEY"),
        "endpoint_url": f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        "region_name": "auto",
        "signature_version": "s3v4",
        "default_acl": None,
        "file_overwrite": False,
        "addressing_style": "path",
    }
    _public_media = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            **_r2_common,
            "bucket_name": env("R2_BUCKET_PUBLIC"),
            "querystring_auth": False,
            "custom_domain": env("R2_PUBLIC_DOMAIN") or None,
        },
    }
    _private_media = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            **_r2_common,
            "bucket_name": env("R2_BUCKET_PRIVATE"),
            "querystring_auth": True,
            "querystring_expire": PRESIGNED_URL_TTL,
        },
    }
else:
    _public_media = {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {"location": MEDIA_ROOT / "public", "base_url": f"{MEDIA_URL}public/"},
    }
    _private_media = {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {"location": MEDIA_ROOT / "private", "base_url": f"{MEDIA_URL}private/"},
    }

STORAGES = {
    "default": _public_media,
    "public": _public_media,
    "private": _private_media,
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# --- Logging, monitoring ----------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL")},
    "loggers": {
        "django.request": {"level": "WARNING"},
        "django.db.backends": {"level": "WARNING"},
    },
}

SENTRY_DSN = env("SENTRY_DSN")
if SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(dsn=SENTRY_DSN, send_default_pii=False, traces_sample_rate=0.1)
