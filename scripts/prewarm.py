"""Fetch and store everything the dashboard needs so it can run offline.

Usage (from the repo root):  python scripts/prewarm.py
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.analysis import AnalysisError, anthropic_client, get_or_create_analysis
from app.db import SessionLocal, init_db
from app.trending import YOUTUBE, collect_youtube_evidence, list_trending, refresh_youtube

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("prewarm")


async def prewarm_youtube() -> list[str]:
    with SessionLocal() as session:
        try:
            await refresh_youtube(session)
        except Exception as exc:
            log.error("YouTube refresh failed, using stored data: %s", exc)
        ids = sorted({i["video_id"] for relevant in (True, False) for i in list_trending(session, YOUTUBE, relevant)})
        if not ids:
            log.error("No YouTube data available")
            return []
        await collect_youtube_evidence(session, ids)
        log.info("YouTube: stored evidence for %d videos", len(ids))
        return ids


async def analyze(platform: str, video_ids: list[str]) -> None:
    try:
        client = anthropic_client()
    except AnalysisError as exc:
        log.error("Skipping analysis: %s", exc)
        return

    async def one(video_id: str) -> bool:
        with SessionLocal() as session:
            try:
                _, cached = await get_or_create_analysis(session, platform, video_id, client)
                log.info("%s:%s analysis %s", platform, video_id, "cached" if cached else "generated")
                return True
            except Exception as exc:
                log.error("%s:%s analysis failed: %s", platform, video_id, exc)
                return False

    results = await asyncio.gather(*(one(v) for v in video_ids))
    log.info("%s: %d/%d analyses ready", platform, sum(results), len(video_ids))


async def main() -> None:
    init_db()
    youtube_ids = await prewarm_youtube()
    await analyze(YOUTUBE, youtube_ids)


if __name__ == "__main__":
    asyncio.run(main())
