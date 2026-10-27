import json

from app import db


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
