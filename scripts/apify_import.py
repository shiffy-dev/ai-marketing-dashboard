"""Convert an Apify Instagram Reels export into the app dataset.

Reads   data/raw_apify_reels.json
Writes  data/instagram_reels.json   (the file the app loads on startup)
        data/static/reels/<id>.jpg  (downloaded thumbnails, best effort)

Usage (from the repo root):  python scripts/apify_import.py
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
RAW_FILE = ROOT / "data" / "raw_apify_reels.json"
OUT_FILE = ROOT / "data" / "instagram_reels.json"
THUMB_DIR = ROOT / "data" / "static" / "reels"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("apify_import")


def _audio_label(audio: dict | None) -> str | None:
    if not audio:
        return None
    title, artist = audio.get("title"), audio.get("artist")
    return f"{title} — {artist}" if title and artist and artist != title else title or artist


def _download_thumbnail(item: dict, http: httpx.Client) -> str | None:
    url = (item.get("image") or {}).get("url")
    if not url:
        return None
    path = THUMB_DIR / f"{item['id']}.jpg"
    try:
        resp = http.get(url)
        resp.raise_for_status()
        path.write_bytes(resp.content)
        return f"/static/reels/{path.name}"
    except httpx.HTTPError as exc:
        log.warning("thumbnail download failed for %s (%s); keeping remote URL", item["id"], exc)
        return url


def to_reel(item: dict, http: httpx.Client) -> dict:
    owner = item.get("owner") or {}
    video = item.get("video") or {}
    return {
        "id": item["id"],
        "url": item.get("url"),
        "account": owner.get("username") or owner.get("fullName") or "",
        "followers": owner.get("followerCount"),
        "caption": item.get("caption") or "",
        "hashtags": item.get("hashtags") or [],
        "audio": _audio_label(item.get("audio")),
        "plays": video.get("playCount"),
        "likes": item.get("likeCount"),
        "comments": item.get("commentCount"),
        "comments_disabled": bool(item.get("commentsDisabled")),
        "posted_at": item.get("createdAt"),
        "top_comments": [],
        "transcript": item.get("transcript") or "",
        "transcript_language": item.get("transcriptLanguage"),
        "duration_seconds": video.get("duration"),
        "frames": [],
        "thumbnail": _download_thumbnail(item, http),
        "reviewer_notes": "",
    }


def main() -> None:
    items = json.loads(RAW_FILE.read_text(encoding="utf-8"))
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    scraped_at = datetime.fromtimestamp(RAW_FILE.stat().st_mtime, tz=timezone.utc).isoformat()
    sources = {((i.get("source") or {}).get("input")) for i in items}
    with httpx.Client(timeout=30, follow_redirects=True) as http:
        reels = [to_reel(i, http) for i in items]
    dataset = {
        "scraped_at": scraped_at,
        "source": "apify",
        "source_urls": sorted(s for s in sources if s),
        "reels": reels,
    }
    OUT_FILE.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("wrote %d reels -> %s", len(reels), OUT_FILE)


if __name__ == "__main__":
    main()
