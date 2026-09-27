"""Customer uploads: direct-to-R2 presigned PUTs, or a Django endpoint locally."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from django.conf import settings
from django.core.files.storage import storages

from .models import ServiceFile, ServiceOrder

SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class UploadRejected(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def clean_name(name: str) -> str:
    base = SAFE_NAME.sub("-", name.strip())[:120].strip("-.") or "upload"
    return base


def validate(service_order: ServiceOrder, name: str, size: int) -> str:
    if not service_order.accepts_uploads:
        raise UploadRejected("uploads_closed", "This order is not accepting files right now.")
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in settings.SERVICE_UPLOAD_EXTENSIONS:
        allowed = ", ".join(settings.SERVICE_UPLOAD_EXTENSIONS)
        raise UploadRejected("bad_extension", f"Allowed file types: {allowed}.")
    if size <= 0 or size > settings.SERVICE_UPLOAD_MAX_MB * 1024 * 1024:
        raise UploadRejected(
            "too_large", f"Files must be under {settings.SERVICE_UPLOAD_MAX_MB} MB."
        )
    current_round = service_order.revisions_used
    uploaded = service_order.files.filter(
        direction=ServiceFile.Direction.CUSTOMER_UPLOAD, round=current_round
    ).count()
    if uploaded >= service_order.service_product.max_stems:
        raise UploadRejected(
            "too_many_files",
            f"This service accepts up to {service_order.service_product.max_stems} file(s).",
        )
    return clean_name(name)


def object_key(service_order: ServiceOrder, name: str) -> str:
    return f"services/{service_order.pk}/customer_upload/{uuid.uuid4().hex}-{name}"


@dataclass
class Presigned:
    direct: bool
    key: str
    upload_url: str
    method: str
    headers: dict[str, str]


def presign(service_order: ServiceOrder, name: str, size: int, content_type: str) -> Presigned:
    name = validate(service_order, name, size)
    key = object_key(service_order, name)
    storage = storages["private"]
    if hasattr(storage, "bucket"):
        client = storage.connection.meta.client
        url = client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": storage.bucket_name,
                "Key": key,
                "ContentType": content_type or "application/octet-stream",
                "ContentLength": size,
            },
            ExpiresIn=settings.PRESIGNED_URL_TTL,
        )
        return Presigned(
            direct=True,
            key=key,
            upload_url=url,
            method="PUT",
            headers={"Content-Type": content_type or "application/octet-stream"},
        )
    # Local fallback: the browser posts the file to our own endpoint.
    return Presigned(direct=False, key=key, upload_url="", method="POST", headers={})


def object_exists(key: str, expected_size: int) -> bool:
    storage = storages["private"]
    if hasattr(storage, "bucket"):
        try:
            head = storage.connection.meta.client.head_object(Bucket=storage.bucket_name, Key=key)
        except Exception:
            return False
        return int(head.get("ContentLength", -1)) == expected_size
    return storage.exists(key)
