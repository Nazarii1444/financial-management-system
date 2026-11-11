#!/bin/sh
set -e

# Bring the schema to the latest Alembic revision (also adopts databases that
# scripts/init_db created before migrations were wired in — see scripts/migrate.py)
python -m scripts.migrate

# Demo data on first start; the seed script skips users that already exist
if [ "${SEED_DATA:-false}" = "true" ]; then
  python -m scripts.seed
fi

# PORT is set by hosts like Render; behind their TLS proxy, FORWARDED_ALLOW_IPS="*" makes
# uvicorn trust X-Forwarded-Proto so OAuth redirect URLs are built with https://
exec uvicorn src.app:app --host 0.0.0.0 --port "${PORT:-8000}"
