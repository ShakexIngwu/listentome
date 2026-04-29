"""
earnings_tracker/notifications/alerter.py
Sends local macOS desktop notifications for significant earnings events
and Buffett score changes using plyer.
"""
import structlog

log = structlog.get_logger()


def _notify(title: str, message: str, app_icon: str = "") -> None:
    """Sends a desktop notification. Silent fail if plyer is unavailable."""
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            app_name="Buffett Screener",
            app_icon=app_icon or "",
            timeout=10,
        )
    except Exception as e:
        log.warning("notification_failed", error=str(e))


def alert_earnings_surprise(ticker: str, company_name: str, surprise_pct: float, eps_actual: float) -> None:
    """Alert on a significant EPS beat or miss."""
    direction = "BEAT ✅" if surprise_pct > 0 else "MISS ❌"
    _notify(
        title=f"{ticker} Earnings {direction}",
        message=f"{company_name}\nEPS: ${eps_actual:.2f} ({surprise_pct:+.1%} vs estimate)",
    )
    log.info("alert_sent", type="earnings_surprise", ticker=ticker, surprise=surprise_pct)


def alert_rank_change(ticker: str, company_name: str, old_rank: int, new_rank: int, score: float) -> None:
    """Alert when a stock enters or significantly re-ranks in the Top 20."""
    if new_rank <= 5:
        emoji = "🔥"
    elif new_rank <= 10:
        emoji = "📈"
    else:
        emoji = "📊"

    _notify(
        title=f"{emoji} {ticker} Rank #{new_rank} (was #{old_rank})",
        message=f"{company_name}\nBuffett Score: {score:.0f}/100",
    )
    log.info("alert_sent", type="rank_change", ticker=ticker, old=old_rank, new=new_rank)


def alert_new_top20_entry(ticker: str, company_name: str, score: float, recommendation: str) -> None:
    """Alert when a stock newly enters the Top 20."""
    _notify(
        title=f"🆕 {ticker} entered Top 20",
        message=f"{company_name}\nScore: {score:.0f} · {recommendation.replace('_', ' ')}",
    )
    log.info("alert_sent", type="new_top20", ticker=ticker, score=score)


def alert_pipeline_failure(pipeline_name: str, error: str) -> None:
    """Alert when a pipeline fails (high-failure-rate threshold crossed)."""
    _notify(
        title=f"⚠️ Pipeline Failure: {pipeline_name}",
        message=error[:200],
    )
    log.error("alert_sent", type="pipeline_failure", pipeline=pipeline_name, error=error)
