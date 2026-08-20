"""
ingestion/yfinance_fetcher.py
Fetches comprehensive financial data for a single ticker via yfinance.
Runs synchronous yfinance calls in a thread pool to avoid blocking the event loop.
"""
import asyncio

import structlog
import yfinance as yf
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings

log = structlog.get_logger()


import math

def _clean_float(val) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        if math.isinf(f) or math.isnan(f):
            return None
        return f
    except (ValueError, TypeError):
        return None


@retry(
    stop=stop_after_attempt(settings.yfinance_retry_attempts),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    reraise=True,
)
async def fetch_ticker_info(ticker: str) -> dict:
    """
    Fetches financial metadata for a single ticker from Yahoo Finance.
    yfinance is blocking I/O — always run via run_in_executor.

    Returns a flat dict matching the financial_snapshots schema.
    Raises on repeated failure (after retries).
    """
    loop = asyncio.get_event_loop()

    # Build the Ticker object in a thread (network I/O)
    stock: yf.Ticker = await loop.run_in_executor(None, yf.Ticker, ticker)

    # .info triggers the actual HTTP request
    info: dict = await loop.run_in_executor(None, lambda: stock.info)

    if not info or info.get("quoteType") is None:
        raise ValueError(f"Empty or invalid yfinance response for {ticker}")

    # Fetch calendar details (upcoming earnings date, estimates)
    try:
        calendar_data = await loop.run_in_executor(None, lambda: stock.calendar)
    except Exception as e:
        log.warning("calendar_fetch_failed", ticker=ticker, error=str(e))
        calendar_data = None

    result = {
        "ticker":             ticker,
        "market_cap":         _clean_float(info.get("marketCap")),
        "enterprise_value":   _clean_float(info.get("enterpriseValue")),
        "pe_ratio":           _clean_float(info.get("trailingPE")),
        "forward_pe":         _clean_float(info.get("forwardPE")),
        "price_to_book":      _clean_float(info.get("priceToBook")),
        "price_to_sales":     _clean_float(info.get("priceToSalesTrailing12Months")),
        "ev_to_ebitda":       _clean_float(info.get("enterpriseToEbitda")),
        "eps_ttm":            _clean_float(info.get("trailingEps")),
        "eps_growth_5y":      _clean_float(info.get("earningsGrowth")),
        "eps_growth_1y":      _clean_float(info.get("earningsQuarterlyGrowth")),
        "revenue_ttm":        _clean_float(info.get("totalRevenue")),
        "gross_margin":       _clean_float(info.get("grossMargins")),
        "operating_margin":   _clean_float(info.get("operatingMargins")),
        "net_margin":         _clean_float(info.get("profitMargins")),
        "total_debt":         _clean_float(info.get("totalDebt")),
        "debt_to_equity":     _clean_float(info.get("debtToEquity")),
        "current_ratio":      _clean_float(info.get("currentRatio")),
        "free_cash_flow":     _clean_float(info.get("freeCashflow")),
        "return_on_equity":   _clean_float(info.get("returnOnEquity")),
        "return_on_assets":   _clean_float(info.get("returnOnAssets")),
        "current_price":      _clean_float(info.get("currentPrice") or info.get("regularMarketPrice")),
        "fifty_two_week_high": _clean_float(info.get("fiftyTwoWeekHigh")),
        "fifty_two_week_low":  _clean_float(info.get("fiftyTwoWeekLow")),
        "data_source":        "yfinance",
    }

    if calendar_data:
        result["_calendar"] = calendar_data

    return result


async def fetch_eps_history(ticker: str) -> list[dict]:
    """
    Fetches annual EPS history for eps_history table.
    Returns list of {ticker, fiscal_year, eps, source}.
    """
    loop = asyncio.get_event_loop()
    stock: yf.Ticker = await loop.run_in_executor(None, yf.Ticker, ticker)

    try:
        income_stmt = await loop.run_in_executor(None, lambda: stock.income_stmt)
        if income_stmt is None or income_stmt.empty:
            return []

        eps_rows = []
        if "Diluted EPS" in income_stmt.index:
            eps_series = income_stmt.loc["Diluted EPS"]
            for col in eps_series.index:
                try:
                    year = int(str(col.year))
                    value = float(eps_series[col])
                    if not (value != value):  # filter NaN
                        eps_rows.append({"ticker": ticker, "fiscal_year": year, "eps": value, "source": "yfinance"})
                except Exception:
                    continue
        return eps_rows
    except Exception as e:
        log.warning("eps_history_failed", ticker=ticker, error=str(e))
        return []
