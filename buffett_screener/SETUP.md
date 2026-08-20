# Warren Buffett Stock Screener — Setup Guide

## 🐳 Docker (Recommended — Production)

> **Prerequisites:** Docker Desktop ≥ 24 or Docker Engine + Compose V2.

### 1. Configure secrets

```bash
cd /Users/kesha/Documents/listentome/buffett_screener
cp .env.example .env
```

Your `.env` already has `GEMINI_API_KEY` set. Just confirm these two lines:
```env
GEMINI_API_KEY=your_gemini_api_key_here
POSTGRES_PASSWORD=buffett   # change to something strong in production
```

### 2. Build and start all services

```bash
docker compose up -d --build
```

This starts **4 containers**:

| Container | Role | Exposes |
|-----------|------|---------|
| `buffett_postgres` | PostgreSQL 16 — primary data store | internal only |
| `buffett_backend` | Pipeline scheduler (weekly + daily) | internal only |
| `buffett_api` | FastAPI backend service | **localhost:8000** |
| `buffett_frontend` | Flutter Web UI dashboard | **localhost:8080** |

On first boot the backend will:
1. Wait for PostgreSQL to be healthy
2. Run Alembic migrations (creates all tables)
3. Start the APScheduler daemon

### 3. Open the dashboard

```
http://localhost:8080
```

> The dashboard will show empty data until the first pipeline run completes.

### 4. Trigger the pipeline now (don't wait for Sunday 2 AM)

```bash
docker compose -f docker/docker-compose.yml exec backend python main.py --run-now
```

This runs the full weekly pipeline immediately (~20–60 min for 3,500+ tickers).

### 5. Watch live logs

```bash
# All services
docker compose -f docker/docker-compose.yml logs -f

# Backend only (pipeline progress in JSON)
docker compose logs -f backend

# Pretty-print JSON logs
docker compose logs -f backend | python -m json.tool
```

---

## Useful Docker Commands

| Command | What it does |
|---------|-------------|
| `make build` | Rebuild images + start all services |
| `make up` | Start services (no rebuild) |
| `make down` | Stop all services (data preserved) |
| `make restart` | Restart running containers |
| `make logs` | Tail all service logs |
| `make logs-backend` | Tail backend logs only |
| `make run-now` | Run weekly pipeline immediately |
| `make export-duckdb` | Rebuild DuckDB from Postgres |
| `make backup` | Run pg_dump now |
| `make shell-backend` | Open bash in backend container |
| `make shell-db` | Open psql in postgres container |
| `make clean` | ⚠️ Stop + wipe all data volumes |

> **Why Makefile?** Running `docker compose -f docker/docker-compose.yml` with the compose
> file in a subdirectory causes Compose to look for `.env` in `docker/` instead of the
> project root. The Makefile bakes in `--env-file .env` so your API key is always passed.

---

## Architecture

```
Host Machine
└── Docker Network: buffett-net (internal bridge)
    │
    ├── postgres (postgres:16-alpine)
    │     Storage layer — PostgreSQL 16
    │     Volume: pgdata → /var/lib/postgresql/data
    │     Health: pg_isready every 10s
    │
    ├── backend (buffett-screener:latest)
    │     Logic layer — APScheduler daemon
    │     Runs: weekly ingestion + Buffett analysis + daily earnings tracker
    │     Reads/writes: postgres (ACID), analytics volume (DuckDB export)
    │     Volume: analytics → /app/analytics  (read-write)
    │     Volume: output   → /app/output      (pitch deck PDFs)
    │     Volume: backups  → /app/backups     (daily pg_dump)
    │
        ├── api (buffett-screener:latest)
    │     API service — FastAPI
    │     Reads: analytics/output volumes (read-only)
    │     Port: 8000 → host:8000
    │
    └── frontend (nginx/flutter web)
          UI layer — Flutter Web
          Port: 8080 → host:8080 (talks to api:8000)
```

---

## Volumes

| Volume | Contents | Access |
|--------|----------|--------|
| `pgdata` | PostgreSQL WAL + data files | postgres only |
| `analytics` | `stocks_analytics.duckdb` + `parquet/` | backend r/w, dashboard r/o |
| `output` | `pitch_decks/*.pdf` | backend r/w, dashboard r/o |
| `backups` | `stocks_YYYY-MM-DD.sql.gz` | backend only |

---

## Local Development (without Docker)

```bash
# 1. PostgreSQL (macOS)
brew install postgresql@16 && brew services start postgresql@16
psql postgres -c "CREATE USER buffett WITH PASSWORD 'buffett';"
psql postgres -c "CREATE DATABASE stocks OWNER buffett;"

# 2. Python environment
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# WeasyPrint system deps (macOS)
brew install cairo pango gdk-pixbuf libffi

# 3. Migrations
alembic upgrade head

# 4. Run
python main.py --run-now    # one-shot pipeline
python main.py              # daemon (scheduled)

# 5. Run API & Frontend
uvicorn api:app --reload    # API service at localhost:8000

# To run the Flutter frontend in local development, ensure Flutter is installed:
cd frontend
flutter pub get
flutter run -d chrome       # UI runs in browser, proxies to API
```
