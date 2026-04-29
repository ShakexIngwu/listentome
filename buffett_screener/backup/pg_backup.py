"""
backup/pg_backup.py
Daily pg_dump backup of the PostgreSQL database.
Runs at 03:00 AM via APScheduler alongside the main scheduler.
Keeps only the last N days of backups (configurable).
"""
import asyncio
import glob
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import structlog

from config import settings

log = structlog.get_logger()


def _parse_pg_credentials(url: str) -> dict:
    """Parses a SQLAlchemy postgres URL into connection components."""
    # Strip the +asyncpg driver modifier
    clean_url = url.replace("postgresql+asyncpg://", "postgresql://")
    parsed = urlparse(clean_url)
    return {
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "user": parsed.username or "buffett",
        "password": parsed.password or "",
        "dbname": parsed.path.lstrip("/") or "stocks",
    }


def run_pg_dump() -> str:
    """
    Runs pg_dump and writes a compressed SQL dump to the backup directory.
    Returns the path of the created backup file.
    Raises subprocess.CalledProcessError on failure.
    """
    backup_dir = Path(settings.postgres_backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)

    creds = _parse_pg_credentials(settings.postgres_url)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    backup_file = backup_dir / f"stocks_{timestamp}.sql.gz"

    env = os.environ.copy()
    env["PGPASSWORD"] = creds["password"]

    cmd = [
        "pg_dump",
        "-h", creds["host"],
        "-p", creds["port"],
        "-U", creds["user"],
        "-d", creds["dbname"],
        "--no-password",
        "-F", "c",            # Custom compressed format
        "-f", str(backup_file),
    ]

    log.info("pg_dump_started", backup_file=str(backup_file))
    subprocess.run(cmd, env=env, check=True, capture_output=True)
    log.info("pg_dump_complete", backup_file=str(backup_file), size_mb=round(backup_file.stat().st_size / 1e6, 2))

    return str(backup_file)


def rotate_old_backups() -> int:
    """Deletes backup files older than POSTGRES_BACKUP_KEEP_DAYS. Returns count deleted."""
    backup_dir = Path(settings.postgres_backup_dir)
    pattern = str(backup_dir / "stocks_*.sql.gz")
    files = sorted(glob.glob(pattern))  # Sorted ascending by date in filename

    keep = settings.postgres_backup_keep_days
    to_delete = files[:-keep] if len(files) > keep else []

    for f in to_delete:
        os.remove(f)
        log.info("backup_rotated", file=f)

    return len(to_delete)


async def daily_backup_job() -> None:
    """Async wrapper for scheduler; runs pg_dump then rotates stale backups."""
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, run_pg_dump)
        deleted = await loop.run_in_executor(None, rotate_old_backups)
        log.info("daily_backup_done", rotated=deleted)
    except Exception as e:
        log.error("daily_backup_failed", error=str(e))
