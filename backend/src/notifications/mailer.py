"""
E-mail delivery: one `send_email` call, three interchangeable backends picked by EMAIL_BACKEND.

  console — writes the message to the log (default; local development)
  brevo   — Brevo transactional API over HTTPS (https://developers.brevo.com/reference/sendtransacemail).
            Hosts such as Render's free tier block outbound SMTP ports, HTTPS still works.
  smtp    — any SMTP server (Gmail app password, Mailtrap, a local relay...)

`send_email` never raises: a failed delivery is logged and reported as False, so a
broken mail provider can't break a password-reset request or a cron run.
"""
from __future__ import annotations

import asyncio
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage as _MimeMessage
from email.utils import formataddr
from typing import Optional

import httpx

from src import config
from src.config import logger

BREVO_URL = "https://api.brevo.com/v3/smtp/email"
_TIMEOUT = 10.0


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    text: str
    html: str
    to_name: Optional[str] = None


def brevo_payload(message: Email, sender_email: str, sender_name: str) -> dict:
    to = {"email": message.to}
    if message.to_name:
        to["name"] = message.to_name
    return {
        "sender": {"email": sender_email, "name": sender_name},
        "to": [to],
        "subject": message.subject,
        "htmlContent": message.html,
        "textContent": message.text,
    }


def mime_message(message: Email, sender_email: str, sender_name: str) -> _MimeMessage:
    mime = _MimeMessage()
    mime["From"] = formataddr((sender_name, sender_email))
    mime["To"] = formataddr((message.to_name or "", message.to))
    mime["Subject"] = message.subject
    mime.set_content(message.text)
    mime.add_alternative(message.html, subtype="html")
    return mime


async def _send_brevo(message: Email) -> None:
    if not config.BREVO_API_KEY:
        raise RuntimeError("BREVO_API_KEY is not set")
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            BREVO_URL,
            headers={"api-key": config.BREVO_API_KEY, "accept": "application/json"},
            json=brevo_payload(message, config.EMAIL_FROM, config.EMAIL_FROM_NAME),
        )
    if resp.status_code >= 300:
        raise RuntimeError(f"Brevo answered {resp.status_code}: {resp.text[:300]}")


def _send_smtp_sync(message: Email) -> None:
    if not config.SMTP_HOST:
        raise RuntimeError("SMTP_HOST is not set")
    mime = mime_message(message, config.EMAIL_FROM, config.EMAIL_FROM_NAME)
    context = ssl.create_default_context()
    if config.SMTP_SECURITY == "ssl":
        server = smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=_TIMEOUT, context=context)
    else:
        server = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=_TIMEOUT)
    with server:
        if config.SMTP_SECURITY == "starttls":
            server.starttls(context=context)
        if config.SMTP_USERNAME:
            server.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
        server.send_message(mime)


async def send_email(message: Email) -> bool:
    """Deliver *message* with the configured backend. True on success; never raises."""
    backend = config.EMAIL_BACKEND
    try:
        if backend == "brevo":
            await _send_brevo(message)
        elif backend == "smtp":
            await asyncio.to_thread(_send_smtp_sync, message)
        else:
            logger.info("[email:console] to=%s subject=%r\n%s", message.to, message.subject, message.text)
        return True
    except Exception:
        logger.exception("E-mail delivery failed (backend=%s, to=%s, subject=%r)", backend, message.to, message.subject)
        return False
