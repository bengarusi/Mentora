# Database upgrade procedure

Alembic is the sole owner of application schema changes. The API no longer
creates or alters tables during startup.

## Fresh database

1. Create the empty database.
2. From `backend/`, run `alembic upgrade head`.
3. Start the API only after the upgrade succeeds.

## Existing local Mentora database

The local pre-agent database has the seven tables frozen in revision `0001`
and no `alembic_version` table. Do not stamp a database merely because its
tables have familiar names.

1. Stop the API and take a database backup.
2. Compare columns, nullability, foreign keys, unique constraints, and indexes
   with `0001_existing_schema.py`. If any required object differs, stop and
   create a reconciliation migration; do not stamp it as compatible.
3. When the schema is confirmed compatible, run `alembic stamp 0001`.
4. Run `alembic upgrade head`.
5. Run `alembic current` and verify revision `0005` is reported before starting
   the API.

The repository migration tests exercise both an empty database upgrade and the
verified-baseline/stamp/upgrade path while checking that existing data survives.
