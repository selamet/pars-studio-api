import pytest
from apps.catalog.models import Beat, BeatLicense

@pytest.mark.django_db
def test_admin_pages_render(admin_client):
    beat = Beat.objects.create(title="Night Drive", bpm=92)
    BeatLicense.objects.create(beat=beat, tier="mp3_lease", price_usd="29.00")
    for url in ["/admin/catalog/beat/", f"/admin/catalog/beat/{beat.pk}/change/", "/admin/catalog/beat/add/",
                "/admin/catalog/serviceproduct/", "/admin/catalog/studiorate/"]:
        assert admin_client.get(url).status_code == 200, url
