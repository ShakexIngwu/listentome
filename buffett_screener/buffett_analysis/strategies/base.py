"""
buffett_analysis/strategies/base.py
Abstract base class for investment analysis strategies (skills).

Each strategy defines:
  - A unique name and display name
  - An LLM system instruction tailored to the strategy's lens
  - A Pydantic output schema for structured LLM responses
  - Optional ranking logic to influence pre-LLM candidate selection
"""
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class InvestmentStrategy(ABC):
    """Base class for all investment analysis strategies."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Machine-readable strategy identifier, e.g. 'early_buffett'."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable strategy name for logs and UI."""
        ...

    @property
    @abstractmethod
    def system_instruction(self) -> str:
        """Full system prompt sent to the LLM for this strategy."""
        ...

    @property
    @abstractmethod
    def output_schema(self) -> type[BaseModel]:
        """Pydantic model class defining the structured LLM output."""
        ...

    def rank_candidates(
        self,
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Optional strategy-specific ranking of pre-LLM candidates.
        Default: sort by pre_llm_score descending.
        Override to apply strategy-specific weighting.

        Each candidate dict contains:
          ticker, pre_llm_score, sector, industry, eps_cagr_5y,
          margin_of_safety, fcf_yield, roe, debt_to_equity, pe_ratio,
          current_price, market_cap
        """
        return sorted(
            candidates,
            key=lambda c: c.get("pre_llm_score", 0),
            reverse=True,
        )
