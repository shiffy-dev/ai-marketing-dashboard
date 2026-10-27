"""Evidence-based "why is this trending" analysis via the Claude Code CLI (subscription)."""

import asyncio
import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import DATA_DIR, MARKET, settings
from .models import Analysis, Evidence, Video
from .schemas import AnalysisResult
from .trending import YOUTUBE, ensure_youtube_evidence, fetch_youtube_video, video_item
from .uae_calendar import calendar_context
from .youtube import YouTubeClient

log = logging.getLogger(__name__)

PROMPT_VERSION = "v2"
MAX_TRANSCRIPT_CHARS = 3_000
MAX_DESCRIPTION_CHARS = 1_000
MAX_COMMENTS = 10
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


class VideoNotFoundError(Exception):
    """The video is unknown to us and could not be fetched from its platform API."""


# One CLI session at a time.
_semaphore = asyncio.Semaphore(1)
_locks: dict[str, asyncio.Lock] = {}

MOCK_ANALYSIS = {
    "language": "English with Gulf Arabic phrases",
    "hook": {"text": "POV: your parcel arrives the same day in Dubai", "technique": "direct address"},
    "body": {
        "structure": "relatable problem -> product demo -> price reveal",
        "key_beats": ["pain point in the first 2 seconds", "quick demo sequence", "price/reveal at the end"],
    },
    "cta": {"text": "Link in bio", "type": "link/shop"},
    "why_trending": {
        "summary": "Mock analysis: a direct-address hook plus an outlier view-to-follower ratio suggests "
        "distribution well beyond the account's own audience.",
        "drivers": [
            {
                "type": "content",
                "claim": "Direct-address hook in the first seconds retains viewers",
                "evidence": "hook text: 'POV: your parcel arrives the same day in Dubai'",
                "confidence": "medium",
            },
            {
                "type": "distribution",
                "claim": "Views far exceed the channel's follower base",
                "evidence": "outlier_ratio is high relative to the account's audience size",
                "confidence": "medium",
            },
            {
                "type": "context",
                "claim": "UAE-relevant content rides local purchase intent",
                "evidence": "market AE; video appeared in today's UAE trending chart",
                "confidence": "low",
            },
        ],
        "unknowns": ["paid promotion", "traffic sources", "audience demographics"],
        "takeaways": [
            "Lead with the customer problem in the first 2 seconds",
            "Test direct-address POV hooks for UAE product videos",
        ],
    },
    "format_tags": ["UGC style", "short-form"],
    "confidence": "medium",
}


INSTALL_HINT = (
    "Install Claude Code (`npm install -g @anthropic-ai/claude-code`), run `claude` once "
    "to log in with your Claude subscription, then retry."
)
# Env vars that would make the CLI bill an API key instead of the subscription.
_STRIPPED_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX")


def _cli_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in _STRIPPED_ENV}


def _resolve_binary(binary: str) -> str:
    """Find the CLI executable. On Windows npm installs `claude.cmd`, which
    CreateProcess won't find by bare name and which would route our multi-line
    --system-prompt through cmd.exe; prefer the real claude.exe it wraps."""
    found = shutil.which(binary)
    if not found:
        return binary
    path = Path(found)
    if path.suffix.lower() in (".cmd", ".bat"):
        exe = path.parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
        if exe.is_file():
            return str(exe)
    return found


class ClaudeCLIProvider:
    """Headless Claude Code (`claude -p`) using the user's logged-in subscription.

    The prompt is passed on stdin; `--output-format json` wraps the reply as
    {"result": "...", "is_error": bool}. No API key is ever used."""

    def __init__(self, binary: str = "claude", model: str | None = None, timeout: int | None = None):
        self.binary = binary
        self.model = model
        self.timeout = timeout or settings.llm_timeout_seconds

    def _argv(self) -> list[str]:
        argv = [self.binary, "-p", "--output-format", "json", "--system-prompt", "{system}"]
        if self.model:
            argv += ["--model", self.model]
        return argv

    async def chat(self, *, system: str, messages: list[dict], format: dict | None = None) -> str:
        # Fold the conversation into one stdin prompt; -p is single-turn.
        prompt = "\n\n".join(
            (f"[previous reply]\n{m['content']}" if m["role"] == "assistant" else m["content"]) for m in messages
        )
        argv = [a.replace("{system}", system) for a in self._argv()]
        argv[0] = _resolve_binary(argv[0])
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=_cli_env(),
            )
        except FileNotFoundError as exc:
            raise AnalysisError(f"`{self.binary}` was not found on PATH. {INSTALL_HINT}") from exc
        try:
            out, err = await asyncio.wait_for(proc.communicate(prompt.encode("utf-8")), timeout=self.timeout)
        except asyncio.TimeoutError as exc:
            proc.kill()
            raise AnalysisError(f"Claude CLI timed out after {self.timeout}s") from exc

        stderr = err.decode("utf-8", "replace").strip()
        if proc.returncode != 0:
            lowered = stderr.lower()
            if "log in" in lowered or "login" in lowered or "not authenticated" in lowered or "unauthorized" in lowered:
                raise AnalysisError(f"Claude CLI is not logged in. Run `{self.binary}` and sign in. ({stderr[:200]})")
            raise AnalysisError(f"Claude CLI failed (exit {proc.returncode}): {stderr[:300] or out[:300]!s}")

        text = out.decode("utf-8", "replace")
        try:
            envelope = json.loads(text)
        except ValueError:
            return text  # older CLI builds print the raw reply
        if isinstance(envelope, dict):
            if envelope.get("is_error"):
                raise AnalysisError(f"Claude CLI error: {str(envelope.get('result') or '')[:300]}")
            return str(envelope.get("result") or "")
        return text


class MockProvider:
    """Deterministic offline analysis for tests and UI development (LLM_PROVIDER=mock)."""

    async def chat(self, *, system: str, messages: list[dict], format: dict | None = None) -> str:
        return json.dumps(MOCK_ANALYSIS)


def llm_provider() -> ClaudeCLIProvider | MockProvider:
    if settings.llm_provider == "mock":
        return MockProvider()
    if settings.llm_provider == "claude_cli":
        return ClaudeCLIProvider(settings.claude_cli_bin, settings.llm_model or None)
    raise AnalysisError(f"unknown LLM_PROVIDER {settings.llm_provider!r} (expected 'claude_cli' or 'mock')")


def load_uae_trends() -> dict | list | None:
    path = DATA_DIR / "uae_trends.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("ignoring unreadable %s: %s", path, exc)
        return None


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
        "top_comments": [c["text"] for c in (evidence.top_comments_json or [])[:MAX_COMMENTS]] if evidence else [],
        "comments_status": evidence.comments_status if evidence else None,
        "uae_calendar_context": calendar_context(today.date()),
    }
    trends = load_uae_trends()
    if trends is not None:
        payload["uae_trending_searches_today"] = trends
    return {k: v for k, v in payload.items() if v not in (None, [], "")}


def parse_result(text: str) -> AnalysisResult:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found in response")
    return AnalysisResult.model_validate(json.loads(text[start : end + 1]))


async def call_llm(provider: ClaudeCLIProvider | MockProvider, evidence: dict) -> AnalysisResult:
    messages: list[dict] = [
        {
            "role": "user",
            "content": f"Evidence (JSON):\n{json.dumps(evidence, ensure_ascii=False, indent=1)}\n\n"
            "Respond with ONLY the JSON object. No prose, no markdown fences.",
        }
    ]
    last_error: Exception | None = None
    for _attempt in range(2):
        text = await provider.chat(system=SYSTEM_PROMPT, messages=messages)
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
        "status": "ready",
        "model": row.model,
        "prompt_version": row.prompt_version,
        "created_at": row.created_at.isoformat(),
        "cached": cached,
        "analysis": row.result_json,
    }


async def get_or_create_analysis(
    session: Session,
    platform: str,
    video_id: str,
    llm: ClaudeCLIProvider | MockProvider | None = None,
    youtube: YouTubeClient | None = None,
    force: bool = False,
) -> tuple[Analysis, bool]:
    """Returns (analysis_row, was_cached). Cached by platform:video_id."""
    key = f"{platform}:{video_id}"
    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        if not force and (row := cached_analysis(session, platform, video_id)):
            return row, True

        found = video_item(session, platform, video_id)
        if found is None and platform == YOUTUBE:
            try:
                found = await fetch_youtube_video(session, video_id, youtube)
            except Exception as exc:
                session.rollback()
                log.warning("could not fetch %s from YouTube: %s", key, exc)
        if found is None:
            raise VideoNotFoundError(key)
        video, item = found

        evidence = session.scalar(select(Evidence).where(Evidence.platform == platform, Evidence.video_id == video_id))
        session.commit()  # end the read transaction before the slow network/LLM awaits
        if platform == YOUTUBE:
            try:
                evidence = await ensure_youtube_evidence(session, video)
            except Exception as exc:  # offline: use whatever evidence is stored
                session.rollback()
                log.warning("could not refresh evidence for %s: %s", key, exc)

        llm = llm or llm_provider()
        today = datetime.now(ZoneInfo(MARKET.timezone))
        payload = build_evidence(video, item, evidence, today)

        async with _semaphore:
            result = await call_llm(llm, payload)

        if not has_real_transcript(evidence):
            result.confidence = "low"
            note = "No transcript was available; spoken content was inferred from title, description and comments."
            if note not in result.why_trending.unknowns:
                result.why_trending.unknowns.insert(0, note)

        row = Analysis(
            platform=platform,
            video_id=video_id,
            model=f"{settings.llm_provider}:{settings.llm_model or 'default'}",
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
