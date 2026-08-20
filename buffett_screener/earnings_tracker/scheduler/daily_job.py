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
    alert_upcoming_earnings,
    alert_earnings_summary,
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


async def daily_analysis_job(
    ticker_subset: set[str] | None = None,
    limit: int | None = None,
) -> None:
    """
    Daily full analysis job:
    1. Run yfinance pull for all active tickers to refresh market cap, EPS, price, etc.
    2. Run full Buffett analysis.
    3. Rebuild DuckDB read replica.
    """
    log.info("daily_analysis_job_started")
    try:
        # Refresh ticker basic info
        from streaming.worker import run_streaming_pipeline
        log.info("daily_analysis_refreshing_ticker_info")

        resolved_subset = ticker_subset
        if resolved_subset is None and limit is not None:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    text("SELECT ticker FROM companies WHERE is_active = TRUE ORDER BY ticker LIMIT :limit"),
                    {"limit": limit}
                )
                resolved_subset = {row[0] for row in result.fetchall()}

        await run_streaming_pipeline(
            ticker_subset=resolved_subset,
            skip_eps_history=True,
            concurrency=settings.daily_concurrency,
            rate_limit_rps=settings.daily_rate_limit_rps,
            force_refresh=False,
        )
        
        # Run Buffett analysis
        log.info("daily_analysis_running_buffett_analysis")
        analysis_result = await run_buffett_analysis()
        log.info("daily_analysis_buffett_complete", **analysis_result)
        
        # Export Postgres -> Parquet -> DuckDB view rebuild
        log.info("daily_analysis_exporting_to_duckdb")
        await run_full_export()
        log.info("daily_analysis_job_complete")
    except Exception as e:
        log.error("daily_analysis_job_failed", error=str(e))
        alert_pipeline_failure("daily_analysis_job", str(e))


async def notify_coming_earnings_job() -> None:
    """
    Coming Earnings Job:
    Queries earnings_calendar for companies reporting in the next 7 days and alerts the user.
    """
    log.info("notify_coming_earnings_job_started")
    try:
        async with AsyncSessionLocal() as session:
            # Query upcoming earnings in the next 7 days
            result = await session.execute(
                text("""
                    SELECT ec.ticker, ec.earnings_date, ec.eps_estimate, c.name AS company_name
                    FROM earnings_calendar ec
                    LEFT JOIN companies c ON ec.ticker = c.ticker
                    WHERE ec.earnings_date >= CURRENT_DATE
                      AND ec.earnings_date <= CURRENT_DATE + INTERVAL '7 days'
                    ORDER BY ec.earnings_date ASC
                """)
            )
            upcoming = [
                {
                    "ticker":        row[0],
                    "earnings_date": row[1],
                    "eps_estimate":  row[2],
                    "company_name":  row[3],
                }
                for row in result.fetchall()
            ]
        
        if upcoming:
            alert_upcoming_earnings(upcoming)
        else:
            log.info("no_upcoming_earnings_found")
    except Exception as e:
        log.error("notify_coming_earnings_failed", error=str(e))
        alert_pipeline_failure("notify_coming_earnings", str(e))


async def summarize_recent_earnings_job() -> None:
    """
    Recent Earnings Summarization:
    Queries earnings_events for filings received in the last 24 hours, aggregates beats/misses,
    and publishes a desktop notification summary at 5:00 PM.
    """
    log.info("summarize_recent_earnings_job_started")
    try:
        async with AsyncSessionLocal() as session:
            # Query earnings events reported in the last 24 hours
            result = await session.execute(
                text("""
                    SELECT ee.ticker, ee.eps_actual, ee.eps_estimate, ee.eps_surprise_pct, c.name AS company_name
                    FROM earnings_events ee
                    LEFT JOIN companies c ON ee.ticker = c.ticker
                    WHERE ee.report_date >= CURRENT_DATE - INTERVAL '1 day'
                    ORDER BY ee.report_date DESC
                """)
            )
            events = [
                {
                    "ticker":        row[0],
                    "eps_actual":    row[1],
                    "eps_estimate":  row[2],
                    "surprise_pct":  row[3],
                    "company_name":  row[4],
                }
                for row in result.fetchall()
            ]

        if not events:
            log.info("no_recent_earnings_events_to_summarize")
            alert_earnings_summary("No corporate earnings reported today.")
            return

        beats = 0
        misses = 0
        in_line = 0
        for item in events:
            act = item["eps_actual"]
            est = item["eps_estimate"]
            if act is not None and est is not None and est != 0:
                surprise = (act - est) / abs(est)
                if surprise > 0.02:
                    beats += 1
                elif surprise < -0.02:
                    misses += 1
                else:
                    in_line += 1
            else:
                in_line += 1

        summary_text = (
            f"Total Reports: {len(events)}\n"
            f"✅ Beats: {beats} | ❌ Misses: {misses} | 📊 In-Line/Other: {in_line}\n"
        )
        if events:
            summary_text += "\nLatest: " + ", ".join([f"{e['ticker']}" for e in events[:4]])

        alert_earnings_summary(summary_text)
    except Exception as e:
        log.error("summarize_recent_earnings_failed", error=str(e))
        alert_pipeline_failure("summarize_recent_earnings", str(e))


def build_daily_scheduler() -> AsyncIOScheduler:
    """Builds and returns the daily earnings and analysis APScheduler in Pacific Time."""
    scheduler = AsyncIOScheduler(timezone="America/Los_Angeles")

    # 1. Pre-market scan (7 AM PT)
    scheduler.add_job(
        daily_earnings_job,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour=settings.daily_run_hour_am,
            minute=0,
            timezone=scheduler.timezone,
        ),
        id="daily_earnings_am",
        name="Daily Earnings Tracker (AM)",
        replace_existing=True,
        max_instances=1,
    )

    # 2. After-hours scan (6 PM PT)
    scheduler.add_job(
        daily_earnings_job,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour=settings.daily_run_hour_pm,
            minute=0,
            timezone=scheduler.timezone,
        ),
        id="daily_earnings_pm",
        name="Daily Earnings Tracker (PM)",
        replace_existing=True,
        max_instances=1,
    )

    # 3. Daily full analysis (4 AM PT)
    scheduler.add_job(
        daily_analysis_job,
        trigger=CronTrigger(
            hour=4,
            minute=0,
            timezone=scheduler.timezone,
        ),
        id="daily_analysis",
        name="Daily Buffett Analysis",
        replace_existing=True,
        max_instances=1,
    )

    # 4. Coming Earnings Alert (8:30 AM PT)
    scheduler.add_job(
        notify_coming_earnings_job,
        trigger=CronTrigger(
            hour=8,
            minute=30,
            timezone=scheduler.timezone,
        ),
        id="notify_coming_earnings",
        name="Morning Upcoming Earnings Alert",
        replace_existing=True,
        max_instances=1,
    )

    # 5. Recent Earnings Summarization (5:00 PM PT)
    scheduler.add_job(
        summarize_recent_earnings_job,
        trigger=CronTrigger(
            hour=17,
            minute=0,
            timezone=scheduler.timezone,
        ),
        id="summarize_recent_earnings",
        name="Afternoon Recent Earnings Summary",
        replace_existing=True,
        max_instances=1,
    )

    return scheduler
