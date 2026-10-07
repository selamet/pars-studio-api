from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.conf import settings
from django.core import mail
from django.template.loader import render_to_string

from apps.catalog.models import ServiceProduct
from apps.core.emails import email_context
from apps.orders.fulfilment import send_order_emails
from apps.orders.models import Order, OrderItem

HEADLESS = "/_allauth/browser/v1"
TEMPLATES = Path(settings.BASE_DIR) / "templates"


def html_part(message) -> str:
    return next(content for content, mimetype in message.alternatives if mimetype == "text/html")


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("accept_language", "subject", "heading"),
    [
        ("tr-TR,tr;q=0.9,en;q=0.8", "Pars Studio — E-posta adresini doğrula", "E-postanı doğrula."),
        ("en-US,en;q=0.9", "Pars Studio — Confirm your email address", "Confirm your email."),
        ("de-DE", "Pars Studio — Confirm your email address", "Confirm your email."),
    ],
)
def test_signup_email_is_branded_in_the_browser_language(
    api_client, accept_language, subject, heading
):
    api_client.post(
        f"{HEADLESS}/auth/signup",
        {"email": f"new-{accept_language[:2]}@example.com", "password": "long-and-random-42"},
        format="json",
        HTTP_ACCEPT_LANGUAGE=accept_language,
    )
    [message] = mail.outbox
    assert message.subject == subject
    html = html_part(message)
    assert heading in html
    assert f"{settings.FRONTEND_URL}/pars-studios-logo.png" in html
    assert "/account/verify-email/" in html
    assert "/account/verify-email/" in message.body


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("locale", "subject", "phrase", "cta"),
    [
        ("tr", "Pars Studio — Siparişin onaylandı (PS-T-1)", "Teşekkürler", "Siparişi aç"),
        ("en", "Pars Studio — Order PS-T-1 confirmed", "Thank you", "Open your order"),
    ],
)
def test_order_emails_use_the_order_language_and_turkish_for_the_studio(
    verified_user, locale, subject, phrase, cta
):
    order = Order.objects.create(
        number="PS-T-1",
        user=verified_user,
        customer_email=verified_user.email,
        locale=locale,
        subtotal=Decimal("60.00"),
        total=Decimal("60.00"),
        status=Order.Status.PAID,
    )
    product = ServiceProduct.objects.create(
        name="Single Mastering", slug="single-mastering", kind="mastering", price_usd=60
    )
    OrderItem.objects.create(
        order=order,
        item_type=OrderItem.ItemType.SERVICE,
        service_product=product,
        title="Single Mastering",
        unit_price=Decimal("60.00"),
        line_total=Decimal("60.00"),
    )

    send_order_emails(order, ["Exclusive already sold"])

    customer, studio = mail.outbox
    assert customer.subject == subject
    assert phrase in html_part(customer)
    assert cta in html_part(customer)
    assert f"/{locale}/account/orders/PS-T-1" in customer.body

    assert studio.to == [settings.STUDIO_NOTIFICATION_EMAIL]
    assert "Yeni sipariş PS-T-1" in studio.subject
    assert "Elle müdahale gerekiyor" in html_part(studio)
    assert f"{settings.API_URL}/admin/orders/order/{order.pk}/change/" in studio.body


def _fake_context() -> dict:
    reservation = SimpleNamespace(
        code="AB12",
        customer_name="Ada",
        artist_name="Ada L.",
        customer_email="ada@example.com",
        customer_phone="+90 555",
        session_date=None,
        start_time=None,
        end_time=None,
        duration_hours=2,
        price_usd=Decimal("80.00"),
        project_description="EP",
        reference_links="",
    )
    service_order = SimpleNamespace(
        id=1,
        user=SimpleNamespace(email="ada@example.com"),
        files=SimpleNamespace(count=2),
        due_at=None,
        revisions_left=1,
    )
    return {
        "order": SimpleNamespace(number="PS-1", total=Decimal("1.00"), customer_email="a@b.c"),
        "items": [SimpleNamespace(title="Beat", line_total=Decimal("1.00"))],
        "problems": [],
        "reservation": reservation,
        "service_label": "Miks",
        "service_order": service_order,
        "event": SimpleNamespace(to_status="delivered", message="Enjoy"),
        "status_label": "Delivered",
        "product_name": "Mixing",
        "order_number": "PS-1",
        "email": "ada@example.com",
        "activate_url": "https://example.test/verify",
        "password_reset_url": "https://example.test/reset",
        "signup_url": "https://example.test/signup",
        "cta_url": "https://example.test/cta",
        "cta_label": "Open",
    }


HTML_TEMPLATES = sorted(
    str(path.relative_to(TEMPLATES))
    for folder in ("emails", "account/email")
    for path in (TEMPLATES / folder).glob("*.html")
    if path.name not in {"base.html"} and not path.name.startswith("_")
)


@pytest.mark.parametrize("template", HTML_TEMPLATES)
@pytest.mark.parametrize("locale", ["en", "tr"])
def test_every_html_email_renders_in_the_shared_layout(template, locale):
    html = render_to_string(template, {**_fake_context(), **email_context(locale)})
    assert html.lstrip().startswith("<!doctype html>")
    assert f'<html lang="{locale}">' in html
    assert "pars-studios-logo.png" in html
    assert "{%" not in html and "{{" not in html
