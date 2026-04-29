"""
dashboard.py — Streamlit dashboard for the Buffett Stock Screener.
Reads from DuckDB (read-only Parquet views) — no PostgreSQL connection needed.
The DuckDB file is rebuilt weekly from PostgreSQL by duckdb_replica.py.

Run: streamlit run dashboard.py
"""
import os
import time
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Buffett Stock Screener",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

  html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

  .main { background: #0a0e1a; }
  .stDataFrame { border-radius: 8px; }

  div[data-testid="metric-container"] {
    background: linear-gradient(135deg, rgba(255,255,255,0.04), rgba(255,255,255,0.08));
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 12px;
    padding: 16px;
    backdrop-filter: blur(10px);
  }

  .ticker-card {
    background: linear-gradient(135deg, rgba(30,40,60,0.9), rgba(20,30,50,0.95));
    border: 1px solid rgba(100,140,255,0.15);
    border-radius: 16px;
    padding: 24px;
    margin: 8px 0;
  }

  .score-badge {
    display: inline-block;
    padding: 4px 14px;
    border-radius: 20px;
    font-weight: 600;
    font-size: 0.85em;
  }
  .score-strong-buy { background: #1b5e20; color: #a5d6a7; }
  .score-buy { background: #2e7d32; color: #c8e6c9; }
  .score-hold { background: #f57f17; color: #fff9c4; }
  .score-pass { background: #b71c1c; color: #ef9a9a; }

  .section-header {
    background: linear-gradient(90deg, rgba(100,140,255,0.1), transparent);
    border-left: 3px solid #648cff;
    padding: 8px 16px;
    margin: 20px 0 12px 0;
    border-radius: 0 8px 8px 0;
  }

  .stTabs [data-baseweb="tab-list"] {
    gap: 4px;
  }
  .stTabs [data-baseweb="tab"] {
    background: rgba(255,255,255,0.04);
    border-radius: 8px 8px 0 0;
    padding: 8px 20px;
  }
</style>
""", unsafe_allow_html=True)

# ── DB Connection ─────────────────────────────────────────────────────────────
DUCKDB_PATH = os.environ.get("DUCKDB_PATH", "./analytics/stocks_analytics.duckdb")


def _db_ready() -> bool:
    p = Path(DUCKDB_PATH)
    return p.exists() and p.stat().st_size > 0


@st.cache_resource
def get_connection():
    return duckdb.connect(DUCKDB_PATH, read_only=True)


# ── Not-ready guard ───────────────────────────────────────────────────────────
if not _db_ready():
    st.title("📈 Warren Buffett Stock Screener")
    st.warning(
        "⏳ **No data yet.** The analytics database will be created after the "
        "first pipeline run completes.\n\n"
        "```bash\n"
        "make run-analysis-all\n"
        "```\n\n"
        "The page will refresh automatically every 60 seconds.",
        icon="🔄",
    )
    time.sleep(60)
    st.rerun()

try:
    con = get_connection()
except Exception as exc:
    st.error(f"Could not open analytics database: {exc}")
    if st.button("Retry"):
        st.cache_resource.clear()
        st.rerun()
    st.stop()


# ── Helpers ───────────────────────────────────────────────────────────────────
def _safe_query(sql: str, default=0):
    try:
        return con.execute(sql).fetchone()[0] or default
    except Exception:
        return default


def _safe_df(sql: str) -> pd.DataFrame:
    try:
        return con.execute(sql).df()
    except Exception:
        return pd.DataFrame()


def _rec_badge(rec: str) -> str:
    cls = {
        "STRONG_BUY": "score-strong-buy",
        "BUY": "score-buy",
        "HOLD": "score-hold",
        "PASS": "score-pass",
    }.get(rec, "")
    return f'<span class="score-badge {cls}">{rec}</span>'


def color_rec(val):
    colors = {
        "STRONG_BUY": "background-color: #1b5e20; color: #a5d6a7",
        "BUY":        "background-color: #2e7d32; color: #c8e6c9",
        "HOLD":       "background-color: #f57f17; color: #fff9c4",
        "PASS":       "background-color: #b71c1c; color: #ef9a9a",
    }
    return colors.get(val, "")


# ── Header ────────────────────────────────────────────────────────────────────
st.title("📈 Warren Buffett Stock Screener")
st.caption("Powered by SEC EDGAR + yfinance · Strategy-driven LLM analysis · Gemini")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("🎯 Filters")
    min_score = st.slider("Min Buffett Score", 0, 100, 50)
    rec_filter = st.multiselect(
        "Recommendation",
        ["STRONG_BUY", "BUY", "HOLD", "PASS"],
        default=["STRONG_BUY", "BUY"],
    )
    try:
        sector_options = con.execute(
            "SELECT DISTINCT sector FROM companies WHERE sector IS NOT NULL ORDER BY sector"
        ).fetchdf()["sector"].tolist()
    except Exception:
        sector_options = []
    sector_filter = st.multiselect("Sector", sector_options)

    st.divider()

    # Available analysis dates for run history
    try:
        run_dates = con.execute(
            "SELECT DISTINCT analysis_date FROM buffett_scores ORDER BY analysis_date DESC LIMIT 20"
        ).fetchdf()["analysis_date"].tolist()
    except Exception:
        run_dates = []

    st.divider()
    st.caption("Data from DuckDB analytics replica.\nUpdated each Sunday after ingestion.")

# ── Build filter SQL fragments ────────────────────────────────────────────────
recs_sql = "', '".join(rec_filter) if rec_filter else "STRONG_BUY', 'BUY"
sector_clause = ""
if sector_filter:
    secs = "', '".join(sector_filter)
    sector_clause = f"AND c.sector IN ('{secs}')"


# ══════════════════════════════════════════════════════════════════════════════
# TAB LAYOUT
# ══════════════════════════════════════════════════════════════════════════════
tab_top50, tab_weekly, tab_daily, tab_ticker = st.tabs([
    "🏆 Top 50 — Strategy Picks",
    "📅 Weekly Runs",
    "⚡ Daily Earnings",
    "🔍 Ticker Deep Dive",
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Top 50 Strategy Picks
# ══════════════════════════════════════════════════════════════════════════════
with tab_top50:
    st.markdown('<div class="section-header"><h3>🏆 Top 50 — Largest Potential (Latest Run)</h3></div>', unsafe_allow_html=True)

    top_df = _safe_df(f"""
        SELECT
            bs.ticker,
            c.name                                    AS company,
            c.sector,
            c.industry,
            ROUND(bs.buffett_total_score, 1)          AS score,
            bs.recommendation                         AS rec,
            ROUND(bs.margin_of_safety_pct * 100, 1)   AS margin_of_safety,
            ROUND(bs.current_price, 2)                AS price,
            ROUND(bs.intrinsic_value, 2)              AS intrinsic_value,
            ROUND(bs.roe_score, 1)                    AS roe,
            ROUND(bs.eps_consistency_score, 1)        AS eps,
            ROUND(bs.fcf_yield_score, 1)              AS fcf,
            ROUND(bs.leverage_score, 1)               AS leverage,
            ROUND(bs.llm_quality_score, 1)            AS llm_score,
            bs.analysis_date
        FROM buffett_scores bs
        JOIN companies c ON bs.ticker = c.ticker
        WHERE bs.analysis_date = (SELECT MAX(analysis_date) FROM buffett_scores)
          AND bs.buffett_total_score >= {min_score}
          AND bs.recommendation IN ('{recs_sql}')
          {sector_clause}
        ORDER BY bs.buffett_total_score DESC
        LIMIT 50
    """)

    # Summary metrics row
    col1, col2, col3, col4, col5 = st.columns(5)
    total_companies = _safe_query("SELECT COUNT(*) FROM companies WHERE is_active = TRUE")
    total_scored = _safe_query("SELECT COUNT(DISTINCT ticker) FROM buffett_scores WHERE analysis_date = (SELECT MAX(analysis_date) FROM buffett_scores)")
    strong_buys = _safe_query("SELECT COUNT(*) FROM buffett_scores WHERE recommendation = 'STRONG_BUY' AND analysis_date = (SELECT MAX(analysis_date) FROM buffett_scores)")
    avg_score = _safe_query("SELECT ROUND(AVG(buffett_total_score), 1) FROM buffett_scores WHERE analysis_date = (SELECT MAX(analysis_date) FROM buffett_scores)")
    llm_analyzed = _safe_query("SELECT COUNT(*) FROM buffett_scores WHERE llm_quality_score != 50 AND analysis_date = (SELECT MAX(analysis_date) FROM buffett_scores)")

    col1.metric("NASDAQ Universe", f"{total_companies:,}")
    col2.metric("Stocks Scored", f"{total_scored:,}")
    col3.metric("LLM Analyzed", f"{llm_analyzed:,}")
    col4.metric("Strong Buys", strong_buys)
    col5.metric("Avg Score", avg_score)

    st.divider()

    if top_df.empty:
        st.info("No stocks match the current filters, or the pipeline hasn't scored any stocks yet.")
    else:
        styled = top_df.style.map(color_rec, subset=["rec"])
        st.dataframe(styled, use_container_width=True, hide_index=True, height=600)

    # Score dimension breakdown chart for top picks
    if not top_df.empty:
        st.divider()
        st.subheader("📊 Score Breakdown — Top 10")
        chart_df = top_df.head(10)[["ticker", "eps", "roe", "leverage", "fcf", "llm_score"]].copy()
        chart_df = chart_df.set_index("ticker")
        chart_df.columns = ["EPS", "ROE", "Leverage", "FCF Yield", "LLM Quality"]
        st.bar_chart(chart_df)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Weekly Run History
# ══════════════════════════════════════════════════════════════════════════════
with tab_weekly:
    st.markdown('<div class="section-header"><h3>📅 Weekly Analysis Runs</h3></div>', unsafe_allow_html=True)

    run_summary_df = _safe_df("""
        SELECT
            analysis_date,
            COUNT(DISTINCT ticker) AS tickers_scored,
            COUNT(CASE WHEN recommendation = 'STRONG_BUY' THEN 1 END) AS strong_buys,
            COUNT(CASE WHEN recommendation = 'BUY' THEN 1 END) AS buys,
            COUNT(CASE WHEN recommendation = 'HOLD' THEN 1 END) AS holds,
            COUNT(CASE WHEN recommendation = 'PASS' THEN 1 END) AS passes,
            ROUND(AVG(buffett_total_score), 1) AS avg_score,
            ROUND(MAX(buffett_total_score), 1) AS max_score,
            run_id
        FROM buffett_scores
        GROUP BY analysis_date, run_id
        ORDER BY analysis_date DESC
        LIMIT 20
    """)

    if run_summary_df.empty:
        st.info("No weekly runs found. Run `make run-analysis-all` to generate the first analysis.")
    else:
        st.dataframe(run_summary_df, use_container_width=True, hide_index=True)

        # Let user select a run to inspect
        st.divider()
        selected_run_date = st.selectbox(
            "Select a run to inspect",
            run_summary_df["analysis_date"].tolist(),
            format_func=lambda d: str(d),
            key="weekly_run_select",
        )

        if selected_run_date:
            run_detail_df = _safe_df(f"""
                SELECT
                    bs.ticker,
                    c.name AS company,
                    c.sector,
                    ROUND(bs.buffett_total_score, 1) AS score,
                    bs.recommendation AS rec,
                    ROUND(bs.margin_of_safety_pct * 100, 1) AS margin_of_safety,
                    ROUND(bs.current_price, 2) AS price,
                    ROUND(bs.intrinsic_value, 2) AS intrinsic_value,
                    ROUND(bs.llm_quality_score, 1) AS llm_score
                FROM buffett_scores bs
                JOIN companies c ON bs.ticker = c.ticker
                WHERE bs.analysis_date = '{selected_run_date}'
                ORDER BY bs.buffett_total_score DESC
                LIMIT 50
            """)
            if not run_detail_df.empty:
                st.subheader(f"Top 50 from {selected_run_date}")
                styled = run_detail_df.style.map(color_rec, subset=["rec"])
                st.dataframe(styled, use_container_width=True, hide_index=True)

        # Score trend over time
        st.divider()
        st.subheader("📈 Average Score Trend Across Runs")
        trend_df = _safe_df("""
            SELECT
                analysis_date,
                ROUND(AVG(buffett_total_score), 1) AS avg_score,
                COUNT(CASE WHEN recommendation IN ('STRONG_BUY', 'BUY') THEN 1 END) AS buy_signals
            FROM buffett_scores
            GROUP BY analysis_date
            ORDER BY analysis_date
        """)
        if not trend_df.empty:
            st.line_chart(trend_df.set_index("analysis_date"))


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Daily Earnings Events
# ══════════════════════════════════════════════════════════════════════════════
with tab_daily:
    st.markdown('<div class="section-header"><h3>⚡ Daily Earnings Events</h3></div>', unsafe_allow_html=True)

    earnings_df = _safe_df("""
        SELECT
            ee.ticker,
            c.name AS company,
            c.sector,
            ee.report_date,
            ROUND(ee.eps_actual, 2) AS eps_actual,
            ROUND(ee.eps_estimate, 2) AS eps_estimate,
            CASE
                WHEN ee.eps_estimate IS NOT NULL AND ee.eps_estimate != 0
                THEN ROUND((ee.eps_actual - ee.eps_estimate) / ABS(ee.eps_estimate) * 100, 1)
                ELSE NULL
            END AS surprise_pct,
            ee.filing_url
        FROM earnings_events ee
        LEFT JOIN companies c ON ee.ticker = c.ticker
        ORDER BY ee.report_date DESC, ee.ticker
        LIMIT 100
    """)

    if earnings_df.empty:
        st.info("No earnings events recorded yet. The daily tracker polls EDGAR for 8-K filings.")
    else:
        # Summary metrics
        c1, c2, c3 = st.columns(3)
        total_events = len(earnings_df)
        beats = len(earnings_df[earnings_df.get("surprise_pct", pd.Series(dtype=float)) > 0]) if "surprise_pct" in earnings_df.columns else 0
        misses = len(earnings_df[earnings_df.get("surprise_pct", pd.Series(dtype=float)) < 0]) if "surprise_pct" in earnings_df.columns else 0
        c1.metric("Total Events", total_events)
        c2.metric("Beats", beats)
        c3.metric("Misses", misses)

        st.divider()
        st.dataframe(earnings_df, use_container_width=True, hide_index=True)

    # Upcoming earnings calendar
    st.divider()
    st.subheader("📆 Upcoming Earnings Calendar")
    calendar_df = _safe_df("""
        SELECT
            ec.ticker,
            c.name AS company,
            ec.earnings_date,
            ec.time_of_day,
            ec.eps_estimate
        FROM earnings_calendar ec
        LEFT JOIN companies c ON ec.ticker = c.ticker
        WHERE ec.earnings_date >= CURRENT_DATE
        ORDER BY ec.earnings_date ASC
        LIMIT 30
    """)
    if calendar_df.empty:
        st.info("No upcoming earnings in the calendar.")
    else:
        st.dataframe(calendar_df, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — Ticker Deep Dive
# ══════════════════════════════════════════════════════════════════════════════
with tab_ticker:
    st.markdown('<div class="section-header"><h3>🔍 Ticker Deep Dive</h3></div>', unsafe_allow_html=True)

    # Ticker search
    try:
        all_tickers = con.execute(
            "SELECT DISTINCT ticker FROM companies WHERE is_active = TRUE ORDER BY ticker"
        ).fetchdf()["ticker"].tolist()
    except Exception:
        all_tickers = []

    selected_ticker = st.selectbox(
        "Search for a ticker",
        [""] + all_tickers,
        format_func=lambda t: t if t else "Type to search...",
        key="ticker_search",
    )

    if selected_ticker:
        # ── Company Info ──────────────────────────────────────────────────
        comp_df = _safe_df(f"""
            SELECT name, sector, industry, market_cap_category
            FROM companies WHERE ticker = '{selected_ticker}'
        """)
        if not comp_df.empty:
            comp = comp_df.iloc[0]
            st.markdown(f"### {comp.get('name', selected_ticker)} ({selected_ticker})")
            st.caption(f"{comp.get('sector', '')} · {comp.get('industry', '')} · {comp.get('market_cap_category', '')}")

        # ── Latest Score Report ───────────────────────────────────────────
        st.divider()
        st.subheader("📋 Latest Analysis Report")

        latest_score = _safe_df(f"""
            SELECT
                bs.analysis_date,
                bs.run_id,
                ROUND(bs.buffett_total_score, 1) AS total_score,
                bs.recommendation,
                ROUND(bs.eps_consistency_score, 1) AS eps_score,
                ROUND(bs.roe_score, 1) AS roe_score,
                ROUND(bs.margin_of_safety_score, 1) AS mos_score,
                ROUND(bs.leverage_score, 1) AS leverage_score,
                ROUND(bs.fcf_yield_score, 1) AS fcf_score,
                ROUND(bs.moat_score, 1) AS moat_score,
                ROUND(bs.llm_quality_score, 1) AS llm_score,
                ROUND(bs.current_price, 2) AS price,
                ROUND(bs.intrinsic_value, 2) AS intrinsic_value,
                ROUND(bs.margin_of_safety_pct * 100, 1) AS margin_of_safety_pct,
                bs.investment_thesis,
                bs.moat_summary,
                bs.risk_factors
            FROM buffett_scores bs
            WHERE bs.ticker = '{selected_ticker}'
            ORDER BY bs.analysis_date DESC
            LIMIT 1
        """)

        if latest_score.empty:
            st.info(f"No analysis found for {selected_ticker}. It may not have been scored yet.")
        else:
            row = latest_score.iloc[0]

            # Score summary cards
            sc1, sc2, sc3, sc4 = st.columns(4)
            rec = row.get("recommendation", "")
            sc1.metric("Buffett Score", f"{row.get('total_score', 0)}/100")
            sc2.metric("Recommendation", rec)
            sc3.metric("Price", f"${row.get('price', 0):.2f}")
            sc4.metric("Intrinsic Value", f"${row.get('intrinsic_value', 0):.2f}")

            st.divider()

            # Dimension breakdown
            dim_col1, dim_col2 = st.columns(2)
            with dim_col1:
                st.markdown("**Score Dimensions**")
                dims = {
                    "EPS Consistency (20%)": row.get("eps_score", 0),
                    "ROE (20%)": row.get("roe_score", 0),
                    "Margin of Safety (20%)": row.get("mos_score", 0),
                    "Leverage (15%)": row.get("leverage_score", 0),
                    "FCF Yield (15%)": row.get("fcf_score", 0),
                    "Moat Proxy (5%)": row.get("moat_score", 0),
                    "LLM Quality (5%)": row.get("llm_score", 0),
                }
                for label, value in dims.items():
                    pct = max(0, min(100, value))
                    color = "#4caf50" if pct >= 70 else "#ff9800" if pct >= 40 else "#f44336"
                    st.markdown(f"**{label}**: {value}")
                    st.progress(pct / 100)

            with dim_col2:
                st.markdown("**Valuation**")
                mos_pct = row.get("margin_of_safety_pct", 0)
                st.metric("Margin of Safety", f"{mos_pct}%",
                          delta=f"{'Undervalued' if mos_pct and mos_pct > 0 else 'Overvalued'}",
                          delta_color="normal" if mos_pct and mos_pct > 0 else "inverse")

                # Bar chart of dimensions
                dim_df = pd.DataFrame({
                    "Dimension": list(dims.keys()),
                    "Score": list(dims.values()),
                })
                st.bar_chart(dim_df.set_index("Dimension"))

            # Investment thesis
            thesis = row.get("investment_thesis", "")
            if str(thesis) and str(thesis) not in ("None", "nan", "NaN", "Qualitative analysis could not be completed for this run."):
                st.divider()
                st.subheader("📝 Investment Thesis")
                st.markdown(str(thesis))

            # Moat summary
            moat = row.get("moat_summary", "")
            if str(moat) and str(moat) not in ("None", "nan", "NaN"):
                st.subheader("🏰 Moat Summary")
                st.markdown(str(moat))

            # Risk factors
            risks = row.get("risk_factors", "")
            if str(risks) and str(risks) not in ("None", "[]", "nan", "NaN"):
                st.subheader("⚠️ Risk Factors")
                if isinstance(risks, (list, tuple)):
                    st.markdown("\n".join([f"- {r}" for r in risks]))
                elif hasattr(risks, "tolist"):
                    st.markdown("\n".join([f"- {r}" for r in risks.tolist()]))
                else:
                    st.markdown(str(risks))

        # ── Historical Scores ─────────────────────────────────────────────
        st.divider()
        st.subheader("📈 Score History")

        history_df = _safe_df(f"""
            SELECT
                analysis_date,
                ROUND(buffett_total_score, 1) AS score,
                recommendation AS rec,
                ROUND(current_price, 2) AS price,
                ROUND(intrinsic_value, 2) AS intrinsic_value,
                ROUND(margin_of_safety_pct * 100, 1) AS margin_of_safety,
                ROUND(llm_quality_score, 1) AS llm_score
            FROM buffett_scores
            WHERE ticker = '{selected_ticker}'
            ORDER BY analysis_date DESC
        """)

        if history_df.empty:
            st.info("No historical scores available.")
        else:
            st.dataframe(history_df, use_container_width=True, hide_index=True)

            # Trend chart
            if len(history_df) > 1:
                chart_data = history_df[["analysis_date", "score", "price"]].copy()
                chart_data = chart_data.set_index("analysis_date").sort_index()
                st.line_chart(chart_data)

        # ── EPS History Chart ─────────────────────────────────────────────
        st.divider()
        st.subheader("📊 EPS History")
        eps_df = _safe_df(f"""
            SELECT fiscal_year, eps FROM eps_history
            WHERE ticker = '{selected_ticker}'
            ORDER BY fiscal_year
        """)
        if not eps_df.empty:
            st.bar_chart(eps_df.set_index("fiscal_year")["eps"])
        else:
            st.info("No EPS history available for this ticker.")

        # ── Financial Snapshot ────────────────────────────────────────────
        st.divider()
        st.subheader("💰 Latest Financial Snapshot")
        snap_df = _safe_df(f"""
            SELECT
                snapshot_date,
                ROUND(market_cap / 1e9, 2) AS market_cap_B,
                ROUND(pe_ratio, 1) AS pe_ratio,
                ROUND(return_on_equity * 100, 1) AS roe_pct,
                ROUND(gross_margin * 100, 1) AS gross_margin_pct,
                ROUND(operating_margin * 100, 1) AS operating_margin_pct,
                ROUND(net_margin * 100, 1) AS net_margin_pct,
                ROUND(debt_to_equity, 2) AS debt_to_equity,
                ROUND(current_ratio, 2) AS current_ratio,
                ROUND(free_cash_flow / 1e6, 1) AS fcf_M,
                ROUND(current_price, 2) AS price,
                ROUND(fifty_two_week_high, 2) AS week_52_high,
                ROUND(fifty_two_week_low, 2) AS week_52_low
            FROM financial_snapshots
            WHERE ticker = '{selected_ticker}'
            ORDER BY snapshot_date DESC
            LIMIT 1
        """)
        if not snap_df.empty:
            st.dataframe(snap_df, use_container_width=True, hide_index=True)
        else:
            st.info("No financial snapshot available.")

        # ── Earnings Events ───────────────────────────────────────────────
        ticker_earnings = _safe_df(f"""
            SELECT
                report_date,
                ROUND(eps_actual, 2) AS eps_actual,
                ROUND(eps_estimate, 2) AS eps_estimate,
                CASE
                    WHEN eps_estimate IS NOT NULL AND eps_estimate != 0
                    THEN ROUND((eps_actual - eps_estimate) / ABS(eps_estimate) * 100, 1)
                    ELSE NULL
                END AS surprise_pct,
                filing_url
            FROM earnings_events
            WHERE ticker = '{selected_ticker}'
            ORDER BY report_date DESC
            LIMIT 10
        """)
        if not ticker_earnings.empty:
            st.divider()
            st.subheader("📰 Earnings Events")
            st.dataframe(ticker_earnings, use_container_width=True, hide_index=True)
