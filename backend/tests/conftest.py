import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("YOUTUBE_API_KEY", "test-key")
os.environ["LLM_PROVIDER"] = "mock"
# Empty dataset file: the app's startup loader becomes a no-op, so each test seeds its own reels.
_EMPTY_DATASET = Path(__file__).resolve().parent / "_empty_dataset.json"
_EMPTY_DATASET.write_text("")
os.environ["INSTAGRAM_DATASET"] = str(_EMPTY_DATASET)
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
# Only reachable via videos.list?id=... — never appears in the chart.
EXTRA_VIDEO = _video(99, "22", 123_000, 3)


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
            if "id" in request.url.params:
                ids = set(request.url.params["id"].split(","))
                items = [v for v in [*VIDEOS, EXTRA_VIDEO] if v["id"] in ids]
                return httpx.Response(200, json={"items": items})
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
