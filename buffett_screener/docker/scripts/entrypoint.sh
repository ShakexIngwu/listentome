#!/usr/bin/env bash
# =============================================================================
# docker/scripts/entrypoint.sh — Container entrypoint for all services.
#
# Env vars:
#   WAIT_FOR_POSTGRES=true   (default) — block until PostgreSQL is accepting connections
#   RUN_MIGRATIONS=true      (default) — run alembic upgrade head before starting
#   WAIT_FOR_POSTGRES=false  — skip both checks (used by the dashboard service)
#   RUN_MIGRATIONS=false     — skip migrations only
# =============================================================================
set -euo pipefail

echo "🚀 Buffett Screener container starting ($(date -u '+%Y-%m-%dT%H:%M:%SZ'))"
echo "   CMD: $*"

# ── 1. Wait for PostgreSQL ────────────────────────────────────────────────────
if [ "${WAIT_FOR_POSTGRES:-true}" = "true" ]; then
    echo "⏳ Waiting for PostgreSQL..."
    python /app/docker/scripts/wait_for_postgres.py
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
