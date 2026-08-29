#!/bin/sh
# Container entrypoint: bring the schema up to date, then serve.
#
# Alembic owns the schema (main.py's lifespan deliberately creates nothing), so
# the upgrade has to run before the first request. `set -e` means a failed
# migration stops the container instead of serving against a stale database.
set -e

echo "==> alembic upgrade head"
alembic upgrade head

echo "==> starting uvicorn on port ${PORT:-8000}"
exec uvicorn app.asgi:app --host 0.0.0.0 --port "${PORT:-8000}"
