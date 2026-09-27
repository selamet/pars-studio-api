"""Settings used by pytest: fast hashing, in-memory email, immediate tasks."""

from .settings import *  # noqa: F403

DEBUG = False
SECRET_KEY = "test-secret-key"  # noqa: S105
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
MAILERS = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}
TASKS = {"default": {"BACKEND": "django.tasks.backends.immediate.ImmediateBackend"}}
STORAGES["staticfiles"] = {  # noqa: F405
    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
}
REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = []  # noqa: F405
ACCOUNT_RATE_LIMITS = {}

STRIPE_SECRET_KEY = "sk_test_dummy"  # noqa: S105
STRIPE_WEBHOOK_SECRET = "whsec_test_dummy"  # noqa: S105
