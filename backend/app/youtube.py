"""Thin async client for the YouTube Data API v3 plus transcript fetching."""

import asyncio
import logging
from datetime import datetime

import httpx
from youtube_transcript_api import YouTubeTranscriptApi, YouTubeTranscriptApiException

from .config import MARKET, settings

log = logging.getLogger(__name__)

API_BASE = "https://www.googleapis.com/youtube/v3"
MAX_TRANSCRIPT_CHARS = 20_000


class YouTubeError(RuntimeError):
    pass


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def best_thumbnail(thumbnails: dict) -> str | None:
    for key in ("maxres", "standard", "high", "medium", "default"):
        if key in thumbnails:
            return thumbnails[key]["url"]
    return None


def _to_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class YouTubeClient:
    def __init__(self, api_key: str | None = None, transport: httpx.AsyncBaseTransport | None = None):
        self.api_key = api_key if api_key is not None else settings.youtube_api_key
        self._transport = transport

    async def _get(self, client: httpx.AsyncClient, path: str, params: dict) -> dict:
        if not self.api_key:
            raise YouTubeError("YOUTUBE_API_KEY is not set")
        # Key goes in a header so it never appears in URLs or logs.
        resp = await client.get(f"{API_BASE}/{path}", params=params, headers={"X-Goog-Api-Key": self.api_key})
        if resp.status_code != 200:
            try:
                err = resp.json().get("error", {})
                reason = (err.get("errors") or [{}])[0].get("reason", "")
                message = err.get("message", "")
            except ValueError:
                reason, message = "", resp.text[:200]
            raise YouTubeError(f"{path} failed ({resp.status_code} {reason}): {message}".strip())
        return resp.json()

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=20, transport=self._transport)

    async def most_popular(self, region: str = MARKET.country, max_results: int | None = None) -> list[dict]:
        async with self._client() as client:
            data = await self._get(
                client,
                "videos",
                {
                    "chart": "mostPopular",
                    "regionCode": region,
                    "part": "snippet,statistics,contentDetails",
                    "maxResults": max_results or settings.youtube_max_results,
                },
            )
        return data.get("items", [])

    async def channel_subscribers(self, channel_ids: list[str]) -> dict[str, int | None]:
        result: dict[str, int | None] = {}
        ids = list(dict.fromkeys(channel_ids))
        async with self._client() as client:
            for i in range(0, len(ids), 50):
                data = await self._get(
                    client, "channels", {"part": "statistics", "id": ",".join(ids[i : i + 50]), "maxResults": 50}
                )
                for item in data.get("items", []):
                    stats = item.get("statistics", {})
                    hidden = stats.get("hiddenSubscriberCount")
                    result[item["id"]] = None if hidden else _to_int(stats.get("subscriberCount"))
        return result

    async def top_comments(self, video_id: str, limit: int | None = None) -> tuple[list[dict], str]:
        """Returns (comments, status). Only comment text and like count are kept."""
        async with self._client() as client:
            try:
                data = await self._get(
                    client,
                    "commentThreads",
                    {
                        "part": "snippet",
                        "videoId": video_id,
                        "maxResults": limit or settings.top_comments,
                        "order": "relevance",
                        "textFormat": "plainText",
                    },
                )
            except YouTubeError as exc:
                if "commentsDisabled" in str(exc):
                    return [], "disabled"
                log.warning("comments unavailable for %s: %s", video_id, exc)
                return [], "error"
        comments = []
        for item in data.get("items", []):
            top = item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
            text = (top.get("textOriginal") or top.get("textDisplay") or "").strip()
            if text:
                comments.append({"text": text, "likes": _to_int(top.get("likeCount")) or 0})
        return comments, "ok"


def _fetch_transcript_sync(video_id: str, languages: tuple[str, ...]) -> tuple[str, str] | None:
    api = YouTubeTranscriptApi()
    try:
        transcripts = api.list(video_id)
        try:
            transcript = transcripts.find_transcript(list(languages))
        except YouTubeTranscriptApiException:
            available = list(transcripts)
            if not available:
                return None
            transcript = available[0]
            if transcript.language_code not in languages and transcript.is_translatable:
                transcript = transcript.translate("en")
        fetched = transcript.fetch()
    except YouTubeTranscriptApiException as exc:
        log.info("no transcript for %s: %s", video_id, type(exc).__name__)
        return None
    text = " ".join(s.text.replace("\n", " ") for s in fetched.snippets).strip()
    if not text:
        return None
    return text[:MAX_TRANSCRIPT_CHARS], fetched.language_code


async def fetch_transcript(video_id: str, languages: tuple[str, ...] = MARKET.languages) -> tuple[str, str] | None:
    """Returns (text, language_code) or None when no captions are available."""
    try:
        return await asyncio.to_thread(_fetch_transcript_sync, video_id, languages)
    except Exception as exc:  # network errors etc. must never break a refresh
        log.warning("transcript fetch failed for %s: %s", video_id, exc)
        return None
