import pytest


@pytest.mark.django_db
def test_healthz_reports_ok(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_openapi_schema_is_served(client):
    response = client.get("/api/schema/")
    assert response.status_code == 200
    assert b"openapi" in response.content


@pytest.mark.django_db
def test_admin_login_page_uses_unfold(client):
    response = client.get("/admin/login/")
    assert response.status_code == 200
    assert b"unfold" in response.content.lower()


def test_loopback_hosts_are_always_allowed(settings):
    assert "127.0.0.1" in settings.ALLOWED_HOSTS
    assert "localhost" in settings.ALLOWED_HOSTS


@pytest.mark.django_db
def test_check_storage_round_trips_both_storages(settings):
    from io import StringIO

    from django.core.management import call_command

    out = StringIO()
    call_command("check_storage", stdout=out)
    text = out.getvalue()
    assert "Storage backend: local filesystem" in text
    assert "public   OK" in text
    assert "private  OK" in text
    assert not list((settings.MEDIA_ROOT / "public" / "probe").glob("*.txt"))
