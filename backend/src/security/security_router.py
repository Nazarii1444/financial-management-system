"""
/api/security/* — what the user sees on Settings → Security.

    GET  /events                     login & activity history (SEC-S1)
    GET  /password-health            password age, strength, leak status + recommendations (SEC-S4)
    POST /password-health/check      re-check the current password now (needs the password)
    POST /password-strength          live strength meter for signup / change forms (no auth, no HIBP)
"""
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.auth_services import refresh_password_health
from src.database import get_db
from src.dependencies import get_current_user
from src.models import SecurityEvent, User, WebAuthnCredential
from src.security import password_policy
from src.security.events import describe_user_agent
from src.utils.auth_services import verify_password

security_router = APIRouter()

PASSWORD_OLD_DAYS = 365   # informational only — NIST advises against forced rotation


class SecurityEventOut(BaseModel):
    id_: int
    event_type: str
    success: bool
    method: Optional[str]
    ip: Optional[str]
    device: Optional[str]       # "Chrome · Windows"
    device_type: Optional[str]  # mobile | desktop
    details: Optional[dict]
    created_at: datetime


class SecurityEventsOut(BaseModel):
    items: List[SecurityEventOut]
    total: int
    failed_last_30_days: int


class PasswordHealthOut(BaseModel):
    changed_at: Optional[datetime]
    age_days: Optional[int]
    score: Optional[int]               # 0..4
    breached: Optional[bool]
    checked_at: Optional[datetime]
    twofa_enabled: bool
    passkeys: int
    level: str                         # good | fair | weak
    recommendations: List[str]         # codes, translated by the frontend


class PasswordCheckIn(BaseModel):
    password: str = Field(max_length=256)


class StrengthIn(BaseModel):
    password: str = Field(max_length=256)
    username: Optional[str] = Field(None, max_length=64)
    email: Optional[str] = Field(None, max_length=255)


class StrengthOut(BaseModel):
    score: int
    acceptable: bool
    codes: List[str]
    errors: List[str]
    warning: Optional[str]
    suggestions: List[str]
    crack_time: Optional[str]
    min_length: int = password_policy.MIN_LENGTH


@security_router.get("/events", response_model=SecurityEventsOut, summary="Login & activity history")
async def list_events(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (await session.execute(
        select(SecurityEvent).where(SecurityEvent.user_id == current_user.id_)
        .order_by(SecurityEvent.created_at.desc(), SecurityEvent.id_.desc()).limit(limit).offset(offset)
    )).scalars().all()
    total = (await session.execute(
        select(func.count()).select_from(SecurityEvent).where(SecurityEvent.user_id == current_user.id_)
    )).scalar_one()
    month_ago = datetime.now(timezone.utc).timestamp() - 30 * 86400
    failed = (await session.execute(
        select(func.count()).select_from(SecurityEvent).where(
            SecurityEvent.user_id == current_user.id_, SecurityEvent.success.is_(False),
            SecurityEvent.created_at >= datetime.fromtimestamp(month_ago, timezone.utc),
        )
    )).scalar_one()
    items = []
    for e in rows:
        ua = describe_user_agent(e.user_agent)
        items.append(SecurityEventOut(
            id_=e.id_, event_type=e.event_type, success=e.success, method=e.method, ip=e.ip,
            device=ua["label"], device_type=ua["device"], details=e.details, created_at=e.created_at,
        ))
    return SecurityEventsOut(items=items, total=total, failed_last_30_days=failed)


def password_health(user: User, passkeys: int, now: Optional[datetime] = None) -> PasswordHealthOut:
    """Pure: the stored snapshots → level + recommendation codes."""
    now = now or datetime.now(timezone.utc)
    age = (now - user.password_changed_at).days if user.password_changed_at else None
    recs: List[str] = []
    if user.password_breached:
        recs.append("change_breached")
    if user.password_score is not None and user.password_score < password_policy.MIN_SCORE:
        recs.append("change_weak")
    if age is not None and age > PASSWORD_OLD_DAYS:
        recs.append("password_old")
    if user.password_score is None or user.password_checked_at is None:
        recs.append("run_check")
    if not user.twofa_enabled and not passkeys:
        recs.append("enable_2fa_or_passkey")
    elif not passkeys:
        recs.append("add_passkey")

    if user.password_breached or (user.password_score is not None and user.password_score < 2):
        level = "weak"
    elif {"change_weak", "password_old", "enable_2fa_or_passkey"} & set(recs):
        level = "fair"
    else:
        level = "good"
    return PasswordHealthOut(
        changed_at=user.password_changed_at, age_days=age, score=user.password_score,
        breached=user.password_breached, checked_at=user.password_checked_at,
        twofa_enabled=bool(user.twofa_enabled), passkeys=passkeys, level=level, recommendations=recs,
    )


async def _passkey_count(session: AsyncSession, user_id: int) -> int:
    return (await session.execute(
        select(func.count()).select_from(WebAuthnCredential).where(WebAuthnCredential.user_id == user_id)
    )).scalar_one()


@security_router.get("/password-health", response_model=PasswordHealthOut, summary="Password age, strength and leak status")
async def get_password_health(session: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    return password_health(current_user, await _passkey_count(session, current_user.id_))


@security_router.post("/password-health/check", response_model=PasswordHealthOut, summary="Re-check the current password")
async def check_password_health(
    payload: PasswordCheckIn,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if len(payload.password.encode("utf-8")) > password_policy.MAX_BYTES or not verify_password(payload.password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    current_user.password_score = None   # re-score with the current rules
    await refresh_password_health(session, current_user, payload.password)
    return password_health(current_user, await _passkey_count(session, current_user.id_))


@security_router.post("/password-strength", response_model=StrengthOut, summary="Live password strength (offline checks)")
async def password_strength(payload: StrengthIn):
    report = password_policy.evaluate(payload.password, payload.username, payload.email)
    return StrengthOut(
        score=report.score, acceptable=report.acceptable, codes=report.codes, errors=report.errors,
        warning=report.warning, suggestions=report.suggestions, crack_time=report.crack_time,
    )
