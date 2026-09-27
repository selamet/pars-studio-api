"""Template-based transactional email, queued through the task backend."""

from django.conf import settings
from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string

from .tasks import send_email


def send_templated_email(
    template: str,
    context: dict,
    to: list[str],
    *,
    reply_to: list[str] | None = None,
) -> None:
    """
    Renders `templates/emails/<template>_subject.txt`, `<template>.txt` and,
    when present, `<template>.html`, then enqueues delivery.
    """
    context = {"site_name": "Pars Studio", "frontend_url": settings.FRONTEND_URL, **context}
    subject = " ".join(render_to_string(f"emails/{template}_subject.txt", context).split())
    body = render_to_string(f"emails/{template}.txt", context)
    try:
        html_body = render_to_string(f"emails/{template}.html", context)
    except TemplateDoesNotExist:
        html_body = None
    send_email.enqueue(
        subject=subject,
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=to,
        html_body=html_body,
        reply_to=reply_to,
    )
