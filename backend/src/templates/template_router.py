"""
Transaction templates — one-click presets ("morning coffee") + suggestions.

A template never fires on its own (that's what recurring transactions are
for); `POST /{id}/use` creates a Transaction dated now via the shared
`create_user_transaction` path, optionally with an overridden amount.
`GET /suggestions` proposes templates for expenses repeated ≥ 5 times in the
last 30 days (see `services/suggestions.py`).
"""
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.dependencies import get_current_user
from src.models import (
    TemplateSuggestionDismissal,
    Transaction,
    TransactionKind,
    TransactionTemplate,
    User,
)
from src.templates.schemas import (
    TemplateCreate,
    TemplateOut,
    TemplateSuggestionDismiss,
    TemplateSuggestionOut,
    TemplateUpdate,
    TemplateUse,
)
from src.templates.services.suggestions import WINDOW_DAYS, similarity_key, suggest_templates
from src.templates.services.template_service import normalize_currency, normalize_tags, use_template
from src.transactions.categories import validate_category
from src.transactions.schemas import TransactionOut
from src.transactions.services.transaction_service import transaction_to_out

template_router = APIRouter()


async def _get_user_template_or_404(session: AsyncSession, template_id: int, user_id: int) -> TransactionTemplate:
    stmt = select(TransactionTemplate).where(
        TransactionTemplate.id_ == template_id,
        TransactionTemplate.user_id == user_id,
    )
    template = (await session.execute(stmt)).scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


# ── CRUD ──────────────────────────────────────────────────────────────────────

@template_router.get("", response_model=List[TemplateOut])
async def list_templates(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = (
        select(TransactionTemplate)
        .where(TransactionTemplate.user_id == current_user.id_)
        .order_by(TransactionTemplate.use_count.desc(), TransactionTemplate.name.asc())
    )
    return (await session.execute(stmt)).scalars().all()


@template_router.post("", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: TemplateCreate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    validate_category(payload.kind, payload.category_name)
    template = TransactionTemplate(
        user_id=current_user.id_,
        name=payload.name.strip(),
        amount=payload.amount,
        kind=payload.kind,
        category_name=payload.category_name.strip().lower(),
        currency=normalize_currency(payload.currency, current_user),
        tags=normalize_tags(payload.tags),
        note=payload.note,
        use_count=0,
    )
    session.add(template)
    await session.commit()
    await session.refresh(template)
    return template


# ── Suggestions (declared before /{template_id}) ──────────────────────────────

@template_router.get("/suggestions", response_model=List[TemplateSuggestionOut])
async def list_suggestions(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    since = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)
    txs = (await session.execute(
        select(Transaction).where(
            Transaction.user_id == current_user.id_,
            Transaction.kind == TransactionKind.EXPENSE,
            Transaction.date >= since,
        )
    )).scalars().all()
    templates = (await session.execute(
        select(TransactionTemplate).where(TransactionTemplate.user_id == current_user.id_)
    )).scalars().all()
    dismissed = (await session.execute(
        select(TemplateSuggestionDismissal.key).where(TemplateSuggestionDismissal.user_id == current_user.id_)
    )).scalars().all()

    existing = [similarity_key(t.name, t.category_name, t.currency) for t in templates]
    return [s.__dict__ for s in suggest_templates(txs, existing, dismissed)]


@template_router.post("/suggestions/dismiss", status_code=status.HTTP_204_NO_CONTENT)
async def dismiss_suggestion(
    payload: TemplateSuggestionDismiss,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = pg_insert(TemplateSuggestionDismissal).values(
        user_id=current_user.id_, key=payload.key,
    ).on_conflict_do_nothing(constraint="uq_template_dismissal_user_key")
    await session.execute(stmt)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@template_router.get("/{template_id}", response_model=TemplateOut)
async def get_template(
    template_id: int,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await _get_user_template_or_404(session, template_id, current_user.id_)


@template_router.patch("/{template_id}", response_model=TemplateOut)
async def update_template(
    template_id: int,
    payload: TemplateUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    template = await _get_user_template_or_404(session, template_id, current_user.id_)
    data = payload.model_dump(exclude_unset=True)
    if not data:
        return template

    for field in ("name", "amount", "kind", "category_name"):
        if field in data and data[field] is None:
            raise HTTPException(status_code=422, detail=f"'{field}' cannot be null")
    if "name" in data:
        data["name"] = data["name"].strip()
    if "category_name" in data:
        data["category_name"] = data["category_name"].strip().lower()
    if "currency" in data:
        data["currency"] = normalize_currency(data["currency"], current_user)
    if "tags" in data:
        data["tags"] = normalize_tags(data["tags"] or [])
    if "kind" in data or "category_name" in data:
        validate_category(data.get("kind", template.kind), data.get("category_name", template.category_name))

    for key, value in data.items():
        setattr(template, key, value)
    await session.commit()
    await session.refresh(template)
    return template


@template_router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: int,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    template = await _get_user_template_or_404(session, template_id, current_user.id_)
    await session.delete(template)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Use ───────────────────────────────────────────────────────────────────────

@template_router.post("/{template_id}/use", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
async def use_template_endpoint(
    template_id: int,
    payload: Optional[TemplateUse] = Body(default=None),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    payload = payload or TemplateUse()
    template = await _get_user_template_or_404(session, template_id, current_user.id_)
    tx = await use_template(
        session, current_user, template,
        amount=payload.amount, remember_amount=payload.remember_amount,
    )
    await session.commit()
    await session.refresh(tx)
    await session.refresh(current_user)
    return transaction_to_out(tx, current_user)
