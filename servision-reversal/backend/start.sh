#!/usr/bin/env bash
set -e

# Run DB migrations, then boot the API. Railway sets $PORT.
echo "Running migrations..."
alembic upgrade head || echo "alembic step skipped/failed (continuing)"

echo "Starting API on port ${PORT:-8000}..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
