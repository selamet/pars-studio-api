"""
Email backend that delivers through Resend's HTTPS API instead of SMTP.

Hosting providers often block outbound SMTP ports; port 443 is always open.
Configured through MAILERS with OPTIONS {"api_key": ...}.
"""

from __future__ import annotations

import base64
import json
import logging
import urllib.error
import urllib.request

from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

RESEND_ENDPOINT = "https://api.resend.com/emails"
# Resend sits behind Cloudflare, which rejects Python's default User-Agent (error 1010).
USER_AGENT = "pars-studio-api/1.0 (+https://api.studiospars.com)"


class ResendEmailBackend(BaseEmailBackend):
    def __init__(self, fail_silently=False, *, api_key: str = "", timeout: int = 20, **kwargs):
        # Same shape as Django's SMTP backend: keep fail_silently out of the
        # kwargs the base class validates against MAILERS options.
        super().__init__(**kwargs)
        self.fail_silently = fail_silently
        if not api_key:
            raise ValueError("ResendEmailBackend needs OPTIONS['api_key'].")
        self.api_key = api_key
        self.timeout = timeout

    def send_messages(self, email_messages) -> int:
        sent = 0
        for message in email_messages:
            try:
                self._send(message)
                sent += 1
            except Exception:
                if not self.fail_silently:
                    raise
                logger.exception("Resend delivery failed")
        return sent

    def _payload(self, message) -> dict:
        payload = {
            "from": message.from_email,
            "to": list(message.to),
            "subject": message.subject,
            "text": message.body,
        }
        if message.cc:
            payload["cc"] = list(message.cc)
        if message.bcc:
            payload["bcc"] = list(message.bcc)
        if message.reply_to:
            payload["reply_to"] = list(message.reply_to)
        for content, mimetype in getattr(message, "alternatives", []):
            if mimetype == "text/html":
                payload["html"] = content
        attachments = []
        for attachment in message.attachments:
            if isinstance(attachment, tuple):
                filename, content, _mimetype = attachment
            else:  # EmailAttachment (Django 5.2+)
                filename, content = attachment.filename, attachment.content
            if isinstance(content, str):
                content = content.encode()
            attachments.append(
                {"filename": filename, "content": base64.b64encode(content).decode()}
            )
        if attachments:
            payload["attachments"] = attachments
        return payload

    def _send(self, message) -> None:
        request = urllib.request.Request(
            RESEND_ENDPOINT,
            data=json.dumps(self._payload(message)).encode(),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:300]
            raise RuntimeError(f"Resend rejected the email ({exc.code}): {detail}") from exc
