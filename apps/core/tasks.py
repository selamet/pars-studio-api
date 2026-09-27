from django.core.mail import EmailMultiAlternatives
from django.tasks import task


@task()
def send_email(
    subject: str,
    body: str,
    from_email: str,
    to: list[str],
    html_body: str | None = None,
    reply_to: list[str] | None = None,
    attachments: list[list[str]] | None = None,
) -> None:
    """
    Deliver one email. Runs in the worker so web requests never wait on SMTP.
    `attachments` is a JSON-friendly list of [filename, text_content, mimetype].
    """
    message = EmailMultiAlternatives(
        subject=subject, body=body, from_email=from_email, to=to, reply_to=reply_to
    )
    if html_body:
        message.attach_alternative(html_body, "text/html")
    for filename, content, mimetype in attachments or []:
        message.attach(filename, content, mimetype)
    message.send()
