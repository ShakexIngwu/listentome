"""
config.py — Centralized, typed configuration for all three pipelines.
Loaded from environment variables / .env file via pydantic-settings.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── PostgreSQL (Operational Store) ────────────────────────────────────────
    postgres_url: str = "postgresql+asyncpg://buffett:buffett@localhost:5432/stocks"
    postgres_backup_dir: str = "./backups"
    postgres_backup_keep_days: int = 30

    # ── DuckDB (Analytics Read Replica) ───────────────────────────────────────
    duckdb_path: str = "./analytics/stocks_analytics.duckdb"
    parquet_dir: str = "./analytics/parquet"

    # ── NASDAQ Ingestion ───────────────────────────────────────────────────────
    nasdaq_url: str = (
        "https://api.nasdaq.com/api/screener/stocks"
        "?tableonly=true&limit=10000&exchange=NASDAQ&download=true"
    )
    worker_concurrency: int = 10
    rate_limit_rps: float = 3.0
    yfinance_retry_attempts: int = 3

    # ── Google ADK / Gemini ───────────────────────────────────────────────────
    google_api_key: str = ""              # Set via GOOGLE_API_KEY env var
    # Default is gemini-1.5-flash for safety; overridden by env var GEMINI_MODEL
    gemini_model: str = "gemini-1.5-flash"

    # ── Analysis Options ──────────────────────────────────────────────────────
    # If True, bypasses the QuantScreener filtering rules and analyzes ALL companies.
    skip_screener: bool = False
    # Investment strategy (skill) to use for LLM analysis stage
    analysis_strategy: str = "early_buffett"
    # Number of top pre-LLM-scored candidates to send to the LLM stage
    llm_top_n: int = 50

    # ── Scheduler ─────────────────────────────────────────────────────────────
    weekly_run_day: str = "sun"
    weekly_run_hour: int = 2
    daily_run_hour_am: int = 7
    daily_run_hour_pm: int = 18

    # ── EDGAR ─────────────────────────────────────────────────────────────────
    edgar_user_agent: str = "BuffettScreener your@email.com"

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = "INFO"
    log_format: str = "json"  # "json" | "console"


# Singleton — import this everywhere
settings = Settings()
