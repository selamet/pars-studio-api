from allauth.account.adapter import DefaultAccountAdapter
from allauth.core import context as allauth_context
from django.utils import translation

from apps.core.emails import LOCALES, email_context
from apps.core.tasks import send_email


def request_locale(request) -> str:
    """The site language the visitor uses, from `Accept-Language`; English otherwise."""
    if request is None:
        return "en"
    language = translation.get_language_from_request(request)
    return language if language in LOCALES else "en"


class AccountAdapter(DefaultAccountAdapter):
    """allauth adapter that renders branded, localized emails and queues them."""

    def send_mail(self, template_prefix: str, email: str, context: dict) -> None:
        request = allauth_context.request
        locale = request_locale(request)
        context = {"request": request, "email": email, **context, **email_context(locale)}
        with translation.override(locale):
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
