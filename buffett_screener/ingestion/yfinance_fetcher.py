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

    return {
        "ticker":             ticker,
        "market_cap":         info.get("marketCap"),
        "enterprise_value":   info.get("enterpriseValue"),
        "pe_ratio":           info.get("trailingPE"),
        "forward_pe":         info.get("forwardPE"),
        "price_to_book":      info.get("priceToBook"),
        "price_to_sales":     info.get("priceToSalesTrailing12Months"),
        "ev_to_ebitda":       info.get("enterpriseToEbitda"),
        "eps_ttm":            info.get("trailingEps"),
        "eps_growth_5y":      info.get("earningsGrowth"),
        "eps_growth_1y":      info.get("earningsQuarterlyGrowth"),
        "revenue_ttm":        info.get("totalRevenue"),
        "gross_margin":       info.get("grossMargins"),
        "operating_margin":   info.get("operatingMargins"),
        "net_margin":         info.get("profitMargins"),
        "total_debt":         info.get("totalDebt"),
        "debt_to_equity":     info.get("debtToEquity"),
        "current_ratio":      info.get("currentRatio"),
        "free_cash_flow":     info.get("freeCashflow"),
        "return_on_equity":   info.get("returnOnEquity"),
        "return_on_assets":   info.get("returnOnAssets"),
        "current_price":      info.get("currentPrice") or info.get("regularMarketPrice"),
        "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
        "fifty_two_week_low":  info.get("fiftyTwoWeekLow"),
        "data_source":        "yfinance",
    }


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
