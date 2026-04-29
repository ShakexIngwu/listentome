"""
buffett_analysis/agents/pitch_deck_generator.py
Renders a PDF investment pitch deck from a Jinja2 HTML template.
Uses WeasyPrint to convert HTML → PDF (no cloud API, fully local).
"""
import asyncio
from datetime import date
from pathlib import Path

import structlog
import weasyprint
from jinja2 import Environment, FileSystemLoader

from buffett_analysis.agents.dcf_engine import DCFResult
from buffett_analysis.agents.scorer import BuffettScore

log = structlog.get_logger()

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
OUTPUT_DIR = Path("./output/pitch_decks")


async def generate_pitch_deck(
    ticker: str,
    company_name: str,
    sector: str,
    score: BuffettScore,
    dcf: DCFResult | None,
    llm_data: dict,
    snap: dict,
    eps_history: dict[int, float],
) -> dict[str, str]:
    """
    Renders the pitch deck HTML template and converts to PDF.
    Returns {"html": path, "pdf": path}.
    Runs WeasyPrint in a thread pool (CPU-bound).
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
    template = env.get_template("pitch_deck.html.j2")

    today = date.today().isoformat()
    eps_sorted = sorted(eps_history.items())  # [(year, eps), ...]

    html_content = template.render(
        ticker=ticker,
        company_name=company_name,
        sector=sector,
        date=today,
        score=score,
        dcf=dcf,
        llm=llm_data,
        snap=snap,
        eps_history=eps_sorted,
        recommendation_color={
            "STRONG_BUY": "#00c853",
            "BUY":        "#64dd17",
            "HOLD":       "#ffd600",
            "PASS":       "#d50000",
        }.get(score.recommendation, "#888"),
    )

    html_path = OUTPUT_DIR / f"{ticker}_{today}.html"
    pdf_path  = OUTPUT_DIR / f"{ticker}_{today}.pdf"

    html_path.write_text(html_content, encoding="utf-8")

    # WeasyPrint is CPU-bound — run in executor to avoid blocking event loop
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        lambda: weasyprint.HTML(string=html_content, base_url=str(TEMPLATE_DIR)).write_pdf(str(pdf_path)),
    )

    log.info("pitch_deck_generated", ticker=ticker, pdf=str(pdf_path))
    return {"html": str(html_path), "pdf": str(pdf_path)}
