import json

from app import db, trending
from app.config import YOUTUBE_CATEGORIES


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
    assert first["duration_seconds"] == 60 and first["format"] == "short"

    unfiltered = fake.client.get("/api/trending?relevant=false").json()
    assert any(i["category_id"] == "10" for i in unfiltered["items"])
    # Second request uses stored data instead of calling the API again (main chart + one call per category chart).
    assert fake.calls.count("videos") == 1 + len(YOUTUBE_CATEGORIES) and "search" not in fake.calls


def test_youtube_is_shorts_only_and_includes_category_charts(fake):
    fake.client.post("/api/refresh/youtube")
    with db.SessionLocal() as s:
        items = trending.list_trending(s, trending.YOUTUBE, relevant=False, limit=100)
    ids = [i["video_id"] for i in items]
    assert "vid5" not in ids and "vid6" not in ids  # 61s and 29s chart videos
    assert "vid7" in ids  # exactly 30s
    assert "vid51" not in ids  # 3-minute category-chart video
    assert "vid50" in ids and ids.count("vid0") == 1
    assert all(30 <= i["duration_seconds"] <= 60 and i["format"] == "short" for i in items)
    by_id = {i["video_id"]: i for i in items}
    assert by_id["vid0"]["chart_rank"] == 1 and by_id["vid50"]["chart_rank"] is None


def test_category_chart_failure_keeps_main_chart(fake):
    fake.category_fail = True
    body = fake.client.post("/api/refresh/youtube").json()
    assert body["cached"] is False and len(body["items"]) == 10
    assert "vid50" not in {i["video_id"] for i in body["items"]}


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
