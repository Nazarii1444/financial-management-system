from alembic.operations import Operations
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import User


async def get_user_by_email(db: AsyncSession, email: str):
    return (await db.execute(select(User).where(User.email == email))).scalars().first()


async def get_user_by_username(db: AsyncSession, username: str):
    return (await db.execute(select(User).where(User.username == username))).scalars().first()


async def get_user_by_id(db: AsyncSession, user_id: int):
    return (await db.execute(select(User).where(User.id == user_id))).scalars().first()
