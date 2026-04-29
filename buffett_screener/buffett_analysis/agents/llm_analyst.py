"""
buffett_analysis/agents/llm_analyst.py
Strategy-driven qualitative analysis agent powered by Google ADK + Gemini.

Uses google-adk's LlmAgent with a strategy-provided Pydantic output_schema
so the model returns structured JSON — no manual parsing needed.

The strategy determines the system instruction and output schema.
Model: configurable via settings.gemini_model
"""
import json
import os
import uuid

import structlog
from google.adk.agents.llm_agent import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel

from buffett_analysis.strategies.base import InvestmentStrategy
from config import settings

log = structlog.get_logger()


# ── Agent Builder ─────────────────────────────────────────────────────────────

def _build_analyst_agent(strategy: InvestmentStrategy) -> LlmAgent:
    """Builds the ADK LlmAgent using the given strategy's instruction and schema."""
    # Set Google API key for ADK runtime
    if settings.google_api_key:
        os.environ.setdefault("GOOGLE_API_KEY", settings.google_api_key)

    agent = LlmAgent(
        name="buffett_analyst",
        model=Gemini(model=settings.gemini_model),
        description=f"Investment analyst — {strategy.display_name}",
        instruction=strategy.system_instruction,
        output_schema=strategy.output_schema,
    )
    
    if not agent.generate_content_config:
        agent.generate_content_config = types.GenerateContentConfig()
    agent.generate_content_config.tools = [types.Tool(google_search=types.GoogleSearch())]
    
    return agent


# ── Prompt Builder ────────────────────────────────────────────────────────────

def _format_prompt(
    ticker: str,
    company_name: str,
    sector: str,
    industry: str,
    eps_ttm: float,
    roe: float,
    gross_margin: float,
    debt_to_equity: float,
    free_cash_flow: int,
    market_cap: int,
    current_price: float,
    pe_ratio: float,
    margin_of_safety: float,
    eps_cagr_5y: float,
    pre_llm_score: float,
    eps_history: dict[int, float],
    dcf_intrinsic_value: float,
) -> str:
    """Builds a rich context prompt with all available data for the LLM."""
    eps_lines = ""
    if eps_history:
        for year in sorted(eps_history):
            eps_lines += f"  {year}: ${eps_history[year]:.2f}\n"
    else:
        eps_lines = "  (No EPS history available)\n"

    return f"""\
Company: {company_name} ({ticker})
Sector: {sector or 'Unknown'} | Industry: {industry or 'Unknown'}

Key Financial Metrics:
  EPS (TTM):           ${eps_ttm:.2f}
  Return on Equity:    {roe * 100:.1f}%
  Gross Margin:        {gross_margin * 100:.1f}%
  Debt / Equity:       {debt_to_equity:.2f}
  Free Cash Flow:      ${free_cash_flow:,}
  Market Cap:          ${market_cap:,}
  Current Price:       ${current_price:.2f}
  P/E Ratio:           {pe_ratio:.1f}
  EPS CAGR (5yr):      {eps_cagr_5y * 100:.1f}%

DCF Valuation:
  Intrinsic Value/Share: ${dcf_intrinsic_value:.2f}
  Margin of Safety:      {margin_of_safety:.1%}

EPS History (annual):
{eps_lines}
Pre-LLM Quantitative Score: {pre_llm_score:.1f}/100

Provide a thorough qualitative investment analysis using the strategy lens described in your instructions.
"""


# ── Main Analysis Function ────────────────────────────────────────────────────

async def analyze_company(
    strategy: InvestmentStrategy,
    ticker: str,
    company_name: str,
    sector: str,
    industry: str,
    eps_ttm: float,
    roe: float,
    gross_margin: float,
    debt_to_equity: float,
    free_cash_flow: int,
    market_cap: int,
    current_price: float,
    pe_ratio: float,
    margin_of_safety: float,
    eps_cagr_5y: float,
    pre_llm_score: float,
    eps_history: dict[int, float],
    dcf_intrinsic_value: float,
) -> dict:
    """
    Runs the ADK LlmAgent with the given strategy to produce a structured
    qualitative analysis. Returns a dict matching the strategy's output schema.
    Falls back to a neutral default dict on failure.
    """
    agent = _build_analyst_agent(strategy)
    session_service = InMemorySessionService()

    # Each company gets its own isolated session
    session_id = f"{ticker}-{uuid.uuid4().hex[:8]}"
    user_id = "buffett_pipeline"

    runner = Runner(
        agent=agent,
        app_name="buffett_screener",
        session_service=session_service,
    )

    await session_service.create_session(
        app_name="buffett_screener",
        user_id=user_id,
        session_id=session_id,
        state={},
    )

    prompt = _format_prompt(
        ticker=ticker,
        company_name=company_name,
        sector=sector,
        industry=industry,
        eps_ttm=eps_ttm,
        roe=roe,
        gross_margin=gross_margin,
        debt_to_equity=debt_to_equity,
        free_cash_flow=free_cash_flow,
        market_cap=market_cap,
        current_price=current_price,
        pe_ratio=pe_ratio,
        margin_of_safety=margin_of_safety,
        eps_cagr_5y=eps_cagr_5y,
        pre_llm_score=pre_llm_score,
        eps_history=eps_history,
        dcf_intrinsic_value=dcf_intrinsic_value,
    )

    try:
        final_response: BaseModel | None = None

        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=types.Content(
                role="user",
                parts=[types.Part.from_text(text=prompt)],
            ),
        ):
            # The last event with a structured response carries the output_schema result
            if event.is_final_response() and event.content:
                for part in event.content.parts:
                    if part.text:
                        data = json.loads(part.text)
                        schema_cls = strategy.output_schema
                        final_response = schema_cls(**data)

        if final_response:
            log.info(
                "llm_analysis_done",
                ticker=ticker,
                model=settings.gemini_model,
                strategy=strategy.name,
                score=final_response.llm_quality_score,
            )
            return final_response.model_dump()

        raise ValueError("No final structured response from ADK runner")

    except Exception as exc:
        log.warning(
            "llm_analysis_failed",
            ticker=ticker,
            strategy=strategy.name,
            error=str(exc),
        )
        return _fallback_analysis(ticker)


def _fallback_analysis(ticker: str) -> dict:
    """Returns a neutral fallback when the LLM call fails."""
    return {
        "moat_type":              "none",
        "moat_strength":           0,
        "moat_summary":           "LLM analysis unavailable; using neutral defaults.",
        "leadership_score":        5,
        "leadership_notes":       "LLM analysis unavailable.",
        "execution_score":         5,
        "execution_notes":        "LLM analysis unavailable.",
        "growth_vs_price":        "fair_value",
        "growth_assessment":      "LLM analysis could not be completed.",
        "industry_essentiality":  "important",
        "industry_notes":         "LLM analysis unavailable.",
        "ai_positioning":         "neutral",
        "ai_assessment":          "LLM analysis unavailable.",
        "competitive_risks":       [],
        "news_sentiment":         "neutral",
        "llm_quality_score":       50,
        "investment_thesis":      "Qualitative analysis could not be completed for this run.",
        "management_quality":      5,
        "management_notes":       "LLM analysis unavailable.",
        "fact_references":        [],
    }
