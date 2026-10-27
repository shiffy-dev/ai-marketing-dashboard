"""Fetching, storing and ranking trending videos."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import MARKET, NOISE_CATEGORY_IDS, YOUTUBE_CATEGORIES, settings
from .metrics import compute_metrics, score_items
from .models import Evidence, Video, VideoSnapshot, utcnow
from .youtube import YouTubeClient, best_thumbnail, fetch_transcript, parse_ts

log = logging.getLogger(__name__)

YOUTUBE = "youtube"
PLATFORMS = (YOUTUBE, "instagram")

# Outcome of the most recent refresh attempt per platform (process-local).
refresh_status: dict[str, dict] = {}


def as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def latest_capture(session: Session, platform: str) -> datetime | None:
    return as_utc(session.scalar(select(func.max(VideoSnapshot.captured_at)).where(VideoSnapshot.platform == platform)))


def is_stale(captured_at: datetime | None, hours: int = settings.youtube_stale_hours) -> bool:
    return captured_at is None or utcnow() - captured_at > timedelta(hours=hours)


async def refresh_youtube(session: Session, client: YouTubeClient | None = None) -> datetime:
    """Fetches the UAE mostPopular chart and stores videos + a snapshot. Raises on API failure."""
    client = client or YouTubeClient()
    attempted_at = utcnow()
    session.commit()  # end any open read transaction before network awaits
    try:
        items = await client.most_popular(MARKET.country)
        subs = await client.channel_subscribers([i["snippet"]["channelId"] for i in items])
    except Exception as exc:
        refresh_status[YOUTUBE] = {"ok": False, "error": str(exc), "attempted_at": attempted_at}
        raise

    captured_at = utcnow()
    existing = {
        v.video_id: v
        for v in session.scalars(
            select(Video).where(Video.platform == YOUTUBE, Video.video_id.in_([i["id"] for i in items]))
        )
    }
    for rank, item in enumerate(items, start=1):
        snippet, stats = item.get("snippet", {}), item.get("statistics", {})
        video = existing.get(item["id"]) or Video(platform=YOUTUBE, video_id=item["id"])
        video.title = snippet.get("title", "")
        video.channel = snippet.get("channelTitle", "")
        video.channel_id = snippet.get("channelId")
        video.followers_or_subs = subs.get(snippet.get("channelId"))
        video.published_at = parse_ts(snippet.get("publishedAt"))
        video.thumbnail = best_thumbnail(snippet.get("thumbnails", {}))
        video.category_id = snippet.get("categoryId")
        video.language = snippet.get("defaultAudioLanguage") or snippet.get("defaultLanguage")
        video.raw_json = item
        video.fetched_at = captured_at
        session.add(video)
        session.flush()
        session.add(
            VideoSnapshot(
                video_id=video.id,
                platform=YOUTUBE,
                captured_at=captured_at,
                views=int(stats.get("viewCount", 0)),
                likes=int(stats["likeCount"]) if "likeCount" in stats else None,
                comments=int(stats["commentCount"]) if "commentCount" in stats else None,
                rank=rank,
            )
        )
    session.commit()
    refresh_status[YOUTUBE] = {"ok": True, "error": None, "attempted_at": attempted_at}
    log.info("refreshed %d YouTube trending videos", len(items))
    return captured_at


def _serialize(video: Video, snap: VideoSnapshot, as_of: datetime) -> dict:
    raw = video.raw_json or {}
    url = raw.get("url") or (f"https://www.youtube.com/watch?v={video.video_id}" if video.platform == YOUTUBE else None)
    return {
        "platform": video.platform,
        "video_id": video.video_id,
        "url": url,
        "title": video.title,
        "channel": video.channel,
        "channel_id": video.channel_id,
        "followers_or_subs": video.followers_or_subs,
        "thumbnail": video.thumbnail,
        "category_id": video.category_id,
        "category": YOUTUBE_CATEGORIES.get(video.category_id or ""),
        "language": video.language,
        "published_at": as_utc(video.published_at).isoformat() if video.published_at else None,
        "duration": raw.get("contentDetails", {}).get("duration"),
        "chart_rank": snap.rank,
        "views": snap.views,
        "likes": snap.likes,
        "comments": snap.comments,
        "metrics": compute_metrics(
            snap.views, snap.likes, snap.comments, video.followers_or_subs, as_utc(video.published_at), as_of
        ),
    }


def list_trending(session: Session, platform: str, relevant: bool = True, limit: int | None = None) -> list[dict]:
    """Top-N from the latest stored capture, ranked by velocity + outlier ratio."""
    captured_at = latest_capture(session, platform)
    if captured_at is None:
        return []
    rows = session.execute(
        select(Video, VideoSnapshot)
        .join(VideoSnapshot, VideoSnapshot.video_id == Video.id)
        .where(VideoSnapshot.platform == platform, VideoSnapshot.captured_at == captured_at)
    ).all()
    if relevant and platform == YOUTUBE:
        rows = [(v, s) for v, s in rows if v.category_id not in NOISE_CATEGORY_IDS]
    items = score_items([_serialize(v, s, captured_at) for v, s in rows])[: limit or settings.top_n]
    for rank, item in enumerate(items, start=1):
        item["rank"] = rank
    return items


def evidence_is_fresh(evidence: Evidence | None) -> bool:
    if evidence is None:
        return False
    if evidence.platform != YOUTUBE:
        return True
    return not is_stale(as_utc(evidence.fetched_at))


_evidence_locks: dict[str, asyncio.Lock] = {}


async def ensure_youtube_evidence(
    session: Session, video: Video, client: YouTubeClient | None = None, force: bool = False
) -> Evidence:
    """Transcript (en/ar captions, else title+description) and top comments for one video."""
    # The background collector and analysis requests can race for the same video.
    async with _evidence_locks.setdefault(video.video_id, asyncio.Lock()):
        evidence = session.scalar(
            select(Evidence).where(Evidence.platform == YOUTUBE, Evidence.video_id == video.video_id)
        )
        if evidence is not None:
            session.refresh(evidence)
        if not force and evidence_is_fresh(evidence):
            return evidence
        session.commit()  # end the read transaction before network awaits
        return await _fetch_and_store_evidence(session, video, evidence, client or YouTubeClient())


async def _fetch_and_store_evidence(
    session: Session, video: Video, evidence: Evidence | None, client: YouTubeClient
) -> Evidence:
    transcript, (comments, comments_status) = await asyncio.gather(
        fetch_transcript(video.video_id), client.top_comments(video.video_id)
    )
    if evidence is None:  # another process (e.g. prewarm) may have inserted it meanwhile
        evidence = session.scalar(
            select(Evidence).where(Evidence.platform == YOUTUBE, Evidence.video_id == video.video_id)
        ) or Evidence(platform=YOUTUBE, video_id=video.video_id)
    if transcript:
        evidence.transcript, evidence.transcript_language = transcript
        evidence.transcript_source = "captions"
    else:
        description = (video.raw_json or {}).get("snippet", {}).get("description", "")
        evidence.transcript = f"{video.title}\n\n{description}".strip()
        evidence.transcript_language = video.language
        evidence.transcript_source = "title_description"
    evidence.top_comments_json = comments
    evidence.comments_status = comments_status
    evidence.fetched_at = utcnow()
    session.add(evidence)
    session.commit()
    return evidence


async def collect_youtube_evidence(
    session: Session, video_ids: list[str], client: YouTubeClient | None = None, concurrency: int = 4
) -> None:
    client = client or YouTubeClient()
    videos = session.scalars(select(Video).where(Video.platform == YOUTUBE, Video.video_id.in_(video_ids))).all()
    sem = asyncio.Semaphore(concurrency)

    async def one(video: Video) -> None:
        async with sem:
            try:
                await ensure_youtube_evidence(session, video, client)
            except Exception as exc:
                log.warning("evidence collection failed for %s: %s", video.video_id, exc)

    await asyncio.gather(*(one(v) for v in videos))


def evidence_summary(session: Session, platform: str, video_ids: list[str]) -> dict[str, dict]:
    rows = session.scalars(
        select(Evidence).where(Evidence.platform == platform, Evidence.video_id.in_(video_ids))
    ).all()
    return {
        e.video_id: {
            "transcript_source": e.transcript_source,
            "transcript_language": e.transcript_language,
            "comments": len(e.top_comments_json or []),
            "comments_status": e.comments_status,
        }
        for e in rows
    }


def video_item(session: Session, platform: str, video_id: str) -> tuple[Video, dict] | None:
    """The video with stats/metrics from its most recent snapshot."""
    video = session.scalar(select(Video).where(Video.platform == platform, Video.video_id == video_id))
    if video is None:
        return None
    snap = session.scalar(
        select(VideoSnapshot).where(VideoSnapshot.video_id == video.id).order_by(VideoSnapshot.captured_at.desc())
    )
    if snap is None:
        return None
    return video, _serialize(video, snap, as_utc(snap.captured_at))
