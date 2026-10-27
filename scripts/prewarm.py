"""Fetch and store everything the dashboard needs so it can run offline.

Runs local LLM analyses in the background for the current top 10 on both
platforms. Resumable: videos that already have a stored analysis are skipped.

Usage (from the repo root):  python scripts/prewarm.py
"""

import asyncio
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.analysis import AnalysisError, get_or_create_analysis, llm_provider
from app.config import settings
from app.db import SessionLocal, init_db
from app.trending import PLATFORMS, YOUTUBE, collect_youtube_evidence, list_trending, refresh_youtube

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


async def analyze(provider, platform: str, video_ids: list[str]) -> None:
    total = len(video_ids)
    for i, video_id in enumerate(video_ids, start=1):
        started = time.monotonic()
        with SessionLocal() as session:
            try:
                _, cached = await get_or_create_analysis(session, platform, video_id, provider)
            except Exception as exc:
                log.error("[%s %d/%d] %s failed: %s", platform, i, total, video_id, exc)
                continue
        log.info(
            "[%s %d/%d] %s %s (%.0fs)",
            platform,
            i,
            total,
            video_id,
            "cached" if cached else "generated",
            time.monotonic() - started,
        )


async def main() -> None:
    init_db()
    youtube_ids = await prewarm_youtube()

    try:
        provider = llm_provider()
    except AnalysisError as exc:
        log.error("Skipping analysis: %s", exc)
        return
    log.info("LLM provider=%s model=%s — analyses run one at a time", settings.llm_provider, settings.llm_model)

    await analyze(provider, YOUTUBE, youtube_ids)
    with SessionLocal() as session:
        instagram_ids = [i["video_id"] for i in list_trending(session, "instagram")]
    if "instagram" in PLATFORMS:
        await analyze(provider, "instagram", instagram_ids)


if __name__ == "__main__":
    asyncio.run(main())
