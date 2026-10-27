import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("YOUTUBE_API_KEY", "test-key")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime, timedelta, timezone  # noqa: E402
from unittest.mock import patch  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import db, main  # noqa: E402
from app.youtube import YouTubeClient  # noqa: E402


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
