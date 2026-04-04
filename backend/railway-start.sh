#!/usr/bin/env bash
set -euo pipefail

echo "[railway] Running DB migrations..."
alembic upgrade head

echo "[railway] Starting API..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
