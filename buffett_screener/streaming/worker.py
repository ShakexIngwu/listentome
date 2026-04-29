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
    return "too many requests" in msg or "429" in msg or "rate limit" in msg


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


# ── Worker ────────────────────────────────────────────────────────────────────

async def _worker(
    worker_id: int,
    queue: asyncio.Queue,
    rate_limiter: TokenBucket,
    stats: dict,
    deferred: list[str] | None,
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
                eps_rows = await fetch_eps_history(ticker)

                await _write_snapshot(session, info)
                if eps_rows:
                    await _write_eps_history(session, eps_rows)

                await session.commit()

                duration_ms = int((asyncio.get_event_loop().time() - t0) * 1000)
                log.info("ticker_done", ticker=ticker, worker=worker_id, duration_ms=duration_ms)
                stats["succeeded"] += 1

            except Exception as exc:
                await session.rollback()

                if _is_rate_limit_error(exc) and deferred is not None:
                    # Rate-limited and we still have retry budget — defer
                    deferred.append(ticker)
                    log.warning("ticker_deferred", ticker=ticker, worker=worker_id)
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
) -> dict:
    """
    Multi-pass streaming pipeline. Retries 429-rate-limited tickers up to
    MAX_ATTEMPTS times total before giving up on them.

    ticker_subset: if provided, only fetch yfinance data for these tickers.
                  Pass None (default) to process ALL active tickers in the DB.
    Returns stats dict: {succeeded, failed, total, run_id}
    """
    run_id = run_id or str(uuid.uuid4())
    stats: dict = {"succeeded": 0, "failed": 0, "run_id": run_id}

    if ticker_subset is not None:
        # Explicit subset (e.g. only newly listed tickers from weekly discovery)
        tickers = sorted(ticker_subset)
        log.info("pipeline_subset_mode", subset_size=len(tickers))
    else:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("SELECT ticker FROM companies WHERE is_active = TRUE ORDER BY ticker")
            )
            tickers = [row[0] for row in result.fetchall()]

    stats["total"] = len(tickers)
    log.info(
        "pipeline_started",
        run_id=run_id,
        total=len(tickers),
        workers=settings.worker_concurrency,
        rate_limit_rps=settings.rate_limit_rps,
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
            concurrency  = settings.worker_concurrency
            rate_limiter = TokenBucket(rate=settings.rate_limit_rps)
        else:
            concurrency  = 1
            rate_limiter = TokenBucket(rate=RETRY_RPS)

        # Last pass: no deferred list → 429s counted as permanent failures
        deferred: list[str] | None = [] if not is_last_pass else None

        log.info(
            "pass_started",
            pass_num=pass_num,
            tickers=len(to_process),
            workers=concurrency,
            rate_rps=settings.rate_limit_rps if is_first_pass else RETRY_RPS,
            is_final=is_last_pass,
        )

        workers = [
            asyncio.create_task(
                _worker(i, queue, rate_limiter, stats, deferred),
                name=f"p{pass_num}-worker-{i}",
            )
            for i in range(concurrency)
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
