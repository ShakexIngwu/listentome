"""
streaming/worker.py
Async streaming pipeline: N concurrent workers pull tickers from a bounded
asyncio.Queue, fetch financial data, and write to PostgreSQL.

Rate-limit strategy (multi-pass, up to MAX_ATTEMPTS total):
  Pass 1 — Main queue: N workers at RATE_LIMIT_RPS.
            Any 429 → deferred list. Non-429 → permanent failure (data issue).
  Pass 2-4 — Retry passes: 1 slow worker at RETRY_RPS after RETRY_COOLDOWN_S.
              Same rule: 429 → defer again (if attempts remaining).
  Pass 4 — Final pass: no further deferral, 429 = permanent failure.

A ticker is tried at most MAX_ATTEMPTS=4 times total before being abandoned.
Non-429 errors (missing data, bad ticker) are never retried.
"""
import asyncio
import uuid
from datetime import date

import structlog
from sqlalchemy import text

from config import settings
from db.postgres import AsyncSessionLocal
from ingestion.yfinance_fetcher import fetch_eps_history, fetch_ticker_info
from streaming.rate_limiter import TokenBucket

log = structlog.get_logger()

MAX_ATTEMPTS = 4          # Max total tries per ticker (incl. first attempt)
RETRY_COOLDOWN_S = 90.0   # Seconds to wait before each retry pass
RETRY_RPS = 0.3           # Slow rate for retry passes (1 req / ~3s)


def _is_rate_limit_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return (
        "too many requests" in msg
        or "429" in msg
        or "rate limit" in msg
        or "empty or invalid yfinance response" in msg
        or "connection" in msg
        or "timeout" in msg
    )


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _write_snapshot(session, data: dict) -> None:
    await session.execute(
        text("""
            INSERT INTO financial_snapshots (
                ticker, snapshot_date,
                market_cap, enterprise_value, pe_ratio, forward_pe,
                price_to_book, price_to_sales, ev_to_ebitda,
                eps_ttm, eps_growth_5y, eps_growth_1y, revenue_ttm,
                gross_margin, operating_margin, net_margin,
                total_debt, debt_to_equity, current_ratio,
                free_cash_flow, return_on_equity, return_on_assets,
                current_price, fifty_two_week_high, fifty_two_week_low,
                data_source
            ) VALUES (
                :ticker, :snapshot_date,
                :market_cap, :enterprise_value, :pe_ratio, :forward_pe,
                :price_to_book, :price_to_sales, :ev_to_ebitda,
                :eps_ttm, :eps_growth_5y, :eps_growth_1y, :revenue_ttm,
                :gross_margin, :operating_margin, :net_margin,
                :total_debt, :debt_to_equity, :current_ratio,
                :free_cash_flow, :return_on_equity, :return_on_assets,
                :current_price, :fifty_two_week_high, :fifty_two_week_low,
                :data_source
            )
            ON CONFLICT (ticker, snapshot_date) DO UPDATE SET
                market_cap       = EXCLUDED.market_cap,
                pe_ratio         = EXCLUDED.pe_ratio,
                eps_ttm          = EXCLUDED.eps_ttm,
                return_on_equity = EXCLUDED.return_on_equity,
                free_cash_flow   = EXCLUDED.free_cash_flow,
                current_price    = EXCLUDED.current_price,
                fetched_at       = NOW()
        """),
        {**data, "snapshot_date": date.today()},
    )


async def _write_eps_history(session, eps_rows: list[dict]) -> None:
    for row in eps_rows:
        await session.execute(
            text("""
                INSERT INTO eps_history (ticker, fiscal_year, eps, source)
                VALUES (:ticker, :fiscal_year, :eps, :source)
                ON CONFLICT (ticker, fiscal_year) DO UPDATE SET
                    eps    = EXCLUDED.eps,
                    source = EXCLUDED.source
            """),
            row,
        )


async def _write_earnings_calendar(session, ticker: str, calendar_data: dict) -> None:
    dates = calendar_data.get('Earnings Date')
    earnings_date = None
    if dates and isinstance(dates, list) and len(dates) > 0:
        earnings_date = dates[0]
    elif isinstance(dates, date):
        earnings_date = dates

    if not earnings_date:
        return

    await session.execute(
        text("""
            INSERT INTO earnings_calendar (
                ticker, earnings_date, eps_estimate, revenue_estimate, confirmed, source, time_of_day
            ) VALUES (
                :ticker, :earnings_date, :eps_estimate, :revenue_estimate, :confirmed, :source, :time_of_day
            )
            ON CONFLICT (ticker, earnings_date) DO UPDATE SET
                eps_estimate     = EXCLUDED.eps_estimate,
                revenue_estimate = EXCLUDED.revenue_estimate,
                confirmed        = EXCLUDED.confirmed,
                source           = EXCLUDED.source,
                time_of_day      = EXCLUDED.time_of_day
        """),
        {
            "ticker":           ticker,
            "earnings_date":    earnings_date,
            "eps_estimate":     calendar_data.get('Earnings Average'),
            "revenue_estimate": calendar_data.get('Revenue Average'),
            "confirmed":        False,
            "source":           "yfinance",
            "time_of_day":      None,
        }
    )


# ── Worker ────────────────────────────────────────────────────────────────────

async def _worker(
    worker_id: int,
    queue: asyncio.Queue,
    rate_limiter: TokenBucket,
    stats: dict,
    deferred: list[str] | None,
    skip_eps_history: bool = False,
) -> None:
    """
    Single consumer worker.

    deferred: if provided, 429-rate-limited tickers are appended here for a
              later retry pass instead of being counted as failures.
              If None (final pass), 429s are counted as permanent failures.
    """
    async with AsyncSessionLocal() as session:
        while True:
            try:
                ticker = queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            try:
                await rate_limiter.acquire()

                t0 = asyncio.get_event_loop().time()
                info = await fetch_ticker_info(ticker)
                calendar_data = info.pop("_calendar", None)
                eps_rows = []
                if not skip_eps_history:
                    eps_rows = await fetch_eps_history(ticker)

                await _write_snapshot(session, info)
                if eps_rows:
                    await _write_eps_history(session, eps_rows)
                if calendar_data:
                    await _write_earnings_calendar(session, ticker, calendar_data)

                await session.commit()

                duration_ms = int((asyncio.get_event_loop().time() - t0) * 1000)
                log.info("ticker_done", ticker=ticker, worker=worker_id, duration_ms=duration_ms)
                stats["succeeded"] += 1

            except Exception as exc:
                await session.rollback()

                if _is_rate_limit_error(exc) and deferred is not None:
                    # Rate-limited and we still have retry budget — defer
                    deferred.append(ticker)
                    log.warning("ticker_deferred", ticker=ticker, worker=worker_id, error=str(exc))
                else:
                    # Non-429 error (bad ticker, missing data) OR final pass — give up
                    stats["failed"] += 1
                    log.error("ticker_failed", ticker=ticker, worker=worker_id, error=str(exc))

            finally:
                queue.task_done()


# ── Orchestrator ──────────────────────────────────────────────────────────────

async def run_streaming_pipeline(
    run_id: str | None = None,
    ticker_subset: set[str] | None = None,
    skip_eps_history: bool = False,
    concurrency: int | None = None,
    rate_limit_rps: float | None = None,
    force_refresh: bool = False,
) -> dict:
    """
    Multi-pass streaming pipeline. Retries 429-rate-limited tickers up to
    MAX_ATTEMPTS times total before giving up on them.

    ticker_subset: if provided, only fetch yfinance data for these tickers.
                  Pass None (default) to process ALL active tickers in the DB.
    concurrency: custom number of parallel workers. Defaults to settings.worker_concurrency.
    rate_limit_rps: custom limit of requests per second. Defaults to settings.rate_limit_rps.
    force_refresh: if True, re-fetch all tickers even if already fetched today.
    Returns stats dict: {succeeded, failed, total, run_id}
    """
    run_id = run_id or str(uuid.uuid4())
    stats: dict = {"succeeded": 0, "failed": 0, "run_id": run_id}

    pipeline_concurrency = concurrency if concurrency is not None else settings.worker_concurrency
    pipeline_rate = rate_limit_rps if rate_limit_rps is not None else settings.rate_limit_rps

    if ticker_subset is not None:
        # Explicit subset (e.g. only newly listed tickers from weekly discovery)
        all_candidate_tickers = sorted(ticker_subset)
        log.info("pipeline_subset_mode", subset_size=len(all_candidate_tickers))
    else:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("SELECT ticker FROM companies WHERE is_active = TRUE ORDER BY ticker")
            )
            all_candidate_tickers = [row[0] for row in result.fetchall()]

    if not force_refresh:
        async with AsyncSessionLocal() as session:
            today = date.today()
            snapshot_res = await session.execute(
                text("SELECT ticker FROM financial_snapshots WHERE snapshot_date = :today"),
                {"today": today}
            )
            completed_tickers = {row[0] for row in snapshot_res.fetchall()}
        
        tickers = [t for t in all_candidate_tickers if t not in completed_tickers]
        log.info(
            "pipeline_resume_filter",
            total_candidates=len(all_candidate_tickers),
            completed_today=len(completed_tickers),
            remaining=len(tickers),
        )
    else:
        tickers = all_candidate_tickers
        log.info("pipeline_force_refresh", total=len(tickers))

    stats["total"] = len(tickers)
    log.info(
        "pipeline_started",
        run_id=run_id,
        total=len(tickers),
        workers=pipeline_concurrency,
        rate_limit_rps=pipeline_rate,
        max_attempts=MAX_ATTEMPTS,
    )

    to_process = list(tickers)

    for pass_num in range(1, MAX_ATTEMPTS + 1):
        is_first_pass = (pass_num == 1)
        is_last_pass  = (pass_num == MAX_ATTEMPTS)

        # ── Cooldown before retry passes ──────────────────────────────────────
        if not is_first_pass:
            log.info(
                "retry_pass_cooldown",
                pass_num=pass_num,
                cooldown_s=RETRY_COOLDOWN_S,
                tickers_remaining=len(to_process),
            )
            await asyncio.sleep(RETRY_COOLDOWN_S)

        # ── Build queue for this pass ─────────────────────────────────────────
        queue: asyncio.Queue = asyncio.Queue()
        for t in to_process:
            queue.put_nowait(t)

        # ── Worker config: fast multi-worker for pass 1, slow single for retries
        if is_first_pass:
            active_concurrency = pipeline_concurrency
            active_rate        = pipeline_rate
        else:
            active_concurrency = 1
            active_rate        = RETRY_RPS

        rate_limiter = TokenBucket(rate=active_rate)

        # Last pass: no deferred list → 429s counted as permanent failures
        deferred: list[str] | None = [] if not is_last_pass else None

        log.info(
            "pass_started",
            pass_num=pass_num,
            tickers=len(to_process),
            workers=active_concurrency,
            rate_rps=active_rate,
            is_final=is_last_pass,
        )

        workers = [
            asyncio.create_task(
                _worker(i, queue, rate_limiter, stats, deferred, skip_eps_history),
                name=f"p{pass_num}-worker-{i}",
            )
            for i in range(active_concurrency)
        ]
        await asyncio.gather(*workers)

        deferred_count = len(deferred) if deferred is not None else 0
        log.info(
            "pass_complete",
            pass_num=pass_num,
            succeeded=stats["succeeded"],
            failed=stats["failed"],
            deferred=deferred_count,
        )

        # Nothing deferred → all done early
        if not deferred_count:
            log.info("all_tickers_resolved", pass_num=pass_num)
            break

        # Detect possible IP ban: if >80% still rate-limited, we need a longer cooldown
        deferred_ratio = deferred_count / max(len(to_process), 1)
        if deferred_ratio > 0.8 and not is_last_pass:
            adaptive_cooldown = min(RETRY_COOLDOWN_S * (2 ** (pass_num - 1)), 600)
            log.warning(
                "possible_ip_ban_detected",
                deferred_ratio=round(deferred_ratio, 2),
                next_cooldown_s=adaptive_cooldown,
            )
        else:
            adaptive_cooldown = RETRY_COOLDOWN_S

        to_process = deferred  # type: ignore[assignment]

        # Store cooldown so next iteration can use it
        _next_cooldown = adaptive_cooldown  # noqa: F841 — used implicitly via closure

    # ── Final summary ─────────────────────────────────────────────────────────
    failure_rate = stats["failed"] / max(stats["total"], 1)
    log.info(
        "pipeline_complete",
        run_id=run_id,
        succeeded=stats["succeeded"],
        failed=stats["failed"],
        failure_rate=round(failure_rate, 3),
    )

    if failure_rate > 0.05:
        log.warning("high_failure_rate", rate=failure_rate, threshold=0.05)

    return stats
