import json
from datetime import date
from types import SimpleNamespace
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
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.messages = self

    async def create(self, **kwargs):
        self.requests.append(kwargs)
        text = self.responses.pop(0)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


@pytest.fixture
def setup(fake):
    async def no_image(ref, http):
        return None

    with patch("app.analysis.load_image", no_image):
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


def test_analysis_generated_cached_and_listed(setup):
    _with_captions("vid13")
    llm = FakeLLM([json.dumps(VALID)])
    _use(llm)
    with patch("app.analysis.ensure_youtube_evidence", side_effect=_stored_evidence):
        first = setup.client.get("/api/analysis/youtube/vid13").json()
        second = setup.client.get("/api/analysis/youtube/vid13").json()
    assert first["cached"] is False and second["cached"] is True
    assert len(llm.requests) == 1
    assert first["analysis"]["confidence"] == "high"
    assert first["analysis"]["why_trending"]["drivers"][0]["evidence"]

    prompt = llm.requests[0]["messages"][0]["content"][-1]["text"]
    assert "Hello habibi" in prompt and "computed_metrics" in prompt and "uae_calendar_context" in prompt

    items = setup.client.get("/api/trending").json()["items"]
    listed = next(i for i in items if i["video_id"] == "vid13")
    assert listed["analysis"]["confidence"] == "high"


def test_no_transcript_forces_low_confidence(setup):
    _use(FakeLLM([json.dumps(VALID)]))
    with patch("app.analysis.ensure_youtube_evidence", side_effect=_stored_evidence):
        body = setup.client.get("/api/analysis/youtube/vid12").json()
    assert body["analysis"]["confidence"] == "low"
    assert "No transcript" in body["analysis"]["why_trending"]["unknowns"][0]


def test_invalid_json_retried_once(setup):
    llm = FakeLLM(["not json", "```json\n" + json.dumps(VALID) + "\n```"])
    _use(llm)
    with patch("app.analysis.ensure_youtube_evidence", side_effect=_stored_evidence):
        assert setup.client.get("/api/analysis/youtube/vid11").status_code == 200
    assert len(llm.requests) == 2

    bad_driver = {**VALID, "why_trending": {**VALID["why_trending"], "drivers": [{"type": "x"}]}}
    _use(FakeLLM([json.dumps(bad_driver), "{}"]))
    with patch("app.analysis.ensure_youtube_evidence", side_effect=_stored_evidence):
        resp = setup.client.get("/api/analysis/youtube/vid10")
    assert resp.status_code == 502


def test_unknown_video_404(setup):
    _use(FakeLLM([]))
    assert setup.client.get("/api/analysis/youtube/nope").status_code == 404


def test_aggregate_counts(setup):
    _use(FakeLLM([json.dumps(VALID), json.dumps(VALID)]))
    with patch("app.analysis.ensure_youtube_evidence", side_effect=_stored_evidence):
        setup.client.get("/api/analysis/youtube/vid13")
        setup.client.get("/api/analysis/youtube/vid12")
    body = setup.client.get("/api/aggregate?platform=youtube").json()
    assert body["total"] == 10 and body["analyzed"] == 2
    assert body["hook_techniques"] == [{"label": "curiosity gap", "count": 2}]
    assert {"label": "unboxing", "count": 2} in body["format_tags"]


def test_calendar_context():
    events = {e["event"]: e["status"] for e in calendar_context(date(2026, 11, 25))}
    assert "ongoing" in events["White Friday sales"]
    assert "starts in 7 days" == events["UAE National Day (Eid Al Etihad)"]
    assert "Ramadan" in {e["event"] for e in calendar_context(date(2026, 3, 1))}
