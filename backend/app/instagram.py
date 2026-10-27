"""Load the static Instagram Reels dataset into the DB (idempotent upsert).

Reads data/instagram_reels.json. When that file is missing, falls back to
data/seed_reels.json — clearly-labeled sample data so the Instagram view is
never empty. Dataset-level meta (scraped_at, source, sample) is stored in
dataset_meta and surfaced in the trending payload.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import DATA_DIR
from .models import DatasetMeta, Evidence, Video, VideoSnapshot, utcnow
from .trending import INSTAGRAM

log = logging.getLogger(__name__)

DATASET_FILE = DATA_DIR / "instagram_reels.json"
SEED_FILE = DATA_DIR / "seed_reels.json"


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def get_dataset_meta(session: Session, platform: str = INSTAGRAM) -> dict | None:
    row = session.get(DatasetMeta, platform)
    return row.value_json if row else None


def _snapshot_stats(reel: dict) -> tuple[int, int | None, int | None]:
    plays = int(reel.get("plays") or 0)
    likes = int(reel["likes"]) if reel.get("likes") is not None else None
    comments = int(reel["comments"]) if reel.get("comments") is not None else None
    return plays, likes, comments


def load_instagram_dataset(session: Session, path: Path | None = None) -> dict | None:
    """Upsert reels into videos/snapshots/evidence. Safe to run on every startup:
    videos and evidence are upserted, and a new snapshot is only added when the
    stats changed since the last stored one."""
    path = path or (DATASET_FILE if DATASET_FILE.exists() else SEED_FILE)
    if not path.exists():
        log.warning("no instagram dataset found (%s or %s missing)", DATASET_FILE.name, SEED_FILE.name)
        return None
    sample = path == SEED_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("unreadable instagram dataset %s: %s", path, exc)
        return None

    reels = data.get("reels") or []
    scraped_at = _parse_ts(data.get("scraped_at")) or utcnow()
    meta = {
        "scraped_at": scraped_at.isoformat(),
        "source": data.get("source") or path.stem,
        "sample": sample,
        "file": path.name,
        "reel_count": len(reels),
    }

    existing = (
        {
            v.video_id: v
            for v in session.scalars(
                select(Video).where(Video.platform == INSTAGRAM, Video.video_id.in_([r["id"] for r in reels]))
            )
        }
        if reels
        else {}
    )

    for rank, reel in enumerate(reels, start=1):
        video = existing.get(reel["id"]) or Video(platform=INSTAGRAM, video_id=reel["id"])
        caption = (reel.get("caption") or "").strip()
        video.title = caption.split("\n")[0][:140] if caption else f"Reel by @{reel.get('account', '?')}"
        video.channel = reel.get("account") or ""
        video.channel_id = None
        video.followers_or_subs = reel.get("followers")
        video.published_at = _parse_ts(reel.get("posted_at"))
        video.thumbnail = reel.get("thumbnail")
        video.category_id = None
        video.language = reel.get("transcript_language")
        video.raw_json = reel
        video.fetched_at = scraped_at
        session.add(video)
        session.flush()

        plays, likes, comments = _snapshot_stats(reel)
        latest = session.scalar(
            select(VideoSnapshot)
            .where(VideoSnapshot.video_id == video.id)
            .order_by(VideoSnapshot.captured_at.desc())
            .limit(1)
        )
        if latest is None or (latest.views, latest.likes, latest.comments) != (plays, likes, comments):
            session.add(
                VideoSnapshot(
                    video_id=video.id,
                    platform=INSTAGRAM,
                    captured_at=scraped_at,
                    views=plays,
                    likes=likes,
                    comments=comments,
                    rank=rank,
                )
            )

        evidence = session.scalar(
            select(Evidence).where(Evidence.platform == INSTAGRAM, Evidence.video_id == reel["id"])
        ) or Evidence(platform=INSTAGRAM, video_id=reel["id"])
        transcript = (reel.get("transcript") or "").strip() or None
        evidence.transcript = transcript
        evidence.transcript_source = "dataset" if transcript else None
        evidence.transcript_language = reel.get("transcript_language") if transcript else None
        evidence.top_comments_json = [
            {"text": c["text"], "likes": int(c.get("likes") or 0)}
            for c in (reel.get("top_comments") or [])
            if c.get("text")
        ]
        evidence.comments_status = "disabled" if reel.get("comments_disabled") else "ok"
        evidence.fetched_at = scraped_at
        session.add(evidence)

    meta_row = session.get(DatasetMeta, INSTAGRAM) or DatasetMeta(key=INSTAGRAM)
    meta_row.value_json = meta
    meta_row.updated_at = utcnow()
    session.add(meta_row)
    session.commit()
    log.info("instagram dataset loaded: %d reels from %s (sample=%s)", len(reels), path.name, sample)
    return meta
