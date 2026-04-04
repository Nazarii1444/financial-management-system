from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.dependencies import get_current_user
from src.goals.schemas import GoalCreate, GoalDepositWithdraw, GoalOut, GoalUpdate
from src.models import Currencies, Goal, User

goal_router = APIRouter()


# ── Guard ─────────────────────────────────────────────────────────────────────

async def _get_user_goal_or_404(session: AsyncSession, goal_id: int, user_id: int) -> Goal:
    stmt = select(Goal).where(Goal.id_ == goal_id, Goal.user_id == user_id)
    goal = (await session.execute(stmt)).scalar_one_or_none()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal


# ── CRUD ──────────────────────────────────────────────────────────────────────

@goal_router.post("", response_model=GoalOut, status_code=status.HTTP_201_CREATED)
async def create_goal(
        payload: GoalCreate,
        session: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    currency = payload.currency.strip().upper()
    if currency not in {c.value for c in Currencies}:
        raise HTTPException(status_code=422, detail="Invalid currency")

    goal = Goal(
        user_id=current_user.id_,
        name=payload.name,
        target_amount=payload.target_amount,
        saved_amount=Decimal("0"),
        currency=currency,
        description=payload.description,
        deadline=payload.deadline,
    )
    session.add(goal)
    await session.commit()
    await session.refresh(goal)
    return goal


@goal_router.get("", response_model=List[GoalOut])
async def list_goals(
        session: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
        q: Optional[str] = Query(None, description="Search by name (case-insensitive, partial match)"),
        is_completed: Optional[bool] = Query(None, description="Filter: true=completed, false=active"),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
):
    stmt = select(Goal).where(Goal.user_id == current_user.id_)

    if q:
        stmt = stmt.where(Goal.name.ilike(f"%{q}%"))  # fix: was == (exact match)

    if is_completed is not None:
        stmt = stmt.where(Goal.is_completed == is_completed)

    stmt = stmt.order_by(Goal.is_completed.asc(), Goal.created_at.desc()).offset(offset).limit(limit)
    return (await session.execute(stmt)).scalars().all()


@goal_router.get("/{goal_id}", response_model=GoalOut)
async def get_goal(
        goal_id: int,
        session: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    return await _get_user_goal_or_404(session, goal_id, current_user.id_)


@goal_router.patch("/{goal_id}", response_model=GoalOut)
async def update_goal(
        goal_id: int,
        payload: GoalUpdate,
        session: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    goal = await _get_user_goal_or_404(session, goal_id, current_user.id_)

    data = payload.model_dump(exclude_unset=True)   # fix: was manual if-checks
    if not data:
        return goal

    if "currency" in data and data["currency"]:
        cur = data["currency"].strip().upper()
        if cur not in {c.value for c in Currencies}:
            raise HTTPException(status_code=422, detail="Invalid currency")
        data["currency"] = cur

    for field, value in data.items():
        setattr(goal, field, value)

    await session.commit()
    await session.refresh(goal)
    return goal


@goal_router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_goal(
        goal_id: int,
        session: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    goal = await _get_user_goal_or_404(session, goal_id, current_user.id_)
    await session.delete(goal)
    await session.commit()
    return None


# ── Jar operations ─────────────────────────────────────────────────────────────

@goal_router.post("/{goal_id}/deposit", response_model=GoalOut)
async def deposit_to_goal(
        goal_id: int,
        payload: GoalDepositWithdraw,
        session: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """Add money to a savings jar."""
    goal = await _get_user_goal_or_404(session, goal_id, current_user.id_)
    if goal.is_completed:
        raise HTTPException(status_code=409, detail="Goal is already completed")

    goal.saved_amount = Decimal(str(goal.saved_amount)) + payload.amount

    # Auto-complete if target reached
    if goal.saved_amount >= goal.target_amount:
        goal.saved_amount = goal.target_amount   # cap at 100%
        goal.is_completed = True
        goal.completed_at = datetime.now(timezone.utc)

    await session.commit()
    await session.refresh(goal)
    return goal


@goal_router.post("/{goal_id}/withdraw", response_model=GoalOut)
async def withdraw_from_goal(
        goal_id: int,
        payload: GoalDepositWithdraw,
        session: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """Take money back from a savings jar."""
    goal = await _get_user_goal_or_404(session, goal_id, current_user.id_)

    new_saved = Decimal(str(goal.saved_amount)) - payload.amount
    if new_saved < 0:
        raise HTTPException(
            status_code=422,
            detail=f"Cannot withdraw {payload.amount} — only {goal.saved_amount} saved",
        )

    goal.saved_amount = new_saved

    # If goal was completed and money was taken out, reopen it automatically
    if goal.is_completed and goal.saved_amount < goal.target_amount:
        goal.is_completed = False
        goal.completed_at = None

    await session.commit()
    await session.refresh(goal)
    return goal


# ── Status transitions ─────────────────────────────────────────────────────────

@goal_router.post("/{goal_id}/close", response_model=GoalOut)
async def close_goal(
        goal_id: int,
        force: bool = Query(False, description="Close even if target not yet reached"),
        session: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """
    Mark goal as completed.
    Succeeds automatically when saved_amount >= target_amount.
    Pass ?force=true to close early (e.g. user decided to cancel goal).
    """
    goal = await _get_user_goal_or_404(session, goal_id, current_user.id_)
    if goal.is_completed:
        raise HTTPException(status_code=409, detail="Goal is already completed")

    if not force and goal.saved_amount < goal.target_amount:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Target not reached ({goal.saved_amount}/{goal.target_amount}). "
                "Use ?force=true to close anyway."
            ),
        )

    goal.is_completed = True
    goal.completed_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(goal)
    return goal


@goal_router.post("/{goal_id}/reopen", response_model=GoalOut)
async def reopen_goal(
        goal_id: int,
        session: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """Reopen a previously completed goal."""
    goal = await _get_user_goal_or_404(session, goal_id, current_user.id_)
    if not goal.is_completed:
        raise HTTPException(status_code=409, detail="Goal is not completed")

    goal.is_completed = False
    goal.completed_at = None
    await session.commit()
    await session.refresh(goal)
    return goal

