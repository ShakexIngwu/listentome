"""
earnings_tracker/notifications/alerter.py
Sends local macOS desktop notifications for significant earnings events
and Buffett score changes using plyer.
"""
import structlog

log = structlog.get_logger()


def _notify(title: str, message: str, app_icon: str = "") -> None:
    """Sends a desktop notification. Gracefully falls back to console logs in headless/Docker environments."""
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            app_name="Buffett Screener",
            app_icon=app_icon or "",
            timeout=10,
        )
    except (FileNotFoundError, OSError) as e:
        # Expected in containerized/headless environments (e.g. no gdbus/notify-send)
        log.info(
            "notification_skipped_headless",
            title=title,
            message=message,
            reason="Running inside headless Docker container; skipped desktop GUI popup."
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


def alert_upcoming_earnings(upcoming: list[dict]) -> None:
    """Alert about upcoming earnings events in the next week."""
    if not upcoming:
        return
    lines = []
    for item in upcoming[:5]:  # show top 5
        ticker = item["ticker"]
        name = item.get("company_name") or ticker
        date_str = str(item["earnings_date"])
        est = item.get("eps_estimate")
        est_str = f" (Est: ${est:.2f})" if est is not None else ""
        lines.append(f"• {ticker}: {date_str}{est_str}")
    
    message = "\n".join(lines)
    if len(upcoming) > 5:
        message += f"\n...and {len(upcoming) - 5} more tickers."
        
    _notify(
        title=f"📅 {len(upcoming)} Upcoming Earnings (Next 7 Days)",
        message=message,
    )
    log.info("alert_sent", type="upcoming_earnings", count=len(upcoming))


def alert_earnings_summary(summary_text: str) -> None:
    """Alert with a summary of recent earnings events."""
    _notify(
        title="📊 Daily Earnings Summary (5:00 PM)",
        message=summary_text,
    )
    log.info("alert_sent", type="earnings_summary")
