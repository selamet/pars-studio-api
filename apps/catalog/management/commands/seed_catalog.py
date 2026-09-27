"""Development data: a few beats, the two services and studio rates. Idempotent."""

from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.catalog.models import Beat, BeatLicense, ServiceProduct, StudioRate

BEATS = [
    ("Night Drive", 92, "Am", "trap", ["dark", "808", "night"]),
    ("Golden Hour", 120, "F#m", "afrobeat", ["warm", "summer"]),
    ("Static", 140, "Cm", "drill", ["uk", "hard"]),
    ("Velvet", 76, "Dm", "rnb", ["smooth", "late"]),
]
LICENSES = [
    (BeatLicense.Tier.MP3_LEASE, "29.00"),
    (BeatLicense.Tier.WAV_LEASE, "49.00"),
    (BeatLicense.Tier.TRACKOUT, "99.00"),
    (BeatLicense.Tier.EXCLUSIVE, "499.00"),
]
SERVICES = [
    ("Single Mastering", ServiceProduct.Kind.MASTERING, "60.00", 3, 1, 1),
    ("Mixing (up to 40 stems)", ServiceProduct.Kind.MIXING, "250.00", 7, 2, 40),
]
RATES = [
    (StudioRate.ServiceType.RECORDING, "45.00"),
    (StudioRate.ServiceType.VOCAL, "55.00"),
    (StudioRate.ServiceType.BEAT, "60.00"),
    (StudioRate.ServiceType.MIXING, "50.00"),
    (StudioRate.ServiceType.MASTERING, "50.00"),
]


class Command(BaseCommand):
    help = "Seed the catalog with sample beats, services and studio rates."

    def handle(self, *args, **options):
        for title, bpm, key, genre, tags in BEATS:
            beat, _ = Beat.objects.update_or_create(
                title=title,
                defaults={
                    "bpm": bpm,
                    "key": key,
                    "genre": genre,
                    "tags": tags,
                    "status": Beat.Status.PUBLISHED,
                    "description": f"{title} — sample beat for development.",
                },
            )
            for tier, price in LICENSES:
                BeatLicense.objects.update_or_create(
                    beat=beat, tier=tier, defaults={"price_usd": Decimal(price)}
                )
        for name, kind, price, days, revisions, stems in SERVICES:
            ServiceProduct.objects.update_or_create(
                name=name,
                defaults={
                    "kind": kind,
                    "price_usd": Decimal(price),
                    "turnaround_days": days,
                    "included_revisions": revisions,
                    "max_stems": stems,
                },
            )
        for service_type, price in RATES:
            StudioRate.objects.update_or_create(
                service_type=service_type, defaults={"hourly_price_usd": Decimal(price)}
            )
        self.stdout.write(self.style.SUCCESS("Catalog seeded."))
