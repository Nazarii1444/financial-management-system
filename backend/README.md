# Homiak Finance

---

## Installation
1. Clone the repo:
```bash
git clone https://github.com/Nazarii1444/HomiakFinance.git
```

2. Create an environment:
```bash
python -m venv .venv
```

3. Activate environment

```bash
source .venv/bin/activate (mac/linux)
```

```bash
.\.venv\Scripts\activate (windows)
```

4. Install requirements

```bash
pip install -r requirements.txt
```

5. Create a DB named `homiakdb` in pgadmin4.

6. Init alembic:
```bash
alembic init alembic
```

7. Ensure you have `.env` file with the following variables:

```bash
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
DB_HOST=localhost
DB_PORT=5432
DB_NAME=homiakdb
```

8. Change `alembic/env.py` to the following code:
```python
import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from src.config import DATABASE_URL
from src.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable: AsyncEngine = create_async_engine(DATABASE_URL, echo=True)

    async with connectable.begin() as connection:

        def do_migrations(sync_connection):
            context.configure(connection=sync_connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()

        await connection.run_sync(do_migrations)

if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

9. Change `alembic.ini` to the following:
```bash
[alembic]
script_location = %(here)s/alembic

prepend_sys_path = .

path_separator = os

sqlalchemy.url = postgresql+asyncpg://placeholder

[post_write_hooks]

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARNING
handlers = console
qualname =

[logger_sqlalchemy]
level = WARNING
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

10. Run migrations
```bash
alembic revision --autogenerate -m "Init tables"
```

```bash
alembic upgrade head
```

11. Run development server
```bash
python app.py
```

12. Go to: `http://localhost:8000/health/`

If you get this response: `{"status":"OK"}`, then you are good to go!

---

### Delete all tables and enums
```sql
DO
$$
DECLARE
    tbl TEXT;
    enum_type RECORD;
BEGIN
    FOR tbl IN
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'public'
    LOOP
        EXECUTE format('DROP TABLE IF EXISTS public.%I CASCADE', tbl);
    END LOOP;

    FOR enum_type IN
        SELECT n.nspname AS schema_name, t.typname AS enum_name
        FROM pg_type t
        JOIN pg_enum e ON t.oid = e.enumtypid
        JOIN pg_namespace n ON n.oid = t.typnamespace
        GROUP BY n.nspname, t.typname
    LOOP
        EXECUTE format('DROP TYPE IF EXISTS %I.%I CASCADE', enum_type.schema_name, enum_type.enum_name);
    END LOOP;
END;
$$;
