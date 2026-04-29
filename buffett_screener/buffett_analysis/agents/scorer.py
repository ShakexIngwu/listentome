"""
buffett_analysis/agents/scorer.py
Combines quantitative metrics and DCF results into a 0–100 Buffett Score.

Weights:
  EPS Consistency  20%  — 7+ years of positive, growing EPS
  ROE              20%  — average ROE > 15%
  Margin of Safety 20%  — price < intrinsic value (DCF)
  Low Leverage     15%  — Debt/Equity < 0.5
  FCF Yield        15%  — Free Cash Flow / Market Cap > 5%
  Moat Proxy        5%  — Gross Margin > 40%
  LLM Quality       5%  — LLM-assessed moat/management score
"""
from dataclasses import dataclass

from buffett_analysis.agents.dcf_engine import DCFResult


@dataclass
class BuffettScore:
    ticker: str
    eps_consistency_score: float
    roe_score: float
    margin_of_safety_score: float
    leverage_score: float
    fcf_yield_score: float
    moat_score: float
    llm_quality_score: float
    buffett_total_score: float
    recommendation: str          # STRONG_BUY | BUY | HOLD | PASS


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


def score_eps_consistency(eps_by_year: dict[int, float]) -> float:
    """
    Score 0–100 based on:
    - Number of positive EPS years (max 10)
    - Whether the trend is consistently growing
    """
    if not eps_by_year:
        return 0.0

    values = [eps_by_year[y] for y in sorted(eps_by_year)]
    positive_years = sum(1 for v in values if v > 0)
    year_score = (positive_years / max(len(values), 1)) * 60  # 60 pts for all positive

    # Trend bonus: how many consecutive year-over-year increases?
    consecutive = 0
    for i in range(1, len(values)):
        if values[i] > values[i - 1]:
            consecutive += 1
        else:
            break
    trend_score = min(consecutive / max(len(values) - 1, 1), 1.0) * 40  # 40 pts for perfect trend

    return _clamp(year_score + trend_score)


def score_roe(roe_values: list[float]) -> float:
    """Score based on average ROE. 100 = avg ROE >= 25%."""
    if not roe_values:
        return 0.0
    avg_roe = sum(roe_values) / len(roe_values)
    # Linear scale: 0% → 0pts, 15% → 60pts, 25%+ → 100pts
    if avg_roe <= 0:
        return 0.0
    if avg_roe >= 0.25:
        return 100.0
    return _clamp((avg_roe / 0.25) * 100)


def score_margin_of_safety(dcf: DCFResult | None) -> float:
    """Score based on margin of safety. 100 = MoS >= 50%."""
    if dcf is None:
        return 0.0
    mos = dcf.margin_of_safety
    if mos <= 0:
        return 0.0  # Overvalued → no score
    if mos >= 0.50:
        return 100.0
    return _clamp((mos / 0.50) * 100)


def score_leverage(debt_to_equity: float | None) -> float:
    """Score based on D/E. 100 = D/E == 0, 0 = D/E >= 2."""
    if debt_to_equity is None:
        return 50.0  # Neutral if unknown
    if debt_to_equity <= 0:
        return 100.0
    if debt_to_equity >= 2.0:
        return 0.0
    return _clamp(100 - (debt_to_equity / 2.0) * 100)


def score_fcf_yield(free_cash_flow: float | None, market_cap: float | None) -> float:
    """Score based on FCF yield. 100 = yield >= 10%."""
    if not free_cash_flow or not market_cap or market_cap <= 0:
        return 0.0
    fcf_yield = free_cash_flow / market_cap
    if fcf_yield <= 0:
        return 0.0
    if fcf_yield >= 0.10:
        return 100.0
    return _clamp((fcf_yield / 0.10) * 100)


def score_moat_proxy(gross_margin: float | None) -> float:
    """Score based on gross margin proxy. 100 = gross margin >= 60%."""
    if gross_margin is None:
        return 0.0
    if gross_margin >= 0.60:
        return 100.0
    if gross_margin <= 0:
        return 0.0
    return _clamp((gross_margin / 0.60) * 100)


def compute_buffett_score(
    ticker: str,
    eps_by_year: dict[int, float],
    roe_values: list[float],
    dcf_result: DCFResult | None,
    debt_to_equity: float | None,
    free_cash_flow: float | None,
    market_cap: float | None,
    gross_margin: float | None,
    llm_quality_score: float = 50.0,
) -> BuffettScore:
    """Combines all dimension scores into a weighted Buffett Score."""
    eps   = score_eps_consistency(eps_by_year)
    roe   = score_roe(roe_values)
    mos   = score_margin_of_safety(dcf_result)
    lev   = score_leverage(debt_to_equity)
    fcf   = score_fcf_yield(free_cash_flow, market_cap)
    moat  = score_moat_proxy(gross_margin)
    llm   = _clamp(llm_quality_score)

    total = (
        eps  * 0.20 +
        roe  * 0.20 +
        mos  * 0.20 +
        lev  * 0.15 +
        fcf  * 0.15 +
        moat * 0.05 +
        llm  * 0.05
    )

    if total >= 75:
        rec = "STRONG_BUY"
    elif total >= 60:
        rec = "BUY"
    elif total >= 45:
        rec = "HOLD"
    else:
        rec = "PASS"

    return BuffettScore(
        ticker=ticker,
        eps_consistency_score=round(eps, 2),
        roe_score=round(roe, 2),
        margin_of_safety_score=round(mos, 2),
        leverage_score=round(lev, 2),
        fcf_yield_score=round(fcf, 2),
        moat_score=round(moat, 2),
        llm_quality_score=round(llm, 2),
        buffett_total_score=round(total, 2),
        recommendation=rec,
    )
