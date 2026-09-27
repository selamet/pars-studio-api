import json
from unittest import mock

import pytest
from django.core.mail import EmailMultiAlternatives

from apps.core.mail import ResendEmailBackend


def test_resend_backend_posts_json_with_html_and_attachments():
    backend = ResendEmailBackend(api_key="re_test")
    message = EmailMultiAlternatives(
        "Hi", "plain", "Pars <noreply@example.com>", ["to@example.com"], reply_to=["r@example.com"]
    )
    message.attach_alternative("<b>html</b>", "text/html")
    message.attach("a.ics", "BEGIN:VCALENDAR", "text/calendar")

    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"id":"1"}'

    def fake_urlopen(request, timeout):
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data)
        return Response()

    with mock.patch("apps.core.mail.urllib.request.urlopen", fake_urlopen):
        assert backend.send_messages([message]) == 1

    assert captured["headers"]["Authorization"] == "Bearer re_test"
    body = captured["body"]
    assert body["to"] == ["to@example.com"] and body["reply_to"] == ["r@example.com"]
    assert body["html"] == "<b>html</b>" and body["text"] == "plain"
    assert body["attachments"][0]["filename"] == "a.ics"


def test_resend_backend_surfaces_api_errors():
    import urllib.error

    backend = ResendEmailBackend(api_key="re_test")
    message = EmailMultiAlternatives("Hi", "plain", "a@example.com", ["b@example.com"])
    error = urllib.error.HTTPError(
        "u", 403, "Forbidden", {}, mock.Mock(read=lambda: b"domain not verified")
    )
    with mock.patch("apps.core.mail.urllib.request.urlopen", side_effect=error):
        with pytest.raises(RuntimeError, match="403"):
            backend.send_messages([message])


def test_backend_works_through_mailers(settings):
    """send() goes through mail.mailers, which passes alias= and fail_silently=."""
    from django.core.mail import EmailMessage

    settings.MAILERS = {
        "default": {"BACKEND": "apps.core.mail.ResendEmailBackend", "OPTIONS": {"api_key": "re_x"}}
    }
    with mock.patch("apps.core.mail.ResendEmailBackend._send") as send:
        assert EmailMessage("s", "b", "a@example.com", ["b@example.com"]).send() == 1
    send.assert_called_once()
