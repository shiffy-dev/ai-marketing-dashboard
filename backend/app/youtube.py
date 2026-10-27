"""Thin async client for the YouTube Data API v3 plus transcript fetching."""

import asyncio
import logging
import re
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


_DURATION_RE = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")


def parse_duration(value: str | None) -> int | None:
    """ISO-8601 duration (e.g. PT4M13S) to seconds."""
    if not value or not (m := _DURATION_RE.match(value)):
        return None
    days, hours, minutes, seconds = (int(g) if g else 0 for g in m.groups())
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


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

    async def chart(self, region: str = MARKET.country, category_id: str | None = None, pages: int = 4) -> list[dict]:
        """Full mostPopular chart (up to 200 videos), optionally for one category. 1 quota unit per page."""
        params = {
            "chart": "mostPopular",
            "regionCode": region,
            "part": "snippet,statistics,contentDetails",
            "maxResults": 50,
        }
        if category_id:
            params["videoCategoryId"] = category_id
        items: list[dict] = []
        async with self._client() as client:
            for _ in range(pages):
                data = await self._get(client, "videos", params)
                items += data.get("items", [])
                if not (token := data.get("nextPageToken")):
                    break
                params = {**params, "pageToken": token}
        return items

    async def search_short_ids(
        self, region: str = MARKET.country, published_after: datetime | None = None, pages: int | None = None
    ) -> list[str]:
        """Most-viewed recent videos under 4 minutes in the region (the API's narrowest duration filter)."""
        params = {
            "part": "id",
            "type": "video",
            "videoDuration": "short",
            "order": "viewCount",
            "regionCode": region,
            "maxResults": 50,
        }
        if published_after:
            params["publishedAfter"] = published_after.strftime("%Y-%m-%dT%H:%M:%SZ")
        ids: list[str] = []
        async with self._client() as client:
            for _ in range(pages or settings.shorts_search_pages):
                data = await self._get(client, "search", params)
                ids += [i["id"]["videoId"] for i in data.get("items", []) if i.get("id", {}).get("videoId")]
                if not (token := data.get("nextPageToken")):
                    break
                params = {**params, "pageToken": token}
        return list(dict.fromkeys(ids))

    async def video_details(self, video_ids: list[str]) -> list[dict]:
        """Fetch snippet/statistics/contentDetails for specific video IDs."""
        items: list[dict] = []
        async with self._client() as client:
            for i in range(0, len(video_ids), 50):
                data = await self._get(
                    client,
                    "videos",
                    {
                        "part": "snippet,statistics,contentDetails",
                        "id": ",".join(video_ids[i : i + 50]),
                        "maxResults": 50,
                    },
                )
                items += data.get("items", [])
        return items

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
