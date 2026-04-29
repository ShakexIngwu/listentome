"""
earnings_tracker/scheduler/daily_job.py
APScheduler configuration for the daily earnings tracker.
Runs Mon–Fri at 07:00 AM and 18:00 PM ET (pre-market + after-hours).
"""
import asyncio
from datetime import date, datetime, timezone

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import text

from buffett_analysis.agents.orchestrator import run_buffett_analysis
from config import settings
from db.duckdb_replica import run_full_export
from db.postgres import AsyncSessionLocal
from earnings_tracker.detection.change_detector import evaluate_material_change
from earnings_tracker.detection.edgar_rss_poller import poll_edgar_8k_feed
from earnings_tracker.notifications.alerter import (
    alert_earnings_surprise,
    alert_pipeline_failure,
)
from earnings_tracker.parsing.cik_resolver import build_cik_ticker_map, resolve_ticker

log = structlog.get_logger()


async def daily_earnings_job() -> None:
    """
    Full daily pipeline:
    1. Refresh CIK→ticker mapping in PostgreSQL
    2. Poll EDGAR 8-K RSS for earnings releases filed in the last 25 hours
    3. For each filing: resolve ticker, parse EPS, evaluate materiality
    4. If material: trigger re-analysis via Buffett LangGraph pipeline
    5. Rebuild DuckDB Parquet export
    """
    log.info("daily_earnings_job_started")

    async with AsyncSessionLocal() as db:
        # 1. Keep CIK→ticker map fresh
        try:
            await build_cik_ticker_map(db)
        except Exception as e:
            log.warning("cik_map_refresh_failed", error=str(e))

        # 2. Poll RSS
        filings = await poll_edgar_8k_feed(lookback_hours=25)

        reanalyzed: list[str] = []

        for filing in filings:
            cik = filing["cik"]
            ticker = await resolve_ticker(cik, db)

            if not ticker:
                log.debug("ticker_not_found_for_cik", cik=cik)
                continue

            # 3. Parse EPS from the filing (basic extraction from yfinance as proxy)
            # A full XBRL parser (edgartools) would go here in production
            try:
                import yfinance as yf
                loop = asyncio.get_event_loop()
                info = await loop.run_in_executor(None, lambda: yf.Ticker(ticker).info)
                eps_actual = info.get("trailingEps") or 0.0
                eps_estimate = info.get("epsForward")
            except Exception:
                eps_actual = 0.0
                eps_estimate = None

            # 4. Evaluate materiality
            is_material, reason = await evaluate_material_change(
                ticker=ticker,
                new_eps=eps_actual,
                eps_estimate=eps_estimate,
                db=db,
            )

            # Always record the event
            await db.execute(text("""
                INSERT INTO earnings_events
                    (ticker, report_date, eps_actual, eps_estimate, edgar_cik, filing_url, filed_at)
                VALUES
                    (:ticker, :date, :eps, :est, :cik, :url, :filed)
                ON CONFLICT (ticker, fiscal_year, fiscal_quarter) DO NOTHING
            """), {
                "ticker": ticker,
                "date":   date.today(),
                "eps":    eps_actual,
                "est":    eps_estimate,
                "cik":    cik,
                "url":    filing["filing_url"],
                "filed":  filing["filed_at"],
            })

            # EPS surprise alert
            if eps_estimate and eps_estimate != 0:
                surprise = (eps_actual - eps_estimate) / abs(eps_estimate)
                if abs(surprise) > 0.05:
                    async with AsyncSessionLocal() as meta_db:
                        comp = (await meta_db.execute(
                            text("SELECT name FROM companies WHERE ticker = :t"),
                            {"t": ticker}
                        )).fetchone()
                    alert_earnings_surprise(
                        ticker=ticker,
                        company_name=comp[0] if comp else ticker,
                        surprise_pct=surprise,
                        eps_actual=eps_actual,
                    )

            if is_material:
                log.info("material_change_detected", ticker=ticker, reason=reason)
                reanalyzed.append(ticker)

        await db.commit()

    # 5. Re-run Buffett analysis if any material changes detected
    if reanalyzed:
        log.info("triggering_reanalysis", tickers=reanalyzed)
        try:
            stats = await run_buffett_analysis()
            await run_full_export()
            log.info("reanalysis_complete", **stats)
        except Exception as e:
            log.error("reanalysis_failed", error=str(e))
            alert_pipeline_failure("daily_earnings_reanalysis", str(e))
    else:
        log.info("no_material_changes_detected")

    log.info("daily_earnings_job_complete", filings=len(filings), reanalyzed=len(reanalyzed))


def build_daily_scheduler() -> AsyncIOScheduler:
    """Builds and returns the daily earnings APScheduler."""
    scheduler = AsyncIOScheduler()

    # Pre-market scan (7 AM ET  = 12:00 UTC / 14:00 UTC in DST)
    scheduler.add_job(
        daily_earnings_job,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour=settings.daily_run_hour_am,
            minute=0,
        ),
        id="daily_earnings_am",
        name="Daily Earnings Tracker (AM)",
        replace_existing=True,
        max_instances=1,
    )

    # After-hours scan (6 PM ET)
    scheduler.add_job(
        daily_earnings_job,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour=settings.daily_run_hour_pm,
            minute=0,
        ),
        id="daily_earnings_pm",
        name="Daily Earnings Tracker (PM)",
        replace_existing=True,
        max_instances=1,
    )

    return scheduler
