from allauth.account.adapter import DefaultAccountAdapter

from apps.core.tasks import send_email


class AccountAdapter(DefaultAccountAdapter):
    """allauth adapter that hands rendered emails to the task queue."""

    def send_mail(self, template_prefix: str, email: str, context: dict) -> None:
        message = self.render_mail(template_prefix, email, context)
        html_body = next(
            (content for content, mimetype in message.alternatives if mimetype == "text/html"),
            None,
        )
        send_email.enqueue(
            subject=message.subject,
            body=message.body,
            from_email=message.from_email,
            to=list(message.to),
            html_body=html_body,
        )
