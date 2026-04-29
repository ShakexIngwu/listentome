"""
buffett_analysis/strategies/__init__.py
Strategy registry — maps strategy names to their implementation classes.

Usage:
    from buffett_analysis.strategies import get_strategy
    strategy = get_strategy("early_buffett")
"""
from buffett_analysis.strategies.base import InvestmentStrategy
from buffett_analysis.strategies.early_buffett import EarlyBuffettStrategy

# ── Registry ──────────────────────────────────────────────────────────────────
_STRATEGIES: dict[str, type[InvestmentStrategy]] = {
    "early_buffett": EarlyBuffettStrategy,
}


def get_strategy(name: str) -> InvestmentStrategy:
    """Returns an instantiated strategy by name. Raises KeyError if unknown."""
    cls = _STRATEGIES.get(name)
    if cls is None:
        available = ", ".join(sorted(_STRATEGIES.keys()))
        raise KeyError(
            f"Unknown strategy '{name}'. Available strategies: {available}"
        )
    return cls()


def list_strategies() -> list[str]:
    """Returns all registered strategy names."""
    return sorted(_STRATEGIES.keys())
