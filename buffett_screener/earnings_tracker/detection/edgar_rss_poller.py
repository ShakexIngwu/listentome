"""
earnings_tracker/detection/edgar_rss_poller.py
Polls the SEC EDGAR 8-K RSS feed (Atom format) for earnings releases.
Filters entries containing Item 2.02 (Results of Operations).
"""
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import httpx
import structlog

from config import settings

log = structlog.get_logger()

EDGAR_RSS_URL = (
    "https://www.sec.gov/cgi-bin/browse-edgar"
    "?action=getcurrent&type=8-K&dateb=&owner=include"
    "&count=200&search_text=&output=atom"
)
EDGAR_HEADERS = {
    "User-Agent": settings.edgar_user_agent,
    "Accept-Encoding": "gzip, deflate",
}
NS = {"atom": "http://www.w3.org/2005/Atom"}


def _extract_cik(entry: ET.Element) -> str | None:
    """Extracts CIK from an EDGAR Atom entry's link URL."""
    link = entry.find("atom:link[@type='text/html']", NS)
    if link is None:
        return None
    href = link.get("href", "")
    # EDGAR URLs contain /cgi-bin/browse-edgar?action=getcompany&CIK=XXXXXXXXXX
    import re
    m = re.search(r"CIK=(\d+)", href, re.IGNORECASE)
    return m.group(1).zfill(10) if m else None


async def poll_edgar_8k_feed(lookback_hours: int = 25) -> list[dict]:
    """
    Fetches the EDGAR 8-K RSS feed and returns filings that:
    - Were filed within the last `lookback_hours`
    - Contain Item 2.02 (Results of Operations) → earnings releases

    Returns list of dicts: {cik, filed_at, filing_url, summary}
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    async with httpx.AsyncClient(headers=EDGAR_HEADERS, timeout=30) as client:
        try:
            resp = await client.get(EDGAR_RSS_URL)
            resp.raise_for_status()
        except Exception as e:
            log.error("edgar_rss_fetch_failed", error=str(e))
            return []

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as e:
        log.error("edgar_rss_parse_failed", error=str(e))
        return []

    earnings_filings: list[dict] = []

    for entry in root.findall("atom:entry", NS):
        # Parse the filing timestamp
        updated_str = entry.findtext("atom:updated", namespaces=NS) or ""
        try:
            filed_at = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
        except ValueError:
            continue

        if filed_at < cutoff:
            continue

        summary = entry.findtext("atom:summary", namespaces=NS) or ""

        # Screen for earnings releases: Item 2.02 or "Results of Operations"
        if "2.02" not in summary and "Results of Operations" not in summary:
            continue

        cik = _extract_cik(entry)
        if not cik:
            continue

        link_el = entry.find("atom:link[@type='text/html']", NS)
        filing_url = link_el.get("href", "") if link_el is not None else ""

        earnings_filings.append({
            "cik":        cik,
            "filed_at":   filed_at,
            "filing_url": filing_url,
            "summary":    summary[:500],
        })

    log.info("edgar_poll_complete", found=len(earnings_filings), lookback_hours=lookback_hours)
    return earnings_filings
