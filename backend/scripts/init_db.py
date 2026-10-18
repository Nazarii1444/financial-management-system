"""
Create all tables directly from SQLAlchemy models (local development only).

Usage (from backend/):
    python -m scripts.init_db            # create missing tables
    python -m scripts.init_db --drop     # drop everything first, then create

For real deployments use Alembic migrations (see README).
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.ext.asyncio import create_async_engine

from src.config import DATABASE_URL
from src.models import Base


async def init_db(drop: bool = False) -> None:
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        if drop:
            await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    print("✅  Tables are ready.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--drop", action="store_true", help="Drop all tables before creating")
    asyncio.run(init_db(drop=parser.parse_args().drop))
