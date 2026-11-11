"""
Bring the database schema to the latest Alembic revision (run on every container start).

    python -m scripts.migrate

- database already under Alembic (has `alembic_version`) → `upgrade head`;
- empty database → `upgrade head` (the migrations build the whole schema);
- tables but no `alembic_version` → created earlier by `scripts/init_db` (create_all), which
  the Docker image used before migrations were wired in. Such a schema matches revision
  LEGACY_REVISION (plus `receipt_files`, which the next migration creates only if missing), so it is
  stamped with that revision and then upgraded.

`scripts/init_db` (create_all) only creates missing tables and never adds columns to existing
ones, so a schema change would silently not reach a deployed database; this script fixes that.
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from src.config import DATABASE_URL

LEGACY_REVISION = "c1d2e3f4a5b6"


async def _tables() -> set:
    engine = create_async_engine(DATABASE_URL)
    async with engine.connect() as conn:
        names = await conn.run_sync(lambda sync_conn: set(inspect(sync_conn).get_table_names()))
    await engine.dispose()
    return names


def main() -> None:
    tables = asyncio.run(_tables())
    cfg = Config(str(ROOT / "alembic.ini"))
    if "alembic_version" not in tables and "users" in tables:
        print(f"Schema created without Alembic — stamping {LEGACY_REVISION}")
        command.stamp(cfg, LEGACY_REVISION)
    command.upgrade(cfg, "head")
    print("Database schema is up to date.")


if __name__ == "__main__":
    main()
