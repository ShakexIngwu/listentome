# =============================================================================
# Makefile — Warren Buffett Stock Screener convenience wrapper
#
# Always loads .env from the project root and references docker/docker-compose.yml.
# Usage:  make build   make up   make down   make logs   make run-stock-pull
# =============================================================================

COMPOSE := docker compose -f docker/docker-compose.yml --env-file .env

.PHONY: build up down restart logs logs-backend ps \
        run-stock-pull run-stock-pull-bg run-earnings-update run-daily-analysis run-notify-coming run-summarize-recent run-analysis export-duckdb backup \
        shell-backend shell-db clean

# ── Lifecycle ─────────────────────────────────────────────────────────────────

build:          ## Rebuild images and start all services
	$(COMPOSE) up -d --build

up:             ## Start all services (no rebuild)
	$(COMPOSE) up -d

down:           ## Stop and remove containers (data volumes preserved)
	$(COMPOSE) down

restart:        ## Restart all running containers
	$(COMPOSE) restart

logs:           ## Tail logs for all services
	$(COMPOSE) logs -f

logs-backend:   ## Tail backend logs only
	$(COMPOSE) logs -f backend

logs-api:       ## Tail API logs only
	$(COMPOSE) logs -f api

logs-frontend:  ## Tail frontend logs only
	$(COMPOSE) logs -f frontend

ps:             ## Show container status
	$(COMPOSE) ps

# ── Pipeline triggers ─────────────────────────────────────────────────────────

run-stock-pull:      ## NASDAQ weekly ingestion + analysis. Usage: make run-stock-pull [TICKERS=AAPL,MSFT] [LIMIT=10]
	$(COMPOSE) exec backend python main.py --run-now $(if $(TICKERS),--tickers $(TICKERS),) $(if $(LIMIT),--limit $(LIMIT),)

run-stock-pull-bg:   ## Same as run-stock-pull but runs in background
	$(COMPOSE) exec -d backend python main.py --run-now $(if $(TICKERS),--tickers $(TICKERS),) $(if $(LIMIT),--limit $(LIMIT),)

run-earnings-update: ## Daily earnings tracker (EDGAR 8-K RSS poll + re-analysis)
	$(COMPOSE) exec backend python main.py --run-daily

run-daily-analysis:  ## Daily full analysis + Buffett score updates. Usage: make run-daily-analysis [TICKERS=AAPL,MSFT] [LIMIT=10]
	$(COMPOSE) exec backend python main.py --run-daily-analysis $(if $(TICKERS),--tickers $(TICKERS),) $(if $(LIMIT),--limit $(LIMIT),)

run-notify-coming:   ## Upcoming earnings calendar alerts (next 7 days)
	$(COMPOSE) exec backend python main.py --run-notify-coming

run-summarize-recent: ## Daily recent earnings outcomes summary (last 24 hours)
	$(COMPOSE) exec backend python main.py --run-summarize-recent

run-analysis:   ## Buffett analysis only — skip ingestion, use existing DB data
	$(COMPOSE) exec backend python main.py --run-analysis

run-analysis-all: ## Buffett analysis on ALL companies (skip screener), top 50 to LLM
	$(COMPOSE) exec backend python main.py --run-analysis --all

run-analysis-strategy: ## Usage: make run-analysis-strategy STRATEGY=early_buffett TOP_N=50
	$(COMPOSE) exec backend python main.py --run-analysis --all --strategy $(STRATEGY) --top-n $(TOP_N)

export-duckdb:  ## Rebuild DuckDB analytics replica from Postgres
	$(COMPOSE) exec backend python main.py --export-duckdb

backup:         ## Run a pg_dump backup right now
	$(COMPOSE) exec backend python main.py --backup

# ── Debug shells ──────────────────────────────────────────────────────────────

shell-backend:  ## Open a bash shell in the backend container
	$(COMPOSE) exec backend bash

shell-db:       ## Open a psql shell in the postgres container
	$(COMPOSE) exec postgres psql -U buffett -d stocks

# ── Nuclear option ────────────────────────────────────────────────────────────

clean:          ## ⚠️  Stop containers AND wipe all volumes (data loss!)
	$(COMPOSE) down -v
