# ═══════════════════════════════════════════════════════════════════════════════
# Stage 1 — Builder: compile C-extension wheels (asyncpg, pyarrow, duckdb…)
# Build context: project root (..)
# ═══════════════════════════════════════════════════════════════════════════════
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
        libssl-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
# requirements.txt lives at the project root (build context = ..)
COPY requirements.txt .

RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt


# ═══════════════════════════════════════════════════════════════════════════════
# Stage 2 — Runtime: slim image with only what's needed to run
# ═══════════════════════════════════════════════════════════════════════════════
FROM python:3.11-slim AS runtime

LABEL maintainer="Buffett Screener"
LABEL description="Warren Buffett Stock Screener — backend pipeline + FastAPI service"

# ── System libs ──────────────────────────────────────────────────────────────
# WeasyPrint (PDF rendering) needs Cairo, Pango, GDK-PixBuf at runtime.
# fonts-liberation provides fonts inside the container for PDF generation.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libcairo2 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libgdk-pixbuf-2.0-0 \
        libffi8 \
        shared-mime-info \
        fonts-liberation \
        curl \
    && rm -rf /var/lib/apt/lists/*

# ── Non-root user (security best practice) ───────────────────────────────────
RUN useradd -m -u 1000 -s /bin/bash buffett

# ── Python deps from builder stage ───────────────────────────────────────────
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels /wheels/* \
    && rm -rf /wheels

# ── App source (all relative to project root build context) ──────────────────
WORKDIR /app
COPY --chown=buffett:buffett . .

# ── Runtime directories (created here so named volumes mount cleanly) ─────────
RUN mkdir -p \
        analytics/parquet \
        output/pitch_decks \
        backups \
        logs \
    && chown -R buffett:buffett analytics output backups logs

# ── Entrypoint — copied from docker/scripts/ (relative to project root) ───────
COPY --chown=root:root docker/scripts/entrypoint.sh /entrypoint.sh
COPY --chown=buffett:buffett docker/scripts/wait_for_postgres.py /app/docker/scripts/wait_for_postgres.py
RUN chmod +x /entrypoint.sh

USER buffett

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
# Default CMD — overridden per-service in docker-compose.yml
CMD ["python", "main.py"]
