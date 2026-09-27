"""Helpers around the `public` / `private` media storages defined in settings."""

from django.conf import settings
from django.core.files.storage import storages
from django.db.models.fields.files import FieldFile


def public_storage():
    return storages["public"]


def private_storage():
    return storages["private"]


def presigned_url(file: FieldFile, expires: int | None = None) -> str:
    """
    Short-lived URL for a private file. On R2 this is a presigned GET; on the
    local filesystem fallback it is the plain media URL.
    """
    if not file:
        raise ValueError("No file to sign.")
    storage = file.storage
    ttl = expires or settings.PRESIGNED_URL_TTL
    if hasattr(storage, "bucket"):  # S3Storage
        return storage.url(file.name, expire=ttl)
    return storage.url(file.name)
