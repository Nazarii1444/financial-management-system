from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models import User, Currencies
from src.users.schemas import UserOut, UserUpdate
from src.dependencies import get_current_user

users_router = APIRouter()


@users_router.get("/me", response_model=UserOut, status_code=status.HTTP_200_OK)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@users_router.get("/{user_id}", response_model=UserOut, status_code=status.HTTP_200_OK)
async def get_user_by_id(
        user_id: int,
        current_user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_db),
):
    if user_id != current_user.id_:
        raise HTTPException(status_code=404, detail="User not found")
    return current_user


@users_router.patch("/me", response_model=UserOut, status_code=status.HTTP_200_OK)
async def update_me(
        payload: UserUpdate,
        session: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    data = payload.model_dump(exclude_unset=True)
    if not data:
        return current_user

    if "default_currency" in data and data["default_currency"] is not None:
        cur = data["default_currency"].upper()
        allowed = {c.value for c in Currencies}
        if cur not in allowed:
            raise HTTPException(status_code=422, detail="Invalid default_currency")
        data["default_currency"] = cur

    if "email" in data and data["email"] is not None:
        data["email"] = data["email"].lower()

    if "username" in data and data["username"] is not None:
        q = select(User.id_).where(
            User.username == data["username"],
            User.id_ != current_user.id_,
        )
        exists = (await session.execute(q)).scalar_one_or_none()
        if exists:
            raise HTTPException(status_code=409, detail="Username already taken")

    if "email" in data and data["email"] is not None:
        q = select(User.id_).where(
            User.email == data["email"],
            User.id_ != current_user.id_,
        )
        exists = (await session.execute(q)).scalar_one_or_none()
        if exists:
            raise HTTPException(status_code=409, detail="Email already taken")

    for field, value in data.items():
        setattr(current_user, field, value)

    await session.commit()
    await session.refresh(current_user)
    return current_user


@users_router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await session.delete(current_user)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
