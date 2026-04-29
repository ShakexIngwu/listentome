"""
scheduler/weekly_job.py
APScheduler configuration for the weekly ingestion pipeline.
Runs every Sunday at 02:00 AM local time.
Also schedules the daily 03:00 AM pg_dump backup.
"""
import asyncio
import uuid
from datetime import datetime, timezone

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import text

from backup.pg_backup import daily_backup_job
from config import settings
from db.duckdb_replica import run_full_export
from db.postgres import AsyncSessionLocal
from ingestion.nasdaq_discovery import fetch_nasdaq_companies
from streaming.worker import run_streaming_pipeline

log = structlog.get_logger()


async def weekly_ingestion_job() -> None:
    """
    Full weekly pipeline:
    1. Start a pipeline_runs record in PostgreSQL
    2. Discover & upsert all NASDAQ companies
    3. Stream financial data for all active tickers (yfinance)
    4. Run Buffett analysis pipeline (quant screen → DCF → Gemini → score → pitch deck)
    5. Export PostgreSQL → Parquet → rebuild DuckDB views
    6. Mark the run completed
    """
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)

    # Open a run record
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("""
                INSERT INTO pipeline_runs (run_id, run_type, started_at, status)
                VALUES (:run_id, 'weekly_ingestion', :started_at, 'running')
            """),
            {"run_id": run_id, "started_at": started_at},
        )
        await session.commit()

    log.info("weekly_job_started", run_id=run_id)

    try:
        # Stage 1: company discovery
        async with AsyncSessionLocal() as session:
            discovery = await fetch_nasdaq_companies(session)
        changed_tickers = discovery.newly_listed | discovery.newly_delisted
        log.info(
            "discovery_done",
            total=discovery.total,
            newly_listed=len(discovery.newly_listed),
            newly_delisted=len(discovery.newly_delisted),
        )

        # Stage 2: yfinance pull — ONLY for newly listed/delisted tickers
        # Existing tickers already have fresh data from the previous run
        if changed_tickers:
            stats = await run_streaming_pipeline(
                run_id=run_id,
                ticker_subset=changed_tickers,
            )
        else:
            log.info("no_ticker_changes_skip_pull", run_id=run_id)
            stats = {"succeeded": 0, "failed": 0, "total": 0, "run_id": run_id}

        # Stage 3: Buffett analysis on ALL active tickers (uses existing financial data)
        log.info("buffett_analysis_starting", run_id=run_id)
        from buffett_analysis.agents.orchestrator import run_buffett_analysis
        analysis_result = await run_buffett_analysis()
        log.info("buffett_analysis_complete", run_id=run_id, **analysis_result)

        # Stage 4: export to DuckDB (includes fresh buffett_scores)
        await run_full_export()

        # Mark completed
        async with AsyncSessionLocal() as session:
            await session.execute(
                text("""
                    UPDATE pipeline_runs SET
                        status       = 'completed',
                        completed_at = :completed_at,
                        total_tickers = :total,
                        succeeded    = :succeeded,
                        failed       = :failed
                    WHERE run_id = :run_id
                """),
                {
                    "run_id":      run_id,
                    "completed_at": datetime.now(timezone.utc),
                    "total":       stats["total"],
                    "succeeded":   stats["succeeded"],
                    "failed":      stats["failed"],
                },
            )
            await session.commit()

        log.info("weekly_job_complete", run_id=run_id, **stats)

    except Exception as exc:
        async with AsyncSessionLocal() as session:
            await session.execute(
                text("""
                    UPDATE pipeline_runs SET status = 'failed', error_detail = :err
                    WHERE run_id = :run_id
                """),
                {"run_id": run_id, "err": str(exc)},
            )
            await session.commit()
        log.error("weekly_job_failed", run_id=run_id, error=str(exc))
        raise


def build_scheduler() -> AsyncIOScheduler:
    """Builds and returns (but does not start) the APScheduler instance."""
    scheduler = AsyncIOScheduler()

    # Weekly ingestion: Sunday at 02:00 AM
    scheduler.add_job(
        weekly_ingestion_job,
        trigger=CronTrigger(day_of_week=settings.weekly_run_day, hour=settings.weekly_run_hour, minute=0),
        id="weekly_ingestion",
        name="NASDAQ Weekly Ingestion",
        replace_existing=True,
        max_instances=1,  # Never allow overlapping runs
    )

    # Daily backup: every day at 03:00 AM
    scheduler.add_job(
        daily_backup_job,
        trigger=CronTrigger(hour=3, minute=0),
        id="daily_backup",
        name="PostgreSQL Daily Backup",
        replace_existing=True,
        max_instances=1,
    )

    return scheduler
