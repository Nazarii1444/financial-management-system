#!/bin/sh
set -e

# Create tables from the models (no Alembic migrations in the repo yet)
python -m scripts.init_db

# Demo data on first start; the seed script skips users that already exist
if [ "${SEED_DATA:-false}" = "true" ]; then
  python -m scripts.seed
fi

exec uvicorn src.app:app --host 0.0.0.0 --port 8000
