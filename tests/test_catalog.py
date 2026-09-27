from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError

from apps.catalog.models import Beat, BeatLicense, ServiceProduct, StudioRate


@pytest.fixture
def beat(db):
    beat = Beat.objects.create(title="Night Drive", bpm=92, key="Am", genre="trap", tags=["dark"])
    beat.status = Beat.Status.PUBLISHED
    beat.save()
    BeatLicense.objects.create(beat=beat, tier=BeatLicense.Tier.MP3_LEASE, price_usd="29.00")
    BeatLicense.objects.create(beat=beat, tier=BeatLicense.Tier.WAV_LEASE, price_usd="49.00")
    BeatLicense.objects.create(
        beat=beat, tier=BeatLicense.Tier.EXCLUSIVE, price_usd="499.00", is_active=False
    )
    return beat


@pytest.mark.django_db
def test_slug_and_published_at_are_set_on_save():
    beat = Beat.objects.create(title="Golden Hour", bpm=120, status=Beat.Status.PUBLISHED)
    assert beat.slug == "golden-hour"
    assert beat.published_at is not None


@pytest.mark.django_db
def test_one_license_per_tier(beat):
    with pytest.raises(IntegrityError):
        BeatLicense.objects.create(beat=beat, tier=BeatLicense.Tier.MP3_LEASE, price_usd="1.00")


@pytest.mark.django_db
def test_mark_sold_exclusive_deactivates_everything(beat):
    beat.mark_sold_exclusive()
    beat.refresh_from_db()
    assert beat.status == Beat.Status.SOLD_EXCLUSIVE
    assert not beat.licenses.filter(is_active=True).exists()


@pytest.mark.django_db
def test_license_missing_files_reflects_tier():
    beat = Beat.objects.create(title="Static", bpm=140)
    lic = BeatLicense.objects.create(
        beat=beat,
        tier=BeatLicense.Tier.WAV_LEASE,
        price_usd="49.00",
        mp3_file=SimpleUploadedFile("static.mp3", b"id3"),
    )
    assert lic.missing_files == ["wav"]


@pytest.mark.django_db
def test_public_list_only_shows_published_beats_and_active_licenses(api_client, beat):
    Beat.objects.create(title="Draft", bpm=100)
    sold = Beat.objects.create(title="Sold", bpm=100, status=Beat.Status.PUBLISHED)
    sold.mark_sold_exclusive()

    response = api_client.get("/api/v1/catalog/beats/")
    assert response.status_code == 200
    results = response.json()["results"]
    assert [b["slug"] for b in results] == ["night-drive"]
    assert results[0]["min_price_usd"] == "29.00"

    response = api_client.get("/api/v1/catalog/beats/night-drive/")
    assert response.status_code == 200
    licenses = response.json()["licenses"]
    assert [lic["tier"] for lic in licenses] == ["mp3_lease", "wav_lease"]
    assert licenses[1]["includes"] == ["mp3", "wav"]
    assert "mp3_file" not in response.content.decode()

    assert api_client.get("/api/v1/catalog/beats/draft/").status_code == 404


@pytest.mark.django_db
def test_beat_filters_and_search(api_client, beat):
    other = Beat.objects.create(
        title="Velvet", bpm=76, key="Dm", genre="rnb", tags=["smooth"], status="published"
    )
    BeatLicense.objects.create(beat=other, tier="mp3_lease", price_usd="19.00")

    def slugs(query: str) -> list[str]:
        payload = api_client.get(f"/api/v1/catalog/beats/?{query}").json()
        return [b["slug"] for b in payload["results"]]

    assert slugs("genre=RNB") == ["velvet"]
    assert slugs("bpm_min=80") == ["night-drive"]
    assert slugs("bpm_min=70&bpm_max=80") == ["velvet"]
    assert slugs("tag=dark") == ["night-drive"]
    assert slugs("search=velv") == ["velvet"]
    assert slugs("ordering=bpm") == ["velvet", "night-drive"]


@pytest.mark.django_db
def test_services_and_rates_endpoints(api_client):
    ServiceProduct.objects.create(name="Single Mastering", kind="mastering", price_usd="60.00")
    ServiceProduct.objects.create(name="Old", kind="mixing", price_usd="1.00", is_active=False)
    StudioRate.objects.create(service_type="recording", hourly_price_usd=Decimal("45.00"))

    services = api_client.get("/api/v1/catalog/services/").json()
    assert [s["slug"] for s in services] == ["single-mastering"]
    assert services[0]["kind_label"] == "Mastering"
    assert {"name_tr", "description_tr"} <= services[0].keys()

    rates = api_client.get("/api/v1/catalog/studio-rates/").json()
    assert rates == [
        {
            "service_type": "recording",
            "service_type_label": "Recording",
            "hourly_price_usd": "45.00",
        }
    ]


@pytest.mark.django_db
def test_admin_publish_action(admin_client, beat):
    draft = Beat.objects.create(title="Draft", bpm=100)
    response = admin_client.post(
        "/admin/catalog/beat/",
        {"action": "publish", "_selected_action": [draft.pk]},
        follow=True,
    )
    assert response.status_code == 200
    draft.refresh_from_db()
    assert draft.status == Beat.Status.PUBLISHED
    assert draft.published_at is not None


@pytest.mark.django_db
def test_seed_catalog_is_idempotent(django_db_blocker):
    from django.core.management import call_command

    call_command("seed_catalog")
    call_command("seed_catalog")
    assert Beat.objects.count() == 4
    assert BeatLicense.objects.count() == 16
    assert ServiceProduct.objects.count() == 2
    assert StudioRate.objects.count() == 5


@pytest.mark.django_db
def test_bootstrap_catalog_creates_services_and_rates_without_clobbering_edits():
    from decimal import Decimal
    from io import StringIO

    from django.core.management import call_command

    call_command("bootstrap_catalog", stdout=StringIO())
    assert ServiceProduct.objects.count() == 4
    assert StudioRate.objects.count() == 5
    assert Beat.objects.count() == 0
    assert ServiceProduct.objects.filter(kind=ServiceProduct.Kind.MASTERING).count() == 2
    assert ServiceProduct.objects.get(slug="mixing").name_tr == "Miks"

    mixing = ServiceProduct.objects.get(slug="mixing")
    mixing.price_usd = Decimal("300.00")
    mixing.name_tr = "Miks (özel)"
    mixing.description_tr = ""
    mixing.save()

    out = StringIO()
    call_command("bootstrap_catalog", stdout=out)
    mixing.refresh_from_db()
    assert ServiceProduct.objects.count() == 4
    assert mixing.price_usd == Decimal("300.00")
    assert mixing.name_tr == "Miks (özel)"  # edited text survives
    assert mixing.description_tr.startswith("En fazla 40 stem")  # empty field backfilled
    assert "0 created, 9 already existed" in out.getvalue()
