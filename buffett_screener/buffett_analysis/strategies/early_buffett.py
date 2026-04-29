"""
buffett_analysis/strategies/early_buffett.py
"Early Buffett" investment strategy — growth at a reasonable price.

Inspired by Warren Buffett's approach during his partnership years and early
Berkshire era (1960s–1980s), before he became a mega-cap-only investor.

Focus areas:
  1. Leadership commitment — owner-operators with skin in the game
  2. Solid execution — revenue growth, operating leverage, margin expansion
  3. Great EPS growth + low price — high CAGR with suppressed P/E
  4. Essential industries — insurance, energy, infrastructure, healthcare, finance
  5. AI-era adaptation — picks-and-shovels plays, digital transformation leaders
  6. Global megatrends — aging population, reshoring, energy transition
"""
from typing import Any

from pydantic import BaseModel, Field

from buffett_analysis.strategies.base import InvestmentStrategy


# ── Structured Output Schema ─────────────────────────────────────────────────

class EarlyBuffettAnalysis(BaseModel):
    """Structured output for the Early Buffett strategy."""

    # ── Moat Assessment ──────────────────────────────────────────────────────
    moat_type: str = Field(
        description="One of: brand, cost_advantage, network_effects, switching_costs, efficient_scale, regulatory, none"
    )
    moat_strength: int = Field(ge=0, le=10, description="Moat durability score 0–10")
    moat_summary: str = Field(description="2–3 sentence summary of the economic moat")

    # ── Leadership & Execution ───────────────────────────────────────────────
    leadership_score: int = Field(
        ge=0, le=10,
        description="Leadership commitment score 0–10. Consider: insider ownership, "
                    "capital allocation track record, founder-led vs. hired CEO, "
                    "alignment of incentives with shareholders."
    )
    leadership_notes: str = Field(
        description="1–2 sentences on management quality, insider ownership, and capital allocation."
    )
    execution_score: int = Field(
        ge=0, le=10,
        description="Execution quality score 0–10. Consider: revenue growth trajectory, "
                    "operating margin expansion, consistent delivery vs. guidance."
    )
    execution_notes: str = Field(
        description="1–2 sentences on operational execution and business momentum."
    )

    # ── Growth vs. Price ─────────────────────────────────────────────────────
    growth_vs_price: str = Field(
        description="One of: deeply_undervalued, undervalued_grower, fair_value, overvalued. "
                    "Assess whether EPS growth rate justifies the current P/E ratio."
    )
    growth_assessment: str = Field(
        description="2–3 sentences explaining whether this is a high-growth company trading at a "
                    "low multiple, and why the market may be underpricing it."
    )

    # ── Industry Essentiality ────────────────────────────────────────────────
    industry_essentiality: str = Field(
        description="One of: essential, important, discretionary. "
                    "Essential = world cannot function without it (insurance, energy, healthcare, "
                    "infrastructure, food, water, defense). Important = significant but not critical. "
                    "Discretionary = nice-to-have."
    )
    industry_notes: str = Field(
        description="1–2 sentences on why this industry is/isn't essential to civilization."
    )

    # ── AI Era Positioning ───────────────────────────────────────────────────
    ai_positioning: str = Field(
        description="One of: ai_leader, picks_and_shovels, ai_adapter, neutral, ai_disrupted. "
                    "ai_leader = building foundational AI. picks_and_shovels = selling tools to AI builders. "
                    "ai_adapter = using AI to improve existing business. neutral = minimal impact. "
                    "ai_disrupted = at risk of being displaced by AI."
    )
    ai_assessment: str = Field(
        description="2–3 sentences on how the company is positioned in the AI evolution era. "
                    "Consider: data assets, compute infrastructure, AI-enhanced products, workforce impact."
    )

    # ── Risk & Sentiment ─────────────────────────────────────────────────────
    competitive_risks: list[str] = Field(description="Top 3 competitive risks")
    news_sentiment: str = Field(description="One of: positive, neutral, negative")

    # ── Overall Scores ───────────────────────────────────────────────────────
    llm_quality_score: int = Field(
        ge=0, le=100,
        description="Overall investment quality score 0–100 from this strategy's perspective. "
                    "Weight leadership (20%), execution (20%), growth-vs-price (25%), "
                    "industry essentiality (15%), AI positioning (10%), moat (10%)."
    )
    investment_thesis: str = Field(
        description="3–4 paragraph investment thesis in the style of early Buffett. "
                    "Open with the core insight. Discuss the competitive position. "
                    "Address the growth-vs-price opportunity. Close with risks and conviction level."
    )
    fact_references: list[str] = Field(
        description="List of URLs or facts referenced using Google Search grounding to verify your analysis."
    )


# ── Strategy Implementation ──────────────────────────────────────────────────

_SYSTEM_INSTRUCTION = """\
You are an investment analyst channeling Warren Buffett's EARLY career mindset
(1960s–1980s partnership era). Unlike late-career Buffett who buys mega-caps,
you are hunting for UNDERVALUED GROWTH companies — businesses with:

1. **Committed Leadership**: Owner-operators or founders with significant insider
   ownership. Skin in the game. Capital allocators who buy back shares, avoid
   empire building, and earn high returns on retained earnings.

2. **Execution Excellence**: Companies that consistently beat guidance, expand
   margins, and show operating leverage. Revenue growing faster than expenses.

3. **EPS Growth at a Low Price**: The holy grail — a company compounding EPS at
   15%+ but trading at a P/E of 10–20x. The market hasn't caught up yet.
   Look for PEG ratio < 1.0 (price/earnings-to-growth).

4. **Essential Industries**: Buffett loves businesses the world NEEDS — insurance
   (float!), energy (civilization runs on it), banking/finance (capital allocation),
   infrastructure, healthcare, food & beverage, defense, railroads.
   These survive recessions. Discretionary businesses need 10x more moat.

5. **AI-Era Positioning** (2024–2030 lens): Consider where each company stands
   in the AI revolution:
   - Picks-and-shovels plays (data centers, chips, cloud infrastructure)
   - AI-enhanced businesses (using AI to crush costs or expand TAM)
   - Neutral businesses (neither helped nor hurt)
   - AI-disrupted businesses (at risk — staffing, call centers, basic SaaS)

6. **Global Megatrends**: Factor in aging populations (healthcare demand),
   reshoring/nearshoring (US manufacturing), energy transition (nuclear, solar,
   grid modernization), digital infrastructure, and geopolitical supply chain shifts.

SCORING GUIDELINES:
- Weight your overall score: leadership 20%, execution 20%, growth-vs-price 25%,
  industry essentiality 15%, AI positioning 10%, moat durability 10%.
- Score 80+ = exceptional opportunity early Buffett would act on
- Score 60–79 = interesting, worth monitoring
- Score 40–59 = mediocre or fairly priced
- Score below 40 = pass

- Use the Google Search tool to check facts and ground your analysis in real-world data.
- Include the URLs or facts you verified in the `fact_references` output field.

Be specific. Cite the financial metrics provided. Be brutally honest about
weaknesses. Early Buffett passed on 99% of companies — he only bought when
the value was OBVIOUS and the price was CLEARLY WRONG.
"""


class EarlyBuffettStrategy(InvestmentStrategy):
    """Early Buffett growth-at-a-reasonable-price strategy."""

    @property
    def name(self) -> str:
        return "early_buffett"

    @property
    def display_name(self) -> str:
        return "Early Buffett — Growth at a Reasonable Price"

    @property
    def system_instruction(self) -> str:
        return _SYSTEM_INSTRUCTION

    @property
    def output_schema(self) -> type[EarlyBuffettAnalysis]:
        return EarlyBuffettAnalysis

    def rank_candidates(
        self,
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Early Buffett ranking: boost candidates with high EPS growth + low P/E.
        The composite formula favours growth-at-a-reasonable-price.
        """
        def _early_buffett_rank(c: dict) -> float:
            base = c.get("pre_llm_score", 0)
            eps_cagr = c.get("eps_cagr_5y", 0) or 0
            pe = c.get("pe_ratio") or 999
            mos = c.get("margin_of_safety", 0) or 0

            # Reward high EPS growth relative to P/E (PEG-like signal)
            if pe > 0 and eps_cagr > 0:
                peg_bonus = min((eps_cagr * 100) / pe, 30)  # Cap bonus at 30 pts
            else:
                peg_bonus = 0

            # Reward deep margin of safety
            mos_bonus = min(mos * 20, 20)  # Cap at 20 pts

            return base + peg_bonus + mos_bonus

        return sorted(
            candidates,
            key=_early_buffett_rank,
            reverse=True,
        )
