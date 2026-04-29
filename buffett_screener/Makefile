# =============================================================================
# Makefile — Warren Buffett Stock Screener convenience wrapper
#
# Always loads .env from the project root and references docker/docker-compose.yml.
# Usage:  make build   make up   make down   make logs   make run-stock-pull
# =============================================================================

COMPOSE := docker compose -f docker/docker-compose.yml --env-file .env

.PHONY: build up down restart logs logs-backend ps \
        run-stock-pull run-stock-pull-bg run-earnings-update run-analysis export-duckdb backup \
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

ps:             ## Show container status
	$(COMPOSE) ps

# ── Pipeline triggers ─────────────────────────────────────────────────────────

run-stock-pull:      ## NASDAQ ingestion + full Buffett analysis (foreground, 20-60 min)
	$(COMPOSE) exec backend python main.py --run-now

run-stock-pull-bg:   ## Same as run-stock-pull but runs in background (use make logs-backend to watch)
	$(COMPOSE) exec -d backend python main.py --run-now

run-earnings-update: ## Daily earnings tracker (EDGAR 8-K RSS poll + re-analysis)
	$(COMPOSE) exec backend python main.py --run-daily

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
