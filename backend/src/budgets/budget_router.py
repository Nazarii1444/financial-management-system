from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.budgets.schemas import (
    BudgetCreate,
    BudgetMemberCreate,
    BudgetMemberOut,
    BudgetOut,
    BudgetUpdate,
)
from src.database import get_db
from src.dependencies import get_current_user
from src.models import Budget, BudgetMember, BudgetRole, BudgetType, Currencies, User

budget_router = APIRouter()


def _normalize_currency(raw: str) -> str:
    cur = raw.upper()
    allowed = {c.value for c in Currencies}
    if cur not in allowed:
        raise HTTPException(status_code=422, detail="Invalid currency")
    return cur


async def _get_budget_or_404(session: AsyncSession, budget_id: int) -> Budget:
    budget = await session.get(Budget, budget_id)
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    return budget


async def _get_membership_or_403(
    session: AsyncSession,
    budget_id: int,
    current_user: User,
) -> BudgetMember:
    stmt = select(BudgetMember).where(
        BudgetMember.budget_id == budget_id,
        BudgetMember.user_id == current_user.id_,
    )
    membership = (await session.execute(stmt)).scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=403, detail="Forbidden")
    return membership


@budget_router.post("", response_model=BudgetOut, status_code=status.HTTP_201_CREATED)
async def create_budget(
    payload: BudgetCreate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    currency = _normalize_currency(payload.currency)

    budget = Budget(
        owner_user_id=current_user.id_,
        name=payload.name,
        type=payload.type,
        currency=currency,
    )
    session.add(budget)
    await session.flush()

    owner_membership = BudgetMember(
        budget_id=budget.id_,
        user_id=current_user.id_,
        role=BudgetRole.OWNER,
    )
    session.add(owner_membership)

    await session.commit()
    await session.refresh(budget)
    return budget


@budget_router.get("", response_model=List[BudgetOut])
async def list_my_budgets(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = (
        select(Budget)
        .join(BudgetMember, BudgetMember.budget_id == Budget.id_)
        .where(BudgetMember.user_id == current_user.id_)
        .order_by(Budget.id_.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


@budget_router.get("/{budget_id}", response_model=BudgetOut)
async def get_budget(
    budget_id: int,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    budget = await _get_budget_or_404(session, budget_id)
    await _get_membership_or_403(session, budget.id_, current_user)
    return budget


@budget_router.patch("/{budget_id}", response_model=BudgetOut)
async def update_budget(
    budget_id: int,
    payload: BudgetUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    budget = await _get_budget_or_404(session, budget_id)
    membership = await _get_membership_or_403(session, budget.id_, current_user)

    if membership.role not in {BudgetRole.OWNER, BudgetRole.EDITOR}:
        raise HTTPException(status_code=403, detail="Forbidden")

    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        return budget

    if "currency" in updates and updates["currency"] is not None:
        updates["currency"] = _normalize_currency(updates["currency"])

    for field, value in updates.items():
        setattr(budget, field, value)

    await session.commit()
    await session.refresh(budget)
    return budget


@budget_router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget(
    budget_id: int,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    budget = await _get_budget_or_404(session, budget_id)
    membership = await _get_membership_or_403(session, budget.id_, current_user)

    if membership.role != BudgetRole.OWNER:
        raise HTTPException(status_code=403, detail="Only owner can delete budget")

    await session.delete(budget)
    await session.commit()
    return None


@budget_router.get("/{budget_id}/members", response_model=List[BudgetMemberOut])
async def list_budget_members(
    budget_id: int,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    budget = await _get_budget_or_404(session, budget_id)
    await _get_membership_or_403(session, budget.id_, current_user)

    stmt = select(BudgetMember).where(BudgetMember.budget_id == budget.id_).order_by(BudgetMember.id_.asc())
    return (await session.execute(stmt)).scalars().all()


@budget_router.post("/{budget_id}/members", response_model=BudgetMemberOut, status_code=status.HTTP_201_CREATED)
async def add_budget_member(
    budget_id: int,
    payload: BudgetMemberCreate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    budget = await _get_budget_or_404(session, budget_id)
    membership = await _get_membership_or_403(session, budget.id_, current_user)

    if membership.role != BudgetRole.OWNER:
        raise HTTPException(status_code=403, detail="Only owner can manage members")

    if budget.type == BudgetType.PERSONAL:
        raise HTTPException(status_code=422, detail="Personal budget cannot have additional members")

    if payload.user_id == budget.owner_user_id:
        raise HTTPException(status_code=422, detail="Owner is already a member")

    target_user = await session.get(User, payload.user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    existing_stmt = select(BudgetMember).where(
        BudgetMember.budget_id == budget.id_,
        BudgetMember.user_id == payload.user_id,
    )
    existing = (await session.execute(existing_stmt)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Member already exists")

    new_member = BudgetMember(
        budget_id=budget.id_,
        user_id=payload.user_id,
        role=payload.role,
    )
    session.add(new_member)
    await session.commit()
    await session.refresh(new_member)
    return new_member


@budget_router.delete("/{budget_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_budget_member(
    budget_id: int,
    user_id: int,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    budget = await _get_budget_or_404(session, budget_id)
    membership = await _get_membership_or_403(session, budget.id_, current_user)

    if membership.role != BudgetRole.OWNER:
        raise HTTPException(status_code=403, detail="Only owner can manage members")

    if user_id == budget.owner_user_id:
        raise HTTPException(status_code=422, detail="Owner cannot be removed")

    stmt = select(BudgetMember).where(
        BudgetMember.budget_id == budget.id_,
        BudgetMember.user_id == user_id,
    )
    member = (await session.execute(stmt)).scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    await session.delete(member)
    await session.commit()
    return None

