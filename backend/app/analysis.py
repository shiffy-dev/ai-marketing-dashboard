"""Evidence-based "why is this trending" analysis with Claude."""

import asyncio
import base64
import json
import logging
import mimetypes
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from anthropic import APIConnectionError, APIStatusError, AsyncAnthropic
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import DATA_DIR, MARKET, settings
from .models import Analysis, Evidence, Video
from .schemas import AnalysisResult
from .trending import YOUTUBE, ensure_youtube_evidence, video_item
from .uae_calendar import calendar_context

log = logging.getLogger(__name__)

PROMPT_VERSION = "v1"
MAX_TRANSCRIPT_CHARS = 8_000
MAX_DESCRIPTION_CHARS = 2_000
MAX_IMAGES = 6
REAL_TRANSCRIPT_SOURCES = {"captions", "dataset"}

HOOK_TECHNIQUES = [
    "curiosity gap",
    "bold claim",
    "question",
    "pattern interrupt",
    "visual shock",
    "pain point",
    "transformation preview",
    "social proof",
    "challenge",
    "humor",
    "celebrity/creator face",
    "countdown/list",
    "direct address",
    "trend/audio reference",
    "emotional moment",
    "news/announcement",
]
CTA_TYPES = ["subscribe/follow", "comment prompt", "share", "link/shop", "watch next", "save", "none/implicit"]
FORMAT_TAGS = [
    "talking head",
    "vlog",
    "tutorial",
    "review",
    "unboxing",
    "comedy sketch",
    "reaction",
    "challenge",
    "storytime",
    "music video",
    "trailer",
    "highlights",
    "news",
    "interview",
    "listicle",
    "behind the scenes",
    "UGC style",
    "short-form",
    "long-form",
    "ad/sponsored",
    "Arabic",
    "English",
    "Hindi/Urdu",
    "code-switching",
]

SYSTEM_PROMPT = f"""You are a senior performance-marketing strategist for ecommerce brands in the {MARKET.name}.
You explain, with evidence, why a specific short-form or YouTube video is trending in the {MARKET.name}.

Rules:
- Every claim must cite a specific signal from the evidence: a stat or computed metric, a transcript quote,
  a viewer comment, an observation from the thumbnail/frames, a reviewer note, or the date / a calendar event /
  a trending search. Put that signal in the driver's "evidence" field (quote text verbatim, cite numbers exactly).
  No generic statements such as "high-quality content" or "engaging video".
- Explain in marketing terms: hook technique, retention mechanics, format, audience fit, trend/audio/event riding,
  and distribution factors (channel size vs. views via outlier_ratio, velocity, posting timing).
- "drivers": the top 3 drivers ranked by likely impact (most impactful first), each with its own confidence.
- "unknowns": what cannot be known from this data (e.g. paid promotion, retention curves, traffic sources, audience
  demographics, algorithmic boosts).
- Detect the spoken/written language, including Arabic dialect (e.g. Emirati/Gulf, Egyptian, Levantine, MSA) and
  code-switching (e.g. Arabic-English). Put this in "language". Write the analysis itself in English.
- If transcript_source is not "captions"/"dataset" there is no real transcript: say so in "unknowns", avoid claims
  about spoken content, and set overall "confidence" to "low".
- "takeaways": 2-3 specific, actionable takeaways for a {MARKET.name} ecommerce marketing team.
- hook.technique: pick the closest from {json.dumps(HOOK_TECHNIQUES)} (lowercase).
- cta.type: pick from {json.dumps(CTA_TYPES)}. If there is no explicit CTA, use "none/implicit" and describe the
  implicit one in cta.text.
- format_tags: 2-5 tags, preferably from {json.dumps(FORMAT_TAGS)}.

Respond with ONLY a JSON object (no markdown fences, no commentary) matching exactly:
{{
  "language": "",
  "hook": {{"text": "", "technique": ""}},
  "body": {{"structure": "", "key_beats": []}},
  "cta": {{"text": "", "type": ""}},
  "why_trending": {{
    "summary": "",
    "drivers": [
      {{"type": "content|distribution|context", "claim": "", "evidence": "", "confidence": "high|medium|low"}}
    ],
    "unknowns": [],
    "takeaways": []
  }},
  "format_tags": [],
  "confidence": "high|medium|low"
}}"""


class AnalysisError(RuntimeError):
    pass


_semaphore = asyncio.Semaphore(5)
_locks: dict[str, asyncio.Lock] = {}
_client: AsyncAnthropic | None = None


def anthropic_client() -> AsyncAnthropic:
    global _client
    if not settings.anthropic_api_key:
        raise AnalysisError("ANTHROPIC_API_KEY is not set")
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


def load_uae_trends() -> dict | list | None:
    path = DATA_DIR / "uae_trends.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("ignoring unreadable %s: %s", path, exc)
        return None


async def load_image(ref: str, http: httpx.AsyncClient) -> dict | None:
    """Anthropic image block from a URL or a path relative to data/."""
    try:
        if ref.startswith(("http://", "https://")):
            resp = await http.get(ref)
            resp.raise_for_status()
            data, media_type = resp.content, resp.headers.get("content-type", "image/jpeg").split(";")[0]
        else:
            path = (DATA_DIR / ref.removeprefix("/static/").lstrip("/")).resolve()
            if DATA_DIR.resolve() not in path.parents:
                return None
            data, media_type = path.read_bytes(), mimetypes.guess_type(path.name)[0] or "image/jpeg"
    except (httpx.HTTPError, OSError) as exc:
        log.info("image unavailable %s: %s", ref, exc)
        return None
    if media_type not in {"image/jpeg", "image/png", "image/gif", "image/webp"}:
        return None
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": base64.b64encode(data).decode()},
    }


def has_real_transcript(evidence: Evidence | None) -> bool:
    return bool(evidence and evidence.transcript and evidence.transcript_source in REAL_TRANSCRIPT_SOURCES)


def build_evidence(video: Video, item: dict, evidence: Evidence | None, today: datetime) -> dict:
    raw = video.raw_json or {}
    snippet = raw.get("snippet", {})
    payload = {
        "platform": video.platform,
        "market": MARKET.country,
        "today": today.strftime("%A %Y-%m-%d %H:%M %Z"),
        "url": item.get("url"),
        "title": video.title,
        "channel_or_account": video.channel,
        "channel_subscribers_or_followers": video.followers_or_subs,
        "published_at": item.get("published_at"),
        "category": item.get("category"),
        "duration": item.get("duration"),
        "declared_language": video.language,
        "stats": {"views_or_plays": item["views"], "likes": item["likes"], "comments": item["comments"]},
        "computed_metrics": item["metrics"],
        "rank_in_uae_top10": item.get("rank"),
        "youtube_chart_position": item.get("chart_rank") if video.platform == YOUTUBE else None,
        "description_or_caption": (snippet.get("description") or raw.get("caption") or "")[:MAX_DESCRIPTION_CHARS],
        "tags_or_hashtags": snippet.get("tags") or raw.get("hashtags") or [],
        "audio": raw.get("audio"),
        "reviewer_notes": raw.get("reviewer_notes"),
        "transcript_source": evidence.transcript_source if evidence else None,
        "transcript_language": evidence.transcript_language if evidence else None,
        "transcript": (evidence.transcript or "")[:MAX_TRANSCRIPT_CHARS] if has_real_transcript(evidence) else None,
        "top_comments": [c["text"] for c in (evidence.top_comments_json or [])] if evidence else [],
        "comments_status": evidence.comments_status if evidence else None,
        "uae_calendar_context": calendar_context(today.date()),
    }
    trends = load_uae_trends()
    if trends is not None:
        payload["uae_trending_searches_today"] = trends
    return {k: v for k, v in payload.items() if v not in (None, [], "")}


def image_refs(video: Video) -> list[str]:
    raw = video.raw_json or {}
    refs = [video.thumbnail] if video.thumbnail else []
    refs += raw.get("frames") or []
    return refs[:MAX_IMAGES]


def parse_result(text: str) -> AnalysisResult:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found in response")
    return AnalysisResult.model_validate(json.loads(text[start : end + 1]))


def api_error_message(exc: APIStatusError) -> str:
    body = exc.body if isinstance(exc.body, dict) else {}
    error = body.get("error") if isinstance(body.get("error"), dict) else body
    return str(error.get("message") or exc.message)


async def call_llm(client: AsyncAnthropic, evidence: dict, images: list[dict]) -> AnalysisResult:
    labels = ["thumbnail"] + [f"frame {i}" for i in range(1, len(images))]
    intro = f"Images attached in order: {', '.join(labels[: len(images)])}." if images else "No images available."
    content = [
        *images,
        {"type": "text", "text": f"{intro}\n\nEvidence (JSON):\n{json.dumps(evidence, ensure_ascii=False, indent=1)}"},
    ]
    messages: list[dict] = [{"role": "user", "content": content}]
    last_error: Exception | None = None
    for _attempt in range(2):
        try:
            resp = await client.messages.create(
                model=settings.llm_model, max_tokens=4096, system=SYSTEM_PROMPT, messages=messages
            )
        except APIStatusError as exc:
            raise AnalysisError(f"Anthropic API error ({exc.status_code}): {api_error_message(exc)}") from exc
        except APIConnectionError as exc:
            raise AnalysisError(f"Could not reach the Anthropic API: {exc}") from exc
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        try:
            return parse_result(text)
        except (ValueError, ValidationError) as exc:
            last_error = exc
            log.warning("analysis JSON invalid, retrying once: %s", str(exc)[:300])
            messages += [
                {"role": "assistant", "content": text or "(empty)"},
                {
                    "role": "user",
                    "content": f"That response was not valid against the schema: {str(exc)[:1000]}\n"
                    "Return ONLY the corrected JSON object.",
                },
            ]
    raise AnalysisError(f"model returned invalid JSON twice: {last_error}")


def cached_analysis(session: Session, platform: str, video_id: str) -> Analysis | None:
    return session.scalar(
        select(Analysis)
        .where(Analysis.platform == platform, Analysis.video_id == video_id, Analysis.prompt_version == PROMPT_VERSION)
        .order_by(Analysis.created_at.desc())
    )


def serialize_analysis(row: Analysis, cached: bool) -> dict:
    return {
        "platform": row.platform,
        "video_id": row.video_id,
        "model": row.model,
        "prompt_version": row.prompt_version,
        "created_at": row.created_at.isoformat(),
        "cached": cached,
        "analysis": row.result_json,
    }


async def get_or_create_analysis(
    session: Session, platform: str, video_id: str, client: AsyncAnthropic | None = None, force: bool = False
) -> tuple[Analysis, bool]:
    """Returns (analysis_row, was_cached). Cached by platform:video_id."""
    key = f"{platform}:{video_id}"
    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        if not force and (row := cached_analysis(session, platform, video_id)):
            return row, True

        found = video_item(session, platform, video_id)
        if found is None:
            raise LookupError(key)
        video, item = found

        evidence = session.scalar(select(Evidence).where(Evidence.platform == platform, Evidence.video_id == video_id))
        session.commit()  # end the read transaction before the slow network/LLM awaits
        if platform == YOUTUBE:
            try:
                evidence = await ensure_youtube_evidence(session, video)
            except Exception as exc:  # offline: use whatever evidence is stored
                session.rollback()
                log.warning("could not refresh evidence for %s: %s", key, exc)

        client = client or anthropic_client()
        today = datetime.now(ZoneInfo(MARKET.timezone))
        payload = build_evidence(video, item, evidence, today)
        async with httpx.AsyncClient(timeout=15) as http:
            images = [b for b in await asyncio.gather(*(load_image(r, http) for r in image_refs(video))) if b]

        async with _semaphore:
            result = await call_llm(client, payload, images)

        if not has_real_transcript(evidence):
            result.confidence = "low"
            note = "No transcript was available; spoken content was inferred from title, description and comments."
            if note not in result.why_trending.unknowns:
                result.why_trending.unknowns.insert(0, note)

        row = Analysis(
            platform=platform,
            video_id=video_id,
            model=settings.llm_model,
            prompt_version=PROMPT_VERSION,
            result_json=result.model_dump(),
            confidence=result.confidence,
        )
        session.add(row)
        session.commit()
        return row, False


def analyses_for(session: Session, platform: str, video_ids: list[str]) -> dict[str, Analysis]:
    rows = session.scalars(
        select(Analysis)
        .where(
            Analysis.platform == platform,
            Analysis.video_id.in_(video_ids),
            Analysis.prompt_version == PROMPT_VERSION,
        )
        .order_by(Analysis.created_at)
    ).all()
    return {r.video_id: r for r in rows}  # latest wins


def aggregate(rows: list[Analysis]) -> dict:
    hooks: dict[str, int] = {}
    tags: dict[str, int] = {}
    for row in rows:
        technique = (row.result_json.get("hook", {}).get("technique") or "").strip().lower()
        if technique:
            hooks[technique] = hooks.get(technique, 0) + 1
        for tag in {t.strip().lower() for t in row.result_json.get("format_tags", []) if t.strip()}:
            tags[tag] = tags.get(tag, 0) + 1

    def ranked(counts: dict[str, int]) -> list[dict]:
        return [{"label": k, "count": v} for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]

    return {"hook_techniques": ranked(hooks), "format_tags": ranked(tags)}
