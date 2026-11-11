"""
Password policy (SEC-S4 + stronger rules), following NIST SP 800-63B:

- length: at least 10 characters, at most 72 UTF-8 bytes (bcrypt ignores the rest);
- strength: zxcvbn score ≥ 3 of 4 — it recognises dictionary words, names,
  keyboard walks, dates, repeats and l33t substitutions that composition rules
  ("one uppercase, one digit, one symbol") let through;
- context: no username or email in the password;
- blocklists: the bundled common-password lists and HaveIBeenPwned (k-anonymity:
  only the first 5 hex chars of the SHA-1 leave the server).

No forced uppercase / digit / symbol and no forced rotation: NIST recommends
against both because they push people to predictable patterns.
"""
import hashlib
from dataclasses import dataclass, field
from typing import Iterable, List, Optional

import httpx
from zxcvbn import zxcvbn

from src.auth.password_validator import validate_password as not_in_common_lists
from src.config import logger

MIN_LENGTH = 10
MAX_BYTES = 72          # bcrypt limit
MIN_SCORE = 3           # zxcvbn: 0 too guessable … 4 very unguessable
_ANALYSE_CHARS = 100    # zxcvbn cost grows with length; the first 100 chars decide the score
_APP_WORDS = ["financehub", "finance", "money", "budget", "гроші", "фінанси"]

# Messages are part of the API (the frontend maps them to translations by substring)
MSG_SHORT = f"Password must be at least {MIN_LENGTH} characters"
MSG_LONG = f"Password is too long (max {MAX_BYTES} bytes)"
MSG_PERSONAL = "Password must not contain your name or email"
MSG_COMMON = "Password too common"
MSG_WEAK = "Password is too easy to guess"
MSG_LEAKED = "Password found in leaked databases"


@dataclass
class PasswordReport:
    score: int                       # 0..4
    errors: List[str] = field(default_factory=list)
    codes: List[str] = field(default_factory=list)
    warning: Optional[str] = None    # zxcvbn feedback (English)
    suggestions: List[str] = field(default_factory=list)
    crack_time: Optional[str] = None  # offline attack on a slow hash, e.g. "3 years"

    @property
    def acceptable(self) -> bool:
        return not self.errors


def _context_words(username: Optional[str], email: Optional[str]) -> List[str]:
    words = [username or ""]
    if email:
        local = email.split("@")[0]
        words += [email, local, *local.replace("_", ".").replace("-", ".").split(".")]
    return [w.lower() for w in words if len(w) >= 3]


def evaluate(password: str, username: Optional[str] = None, email: Optional[str] = None,
             extra_inputs: Iterable[str] = ()) -> PasswordReport:
    """Offline checks (no network) — cheap enough for a live strength meter."""
    context = _context_words(username, email)
    result = zxcvbn(password[:_ANALYSE_CHARS], user_inputs=[*context, *extra_inputs, *_APP_WORDS]) if password else None
    report = PasswordReport(
        score=result["score"] if result else 0,
        warning=(result["feedback"]["warning"] or None) if result else None,
        suggestions=list(result["feedback"]["suggestions"]) if result else [],
        crack_time=str(result["crack_times_display"]["offline_slow_hashing_1e4_per_second"]) if result else None,
    )

    def fail(code: str, message: str) -> None:
        report.codes.append(code)
        report.errors.append(message)

    if len(password) < MIN_LENGTH:
        fail("too_short", MSG_SHORT)
    if len(password.encode("utf-8")) > MAX_BYTES:
        fail("too_long", MSG_LONG)
    lowered = password.lower()
    if any(word in lowered for word in context):
        fail("personal", MSG_PERSONAL)
    if not not_in_common_lists(password):
        fail("common", MSG_COMMON)
    if report.score < MIN_SCORE and "too_short" not in report.codes:
        fail("weak", MSG_WEAK)
    return report


async def is_breached(password: str, timeout: float = 5.0) -> Optional[bool]:
    """HaveIBeenPwned range query. None when the service can't be reached."""
    sha1 = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    prefix, suffix = sha1[:5], sha1[5:]
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            # Add-Padding: the response size no longer hints at which prefix bucket was asked for
            resp = await client.get(f"https://api.pwnedpasswords.com/range/{prefix}", headers={"Add-Padding": "true"})
            resp.raise_for_status()
    except Exception:
        logger.warning("HIBP check skipped: service unreachable")
        return None
    for line in resp.text.splitlines():
        candidate, _, count = line.partition(":")
        if candidate.strip() == suffix:
            return int(count or 0) > 0   # padding rows have count 0
    return False


async def check_password(password: str, username: Optional[str] = None, email: Optional[str] = None) -> PasswordReport:
    """Full check for signup / password change: offline rules + HIBP (skipped if unreachable)."""
    report = evaluate(password, username, email)
    if report.acceptable and await is_breached(password):
        report.codes.append("leaked")
        report.errors.append(MSG_LEAKED)
    return report
