# ElectroStock Migrations

ElectroStock uses a lightweight migration registry in `app/services/schema.py`.

This is intentionally simpler than Alembic for now because the application has a compact SQLite schema, existing real data, and no previous migration history.

## Runtime Behavior

On startup, `app/main.py` runs schema setup in this order:

1. `Base.metadata.create_all(bind=engine)` creates missing tables defined by SQLAlchemy models.
2. `ensure_optional_columns(engine)` preserves the existing safety behavior for known legacy columns.
3. `run_migrations(engine)` creates/checks the migration registry and applies pending migrations.

The migration registry table is:

```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    id VARCHAR(80) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Each migration must be idempotent. If a migration has already been recorded in `schema_migrations`, startup skips it.

## Current Baseline

The first migration is:

```text
0001_baseline - Register existing schema under migration control
```

It is a no-op migration. It does not alter business tables. It only records that the current schema is now migration-managed.

## Adding A Migration

Add a function in `app/services/schema.py` that receives a SQLAlchemy `Connection`:

```python
def add_example_column(connection: Connection):
    columns = {
        row['name']
        for row in inspect(connection).get_columns('some_table')
    }
    if 'example_column' not in columns:
        connection.execute(text(
            'ALTER TABLE some_table ADD COLUMN example_column VARCHAR(120)'
        ))
```

Then append it to `MIGRATIONS` with a stable, ordered id:

```python
Migration(
    id='0002_add_example_column',
    name='Add example column to some table',
    apply=add_example_column,
),
```

Rules:

- Never edit an already-applied migration.
- Prefer additive schema changes.
- Make every migration safe to run on an existing database.
- Check for existing columns/tables/indexes before creating them.
- Update backup/export/restore code in the same feature phase if business tables change.
- Test with a copy of real `data/app.db` before production.

## Docker Dev Verification

Rebuild and start the dev container:

```powershell
docker compose -f docker-compose_dev.yml up -d --build
```

Compile the app inside the container:

```powershell
docker exec electrostock python -m compileall app
```

Inspect migration rows:

```powershell
docker exec electrostock python - <<'PY'
import sqlite3

conn = sqlite3.connect('/app/data/app.db')
rows = conn.execute(
    'SELECT id, name, applied_at FROM schema_migrations ORDER BY id'
).fetchall()
for row in rows:
    print(row)
conn.close()
PY
```

Expected after Phase 1:

```text
('0001_baseline', 'Register existing schema under migration control', '<timestamp>')
```

After Phase 2A, `0002_create_users` should also be present. Restarting the container should leave the same rows and log that already-applied migrations were skipped.
