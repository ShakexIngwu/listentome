"""
earnings_tracker/parsing/cik_resolver.py
Resolves CIK → ticker by downloading EDGAR's full company_tickers.json
and upserting into PostgreSQL companies.edgar_cik.
"""
import httpx
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings

log = structlog.get_logger()

EDGAR_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
EDGAR_HEADERS = {"User-Agent": settings.edgar_user_agent}


async def build_cik_ticker_map(db: AsyncSession) -> int:
    """
    Downloads EDGAR's full CIK→ticker mapping and upserts edgar_cik into companies.
    Returns the number of rows updated.
    """
    async with httpx.AsyncClient(headers=EDGAR_HEADERS, timeout=30) as client:
        try:
            resp = await client.get(EDGAR_TICKERS_URL)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.error("cik_map_fetch_failed", error=str(e))
            return 0

    updated = 0
    for entry in data.values():
        cik = str(entry.get("cik_str", "")).zfill(10)
        ticker = str(entry.get("ticker", "")).upper().strip()
        if not ticker or not cik:
            continue

        result = await db.execute(
            text("UPDATE companies SET edgar_cik = :cik WHERE ticker = :ticker RETURNING ticker"),
            {"cik": cik, "ticker": ticker},
        )
        if result.rowcount:
            updated += 1

    await db.commit()
    log.info("cik_map_built", updated=updated)
    return updated


async def resolve_ticker(cik: str, db: AsyncSession) -> str | None:
    """Returns the ticker symbol for a given CIK from PostgreSQL."""
    cik_padded = str(cik).zfill(10)
    result = await db.execute(
        text("SELECT ticker FROM companies WHERE edgar_cik = :cik"),
        {"cik": cik_padded},
    )
    row = result.fetchone()
    return row[0] if row else None
