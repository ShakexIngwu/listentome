"""
ingestion/nasdaq_discovery.py
Fetches the full NASDAQ company list and upserts into PostgreSQL.
Primary source: NASDAQ screener API (JSON with CSV download).
Fallback: community-maintained GitHub CSV.
"""
import re
from datetime import datetime, timezone

import httpx
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings

log = structlog.get_logger()

FALLBACK_CSV_URL = (
    "https://raw.githubusercontent.com/datasets/nasdaq-listings/"
    "master/data/nasdaq-listed-symbols.csv"
)


def _parse_market_cap(raw: str) -> int | None:
    """Converts NASDAQ market cap strings like '$1.2B', '$450M' to integers."""
    if not raw:
        return None
    raw = raw.strip().lstrip("$").upper().replace(",", "")
    multipliers = {"T": 1_000_000_000_000, "B": 1_000_000_000, "M": 1_000_000, "K": 1_000}
    for suffix, mult in multipliers.items():
        if raw.endswith(suffix):
            try:
                return int(float(raw[:-1]) * mult)
            except ValueError:
                return None
    try:
        return int(float(raw))
    except ValueError:
        return None


from dataclasses import dataclass, field


@dataclass
class DiscoveryResult:
    total: int                             # tickers upserted from NASDAQ
    newly_listed: set[str] = field(default_factory=set)   # not seen in DB before
    newly_delisted: set[str] = field(default_factory=set) # were active, now gone


async def fetch_nasdaq_companies(db: AsyncSession) -> DiscoveryResult:
    """
    Downloads the full NASDAQ company list (JSON) and upserts into PostgreSQL.
    Falls back to a CSV source if the primary API fails.

    Returns a DiscoveryResult containing:
      - total:           number of upserted rows
      - newly_listed:    tickers that didn't exist in the DB before this run
      - newly_delisted:  tickers previously active in DB but absent from NASDAQ list
    """
    headers = {
        "User-Agent": settings.edgar_user_agent,
        "Accept": "application/json",
    }

    rows: list[dict] = []

    async with httpx.AsyncClient(timeout=30, headers=headers) as client:
        # Primary: NASDAQ screener JSON API
        try:
            resp = await client.get(settings.nasdaq_url)
            resp.raise_for_status()
            data = resp.json()
            rows = data.get("data", {}).get("rows", [])
            log.info("nasdaq_primary_fetched", count=len(rows))
        except Exception as e:
            log.warning("nasdaq_primary_failed", error=str(e), fallback=True)
            rows = []

        # Fallback: GitHub CSV
        if not rows:
            try:
                resp = await client.get(FALLBACK_CSV_URL)
                resp.raise_for_status()
                lines = resp.text.splitlines()
                header = [h.strip() for h in lines[0].split(",")]
                for line in lines[1:]:
                    parts = line.split(",")
                    row = dict(zip(header, parts))
                    rows.append({
                        "symbol": row.get("Symbol", "").strip(),
                        "name": row.get("Company Name", "").strip(),
                        "sector": None,
                        "industry": None,
                        "country": "USA",
                        "marketCap": "",
                    })
                log.info("nasdaq_fallback_fetched", count=len(rows))
            except Exception as e:
                log.error("nasdaq_fallback_failed", error=str(e))
                return DiscoveryResult(total=0)

    # Build the set of valid tickers from this run
    nasdaq_tickers: set[str] = set()
    for row in rows:
        ticker = (row.get("symbol") or "").strip().upper()
        if ticker and re.match(r"^[A-Z]{1,5}$", ticker):
            nasdaq_tickers.add(ticker)

    # Fetch currently active tickers from DB to detect new + delisted
    existing = await db.execute(
        text("SELECT ticker FROM companies WHERE is_active = TRUE")
    )
    db_active: set[str] = {r[0] for r in existing.fetchall()}

    newly_listed   = nasdaq_tickers - db_active          # in NASDAQ, not in DB
    newly_delisted = db_active - nasdaq_tickers           # in DB, not in NASDAQ

    # Mark delisted tickers as inactive
    if newly_delisted:
        await db.execute(
            text("UPDATE companies SET is_active = FALSE WHERE ticker = ANY(:tickers)"),
            {"tickers": list(newly_delisted)},
        )
        log.info("tickers_delisted", count=len(newly_delisted))

    # Upsert all rows
    now = datetime.now(timezone.utc)
    upsert_count = 0

    for row in rows:
        ticker = (row.get("symbol") or "").strip().upper()
        if not ticker or not re.match(r"^[A-Z]{1,5}$", ticker):
            continue

        await db.execute(
            text("""
                INSERT INTO companies
                    (ticker, name, sector, industry, country, market_cap, last_updated_at, is_active)
                VALUES
                    (:ticker, :name, :sector, :industry, :country, :market_cap, :updated_at, TRUE)
                ON CONFLICT (ticker) DO UPDATE SET
                    name            = EXCLUDED.name,
                    sector          = EXCLUDED.sector,
                    industry        = EXCLUDED.industry,
                    market_cap      = EXCLUDED.market_cap,
                    last_updated_at = EXCLUDED.last_updated_at,
                    is_active       = TRUE
            """),
            {
                "ticker":     ticker,
                "name":       (row.get("name") or "").strip() or ticker,
                "sector":     row.get("sector") or None,
                "industry":   row.get("industry") or None,
                "country":    row.get("country") or "USA",
                "market_cap": _parse_market_cap(row.get("marketCap", "")),
                "updated_at": now,
            },
        )
        upsert_count += 1

    await db.commit()
    log.info(
        "nasdaq_upsert_complete",
        total=upsert_count,
        newly_listed=len(newly_listed),
        newly_delisted=len(newly_delisted),
    )
    return DiscoveryResult(
        total=upsert_count,
        newly_listed=newly_listed,
        newly_delisted=newly_delisted,
    )
