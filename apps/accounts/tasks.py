from django.core.mail import EmailMultiAlternatives
from django.tasks import task


@task()
def send_email(
    subject: str,
    body: str,
    from_email: str,
    to: list[str],
    html_body: str | None = None,
) -> None:
    """Deliver one email. Runs in the worker so web requests never wait on SMTP."""
    message = EmailMultiAlternatives(subject=subject, body=body, from_email=from_email, to=to)
    if html_body:
        message.attach_alternative(html_body, "text/html")
    message.send()
