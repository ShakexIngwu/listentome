"""
api.py — FastAPI backend for the Buffett Stock Screener Flutter frontend.
Serves data from the DuckDB analytics read replica.
"""
import os
from pathlib import Path
from typing import List, Optional, Any, Dict
import math

import duckdb
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Buffett Screener API")

# Allow Flutter app to access this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DUCKDB_PATH = os.environ.get("DUCKDB_PATH", "./analytics/stocks_analytics.duckdb")

def get_connection():
    if not Path(DUCKDB_PATH).exists() or Path(DUCKDB_PATH).stat().st_size == 0:
        raise HTTPException(status_code=503, detail="Database not ready")
    return duckdb.connect(DUCKDB_PATH, read_only=True)

class TopPick(BaseModel):
    ticker: str
    company: str
    score: float
    recommendation: str
    margin_of_safety: float

def clean_value(val):
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            return None
    return val

def clean_df(df: pd.DataFrame) -> List[Dict[str, Any]]:
    # Convert to standard Python dict records, then strictly replace any NaN/inf floats with None
    records = df.to_dict(orient="records")
    return [{k: clean_value(v) for k, v in r.items()} for r in records]

@app.get("/api/top-picks", response_model=List[TopPick])
def get_top_picks(limit: int = 50):
    try:
        con = get_connection()
        query = f"""
            SELECT
                bs.ticker,
                c.name AS company,
                ROUND(bs.buffett_total_score, 1) AS score,
                bs.recommendation,
                ROUND(bs.margin_of_safety_pct * 100, 1) AS margin_of_safety
            FROM buffett_scores bs
            JOIN companies c ON bs.ticker = c.ticker
            WHERE bs.analysis_date = (SELECT MAX(analysis_date) FROM buffett_scores)
            ORDER BY bs.buffett_total_score DESC
            LIMIT {limit}
        """
        df = con.execute(query).df()
        return clean_df(df)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/tickers", response_model=List[str])
def get_tickers():
    try:
        con = get_connection()
        query = "SELECT DISTINCT ticker FROM companies WHERE is_active = TRUE ORDER BY ticker"
        df = con.execute(query).df()
        return df["ticker"].tolist()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/ticker/{ticker}")
def get_ticker_deep_dive(ticker: str):
    try:
        con = get_connection()
        
        # 1. Company Info
        comp_df = con.execute(f"SELECT name, sector, industry, CASE WHEN market_cap >= 200000000000 THEN 'Mega Cap' WHEN market_cap >= 10000000000 THEN 'Large Cap' WHEN market_cap >= 2000000000 THEN 'Mid Cap' WHEN market_cap >= 300000000 THEN 'Small Cap' ELSE 'Micro/Nano Cap' END AS market_cap_category FROM companies WHERE ticker = '{ticker}'").df()
        if comp_df.empty:
            raise HTTPException(status_code=404, detail="Ticker not found")
        company_info = clean_df(comp_df)[0]
        
        # 2. Latest Score Report
        score_query = f"""
            SELECT
                CAST(bs.analysis_date AS VARCHAR) AS analysis_date,
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
            WHERE bs.ticker = '{ticker}'
            ORDER BY bs.analysis_date DESC
            LIMIT 1
        """
        latest_score_df = con.execute(score_query).df()
        latest_score = clean_df(latest_score_df)[0] if not latest_score_df.empty else None

        # 3. Score History
        history_query = f"""
            SELECT
                CAST(analysis_date AS VARCHAR) AS analysis_date,
                ROUND(buffett_total_score, 1) AS score,
                recommendation AS rec,
                ROUND(current_price, 2) AS price
            FROM buffett_scores
            WHERE ticker = '{ticker}'
            ORDER BY analysis_date ASC
        """
        history_df = con.execute(history_query).df()
        history = clean_df(history_df)
        
        # 4. EPS History
        eps_df = con.execute(f"SELECT fiscal_year, eps FROM eps_history WHERE ticker = '{ticker}' ORDER BY fiscal_year").df()
        eps_history = clean_df(eps_df)

        return {
            "company": company_info,
            "latest_score": latest_score,
            "history": history,
            "eps_history": eps_history
        }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/weekly-runs")
def get_weekly_runs():
    try:
        con = get_connection()
        query = """
            SELECT
                CAST(analysis_date AS VARCHAR) AS analysis_date,
                COUNT(DISTINCT ticker) AS tickers_scored,
                COUNT(CASE WHEN recommendation = 'STRONG_BUY' THEN 1 END) AS strong_buys,
                COUNT(CASE WHEN recommendation = 'BUY' THEN 1 END) AS buys,
                COUNT(CASE WHEN recommendation = 'HOLD' THEN 1 END) AS holds,
                COUNT(CASE WHEN recommendation = 'PASS' THEN 1 END) AS passes,
                ROUND(AVG(buffett_total_score), 1) AS avg_score,
                ROUND(MAX(buffett_total_score), 1) AS max_score
            FROM buffett_scores
            GROUP BY analysis_date
            ORDER BY analysis_date DESC
            LIMIT 20
        """
        df = con.execute(query).df()
        return clean_df(df)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/weekly-runs/{run_date}", response_model=List[TopPick])
def get_weekly_run_details(run_date: str, limit: int = 50):
    try:
        con = get_connection()
        query = f"""
            SELECT
                bs.ticker,
                c.name AS company,
                ROUND(bs.buffett_total_score, 1) AS score,
                bs.recommendation,
                ROUND(bs.margin_of_safety_pct * 100, 1) AS margin_of_safety
            FROM buffett_scores bs
            JOIN companies c ON bs.ticker = c.ticker
            WHERE CAST(bs.analysis_date AS VARCHAR) = '{run_date}'
            ORDER BY bs.buffett_total_score DESC
            LIMIT {limit}
        """
        df = con.execute(query).df()
        return clean_df(df)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/earnings")
def get_earnings():
    try:
        con = get_connection()
        
        # Calendar
        cal_query = """
            SELECT
                ec.ticker,
                c.name AS company,
                CAST(ec.earnings_date AS VARCHAR) AS earnings_date,
                ec.time_of_day,
                ec.eps_estimate,
                bs.recommendation,
                bs.buffett_total_score as score
            FROM earnings_calendar ec
            LEFT JOIN companies c ON ec.ticker = c.ticker
            LEFT JOIN (
                SELECT ticker, recommendation, buffett_total_score
                FROM buffett_scores
                WHERE analysis_date = (SELECT MAX(analysis_date) FROM buffett_scores)
            ) bs ON ec.ticker = bs.ticker
            WHERE ec.earnings_date >= CURRENT_DATE
            ORDER BY ec.earnings_date ASC
            LIMIT 50
        """
        calendar_df = con.execute(cal_query).df()
        
        # Recent events
        events_query = """
            SELECT
                ee.ticker,
                c.name AS company,
                CAST(ee.report_date AS VARCHAR) AS report_date,
                ROUND(ee.eps_actual, 2) AS eps_actual,
                ROUND(ee.eps_estimate, 2) AS eps_estimate,
                CASE
                    WHEN ee.eps_estimate IS NOT NULL AND ee.eps_estimate != 0
                    THEN ROUND((ee.eps_actual - ee.eps_estimate) / ABS(ee.eps_estimate) * 100, 1)
                    ELSE NULL
                END AS surprise_pct,
                bs.recommendation,
                bs.buffett_total_score as score
            FROM earnings_events ee
            LEFT JOIN companies c ON ee.ticker = c.ticker
            LEFT JOIN (
                SELECT ticker, recommendation, buffett_total_score
                FROM buffett_scores
                WHERE analysis_date = (SELECT MAX(analysis_date) FROM buffett_scores)
            ) bs ON ee.ticker = bs.ticker
            ORDER BY ee.report_date DESC, ee.ticker
            LIMIT 50
        """
        events_df = con.execute(events_query).df()

        # Generate summary metrics
        today_calendar = calendar_df[calendar_df['earnings_date'] == str(pd.Timestamp.today().date())]
        summary = {
            "total_reporting_today": len(today_calendar),
            "pre_market": len(today_calendar[today_calendar['time_of_day'] == 'pre_market']),
            "after_hours": len(today_calendar[today_calendar['time_of_day'] == 'after_hours']),
            "high_conviction": len(today_calendar[today_calendar['recommendation'] == 'STRONG_BUY']),
        }

        return {
            "summary": summary,
            "calendar": clean_df(calendar_df),
            "events": clean_df(events_df)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/health")
def health_check():
    return {"status": "ok", "db_ready": Path(DUCKDB_PATH).exists()}
