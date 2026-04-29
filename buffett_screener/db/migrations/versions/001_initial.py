"""
db/migrations/versions/001_initial.py
Initial schema: all tables for Docs 1, 2 & 3.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── companies ─────────────────────────────────────────────────────────────
    op.create_table(
        "companies",
        sa.Column("ticker", sa.VARCHAR(20), primary_key=True),
        sa.Column("name", sa.VARCHAR(255), nullable=False),
        sa.Column("sector", sa.VARCHAR(100)),
        sa.Column("industry", sa.VARCHAR(100)),
        sa.Column("country", sa.VARCHAR(50)),
        sa.Column("ipo_year", sa.SMALLINT()),
        sa.Column("market_cap", sa.BIGINT()),
        sa.Column("exchange", sa.VARCHAR(20), server_default="NASDAQ"),
        sa.Column("edgar_cik", sa.VARCHAR(10)),
        sa.Column("is_active", sa.BOOLEAN(), server_default="true"),
        sa.Column("next_earnings_date", sa.DATE()),
        sa.Column("last_earnings_date", sa.DATE()),
        sa.Column("first_seen_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("last_updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_companies_sector", "companies", ["sector"])
    op.create_index("idx_companies_active", "companies", ["is_active"])

    # ── pipeline_runs ─────────────────────────────────────────────────────────
    op.create_table(
        "pipeline_runs",
        sa.Column("run_id", sa.VARCHAR(64), primary_key=True),
        sa.Column("run_type", sa.VARCHAR(50)),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("total_tickers", sa.INTEGER()),
        sa.Column("succeeded", sa.INTEGER()),
        sa.Column("failed", sa.INTEGER()),
        sa.Column("status", sa.VARCHAR(20)),
        sa.Column("error_detail", sa.TEXT()),
    )

    # ── financial_snapshots ───────────────────────────────────────────────────
    op.create_table(
        "financial_snapshots",
        sa.Column("id", sa.BIGINT(), sa.Identity(), primary_key=True),
        sa.Column("ticker", sa.VARCHAR(20), sa.ForeignKey("companies.ticker", ondelete="CASCADE"), nullable=False),
        sa.Column("snapshot_date", sa.DATE(), nullable=False),
        sa.Column("market_cap", sa.BIGINT()),
        sa.Column("enterprise_value", sa.BIGINT()),
        sa.Column("pe_ratio", sa.DOUBLE_PRECISION()),
        sa.Column("forward_pe", sa.DOUBLE_PRECISION()),
        sa.Column("price_to_book", sa.DOUBLE_PRECISION()),
        sa.Column("price_to_sales", sa.DOUBLE_PRECISION()),
        sa.Column("ev_to_ebitda", sa.DOUBLE_PRECISION()),
        sa.Column("eps_ttm", sa.DOUBLE_PRECISION()),
        sa.Column("eps_growth_5y", sa.DOUBLE_PRECISION()),
        sa.Column("eps_growth_1y", sa.DOUBLE_PRECISION()),
        sa.Column("revenue_ttm", sa.BIGINT()),
        sa.Column("gross_margin", sa.DOUBLE_PRECISION()),
        sa.Column("operating_margin", sa.DOUBLE_PRECISION()),
        sa.Column("net_margin", sa.DOUBLE_PRECISION()),
        sa.Column("total_debt", sa.BIGINT()),
        sa.Column("debt_to_equity", sa.DOUBLE_PRECISION()),
        sa.Column("current_ratio", sa.DOUBLE_PRECISION()),
        sa.Column("free_cash_flow", sa.BIGINT()),
        sa.Column("return_on_equity", sa.DOUBLE_PRECISION()),
        sa.Column("return_on_assets", sa.DOUBLE_PRECISION()),
        sa.Column("current_price", sa.DOUBLE_PRECISION()),
        sa.Column("fifty_two_week_high", sa.DOUBLE_PRECISION()),
        sa.Column("fifty_two_week_low", sa.DOUBLE_PRECISION()),
        sa.Column("data_source", sa.VARCHAR(20)),
        sa.Column("fetched_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("ticker", "snapshot_date", name="uq_snapshot"),
    )
    op.create_index("idx_snapshots_ticker_date", "financial_snapshots", ["ticker", sa.text("snapshot_date DESC")])
    op.create_index("idx_snapshots_roe", "financial_snapshots", ["return_on_equity"])
    op.create_index("idx_snapshots_date", "financial_snapshots", ["snapshot_date"])

    # ── eps_history ───────────────────────────────────────────────────────────
    op.create_table(
        "eps_history",
        sa.Column("ticker", sa.VARCHAR(20), sa.ForeignKey("companies.ticker", ondelete="CASCADE"), nullable=False),
        sa.Column("fiscal_year", sa.SMALLINT(), nullable=False),
        sa.Column("eps", sa.DOUBLE_PRECISION()),
        sa.Column("source", sa.VARCHAR(20)),
        sa.PrimaryKeyConstraint("ticker", "fiscal_year"),
    )
    op.create_index("idx_eps_ticker", "eps_history", ["ticker"])

    # ── buffett_scores ────────────────────────────────────────────────────────
    op.create_table(
        "buffett_scores",
        sa.Column("id", sa.BIGINT(), sa.Identity(), primary_key=True),
        sa.Column("ticker", sa.VARCHAR(20), sa.ForeignKey("companies.ticker", ondelete="CASCADE"), nullable=False),
        sa.Column("analysis_date", sa.DATE(), nullable=False),
        sa.Column("run_id", sa.VARCHAR(64), sa.ForeignKey("pipeline_runs.run_id")),
        sa.Column("eps_consistency_score", sa.DOUBLE_PRECISION()),
        sa.Column("roe_score", sa.DOUBLE_PRECISION()),
        sa.Column("leverage_score", sa.DOUBLE_PRECISION()),
        sa.Column("fcf_yield_score", sa.DOUBLE_PRECISION()),
        sa.Column("margin_of_safety_score", sa.DOUBLE_PRECISION()),
        sa.Column("moat_score", sa.DOUBLE_PRECISION()),
        sa.Column("llm_quality_score", sa.DOUBLE_PRECISION()),
        sa.Column("buffett_total_score", sa.DOUBLE_PRECISION()),
        sa.Column("recommendation", sa.VARCHAR(20)),
        sa.Column("intrinsic_value", sa.DOUBLE_PRECISION()),
        sa.Column("current_price", sa.DOUBLE_PRECISION()),
        sa.Column("margin_of_safety_pct", sa.DOUBLE_PRECISION()),
        sa.Column("investment_thesis", sa.TEXT()),
        sa.Column("moat_summary", sa.TEXT()),
        sa.Column("risk_factors", JSONB()),
        sa.Column("llm_raw_output", JSONB()),
        sa.Column("pitch_deck_path", sa.VARCHAR(512)),
        sa.Column("pitch_deck_html_path", sa.VARCHAR(512)),
        sa.UniqueConstraint("ticker", "analysis_date", name="uq_score"),
    )
    op.create_index("idx_scores_date_total", "buffett_scores", ["analysis_date", sa.text("buffett_total_score DESC")])
    op.create_index("idx_scores_ticker", "buffett_scores", ["ticker"])

    # ── pitch_deck_versions ───────────────────────────────────────────────────
    op.create_table(
        "pitch_deck_versions",
        sa.Column("id", sa.BIGINT(), sa.Identity(), primary_key=True),
        sa.Column("ticker", sa.VARCHAR(20), sa.ForeignKey("companies.ticker", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.INTEGER(), nullable=False),
        sa.Column("generated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("trigger_event", sa.VARCHAR(30)),
        sa.Column("buffett_score", sa.DOUBLE_PRECISION()),
        sa.Column("recommendation", sa.VARCHAR(20)),
        sa.Column("pdf_path", sa.VARCHAR(512), nullable=False),
        sa.Column("html_path", sa.VARCHAR(512)),
        sa.Column("is_current", sa.BOOLEAN(), server_default="true"),
        sa.Column("superseded_at", sa.TIMESTAMP(timezone=True)),
        sa.UniqueConstraint("ticker", "version", name="uq_deck_version"),
    )
    op.create_index("idx_decks_ticker", "pitch_deck_versions", ["ticker"])
    op.create_index("idx_decks_is_current", "pitch_deck_versions", ["is_current"],
                    postgresql_where=sa.text("is_current = TRUE"))

    # ── earnings_calendar ─────────────────────────────────────────────────────
    op.create_table(
        "earnings_calendar",
        sa.Column("ticker", sa.VARCHAR(20), sa.ForeignKey("companies.ticker", ondelete="CASCADE"), nullable=False),
        sa.Column("expected_date", sa.DATE(), nullable=False),
        sa.Column("fiscal_quarter", sa.VARCHAR(10)),
        sa.Column("eps_estimate", sa.DOUBLE_PRECISION()),
        sa.Column("revenue_estimate", sa.BIGINT()),
        sa.Column("confirmed", sa.BOOLEAN(), server_default="false"),
        sa.Column("source", sa.VARCHAR(20)),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("ticker", "expected_date"),
    )
    op.create_index("idx_calendar_date", "earnings_calendar", ["expected_date"])

    # ── earnings_events ───────────────────────────────────────────────────────
    op.create_table(
        "earnings_events",
        sa.Column("id", sa.BIGINT(), sa.Identity(), primary_key=True),
        sa.Column("ticker", sa.VARCHAR(20), sa.ForeignKey("companies.ticker", ondelete="CASCADE"), nullable=False),
        sa.Column("report_date", sa.DATE(), nullable=False),
        sa.Column("fiscal_period", sa.VARCHAR(10)),
        sa.Column("fiscal_year", sa.SMALLINT()),
        sa.Column("fiscal_quarter", sa.SMALLINT()),
        sa.Column("eps_actual", sa.DOUBLE_PRECISION()),
        sa.Column("revenue_actual", sa.BIGINT()),
        sa.Column("net_income_actual", sa.BIGINT()),
        sa.Column("gross_margin_actual", sa.DOUBLE_PRECISION()),
        sa.Column("eps_estimate", sa.DOUBLE_PRECISION()),
        sa.Column("eps_surprise_pct", sa.DOUBLE_PRECISION()),
        sa.Column("revenue_surprise_pct", sa.DOUBLE_PRECISION()),
        sa.Column("edgar_cik", sa.VARCHAR(10)),
        sa.Column("filing_url", sa.VARCHAR(512)),
        sa.Column("form_type", sa.VARCHAR(10), server_default="8-K"),
        sa.Column("filed_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("processed_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("ticker", "fiscal_year", "fiscal_quarter", name="uq_earnings"),
    )
    op.create_index("idx_events_ticker", "earnings_events", ["ticker"])
    op.create_index("idx_events_report_date", "earnings_events", [sa.text("report_date DESC")])
    op.create_index("idx_events_surprise", "earnings_events", ["eps_surprise_pct"])


def downgrade() -> None:
    for table in [
        "earnings_events", "earnings_calendar", "pitch_deck_versions",
        "buffett_scores", "eps_history", "financial_snapshots",
        "pipeline_runs", "companies",
    ]:
        op.drop_table(table)
