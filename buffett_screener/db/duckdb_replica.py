"""
db/duckdb_replica.py
Exports all operational PostgreSQL tables to Parquet files, then
rebuilds DuckDB views pointing at those files.

DuckDB is NEVER written to by pipelines — it is a read-only analytics
replica rebuilt from Postgres each week (and after daily earnings runs).
"""
import asyncio
from pathlib import Path

import duckdb
import pandas as pd
import structlog
from sqlalchemy import text

from config import settings
from db.postgres import engine

log = structlog.get_logger()

# Tables to export (order matters for FK deps)
EXPORT_TABLES = [
    "companies",
    "financial_snapshots",
    "eps_history",
    "buffett_scores",
    "earnings_events",
    "earnings_calendar",
]


async def export_to_parquet() -> dict[str, int]:
    """
    Reads each table from PostgreSQL and writes to a Parquet file.
    Returns row counts per table.
    """
    parquet_dir = Path(settings.parquet_dir)
    parquet_dir.mkdir(parents=True, exist_ok=True)

    row_counts: dict[str, int] = {}

    async with engine.connect() as conn:
        for table in EXPORT_TABLES:
            result = await conn.execute(text(f"SELECT * FROM {table}"))
            rows = result.fetchall()
            cols = list(result.keys())

            df = pd.DataFrame(rows, columns=cols)
            path = parquet_dir / f"{table}.parquet"
            df.to_parquet(path, index=False, engine="pyarrow")

            row_counts[table] = len(df)
            log.info("parquet_exported", table=table, rows=len(df), path=str(path))

    return row_counts


def rebuild_duckdb_views() -> None:
    """
    Rebuilds DuckDB views by writing to a TEMP file first, then atomically
    replacing the production file with os.replace().

    Why: the dashboard holds a read-only connection to stocks_analytics.duckdb.
    Even read-only connections hold a shared OS-level lock, which blocks the
    exclusive lock DuckDB needs to open a file for writing.

    The temp-file + atomic rename pattern avoids this:
      1. Write the new DB to stocks_analytics.duckdb.tmp  (no lock conflict)
      2. os.replace() atomically swaps the inode at the canonical path
      3. Dashboard's existing fd keeps pointing at the OLD inode until its
         cache_resource is cleared — no errors, no interruption
      4. Next time the dashboard reconnects it opens the fresh file
    """
    import os

    parquet_dir = Path(settings.parquet_dir).resolve()
    duckdb_path = Path(settings.duckdb_path)
    tmp_path    = duckdb_path.with_suffix(".duckdb.tmp")

    duckdb_path.parent.mkdir(parents=True, exist_ok=True)

    # Remove any stale temp file from a previous crashed run
    if tmp_path.exists():
        tmp_path.unlink()

    con = duckdb.connect(str(tmp_path))
    try:
        for table in EXPORT_TABLES:
            parquet_file = parquet_dir / f"{table}.parquet"
            if not parquet_file.exists():
                log.warning("parquet_missing", table=table)
                con.execute(f"CREATE OR REPLACE VIEW {table} AS SELECT 1 WHERE FALSE")
                continue
            con.execute(f"""
                CREATE OR REPLACE VIEW {table} AS
                SELECT * FROM read_parquet('{parquet_file}')
            """)
            log.info("duckdb_view_refreshed", table=table)
    finally:
        con.close()

    # Atomic swap — replaces canonical path in one syscall
    os.replace(tmp_path, duckdb_path)
    log.info("duckdb_atomic_swap_complete", path=str(duckdb_path))


async def run_full_export() -> None:
    """Entry point: export Postgres → Parquet, then rebuild DuckDB views."""
    log.info("duckdb_export_started")
    counts = await export_to_parquet()
    rebuild_duckdb_views()
    log.info("duckdb_export_complete", tables=counts)


def initialize_empty_duckdb() -> None:
    """
    Creates the DuckDB file and empty placeholder views on first startup.
    Called by main.py before the schedulers start so the dashboard can connect
    immediately without waiting for the first full pipeline run.

    If Parquet files already exist (subsequent starts), real views are used.
    If not, placeholder views return zero rows — the dashboard handles that gracefully.
    """
    duckdb_path = Path(settings.duckdb_path)
    if duckdb_path.exists():
        log.info("duckdb_already_initialized", path=str(duckdb_path))
        return

    duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    parquet_dir = Path(settings.parquet_dir).resolve()

    con = duckdb.connect(str(duckdb_path))
    try:
        for table in EXPORT_TABLES:
            parquet_file = parquet_dir / f"{table}.parquet"
            if parquet_file.exists():
                con.execute(f"""
                    CREATE OR REPLACE VIEW {table} AS
                    SELECT * FROM read_parquet('{parquet_file}')
                """)
            else:
                # Empty placeholder — SELECT returns 0 rows, dashboard handles gracefully
                con.execute(f"CREATE OR REPLACE VIEW {table} AS SELECT 1 WHERE FALSE")
        log.info("duckdb_initialized_empty", path=str(duckdb_path))
    finally:
        con.close()
