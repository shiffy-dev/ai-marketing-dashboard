import json
from pathlib import Path

from app import db
from app.instagram import load_instagram_dataset
from app.models import Evidence, Video, VideoSnapshot

REEL = {
    "id": "reel1",
    "url": "https://www.instagram.com/reel/reel1/",
    "account": "dubaifinds",
    "followers": 50_000,
    "caption": "Best abaya deals in Dubai\nmore text",
    "hashtags": ["dubai"],
    "audio": "Original audio",
    "plays": 120_000,
    "likes": 4_000,
    "comments": 200,
    "posted_at": "2026-10-25T10:00:00Z",
    "top_comments": [{"text": "where to buy?", "likes": 3, "username": "should-not-be-stored"}],
    "transcript": "Habibti look at this price",
    "transcript_language": "en",
    "frames": [],
    "thumbnail": "/static/reels/reel1.jpg",
    "reviewer_notes": "Strong price hook",
}


def _write(tmp_path: Path, reels: list[dict], scraped_at="2026-10-27T08:00:00+00:00") -> Path:
    path = tmp_path / "instagram_reels.json"
    path.write_text(json.dumps({"scraped_at": scraped_at, "source": "apify", "reels": reels}), encoding="utf-8")
    return path


def test_loader_is_idempotent_and_serves_trending(fake, tmp_path):
    path = _write(tmp_path, [REEL])
    with db.SessionLocal() as s:
        meta = load_instagram_dataset(s, path)
        load_instagram_dataset(s, path)  # second run: no duplicates
        assert s.query(Video).filter_by(platform="instagram").count() == 1
        assert s.query(VideoSnapshot).filter_by(platform="instagram").count() == 1
        ev = s.query(Evidence).filter_by(platform="instagram", video_id="reel1").one()
        assert ev.transcript_source == "dataset"
        assert "should-not-be-stored" not in json.dumps(ev.top_comments_json)
    assert meta["sample"] is False and meta["reel_count"] == 1

    body = fake.client.get("/api/trending?platform=instagram").json()
    assert body["dataset"]["source"] == "apify" and body["dataset"]["sample"] is False
    item = body["items"][0]
    assert item["video_id"] == "reel1" and item["views"] == 120_000 and item["format"] == "short"
    assert item["url"] == REEL["url"] and item["title"] == "Best abaya deals in Dubai"
    assert item["metrics"]["outlier_ratio"] == 120_000 / 50_000


def test_loader_adds_snapshot_only_when_stats_change(fake, tmp_path):
    with db.SessionLocal() as s:
        load_instagram_dataset(s, _write(tmp_path, [REEL]))
        load_instagram_dataset(s, _write(tmp_path, [{**REEL, "plays": 130_000}], scraped_at="2026-10-28T08:00:00Z"))
        assert s.query(VideoSnapshot).filter_by(platform="instagram").count() == 2
    assert fake.client.get("/api/trending?platform=instagram").json()["items"][0]["views"] == 130_000


def test_seed_fallback_is_marked_sample(fake):
    from app import instagram

    with db.SessionLocal() as s:
        meta = load_instagram_dataset(s, instagram.SEED_FILE)
    assert meta["sample"] is True and meta["reel_count"] == 10
    body = fake.client.get("/api/trending?platform=instagram").json()
    assert body["dataset"]["sample"] is True and len(body["items"]) == 10
    assert all(i["thumbnail"].startswith("/static/seed/") for i in body["items"])


def test_static_serves_seed_thumbnails(fake):
    resp = fake.client.get("/static/seed/seed01.svg")
    assert resp.status_code == 200 and b"SAMPLE 1" in resp.content
