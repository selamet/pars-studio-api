import re
from urllib.parse import unquote

import pytest
from django.core import mail

HEADLESS = "/_allauth/browser/v1"


@pytest.mark.django_db
def test_me_requires_authentication(api_client):
    response = api_client.get("/api/v1/me")
    assert response.status_code == 403
    assert response.json()["code"] == "not_authenticated"


@pytest.mark.django_db
def test_me_returns_profile_and_allows_name_update(api_client, verified_user):
    api_client.force_authenticate(verified_user)
    response = api_client.get("/api/v1/me")
    assert response.status_code == 200
    assert response.json()["email"] == "ada@example.com"
    assert response.json()["email_verified"] is True

    response = api_client.patch("/api/v1/me", {"first_name": "Ada", "email": "x@example.com"})
    assert response.status_code == 200
    verified_user.refresh_from_db()
    assert verified_user.first_name == "Ada"
    assert verified_user.email == "ada@example.com", "email must be read-only here"


@pytest.mark.django_db
def test_signup_requires_email_verification_then_logs_in(api_client, django_user_model):
    response = api_client.post(
        f"{HEADLESS}/auth/signup",
        {
            "email": "new@example.com",
            "password": "long-and-random-42",
            "first_name": " Ada ",
            "last_name": "Lovelace",
        },
        format="json",
    )
    # 401 with a pending verify_email flow: the account exists but is not usable yet.
    assert response.status_code == 401
    flows = {flow["id"]: flow for flow in response.json()["data"]["flows"]}
    assert flows["verify_email"]["is_pending"] is True
    new_user = django_user_model.objects.get(email="new@example.com")
    assert (new_user.first_name, new_user.last_name) == ("Ada", "Lovelace")

    # The verification mail was rendered in-request and delivered by the (immediate) task.
    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.to == ["new@example.com"]
    match = re.search(r"/account/verify-email/([^\s/]+)", message.body)
    assert match, message.body
    key = unquote(match.group(1))

    response = api_client.post(f"{HEADLESS}/auth/email/verify", {"key": key}, format="json")
    assert response.status_code == 200
    assert response.json()["meta"]["is_authenticated"] is True

    response = api_client.get("/api/v1/me")
    assert response.status_code == 200
    assert response.json()["email_verified"] is True


@pytest.mark.django_db
def test_signup_requires_first_and_last_name(api_client, django_user_model):
    response = api_client.post(
        f"{HEADLESS}/auth/signup",
        {"email": "new@example.com", "password": "long-and-random-42"},
        format="json",
    )
    assert response.status_code == 400
    assert {error["param"] for error in response.json()["errors"]} == {"first_name", "last_name"}
    assert not django_user_model.objects.filter(email="new@example.com").exists()
    assert mail.outbox == []


@pytest.mark.django_db
def test_login_with_email_and_password(api_client, verified_user):
    response = api_client.post(
        f"{HEADLESS}/auth/login",
        {"email": "ada@example.com", "password": "s3cret-pass-1"},
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["data"]["user"]["email"] == "ada@example.com"

    response = api_client.delete(f"{HEADLESS}/auth/session")
    assert response.status_code == 401  # logged out: no session anymore
    assert api_client.get("/api/v1/me").status_code == 403


@pytest.mark.django_db
def test_login_with_wrong_password_is_rejected(api_client, verified_user):
    response = api_client.post(
        f"{HEADLESS}/auth/login",
        {"email": "ada@example.com", "password": "nope"},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_password_reset_flow(api_client, verified_user):
    response = api_client.post(
        f"{HEADLESS}/auth/password/request", {"email": "ada@example.com"}, format="json"
    )
    assert response.status_code == 200
    assert len(mail.outbox) == 1
    match = re.search(r"/account/password/reset/key/([^\s/]+)", mail.outbox[0].body)
    assert match, mail.outbox[0].body
    key = unquote(match.group(1))

    response = api_client.post(
        f"{HEADLESS}/auth/password/reset",
        {"key": key, "password": "brand-new-pass-99"},
        format="json",
    )
    assert response.status_code in (200, 401)  # 401 = reset done, session not opened
    verified_user.refresh_from_db()
    assert verified_user.check_password("brand-new-pass-99")


@pytest.mark.django_db
def test_google_provider_is_configured(api_client):
    response = api_client.get(f"{HEADLESS}/config")
    assert response.status_code == 200
    providers = response.json()["data"]["socialaccount"]["providers"]
    assert [p["id"] for p in providers] == ["google"]
