"""Fetch and store everything the dashboard needs so it can run offline.

Usage (from the repo root):  python scripts/prewarm.py
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.db import SessionLocal, init_db  # noqa: E402
from app.trending import YOUTUBE, collect_youtube_evidence, list_trending, refresh_youtube  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("prewarm")


async def prewarm_youtube() -> None:
    with SessionLocal() as session:
        try:
            await refresh_youtube(session)
        except Exception as exc:
            log.error("YouTube refresh failed, using stored data: %s", exc)
        ids = {i["video_id"] for relevant in (True, False) for i in list_trending(session, YOUTUBE, relevant)}
        if not ids:
            log.error("No YouTube data available")
            return
        await collect_youtube_evidence(session, sorted(ids))
        log.info("YouTube: stored evidence for %d videos", len(ids))


async def main() -> None:
    init_db()
    await prewarm_youtube()


if __name__ == "__main__":
    asyncio.run(main())
