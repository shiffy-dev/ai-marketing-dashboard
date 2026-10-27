"""Live Instagram Reels via Apify.

Re-runs the actor (and input) of the account's most recent Apify run, or
APIFY_ACTOR when set, capped at APIFY_MAX_ITEMS results so it stays inside
Apify's free monthly credit. Results are converted to the app dataset format,
written to data/instagram_reels.json and loaded into the DB.
"""

import json
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from .config import DATA_DIR, settings
from .instagram import DATASET_FILE, load_instagram_dataset

log = logging.getLogger(__name__)

API_BASE = "https://api.apify.com/v2"
RAW_FILE = DATA_DIR / "raw_apify_reels.json"
THUMB_DIR = DATA_DIR / "static" / "reels"


class ApifyError(RuntimeError):
    pass


def _audio_label(audio: dict | None) -> str | None:
    if not audio:
        return None
    title, artist = audio.get("title"), audio.get("artist")
    return f"{title} — {artist}" if title and artist and artist != title else title or artist


def _download_thumbnail(item: dict, http: httpx.Client) -> str | None:
    # Instagram CDN URLs expire, so keep a local copy when possible.
    url = (item.get("image") or {}).get("url")
    if not url:
        return None
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
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


def build_dataset(items: list[dict], scraped_at: datetime) -> dict:
    items = [i for i in items if i.get("id") and (i.get("isVideo") or i.get("video"))]
    sources = {(i.get("source") or {}).get("input") for i in items}
    with httpx.Client(timeout=30, follow_redirects=True) as http:
        reels = [to_reel(i, http) for i in items]
    return {
        "scraped_at": scraped_at.isoformat(),
        "source": "apify",
        "source_urls": sorted(s for s in sources if s),
        "reels": reels,
    }


def _check(resp: httpx.Response, what: str) -> httpx.Response:
    if resp.status_code >= 400:
        try:
            message = resp.json().get("error", {}).get("message", "")
        except ValueError:
            message = resp.text[:200]
        raise ApifyError(f"Apify {what} failed ({resp.status_code}): {message}".strip())
    return resp


async def _actor_and_input(client: httpx.AsyncClient) -> tuple[str, dict]:
    """Actor + input of the most recent run, so a refresh repeats what the user already set up."""
    runs = _check(await client.get("/actor-runs", params={"desc": 1, "limit": 1}), "listing runs").json()
    last = next(iter(runs.get("data", {}).get("items", [])), None)
    if settings.apify_actor:
        actor = settings.apify_actor
        if last is None or last.get("actId") != actor:
            return actor, {}
    elif last is None:
        raise ApifyError("No previous Apify run found. Run your Instagram actor once in the Apify console.")
    else:
        actor = last["actId"]
    run = _check(await client.get(f"/actor-runs/{last['id']}"), "reading last run").json()["data"]
    store = run.get("defaultKeyValueStoreId")
    resp = await client.get(f"/key-value-stores/{store}/records/INPUT")
    return actor, resp.json() if resp.status_code == 200 else {}


async def fetch_reels(transport: httpx.AsyncBaseTransport | None = None) -> list[dict]:
    if not settings.apify_token:
        raise ApifyError("APIFY_TOKEN is not set in .env")
    headers = {"Authorization": f"Bearer {settings.apify_token}"}
    async with httpx.AsyncClient(
        base_url=API_BASE, headers=headers, timeout=settings.apify_timeout_seconds + 30, transport=transport
    ) as client:
        actor, run_input = await _actor_and_input(client)
        log.info("running Apify actor %s (max %d items)", actor, settings.apify_max_items)
        resp = await client.post(
            f"/acts/{actor.replace('/', '~')}/run-sync-get-dataset-items",
            params={"maxItems": settings.apify_max_items, "timeout": settings.apify_timeout_seconds},
            json=run_input,
        )
        items = _check(resp, "actor run").json()
    if not isinstance(items, list):
        raise ApifyError("Apify returned an unexpected response")
    return items[: settings.apify_max_items]


async def refresh_instagram(session: Session, transport: httpx.AsyncBaseTransport | None = None) -> dict | None:
    session.commit()  # end any open read transaction before network awaits
    items = await fetch_reels(transport)
    if not items:
        raise ApifyError("Apify run returned no reels")
    dataset = build_dataset(items, datetime.now(timezone.utc))
    RAW_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    DATASET_FILE.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
    return load_instagram_dataset(session, DATASET_FILE)
