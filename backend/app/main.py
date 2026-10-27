import logging
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .config import MARKET, settings
from .db import SessionLocal, get_session, init_db
from .trending import (
    YOUTUBE,
    collect_youtube_evidence,
    evidence_summary,
    is_stale,
    latest_capture,
    list_trending,
    refresh_status,
    refresh_youtube,
)
from .youtube import YouTubeClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger(__name__)

Platform = Literal["youtube", "instagram"]


def youtube_client() -> YouTubeClient:
    return YouTubeClient()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="AI Marketing Dashboard", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


async def _collect_evidence_background(video_ids: list[str], client: YouTubeClient) -> None:
    with SessionLocal() as session:
        await collect_youtube_evidence(session, video_ids, client)


def _trending_payload(session: Session, platform: str, relevant: bool, refresh_error: str | None) -> dict:
    items = list_trending(session, platform, relevant)
    evidence = evidence_summary(session, platform, [i["video_id"] for i in items])
    for item in items:
        item["evidence"] = evidence.get(item["video_id"])
    last_updated = latest_capture(session, platform)
    return {
        "market": MARKET.country,
        "platform": platform,
        "relevant": relevant,
        "last_updated": last_updated.isoformat() if last_updated else None,
        "cached": refresh_error is not None,
        "error": refresh_error,
        "items": items,
    }


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "market": MARKET.country}


@app.get("/api/trending")
async def trending(
    background: BackgroundTasks,
    platform: Platform = Query(YOUTUBE),
    relevant: bool = Query(True),
    session: Session = Depends(get_session),
    client: YouTubeClient = Depends(youtube_client),
) -> dict:
    refresh_error = None
    if platform == YOUTUBE:
        if is_stale(latest_capture(session, YOUTUBE)):
            try:
                await refresh_youtube(session, client)
            except Exception as exc:
                log.warning("YouTube refresh failed, serving stored data: %s", exc)
                refresh_error = str(exc)
        elif refresh_status.get(YOUTUBE, {}).get("ok") is False:
            refresh_error = refresh_status[YOUTUBE]["error"]

    payload = _trending_payload(session, platform, relevant, refresh_error)
    missing = [i["video_id"] for i in payload["items"] if platform == YOUTUBE and not i["evidence"]]
    if missing and refresh_error is None:
        background.add_task(_collect_evidence_background, missing, client)
    return payload


@app.post("/api/refresh/youtube")
async def refresh(
    background: BackgroundTasks,
    relevant: bool = Query(True),
    session: Session = Depends(get_session),
    client: YouTubeClient = Depends(youtube_client),
) -> dict:
    refresh_error = None
    try:
        await refresh_youtube(session, client)
    except Exception as exc:
        log.warning("YouTube refresh failed, serving stored data: %s", exc)
        refresh_error = str(exc)
    payload = _trending_payload(session, YOUTUBE, relevant, refresh_error)
    if refresh_error is None and payload["items"]:
        background.add_task(_collect_evidence_background, [i["video_id"] for i in payload["items"]], client)
    elif not payload["items"]:
        raise HTTPException(status_code=502, detail=f"YouTube refresh failed and no stored data: {refresh_error}")
    return payload
