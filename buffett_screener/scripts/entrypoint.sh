#!/usr/bin/env bash
# =============================================================================
# entrypoint.sh — Container entrypoint for both backend and dashboard services.
#
# Environment variables that control behaviour:
#   WAIT_FOR_POSTGRES=true   (default) — block until PostgreSQL is up
#   RUN_MIGRATIONS=true      (default) — run alembic upgrade head on start
#   WAIT_FOR_POSTGRES=false  — skip both (used by the dashboard service)
#   RUN_MIGRATIONS=false     — skip migrations only
# =============================================================================
set -euo pipefail

echo "🚀 Buffett Screener container starting ($(date -u '+%Y-%m-%dT%H:%M:%SZ'))"
echo "   CMD: $*"

# ── 1. Wait for PostgreSQL ────────────────────────────────────────────────────
if [ "${WAIT_FOR_POSTGRES:-true}" = "true" ]; then
    echo "⏳ Waiting for PostgreSQL..."
    python /app/scripts/wait_for_postgres.py
fi

# ── 2. Run Alembic migrations ─────────────────────────────────────────────────
if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    echo "🗃️  Running database migrations (alembic upgrade head)..."
    cd /app && alembic upgrade head
    echo "✅ Migrations complete."
fi

# ── 3. Hand off to the actual service command ─────────────────────────────────
echo "▶️  Starting service: $*"
exec "$@"
