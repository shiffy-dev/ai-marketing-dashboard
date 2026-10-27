import json
from datetime import date
from unittest.mock import patch

import pytest

from app import main
from app.models import Evidence
from app.uae_calendar import calendar_context

VALID = {
    "language": "Gulf Arabic with English code-switching",
    "hook": {"text": "You won't believe this price", "technique": "Curiosity Gap"},
    "body": {"structure": "problem -> demo -> reveal", "key_beats": ["unboxing", "price reveal"]},
    "cta": {"text": "Follow for part 2", "type": "subscribe/follow"},
    "why_trending": {
        "summary": "Small channel, huge reach.",
        "drivers": [
            {"type": "distribution", "claim": "Outlier reach", "evidence": "outlier_ratio 12.3", "confidence": "high"}
        ],
        "unknowns": ["Paid promotion"],
        "takeaways": ["Lead with the price", "Use Gulf dialect"],
    },
    "format_tags": ["Unboxing", "short-form"],
    "confidence": "high",
}


class FakeLLM:
    """Provider test double matching the ClaudeCLIProvider.chat interface."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    async def chat(self, *, system, messages, format=None):
        self.requests.append({"system": system, "messages": messages, "format": format})
        return self.responses.pop(0)


@pytest.fixture
def setup(fake):
    fake.client.get("/api/trending")
    yield fake


async def _stored_evidence(session, video):
    return session.query(Evidence).filter_by(video_id=video.video_id).one()


def _use(llm):
    main.app.dependency_overrides[main.llm_client] = lambda: llm


def _with_captions(video_id):
    from app import db

    with db.SessionLocal() as s:
        ev = s.query(Evidence).filter_by(video_id=video_id).one()
        ev.transcript, ev.transcript_source, ev.transcript_language = "Hello habibi, check this out", "captions", "en"
        s.commit()


def test_analysis_pending_does_not_generate(setup):
    llm = FakeLLM([json.dumps(VALID)])
    _use(llm)
    resp = setup.client.get("/api/analysis/youtube/vid13")
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending" and resp.json()["analysis"] is None
    assert llm.requests == []


def test_analysis_generated_cached_and_listed(setup):
    _with_captions("vid13")
    llm = FakeLLM([json.dumps(VALID)])
    _use(llm)
    with patch("app.analysis.ensure_youtube_evidence", side_effect=_stored_evidence):
        first = setup.client.post("/api/analysis/youtube/vid13").json()
        second = setup.client.get("/api/analysis/youtube/vid13").json()
    assert first["cached"] is False and first["status"] == "ready"
    assert second["cached"] is True
    assert len(llm.requests) == 1
    assert first["analysis"]["confidence"] == "high"
    assert first["analysis"]["why_trending"]["drivers"][0]["evidence"]

    prompt = llm.requests[0]["messages"][-1]["content"]
    assert "Hello habibi" in prompt and "computed_metrics" in prompt and "uae_calendar_context" in prompt

    items = setup.client.get("/api/trending").json()["items"]
    listed = next(i for i in items if i["video_id"] == "vid13")
    assert listed["analysis"]["confidence"] == "high"


def test_no_transcript_forces_low_confidence(setup):
    _use(FakeLLM([json.dumps(VALID)]))
    with patch("app.analysis.ensure_youtube_evidence", side_effect=_stored_evidence):
        body = setup.client.post("/api/analysis/youtube/vid12").json()
    assert body["analysis"]["confidence"] == "low"
    assert "No transcript" in body["analysis"]["why_trending"]["unknowns"][0]


def test_invalid_json_retried_once(setup):
    llm = FakeLLM(["not json", "```json\n" + json.dumps(VALID) + "\n```"])
    _use(llm)
    with patch("app.analysis.ensure_youtube_evidence", side_effect=_stored_evidence):
        assert setup.client.post("/api/analysis/youtube/vid11").status_code == 200
    assert len(llm.requests) == 2

    bad_driver = {**VALID, "why_trending": {**VALID["why_trending"], "drivers": [{"type": "x"}]}}
    _use(FakeLLM([json.dumps(bad_driver), "{}"]))
    with patch("app.analysis.ensure_youtube_evidence", side_effect=_stored_evidence):
        resp = setup.client.post("/api/analysis/youtube/vid10")
    assert resp.status_code == 502


def test_unknown_video_404(setup):
    _use(FakeLLM([]))
    assert setup.client.post("/api/analysis/youtube/nope").status_code == 404


def test_missing_video_fetched_from_youtube(setup):
    _use(FakeLLM([json.dumps(VALID)]))

    async def no_evidence(session, video):
        return None

    with patch("app.analysis.ensure_youtube_evidence", side_effect=no_evidence):
        resp = setup.client.post("/api/analysis/youtube/vid99")
    assert resp.status_code == 200

    from app import db
    from app.models import Video

    with db.SessionLocal() as s:
        assert s.query(Video).filter_by(video_id="vid99").one().title == "Video 99"


def test_aggregate_counts(setup):
    _use(FakeLLM([json.dumps(VALID), json.dumps(VALID)]))
    with patch("app.analysis.ensure_youtube_evidence", side_effect=_stored_evidence):
        setup.client.post("/api/analysis/youtube/vid13")
        setup.client.post("/api/analysis/youtube/vid12")
    body = setup.client.get("/api/aggregate?platform=youtube").json()
    assert body["total"] == 10 and body["analyzed"] == 2
    assert body["hook_techniques"] == [{"label": "curiosity gap", "count": 2}]
    assert {"label": "unboxing", "count": 2} in body["format_tags"]


def test_calendar_context():
    events = {e["event"]: e["status"] for e in calendar_context(date(2026, 11, 25))}
    assert "ongoing" in events["White Friday sales"]
    assert "starts in 7 days" == events["UAE National Day (Eid Al Etihad)"]
    assert "Ramadan" in {e["event"] for e in calendar_context(date(2026, 3, 1))}


class FakeProcess:
    """Stand-in for asyncio.subprocess.Process."""

    def __init__(self, stdout=b"", stderr=b"", returncode=0):
        self._out, self._err, self.returncode = stdout, stderr, returncode
        self.stdin_data = None

    async def communicate(self, data=None):
        self.stdin_data = data
        return self._out, self._err

    def kill(self):
        pass


def _fake_exec(process, calls):
    async def create(*argv, **kwargs):
        calls.append({"argv": list(argv), "env": kwargs.get("env")})
        return process

    return create


def test_claude_cli_invoked_headless_without_api_key(setup, monkeypatch):
    from app.analysis import ClaudeCLIProvider

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-be-stripped")
    envelope = {"type": "result", "is_error": False, "result": json.dumps(VALID)}
    proc = FakeProcess(stdout=json.dumps(envelope).encode())
    calls = []
    _use(ClaudeCLIProvider("claude"))
    with (
        patch("app.analysis.asyncio.create_subprocess_exec", _fake_exec(proc, calls)),
        patch("app.analysis.ensure_youtube_evidence", side_effect=_stored_evidence),
    ):
        resp = setup.client.post("/api/analysis/youtube/vid13")
    assert resp.status_code == 200
    assert resp.json()["analysis"]["hook"]["technique"] == "Curiosity Gap"

    argv = calls[0]["argv"]
    assert argv[0] == "claude" and "-p" in argv and "--output-format" in argv and "json" in argv
    assert "ANTHROPIC_API_KEY" not in calls[0]["env"]
    assert b"Evidence (JSON)" in proc.stdin_data  # prompt went in via stdin


def test_claude_cli_missing_binary_is_clear(setup):
    from app.analysis import ClaudeCLIProvider

    async def not_found(*argv, **kwargs):
        raise FileNotFoundError(argv[0])

    _use(ClaudeCLIProvider("claude"))
    with patch("app.analysis.asyncio.create_subprocess_exec", not_found):
        resp = setup.client.post("/api/analysis/youtube/vid14")
    assert resp.status_code == 502
    assert "not found on PATH" in resp.json()["detail"] and "Install Claude Code" in resp.json()["detail"]


def test_claude_cli_not_logged_in_is_clear(setup):
    from app.analysis import ClaudeCLIProvider

    proc = FakeProcess(stderr=b"Not logged in. Please run /login", returncode=1)
    _use(ClaudeCLIProvider("claude"))
    with patch("app.analysis.asyncio.create_subprocess_exec", _fake_exec(proc, [])):
        resp = setup.client.post("/api/analysis/youtube/vid14")
    assert resp.status_code == 502
    assert "not logged in" in resp.json()["detail"].lower()


def test_mock_provider_returns_valid_analysis(setup):
    from app.analysis import MockProvider

    _use(MockProvider())
    with patch("app.analysis.ensure_youtube_evidence", side_effect=_stored_evidence):
        resp = setup.client.post("/api/analysis/youtube/vid13")
    assert resp.status_code == 200
    assert resp.json()["analysis"]["why_trending"]["drivers"][0]["evidence"]
