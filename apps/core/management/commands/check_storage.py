"""Round-trip a tiny file through the public and private media storages."""

import uuid

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.core.management.base import BaseCommand, CommandError

from apps.core.storage import presigned_url


class Command(BaseCommand):
    help = (
        "Write, read back, sign and delete a probe file on the public and private "
        "storages. Use after configuring R2 to confirm credentials and bucket names."
    )

    def handle(self, *args, **options):
        backend = "R2" if settings.USE_R2 else "local filesystem"
        self.stdout.write(f"Storage backend: {backend}")
        failures = 0
        for alias in ("public", "private"):
            try:
                url = self._probe(alias)
            except Exception as exc:  # noqa: BLE001 - report every backend before failing
                failures += 1
                self.stdout.write(self.style.ERROR(f"{alias:8} FAIL {exc}"))
            else:
                self.stdout.write(self.style.SUCCESS(f"{alias:8} OK   {url}"))
        if failures:
            raise CommandError(f"{failures} storage(s) failed.")

    @staticmethod
    def _probe(alias: str) -> str:
        storage = storages[alias]
        name = storage.save(f"probe/{uuid.uuid4().hex}.txt", ContentFile(b"ok"))
        try:
            with storage.open(name, "rb") as handle:
                if handle.read() != b"ok":
                    raise RuntimeError("read back different content")
            if alias == "private":
                # FieldFile-like shim so the same helper the API uses gets exercised.
                url = presigned_url(_Probe(storage, name))
            else:
                url = storage.url(name)
        finally:
            storage.delete(name)
        return url.split("?", 1)[0] if alias == "private" else url


class _Probe:
    def __init__(self, storage, name):
        self.storage = storage
        self.name = name

    def __bool__(self):
        return True
