import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

from app import db, main
from app.youtube import YouTubeClient


def _video(i: int, category: str, views: int, hours_old: int) -> dict:
    published = (datetime.now(timezone.utc) - timedelta(hours=hours_old)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "id": f"vid{i}",
        "snippet": {
            "title": f"Video {i}",
            "description": f"Description {i}",
            "channelId": f"ch{i}",
            "channelTitle": f"Channel {i}",
            "publishedAt": published,
            "categoryId": category,
            "thumbnails": {"high": {"url": f"https://i.ytimg.com/vi/vid{i}/hq.jpg"}},
        },
        "statistics": {"viewCount": str(views), "likeCount": str(views // 10), "commentCount": str(views // 100)},
        "contentDetails": {"duration": "PT1M"},
    }


VIDEOS = [_video(i, "10" if i < 3 else "22", 5_000_000 if i < 3 else 10_000 * (i + 1), 5 + i) for i in range(15)]


class FakeYouTube:
    def __init__(self):
        self.fail = False
        self.calls = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Goog-Api-Key"] == "test-key"
        assert "key=" not in str(request.url)
        path = request.url.path.rsplit("/", 1)[-1]
        self.calls.append(path)
        if self.fail:
            return httpx.Response(403, json={"error": {"message": "quota", "errors": [{"reason": "quotaExceeded"}]}})
        if path == "videos":
            assert request.url.params["regionCode"] == "AE"
            return httpx.Response(200, json={"items": VIDEOS})
        if path == "channels":
            ids = request.url.params["id"].split(",")
            items = [
                {
                    "id": c,
                    "statistics": {"subscriberCount": str(1_000 * (int(c[2:]) + 1)), "hiddenSubscriberCount": False},
                }
                for c in ids
            ]
            return httpx.Response(200, json={"items": items})
        if path == "commentThreads":
            if request.url.params["videoId"] == "vid14":
                return httpx.Response(
                    403, json={"error": {"message": "disabled", "errors": [{"reason": "commentsDisabled"}]}}
                )
            thread = {
                "snippet": {
                    "topLevelComment": {
                        "snippet": {"textOriginal": "love this", "likeCount": 3, "authorDisplayName": "secret person"}
                    }
                }
            }
            return httpx.Response(200, json={"items": [thread]})
        return httpx.Response(404)


@pytest.fixture
def fake():
    fake = FakeYouTube()
    engine = db.create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    db.engine = engine
    db.SessionLocal.configure(bind=engine)
    main.app.dependency_overrides[main.youtube_client] = lambda: YouTubeClient(
        "test-key", httpx.MockTransport(fake.handler)
    )
    with patch("app.trending.fetch_transcript", return_value=None), TestClient(main.app) as client:
        db.Base.metadata.create_all(engine)
        fake.client = client
        yield fake
    main.app.dependency_overrides.clear()
    main.refresh_status.clear()


def test_trending_fetches_filters_and_ranks(fake):
    resp = fake.client.get("/api/trending?platform=youtube&relevant=true")
    assert resp.status_code == 200
    body = resp.json()
    assert body["market"] == "AE"
    assert body["cached"] is False
    assert len(body["items"]) == 10
    assert all(i["category_id"] != "10" for i in body["items"])
    assert [i["rank"] for i in body["items"]] == list(range(1, 11))
    scores = [i["metrics"]["score"] for i in body["items"]]
    assert scores == sorted(scores, reverse=True)
    first = body["items"][0]
    assert {"velocity", "engagement_rate", "outlier_ratio", "score"} <= first["metrics"].keys()

    unfiltered = fake.client.get("/api/trending?relevant=false").json()
    assert any(i["category_id"] == "10" for i in unfiltered["items"])
    # Second request uses stored data instead of calling the API again.
    assert fake.calls.count("videos") == 1


def test_evidence_collected_without_personal_data(fake):
    fake.client.get("/api/trending")
    items = fake.client.get("/api/trending").json()["items"]
    assert all(i["evidence"] for i in items)
    ev = {i["video_id"]: i["evidence"] for i in items}
    assert ev["vid14"]["comments_status"] == "disabled"
    assert all(e["transcript_source"] == "title_description" for e in ev.values())

    from app.models import Evidence

    with db.SessionLocal() as s:
        stored = s.query(Evidence).filter_by(video_id="vid13").one()
        assert "secret person" not in json.dumps(stored.top_comments_json)
        assert stored.transcript.startswith("Video 13")


def test_refresh_failure_falls_back_to_stored_data(fake):
    fake.client.post("/api/refresh/youtube")
    fake.fail = True
    resp = fake.client.post("/api/refresh/youtube")
    assert resp.status_code == 200
    body = resp.json()
    assert body["cached"] is True
    assert "quotaExceeded" in body["error"]
    assert len(body["items"]) == 10


def test_refresh_failure_without_data_returns_502(fake):
    fake.fail = True
    assert fake.client.post("/api/refresh/youtube").status_code == 502
    body = fake.client.get("/api/trending").json()
    assert body["items"] == [] and body["cached"] is True
