"""
buffett_analysis/agents/orchestrator.py
Google ADK multi-agent pipeline for weekly Buffett analysis.

Architecture:
┌──────────────────────────────────────────────────────────────────────────┐
│  BuffettPipelineOrchestrator  (ADK SequentialAgent)                      │
│                                                                           │
│  1. QuantScreenerAgent     — DuckDB read-only hard-rule filter            │
│  2. DCFAgent               — Deterministic owner-earnings DCF             │
│  2.5 PreLlmRankerAgent     — Composite score → select top-N for LLM      │
│  3. LlmAnalystAgent        — Strategy-driven Gemini analysis              │
│  4. ScorerAgent            — Weighted 7-dimension Buffett Score           │
│  5. PitchDeckAgent         — Jinja2 → WeasyPrint PDF generation           │
│  6. DBWriterAgent          — Persist all results to PostgreSQL            │
│                                                                           │
│  Model: settings.gemini_model (configurable)                              │
│  Strategy: settings.analysis_strategy (pluggable)                         │
│  Framework: google-adk                                                    │
└──────────────────────────────────────────────────────────────────────────┘

Deterministic stages (1, 2, 2.5, 4, 5, 6) are implemented as ADK BaseAgent
subclasses — they do Python work and emit a status Content event.
The LLM stage (3) uses analyze_company() with a pluggable InvestmentStrategy.
"""
import asyncio
import json
import os
import uuid
from datetime import date, datetime, timezone
from typing import AsyncGenerator, TypedDict

import duckdb
import structlog
from google.adk.agents import SequentialAgent
from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.llm_agent import LlmAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.adk.models.google_llm import Gemini
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from sqlalchemy import text

from buffett_analysis.agents.dcf_engine import (
    DCFResult,
    calculate_eps_cagr,
    dcf_valuation,
)
from buffett_analysis.agents.llm_analyst import analyze_company
from buffett_analysis.agents.pitch_deck_generator import generate_pitch_deck
from buffett_analysis.agents.scorer import (
    BuffettScore,
    compute_buffett_score,
    score_eps_consistency,
    score_roe,
    score_margin_of_safety,
    score_leverage,
    score_fcf_yield,
    score_moat_proxy,
)
from buffett_analysis.strategies import get_strategy
from config import settings
from db.postgres import AsyncSessionLocal

log = structlog.get_logger()

# ── Shared in-process pipeline state ──────────────────────────────────────────
# ADK sessions carry text; we store heavy Python objects here and reference
# them by run_id key. A single pipeline run is fully synchronous within
# one event loop, so there are no concurrency conflicts.
_PIPELINE_STATE: dict[str, dict] = {}


class PipelineState(TypedDict):
    run_id: str
    candidate_tickers: list[str]
    snapshots: dict[str, dict]
    eps_histories: dict[str, dict]
    dcf_results: dict[str, DCFResult]
    pre_llm_scores: dict[str, float]       # composite quant score per ticker
    llm_candidates: list[str]              # top-N tickers selected for LLM
    llm_results: dict[str, dict]
    scores: dict[str, BuffettScore]
    top_tickers: list[str]
    pitch_deck_paths: dict[str, str]


def _state(run_id: str) -> PipelineState:
    return _PIPELINE_STATE[run_id]


# ── Helper: emit a simple text event from a BaseAgent ─────────────────────────
def _text_event(author: str, text: str) -> Event:
    return Event(
        author=author,
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(text=text)],
        ),
    )


# ════════════════════════════════════════════════════════════════════════════════
# Stage 1 — Quant Screener
# ════════════════════════════════════════════════════════════════════════════════
class QuantScreenerAgent(BaseAgent):
    """
    Hard-rule filter using DuckDB (read-only Parquet views).
    Eliminates ~90% of the universe before any expensive operations.
    No LLM involved — pure SQL.
    """

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        run_id = ctx.session.state.get("run_id", "")
        s = _state(run_id)

        try:
            con = duckdb.connect(settings.duckdb_path, read_only=True)
            
            if settings.skip_screener:
                log.info("quant_screener_bypassed", run_id=run_id)
                rows = con.execute("SELECT DISTINCT ticker FROM financial_snapshots").fetchall()
            else:
                rows = con.execute("""
                    SELECT DISTINCT fs.ticker
                    FROM financial_snapshots fs
                    JOIN eps_history eh ON fs.ticker = eh.ticker
                    WHERE fs.snapshot_date >= CURRENT_DATE - INTERVAL '8 days'
                      AND fs.return_on_equity >= 0.12
                      AND fs.debt_to_equity   <= 1.0
                      AND fs.net_margin       >= 0.05
                      AND fs.free_cash_flow    > 0
                      AND fs.pe_ratio IS NOT NULL
                      AND fs.pe_ratio BETWEEN 5 AND 40
                    GROUP BY fs.ticker
                    HAVING COUNT(DISTINCT eh.fiscal_year) >= 5
                """).fetchall()

            candidates = [r[0] for r in rows]

            if candidates:
                placeholders = ", ".join(f"'{t}'" for t in candidates)
                # Load latest snapshot for each candidate
                snap_df = con.execute(f"""
                    SELECT * FROM financial_snapshots fs
                    WHERE ticker IN ({placeholders})
                      AND snapshot_date = (
                          SELECT MAX(s2.snapshot_date) FROM financial_snapshots s2
                          WHERE s2.ticker = fs.ticker
                      )
                """).fetchdf()
                snapshots = {row["ticker"]: row.to_dict() for _, row in snap_df.iterrows()}

                eps_rows = con.execute(f"""
                    SELECT ticker, fiscal_year, eps FROM eps_history
                    WHERE ticker IN ({placeholders})
                """).fetchall()
                eps_histories: dict[str, dict] = {}
                for ticker, year, eps in eps_rows:
                    eps_histories.setdefault(ticker, {})[year] = eps
            else:
                snapshots, eps_histories = {}, {}

            con.close()

        except Exception as exc:
            log.error("quant_screener_error", run_id=run_id, error=str(exc))
            candidates, snapshots, eps_histories = [], {}, {}

        s["candidate_tickers"] = candidates
        s["snapshots"]         = snapshots
        s["eps_histories"]     = eps_histories

        log.info("quant_screener_done", run_id=run_id, candidates=len(candidates))
        yield _text_event(self.name, f"Quant screener: {len(candidates)} candidates passed.")


# ════════════════════════════════════════════════════════════════════════════════
# Stage 2 — DCF Engine
# ════════════════════════════════════════════════════════════════════════════════
class DCFAgent(BaseAgent):
    """Runs owner-earnings DCF for every candidate. No LLM."""

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        run_id = ctx.session.state.get("run_id", "")
        s = _state(run_id)
        dcf_results: dict[str, DCFResult] = {}

        import math

        for ticker in s["candidate_tickers"]:
            snap     = s["snapshots"].get(ticker, {})
            eps_hist = s["eps_histories"].get(ticker, {})

            # Guard against NaN / None values from yfinance
            raw_fcf = snap.get("free_cash_flow")
            owner_earnings = raw_fcf if (raw_fcf is not None and math.isfinite(raw_fcf)) else 0
            if owner_earnings <= 0:
                continue

            growth    = calculate_eps_cagr(eps_hist, years=5)
            raw_price = snap.get("current_price")
            price     = raw_price if (raw_price is not None and math.isfinite(raw_price)) else 0
            raw_mcap  = snap.get("market_cap")
            market_cap = raw_mcap if (raw_mcap is not None and math.isfinite(raw_mcap)) else 0
            shares    = int(market_cap / price) if price > 0 and market_cap > 0 else 1

            result = dcf_valuation(
                owner_earnings=owner_earnings,
                growth_rate=growth,
                shares_outstanding=shares,
                current_price=price,
            )
            if result:
                result.ticker = ticker
                dcf_results[ticker] = result

        s["dcf_results"] = dcf_results
        log.info("dcf_engine_done", run_id=run_id, valuations=len(dcf_results))
        yield _text_event(self.name, f"DCF engine: {len(dcf_results)} valuations complete.")


# ════════════════════════════════════════════════════════════════════════════════
# Stage 2.5 — Pre-LLM Ranker
# ════════════════════════════════════════════════════════════════════════════════
class PreLlmRankerAgent(BaseAgent):
    """
    Computes a composite quantitative score for ALL tickers, then selects the
    top-N (settings.llm_top_n) for the expensive LLM analysis stage.
    Uses the active strategy's rank_candidates() for custom ranking.
    """

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        import math
        run_id = ctx.session.state.get("run_id", "")
        s = _state(run_id)

        strategy = get_strategy(settings.analysis_strategy)
        pre_llm_scores: dict[str, float] = {}
        candidate_dicts: list[dict] = []

        for ticker in s["candidate_tickers"]:
            snap     = s["snapshots"].get(ticker, {})
            eps_hist = s["eps_histories"].get(ticker, {})
            dcf      = s["dcf_results"].get(ticker)

            # Compute dimension scores (same logic as scorer, but without LLM)
            eps_score  = score_eps_consistency(eps_hist)
            roe_val    = snap.get("return_on_equity")
            roe_sc     = score_roe([roe_val] if roe_val else [])
            mos_sc     = score_margin_of_safety(dcf)
            lev_sc     = score_leverage(snap.get("debt_to_equity"))
            fcf_sc     = score_fcf_yield(snap.get("free_cash_flow"), snap.get("market_cap"))
            moat_sc    = score_moat_proxy(snap.get("gross_margin"))

            # Weighted composite (same weights as scorer, minus LLM component)
            composite = (
                eps_score * 0.22 +
                roe_sc    * 0.22 +
                mos_sc    * 0.22 +
                lev_sc    * 0.16 +
                fcf_sc    * 0.13 +
                moat_sc   * 0.05
            )

            pre_llm_scores[ticker] = round(composite, 2)

            # Build candidate dict for strategy ranking
            raw_price = snap.get("current_price")
            price = raw_price if (raw_price is not None and math.isfinite(raw_price)) else 0
            raw_mcap = snap.get("market_cap")
            mcap = raw_mcap if (raw_mcap is not None and math.isfinite(raw_mcap)) else 0

            candidate_dicts.append({
                "ticker":           ticker,
                "pre_llm_score":    composite,
                "sector":           snap.get("sector", ""),
                "industry":         snap.get("industry", ""),
                "eps_cagr_5y":      calculate_eps_cagr(eps_hist, years=5),
                "margin_of_safety": dcf.margin_of_safety if dcf else 0,
                "fcf_yield":        (snap.get("free_cash_flow") or 0) / mcap if mcap > 0 else 0,
                "roe":              roe_val or 0,
                "debt_to_equity":   snap.get("debt_to_equity") or 0,
                "pe_ratio":         snap.get("pe_ratio") or 0,
                "current_price":    price,
                "market_cap":       mcap,
            })

        s["pre_llm_scores"] = pre_llm_scores

        # Apply strategy-specific ranking
        ranked = strategy.rank_candidates(candidate_dicts)

        # Filter to candidates that have DCF results (meaningful data)
        eligible = [c for c in ranked if c["ticker"] in s["dcf_results"]]
        top_n = settings.llm_top_n
        selected = [c["ticker"] for c in eligible[:top_n]]

        s["llm_candidates"] = selected

        log.info(
            "pre_llm_ranker_done",
            run_id=run_id,
            strategy=strategy.name,
            total_candidates=len(s["candidate_tickers"]),
            with_dcf=len(eligible),
            eligible_for_llm=len(eligible),
            selected_for_llm=len(selected),
        )
        yield _text_event(
            self.name,
            f"Pre-LLM ranker ({strategy.display_name}): "
            f"{len(eligible)} eligible → {len(selected)} selected for LLM analysis.",
        )


# ════════════════════════════════════════════════════════════════════════════════
# Stage 3 — Strategy-Driven LLM Analyst
# ════════════════════════════════════════════════════════════════════════════════
class LlmAnalystAgent(BaseAgent):
    """
    Calls Gemini for the top-N candidates selected by PreLlmRankerAgent.
    Uses the active investment strategy's system prompt and output schema.
    """

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        import math
        run_id = ctx.session.state.get("run_id", "")
        s = _state(run_id)

        strategy = get_strategy(settings.analysis_strategy)
        llm_candidates = s.get("llm_candidates", [])
        llm_results: dict[str, dict] = {}

        async with AsyncSessionLocal() as db:
            for i, ticker in enumerate(llm_candidates, 1):
                snap     = s["snapshots"].get(ticker, {})
                dcf      = s["dcf_results"].get(ticker)
                eps_hist = s["eps_histories"].get(ticker, {})

                comp = (await db.execute(
                    text("SELECT name, sector, industry FROM companies WHERE ticker = :t"),
                    {"t": ticker},
                )).fetchone()

                # Safe numeric extraction
                def _safe(val, default=0):
                    if val is None:
                        return default
                    try:
                        return val if math.isfinite(val) else default
                    except (TypeError, ValueError):
                        return default

                result = await analyze_company(
                    strategy=strategy,
                    ticker=ticker,
                    company_name=comp[0] if comp else ticker,
                    sector=comp[1] if comp else "",
                    industry=comp[2] if comp else "",
                    eps_ttm=_safe(snap.get("eps_ttm")),
                    roe=_safe(snap.get("return_on_equity")),
                    gross_margin=_safe(snap.get("gross_margin")),
                    debt_to_equity=_safe(snap.get("debt_to_equity")),
                    free_cash_flow=int(_safe(snap.get("free_cash_flow"))),
                    market_cap=int(_safe(snap.get("market_cap"))),
                    current_price=_safe(snap.get("current_price")),
                    pe_ratio=_safe(snap.get("pe_ratio")),
                    margin_of_safety=dcf.margin_of_safety if dcf else 0.0,
                    eps_cagr_5y=calculate_eps_cagr(eps_hist, years=5),
                    pre_llm_score=s["pre_llm_scores"].get(ticker, 0),
                    eps_history=eps_hist,
                    dcf_intrinsic_value=dcf.intrinsic_value_per_share if dcf else 0.0,
                )
                llm_results[ticker] = result

                if i % 10 == 0:
                    log.info("llm_progress", run_id=run_id, completed=i, total=len(llm_candidates))

        s["llm_results"] = llm_results
        log.info(
            "llm_analyst_done",
            run_id=run_id,
            model=settings.gemini_model,
            strategy=strategy.name,
            analyzed=len(llm_results),
        )
        yield _text_event(
            self.name,
            f"LLM analyst ({strategy.display_name}, {settings.gemini_model}): "
            f"{len(llm_results)} companies analyzed.",
        )


# ════════════════════════════════════════════════════════════════════════════════
# Stage 4 — Scorer
# ════════════════════════════════════════════════════════════════════════════════
class ScorerAgent(BaseAgent):
    """Computes the weighted 7-dimension Buffett Score for each candidate."""

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        run_id = ctx.session.state.get("run_id", "")
        s = _state(run_id)
        scores: dict[str, BuffettScore] = {}

        for ticker in s["candidate_tickers"]:
            snap     = s["snapshots"].get(ticker, {})
            eps_hist = s["eps_histories"].get(ticker, {})
            dcf      = s["dcf_results"].get(ticker)
            llm      = s["llm_results"].get(ticker, {})

            roe = snap.get("return_on_equity")
            score = compute_buffett_score(
                ticker=ticker,
                eps_by_year=eps_hist,
                roe_values=[roe] if roe else [],
                dcf_result=dcf,
                debt_to_equity=snap.get("debt_to_equity"),
                free_cash_flow=snap.get("free_cash_flow"),
                market_cap=snap.get("market_cap"),
                gross_margin=snap.get("gross_margin"),
                llm_quality_score=llm.get("llm_quality_score", 50.0),
            )
            scores[ticker] = score

        top_20 = sorted(scores, key=lambda t: scores[t].buffett_total_score, reverse=True)[:20]
        s["scores"]      = scores
        s["top_tickers"] = top_20

        log.info("scorer_done", run_id=run_id, scored=len(scores), top5=top_20[:5])
        yield _text_event(self.name, f"Scorer: {len(scores)} stocks scored. Top: {top_20[:3]}")


# ════════════════════════════════════════════════════════════════════════════════
# Stage 5 — Pitch Deck Generator
# ════════════════════════════════════════════════════════════════════════════════
class PitchDeckAgent(BaseAgent):
    """Generates Jinja2 → WeasyPrint PDF pitch decks for every Top-20 ticker."""

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        run_id = ctx.session.state.get("run_id", "")
        s = _state(run_id)
        deck_paths: dict[str, str] = {}

        async with AsyncSessionLocal() as db:
            for ticker in s["top_tickers"]:
                comp = (await db.execute(
                    text("SELECT name, sector, industry FROM companies WHERE ticker = :t"),
                    {"t": ticker},
                )).fetchone()

                paths = await generate_pitch_deck(
                    ticker=ticker,
                    company_name=comp[0] if comp else ticker,
                    sector=comp[1] if comp else "",
                    score=s["scores"][ticker],
                    dcf=s["dcf_results"].get(ticker),
                    llm_data=s["llm_results"].get(ticker, {}),
                    snap=s["snapshots"].get(ticker, {}),
                    eps_history=s["eps_histories"].get(ticker, {}),
                )
                deck_paths[ticker] = paths["pdf"]

        s["pitch_deck_paths"] = deck_paths
        log.info("pitch_decks_done", run_id=run_id, count=len(deck_paths))
        yield _text_event(self.name, f"Pitch decks: {len(deck_paths)} PDFs generated.")


# ════════════════════════════════════════════════════════════════════════════════
# Stage 6 — PostgreSQL Writer
# ════════════════════════════════════════════════════════════════════════════════
class DBWriterAgent(BaseAgent):
    """Persists all Buffett scores and pitch deck paths to PostgreSQL."""

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        run_id = ctx.session.state.get("run_id", "")
        s = _state(run_id)
        today = date.today()

        async with AsyncSessionLocal() as db:
            for ticker, score in s["scores"].items():
                dcf = s["dcf_results"].get(ticker)
                llm = s["llm_results"].get(ticker, {})

                await db.execute(text("""
                    INSERT INTO buffett_scores (
                        ticker, analysis_date, run_id,
                        eps_consistency_score, roe_score, leverage_score,
                        fcf_yield_score, margin_of_safety_score, moat_score,
                        llm_quality_score, buffett_total_score, recommendation,
                        intrinsic_value, current_price, margin_of_safety_pct,
                        investment_thesis, moat_summary, risk_factors, llm_raw_output,
                        pitch_deck_path
                    ) VALUES (
                        :ticker, :date, :run_id,
                        :eps, :roe, :lev, :fcf, :mos, :moat,
                        :llm_q, :total, :rec,
                        :iv, :price, :mos_pct,
                        :thesis, :moat_sum, CAST(:risks AS jsonb), CAST(:raw AS jsonb),
                        :deck_path
                    )
                    ON CONFLICT (ticker, analysis_date) DO UPDATE SET
                        buffett_total_score = EXCLUDED.buffett_total_score,
                        recommendation      = EXCLUDED.recommendation,
                        pitch_deck_path     = EXCLUDED.pitch_deck_path
                """), {
                    "ticker":    ticker,
                    "date":      today,
                    "run_id":    run_id,
                    "eps":       score.eps_consistency_score,
                    "roe":       score.roe_score,
                    "lev":       score.leverage_score,
                    "fcf":       score.fcf_yield_score,
                    "mos":       score.margin_of_safety_score,
                    "moat":      score.moat_score,
                    "llm_q":     score.llm_quality_score,
                    "total":     score.buffett_total_score,
                    "rec":       score.recommendation,
                    "iv":        dcf.intrinsic_value_per_share if dcf else None,
                    "price":     dcf.current_price if dcf else None,
                    "mos_pct":   dcf.margin_of_safety if dcf else None,
                    "thesis":    llm.get("investment_thesis"),
                    "moat_sum":  llm.get("moat_summary"),
                    "risks":     json.dumps(llm.get("competitive_risks", [])),
                    "raw":       json.dumps(llm),
                    "deck_path": s["pitch_deck_paths"].get(ticker),
                })

            await db.commit()

        log.info("db_writer_done", run_id=run_id, records=len(s["scores"]))
        yield _text_event(self.name, f"DB writer: {len(s['scores'])} scores persisted to PostgreSQL.")


# ════════════════════════════════════════════════════════════════════════════════
# ADK SequentialAgent — chains all 6 stages
# ════════════════════════════════════════════════════════════════════════════════

def _build_pipeline_agent() -> SequentialAgent:
    """
    Constructs the ADK SequentialAgent that wires all six pipeline stages
    in order. ADK runs them one after another, passing session context forward.
    """
    if settings.google_api_key:
        os.environ.setdefault("GOOGLE_API_KEY", settings.google_api_key)

    return SequentialAgent(
        name="buffett_pipeline",
        description=(
            "Warren Buffett stock analysis pipeline: "
            "screen → DCF → rank → LLM analysis → score → pitch deck → persist"
        ),
        sub_agents=[
            QuantScreenerAgent(name="quant_screener"),
            DCFAgent(name="dcf_engine"),
            PreLlmRankerAgent(name="pre_llm_ranker"),
            LlmAnalystAgent(name="llm_analyst"),
            ScorerAgent(name="scorer"),
            PitchDeckAgent(name="pitch_deck_gen"),
            DBWriterAgent(name="db_writer"),
        ],
    )


# ════════════════════════════════════════════════════════════════════════════════
# Public entry point
# ════════════════════════════════════════════════════════════════════════════════

async def run_buffett_analysis() -> dict:
    """
    Runs the full Buffett analysis pipeline via Google ADK.
    Returns a summary dict with run_id, candidate count, and Top-20 tickers.
    """
    run_id = str(uuid.uuid4())

    async with AsyncSessionLocal() as session:
        await session.execute(
            text("""
                INSERT INTO pipeline_runs (run_id, run_type, started_at, status)
                VALUES (:run_id, 'analysis_only', :started_at, 'running')
                ON CONFLICT (run_id) DO NOTHING
            """),
            {"run_id": run_id, "started_at": datetime.now(timezone.utc)},
        )
        await session.commit()

    # Initialise shared in-process state for this run
    _PIPELINE_STATE[run_id] = PipelineState(
        run_id=run_id,
        candidate_tickers=[],
        snapshots={},
        eps_histories={},
        dcf_results={},
        pre_llm_scores={},
        llm_candidates=[],
        llm_results={},
        scores={},
        top_tickers=[],
        pitch_deck_paths={},
    )

    pipeline   = _build_pipeline_agent()
    session_svc = InMemorySessionService()
    runner      = Runner(
        agent=pipeline,
        app_name="buffett_screener",
        session_service=session_svc,
    )

    # Seed the ADK session with the run_id so each BaseAgent can find its state
    await session_svc.create_session(
        app_name="buffett_screener",
        user_id="pipeline",
        session_id=run_id,
        state={"run_id": run_id},
    )

    log.info(
        "buffett_pipeline_started",
        run_id=run_id,
        model=settings.gemini_model,
        strategy=settings.analysis_strategy,
        llm_top_n=settings.llm_top_n,
    )

    async for event in runner.run_async(
        user_id="pipeline",
        session_id=run_id,
        new_message=types.Content(
            role="user",
            parts=[types.Part.from_text(text="Run the full Buffett analysis pipeline.")],
        ),
    ):
        if event.content and event.content.parts:
            log.debug("pipeline_event", author=event.author, text=event.content.parts[0].text[:100])

    final = _state(run_id)
    result = {
        "run_id":     run_id,
        "model":      settings.gemini_model,
        "candidates": len(final["candidate_tickers"]),
        "scored":     len(final["scores"]),
        "top20":      final["top_tickers"],
    }

    log.info("buffett_pipeline_complete", **result)

    # Clean up in-process state to free memory
    del _PIPELINE_STATE[run_id]

    return result
