"""Production starting catalog: the studio's services and hourly rates.

Create-only and idempotent: rows that already exist (matched by slug or service
type) are left untouched so prices edited in the admin survive re-runs. Beats
are not created here because they need audio files; add them in the admin.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.catalog.models import ServiceProduct, StudioRate

SERVICES = [
    {
        "slug": "single-mastering",
        "name": "Single Mastering",
        "kind": ServiceProduct.Kind.MASTERING,
        "price_usd": "60.00",
        "turnaround_days": 3,
        "included_revisions": 1,
        "max_stems": 1,
        "sort_order": 10,
        "description": (
            "Transparent, platform-ready mastering for one track. Send a stereo mix with "
            "at least 3 dB of headroom and we deliver a 24-bit WAV master plus a streaming "
            "MP3, checked against loudness targets for Spotify, Apple Music and YouTube."
        ),
    },
    {
        "slug": "stem-mastering",
        "name": "Stem Mastering",
        "kind": ServiceProduct.Kind.MASTERING,
        "price_usd": "120.00",
        "turnaround_days": 5,
        "included_revisions": 1,
        "max_stems": 8,
        "sort_order": 20,
        "description": (
            "Mastering from up to 8 grouped stems (drums, bass, music, vocals...) for more "
            "control over balance than a stereo master allows. Same deliverables as Single "
            "Mastering, plus an instrumental master on request."
        ),
    },
    {
        "slug": "mixing",
        "name": "Mixing",
        "kind": ServiceProduct.Kind.MIXING,
        "price_usd": "250.00",
        "turnaround_days": 7,
        "included_revisions": 2,
        "max_stems": 40,
        "sort_order": 30,
        "description": (
            "Full mix of one song from up to 40 stems: editing, tuning touch-ups, balance, "
            "EQ, compression, effects and automation. Delivered as a mix-ready 24-bit WAV "
            "with two rounds of revisions included."
        ),
    },
    {
        "slug": "mix-and-master",
        "name": "Mix & Master",
        "kind": ServiceProduct.Kind.MIXING,
        "price_usd": "290.00",
        "turnaround_days": 10,
        "included_revisions": 2,
        "max_stems": 60,
        "sort_order": 40,
        "description": (
            "Mixing and mastering of one song as a single job, up to 60 stems. You get the "
            "mix for approval first, then the final master, instrumental and MP3 in one "
            "delivery. Two rounds of revisions included."
        ),
    },
]

RATES = [
    (StudioRate.ServiceType.RECORDING, "45.00"),
    (StudioRate.ServiceType.VOCAL, "55.00"),
    (StudioRate.ServiceType.BEAT, "60.00"),
    (StudioRate.ServiceType.MIXING, "50.00"),
    (StudioRate.ServiceType.MASTERING, "50.00"),
]


class Command(BaseCommand):
    help = "Create the studio's service products and hourly rates if they do not exist yet."

    def handle(self, *args, **options):
        created = skipped = 0
        for spec in SERVICES:
            spec = {**spec, "price_usd": Decimal(spec["price_usd"])}
            _, was_created = ServiceProduct.objects.get_or_create(
                slug=spec["slug"], defaults={k: v for k, v in spec.items() if k != "slug"}
            )
            created, skipped = self._tally(created, skipped, was_created, spec["name"])
        for service_type, price in RATES:
            _, was_created = StudioRate.objects.get_or_create(
                service_type=service_type, defaults={"hourly_price_usd": Decimal(price)}
            )
            created, skipped = self._tally(
                created, skipped, was_created, f"rate: {service_type.label}"
            )
        self.stdout.write(
            self.style.SUCCESS(f"Done. {created} created, {skipped} already existed.")
        )

    def _tally(self, created: int, skipped: int, was_created: bool, label: str):
        if was_created:
            self.stdout.write(f"  created  {label}")
            return created + 1, skipped
        self.stdout.write(f"  exists   {label}")
        return created, skipped + 1
