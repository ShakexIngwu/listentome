"""
buffett_analysis/agents/dcf_engine.py
Two-stage Owner Earnings DCF calculator.
Fully deterministic — no LLM involved.
"""
from dataclasses import dataclass


@dataclass
class DCFResult:
    ticker: str
    owner_earnings: float
    growth_rate: float           # Capped at 15%
    discount_rate: float
    terminal_multiple: float
    intrinsic_value: float       # Total firm intrinsic value
    intrinsic_value_per_share: float
    current_price: float
    margin_of_safety: float      # (IV_per_share - price) / IV_per_share
    shares_outstanding: int


def calculate_eps_cagr(eps_by_year: dict[int, float], years: int = 5) -> float:
    """
    Calculates compound annual growth rate of EPS over `years`.
    Returns 0.0 if insufficient data or negative base.
    """
    sorted_years = sorted(eps_by_year.keys(), reverse=True)
    if len(sorted_years) < years + 1:
        sorted_years = sorted_years  # Use whatever we have
    if len(sorted_years) < 2:
        return 0.0

    recent = eps_by_year[sorted_years[0]]
    oldest = eps_by_year[sorted_years[-1]]
    n = sorted_years[0] - sorted_years[-1]

    if oldest <= 0 or recent <= 0 or n == 0:
        return 0.0

    return (recent / oldest) ** (1 / n) - 1


def dcf_valuation(
    owner_earnings: float,
    growth_rate: float,
    shares_outstanding: int,
    current_price: float,
    discount_rate: float = 0.09,
    terminal_multiple: float = 15.0,
    years: int = 10,
) -> DCFResult | None:
    """
    Two-stage DCF:
    - Growth phase: projects owner earnings for `years` at `growth_rate`
    - Terminal value: year-10 earnings × terminal_multiple, discounted back
    - Growth rate capped at 15% (conservative Buffett approach)

    Returns None if inputs are invalid.
    """
    if owner_earnings <= 0 or shares_outstanding <= 0:
        return None

    g = min(growth_rate, 0.15)   # Hard cap at 15%
    r = discount_rate

    # Growth phase PV
    pv_sum = 0.0
    for t in range(1, years + 1):
        projected = owner_earnings * ((1 + g) ** t)
        pv = projected / ((1 + r) ** t)
        pv_sum += pv

    # Terminal value
    terminal_earnings = owner_earnings * ((1 + g) ** years)
    terminal_pv = (terminal_earnings * terminal_multiple) / ((1 + r) ** years)

    intrinsic_value = pv_sum + terminal_pv
    iv_per_share = intrinsic_value / shares_outstanding
    mos = (iv_per_share - current_price) / iv_per_share if iv_per_share > 0 else -1.0

    return DCFResult(
        ticker="",
        owner_earnings=owner_earnings,
        growth_rate=g,
        discount_rate=r,
        terminal_multiple=terminal_multiple,
        intrinsic_value=intrinsic_value,
        intrinsic_value_per_share=iv_per_share,
        current_price=current_price,
        margin_of_safety=mos,
        shares_outstanding=shares_outstanding,
    )
