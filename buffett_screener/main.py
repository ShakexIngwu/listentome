"""
main.py — Entry point for the Warren Buffett Stock Screener system.

Usage:
    python main.py                    # Start all schedulers (daemon mode)
    python main.py --run-now          # Trigger the weekly pipeline immediately
    python main.py --export-duckdb    # Rebuild DuckDB from Postgres right now
    python main.py --backup           # Run pg_dump right now
"""
import argparse
import asyncio
import logging
import sys

import structlog

from config import settings


def _configure_logging() -> None:
    """Configure structlog for JSON or console output."""
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]
    if settings.log_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )


async def _run_daemon() -> None:
    """Start all schedulers and run indefinitely."""
    from db.duckdb_replica import initialize_empty_duckdb
    from scheduler.weekly_job import build_scheduler
    from earnings_tracker.scheduler.daily_job import build_daily_scheduler

    log = structlog.get_logger()

    # Ensure the DuckDB file exists so the dashboard can connect immediately.
    # If data is already there from a previous run this is a no-op.
    initialize_empty_duckdb()

    weekly_scheduler = build_scheduler()
    daily_scheduler = build_daily_scheduler()

    weekly_scheduler.start()
    daily_scheduler.start()

    log.info("schedulers_started", weekly="Sunday 02:00", daily="Mon-Fri 07:00 & 18:00 ET")


    try:
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        log.info("shutdown_requested")
        weekly_scheduler.shutdown(wait=False)
        daily_scheduler.shutdown(wait=False)


async def _run_now() -> None:
    """Immediately triggers the full weekly ingestion pipeline."""
    from scheduler.weekly_job import weekly_ingestion_job
    log = structlog.get_logger()
    log.info("manual_run_started")
    await weekly_ingestion_job()
    log.info("manual_run_complete")


async def _run_daily() -> None:
    """Immediately triggers the daily earnings tracker pipeline."""
    from earnings_tracker.scheduler.daily_job import daily_earnings_job
    log = structlog.get_logger()
    log.info("manual_daily_run_started")
    await daily_earnings_job()
    log.info("manual_daily_run_complete")


async def _run_analysis() -> None:
    """
    Runs only the Buffett analysis pipeline (quant screen → DCF → Gemini
    → score → pitch deck → persist). Skips NASDAQ ingestion and yfinance pull.
    Assumes financial_snapshots are already populated in PostgreSQL.
    Exports to DuckDB automatically so the dashboard shows fresh scores.
    """
    from buffett_analysis.agents.orchestrator import run_buffett_analysis
    from db.duckdb_replica import run_full_export
    log = structlog.get_logger()
    log.info("manual_analysis_started")
    result = await run_buffett_analysis()
    log.info("manual_analysis_complete", **result)
    log.info("exporting_to_duckdb")
    await run_full_export()
    log.info("duckdb_export_complete")


async def _export_duckdb() -> None:
    from db.duckdb_replica import run_full_export
    await run_full_export()


async def _backup() -> None:
    from backup.pg_backup import daily_backup_job
    await daily_backup_job()


def main() -> None:
    _configure_logging()

    parser = argparse.ArgumentParser(description="Warren Buffett Stock Screener")
    parser.add_argument("--run-now",      action="store_true", help="Weekly ingestion + Buffett analysis")
    parser.add_argument("--run-daily",    action="store_true", help="Daily earnings tracker")
    parser.add_argument("--run-analysis", action="store_true", help="Buffett analysis only (no ingestion)")
    parser.add_argument("--all",          action="store_true", help="With --run-analysis, skip the quant screener and analyze ALL stocks")
    parser.add_argument("--strategy",     type=str, default=None, help="Investment strategy for LLM analysis (default: early_buffett)")
    parser.add_argument("--top-n",        type=int, default=None, help="Number of top candidates to send to LLM (default: 50)")
    parser.add_argument("--export-duckdb", action="store_true", help="Rebuild DuckDB from Postgres")
    parser.add_argument("--backup",       action="store_true", help="Run pg_dump now")
    args = parser.parse_args()

    if args.run_now:
        asyncio.run(_run_now())
    elif args.run_daily:
        asyncio.run(_run_daily())
    elif args.run_analysis:
        if args.all:
            settings.skip_screener = True
        if args.strategy:
            settings.analysis_strategy = args.strategy
        if args.top_n:
            settings.llm_top_n = args.top_n
        asyncio.run(_run_analysis())
    elif args.export_duckdb:
        asyncio.run(_export_duckdb())
    elif args.backup:
        asyncio.run(_backup())
    else:
        asyncio.run(_run_daemon())


if __name__ == "__main__":
    main()
