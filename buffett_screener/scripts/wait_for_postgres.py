"""
scripts/wait_for_postgres.py
Blocks until PostgreSQL is reachable. Called by entrypoint.sh before
running migrations or starting the backend service.
"""
import asyncio
import os
import sys


async def main() -> None:
    raw_url = os.environ.get("POSTGRES_URL", "")
    if not raw_url:
        print("POSTGRES_URL not set — skipping wait.")
        return

    # asyncpg needs postgresql:// not postgresql+asyncpg://
    url = raw_url.replace("postgresql+asyncpg://", "postgresql://")

    import asyncpg  # noqa: PLC0415

    max_attempts = 40
    for attempt in range(1, max_attempts + 1):
        try:
            conn = await asyncpg.connect(url, timeout=5)
            await conn.close()
            print(f"✅ PostgreSQL is ready (attempt {attempt}).")
            return
        except Exception as exc:
            print(f"⏳ [{attempt}/{max_attempts}] PostgreSQL not ready yet: {exc}")
            await asyncio.sleep(3)

    print("❌ PostgreSQL did not become ready in time. Exiting.")
    sys.exit(1)


asyncio.run(main())
