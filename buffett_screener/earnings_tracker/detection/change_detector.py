"""
earnings_tracker/detection/change_detector.py
Determines whether a new earnings event is material enough to trigger re-analysis.

Materiality thresholds:
  - EPS surprise > 5%  (beat or miss vs analyst estimate)
  - EPS change YoY > 15%
  - Ticker is in the current Top 20 Buffett screener (always re-score)
"""
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger()


async def evaluate_material_change(
    ticker: str,
    new_eps: float,
    eps_estimate: float | None,
    db: AsyncSession,
) -> tuple[bool, str]:
    """
    Compares new earnings data against the prior quarter's snapshot in PostgreSQL.

    Returns (is_material, reason_string).
    PostgreSQL's row-level locking ensures consistent reads even when
    the weekly ingestion pipeline runs concurrently.
    """
    result = await db.execute(
        text("""
            SELECT eps_actual, eps_estimate
            FROM earnings_events
            WHERE ticker = :ticker
            ORDER BY report_date DESC
            LIMIT 1
        """),
        {"ticker": ticker},
    )
    prior = result.fetchone()

    if not prior:
        return True, "first_earnings_event"

    prior_eps, prior_est = prior

    # EPS surprise vs estimate
    estimate = eps_estimate or prior_est or new_eps
    if estimate and estimate != 0:
        surprise = abs((new_eps - estimate) / estimate)
        if surprise > 0.05:
            return True, f"eps_surprise_{surprise:.1%}"

    # YoY EPS change
    if prior_eps and prior_eps != 0:
        yoy_change = abs((new_eps - prior_eps) / prior_eps)
        if yoy_change > 0.15:
            return True, f"eps_yoy_change_{yoy_change:.1%}"

    # Always re-score Top 20
    if await _is_in_top20(ticker, db):
        return True, "in_top20_watchlist"

    return False, "below_materiality_threshold"


async def _is_in_top20(ticker: str, db: AsyncSession) -> bool:
    """Checks if a ticker was in the Top 20 Buffett scores within the last 8 days."""
    result = await db.execute(
        text("""
            SELECT ticker FROM buffett_scores
            WHERE analysis_date >= CURRENT_DATE - INTERVAL '8 days'
            ORDER BY buffett_total_score DESC
            LIMIT 20
        """)
    )
    top20 = {row[0] for row in result.fetchall()}
    return ticker in top20
