import pytest
from rest_framework.test import APIClient


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def user(db, django_user_model):
    return django_user_model.objects.create_user(email="ada@example.com", password="s3cret-pass-1")


@pytest.fixture
def verified_user(user):
    from allauth.account.models import EmailAddress

    EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
    return user
