"""
Security activity history (SEC-S1).

`record_event` is called from the auth flows (login, 2FA, passkeys, OAuth) and
from sensitive changes (password, email, 2FA, passkeys, exports). Failed logins
are recorded only for existing accounts — an unknown email has nobody to show
them to. The user agent is stored raw and described on read, so the parser can
improve without a migration.
"""
import re
from typing import Any, Dict, Optional

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import TRUST_PROXY_HEADERS, logger
from src.models import SecurityEvent


class EventType:
    LOGIN = "login"                      # success=False: wrong password / code / passkey
    TWOFA_CHALLENGE = "twofa_challenge"  # password ok, waiting for the TOTP code
    SIGNUP = "signup"
    LOGOUT = "logout"
    PASSWORD_CHANGED = "password_changed"
    EMAIL_CHANGED = "email_changed"
    TWOFA_ENABLED = "twofa_enabled"
    TWOFA_DISABLED = "twofa_disabled"
    PASSKEY_ADDED = "passkey_added"
    PASSKEY_REMOVED = "passkey_removed"
    DATA_EXPORTED = "data_exported"


def client_ip(request: Optional[Request]) -> Optional[str]:
    if request is None:
        return None
    if TRUST_PROXY_HEADERS:
        # Behind our own reverse proxy (nginx in docker-compose): the left-most address is the client
        forwarded = request.headers.get("x-forwarded-for", "")
        first = forwarded.split(",")[0].strip()
        if first:
            return first[:45]
    return request.client.host if request.client else None


async def record_event(
    db: AsyncSession,
    user_id: int,
    event_type: str,
    request: Optional[Request] = None,
    *,
    success: bool = True,
    method: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """Add an event and commit. Never raises: history must not break a login."""
    user_agent = request.headers.get("user-agent") if request else None
    try:
        db.add(SecurityEvent(
            user_id=user_id,
            event_type=event_type,
            success=success,
            method=method,
            ip=client_ip(request),
            user_agent=user_agent[:512] if user_agent else None,
            details=details,
        ))
        await db.commit()
    except Exception:
        logger.warning("Could not record security event %s for user id=%s", event_type, user_id, exc_info=True)
        await db.rollback()


# ── User agent → "Chrome on Windows" ──────────────────────────────────────────
# Order matters: Edge / Opera / Samsung UAs also contain "Chrome", Chrome contains "Safari".
_BROWSERS = [
    ("Edge", r"Edg(?:e|A|iOS)?/"),
    ("Opera", r"OPR/|Opera"),
    ("Samsung Internet", r"SamsungBrowser/"),
    ("Firefox", r"Firefox/|FxiOS/"),
    ("Chrome", r"Chrome/|CriOS/"),
    ("Safari", r"Safari/"),
]
_OS = [
    ("iOS", r"iPhone|iPad|iPod"),
    ("Android", r"Android"),
    ("Windows", r"Windows"),
    ("macOS", r"Mac OS X|Macintosh"),
    ("ChromeOS", r"CrOS"),
    ("Linux", r"Linux"),
]
_CLIENTS = [("API client", r"python-|httpx|curl/|Wget|PostmanRuntime|okhttp|locust")]


def describe_user_agent(user_agent: Optional[str]) -> Dict[str, Optional[str]]:
    ua = user_agent or ""
    browser = next((name for name, pattern in _BROWSERS + _CLIENTS if re.search(pattern, ua)), None)
    os_name = next((name for name, pattern in _OS if re.search(pattern, ua)), None)
    mobile = bool(re.search(r"Mobi|iPhone|Android", ua)) and "iPad" not in ua
    if browser and os_name:
        label = f"{browser} · {os_name}"
    else:
        label = browser or os_name or None
    return {"browser": browser, "os": os_name, "device": "mobile" if mobile else "desktop" if os_name else None, "label": label}
