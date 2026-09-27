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
