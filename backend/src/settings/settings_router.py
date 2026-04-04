"""
Settings router  —  /api/settings/*

Sections
--------
  /profile            — display name, avatar, timezone
  /currency           — default currency
  /notifications      — per-event and per-channel notification toggles
  /subscription       — plan info + upgrade / downgrade
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.dependencies import get_current_user
from src.models import Currencies, NotificationPreferences, SubscriptionPlan, User
from src.settings.schemas import (
    CurrencySettingOut,
    CurrencySettingUpdate,
    EmailChangeRequest,
    NotificationPreferencesOut,
    NotificationPreferencesUpdate,
    ProfileOut,
    ProfileUpdate,
    SubscriptionFeature,
    SubscriptionOut,
    SubscriptionUpgradeOut,
)

settings_router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Profile
# ─────────────────────────────────────────────────────────────────────────────

@settings_router.get(
    "/profile",
    response_model=ProfileOut,
    summary="Get current user's display profile",
)
async def get_profile(current_user: User = Depends(get_current_user)):
    return current_user


@settings_router.patch(
    "/profile",
    response_model=ProfileOut,
    summary="Update display name, avatar URL, timezone",
)
async def update_profile(
    payload: ProfileUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = payload.model_dump(exclude_unset=True)
    if not data:
        return current_user

    # Username uniqueness check
    if "username" in data:
        taken = (
            await session.execute(
                select(User.id_).where(
                    User.username == data["username"],
                    User.id_ != current_user.id_,
                )
            )
        ).scalar_one_or_none()
        if taken:
            raise HTTPException(status_code=409, detail="Username already taken")

    for field, value in data.items():
        setattr(current_user, field, value)

    await session.commit()
    await session.refresh(current_user)
    return current_user


# ─────────────────────────────────────────────────────────────────────────────
# 2. Currency
# ─────────────────────────────────────────────────────────────────────────────

@settings_router.get(
    "/currency",
    response_model=CurrencySettingOut,
    summary="Get current default currency",
)
async def get_currency(current_user: User = Depends(get_current_user)):
    return {"default_currency": current_user.default_currency}


@settings_router.patch(
    "/currency",
    response_model=CurrencySettingOut,
    summary="Change default currency (ISO-4217)",
)
async def update_currency(
    payload: CurrencySettingUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cur = payload.default_currency.strip().upper()
    if cur not in {c.value for c in Currencies}:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported currency '{cur}'. Allowed: {[c.value for c in Currencies]}",
        )
    current_user.default_currency = cur
    await session.commit()
    return {"default_currency": current_user.default_currency}


# ─────────────────────────────────────────────────────────────────────────────
# 3. Email management
# ─────────────────────────────────────────────────────────────────────────────

@settings_router.patch(
    "/email",
    response_model=ProfileOut,
    summary="Change account email address",
)
async def change_email(
    payload: EmailChangeRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Change email address.
    Checks uniqueness. In production, send a verification link before applying.
    TODO: send confirmation email before persisting.
    """
    new_email = payload.new_email.strip().lower()
    if new_email == current_user.email.lower():
        raise HTTPException(status_code=409, detail="New email is the same as current email")

    taken = (
        await session.execute(
            select(User.id_).where(User.email == new_email, User.id_ != current_user.id_)
        )
    ).scalar_one_or_none()
    if taken:
        raise HTTPException(status_code=409, detail="Email already registered")

    current_user.email = new_email
    await session.commit()
    await session.refresh(current_user)
    return current_user


# ─────────────────────────────────────────────────────────────────────────────
# 4. Notification preferences
# ─────────────────────────────────────────────────────────────────────────────

async def _get_or_create_prefs(session: AsyncSession, user: User) -> NotificationPreferences:
    """Lazily create notification prefs row on first access."""
    prefs = (
        await session.execute(
            select(NotificationPreferences).where(NotificationPreferences.user_id == user.id_)
        )
    ).scalar_one_or_none()

    if prefs is None:
        prefs = NotificationPreferences(user_id=user.id_)
        session.add(prefs)
        await session.commit()
        await session.refresh(prefs)

    return prefs


@settings_router.get(
    "/notifications",
    response_model=NotificationPreferencesOut,
    summary="Get notification preferences (auto-created with defaults on first call)",
)
async def get_notification_preferences(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _get_or_create_prefs(session, current_user)


@settings_router.patch(
    "/notifications",
    response_model=NotificationPreferencesOut,
    summary="Toggle individual notification channels and events",
)
async def update_notification_preferences(
    payload: NotificationPreferencesUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    prefs = await _get_or_create_prefs(session, current_user)

    data = payload.model_dump(exclude_unset=True)
    if not data:
        return prefs

    for field, value in data.items():
        setattr(prefs, field, value)

    await session.commit()
    await session.refresh(prefs)
    return prefs


# ─────────────────────────────────────────────────────────────────────────────
# 5. Subscription
# ─────────────────────────────────────────────────────────────────────────────

def _build_features(plan: SubscriptionPlan):
    """Returns the feature list for a given plan."""
    is_pro = plan == SubscriptionPlan.PRO
    return [
        SubscriptionFeature(label="Unlimited transactions",        available=is_pro),
        SubscriptionFeature(label="Unlimited goals",               available=is_pro),
        SubscriptionFeature(label="Unlimited budgets",             available=is_pro),
        SubscriptionFeature(label="Advanced analytics",            available=is_pro),
        SubscriptionFeature(label="Recurring transactions",        available=is_pro),
        SubscriptionFeature(label="CSV / Excel import",            available=is_pro),
        SubscriptionFeature(label="Budget member management",      available=is_pro),
        SubscriptionFeature(label="Priority support",              available=is_pro),
        SubscriptionFeature(label="Basic dashboard",               available=True),
        SubscriptionFeature(label="Goals (up to 3)",               available=True),
        SubscriptionFeature(label="Up to 50 transactions / month", available=True),
        SubscriptionFeature(label="1 personal budget",             available=True),
    ]


@settings_router.get(
    "/subscription",
    response_model=SubscriptionOut,
    summary="Get current subscription plan and feature availability",
)
async def get_subscription(current_user: User = Depends(get_current_user)):
    return SubscriptionOut(
        plan=current_user.subscription_plan,
        features=_build_features(current_user.subscription_plan),
    )


@settings_router.post(
    "/subscription/upgrade",
    response_model=SubscriptionUpgradeOut,
    status_code=status.HTTP_200_OK,
    summary="Upgrade to Pro plan",
)
async def upgrade_subscription(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.subscription_plan == SubscriptionPlan.PRO:
        raise HTTPException(status_code=409, detail="Already on Pro plan")

    # TODO: integrate with payment provider (e.g. Stripe) before setting plan
    current_user.subscription_plan = SubscriptionPlan.PRO
    await session.commit()
    return SubscriptionUpgradeOut(
        plan=SubscriptionPlan.PRO,
        message="Upgraded to Pro. Enjoy unlimited access!",
    )


@settings_router.post(
    "/subscription/downgrade",
    response_model=SubscriptionUpgradeOut,
    status_code=status.HTTP_200_OK,
    summary="Downgrade to Free plan",
)
async def downgrade_subscription(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.subscription_plan == SubscriptionPlan.FREE:
        raise HTTPException(status_code=409, detail="Already on Free plan")

    current_user.subscription_plan = SubscriptionPlan.FREE
    await session.commit()
    return SubscriptionUpgradeOut(
        plan=SubscriptionPlan.FREE,
        message="Downgraded to Free plan.",
    )

