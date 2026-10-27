from datetime import datetime, timedelta, timezone

from app.metrics import compute_metrics, score_items


def test_compute_metrics():
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    m = compute_metrics(10_000, 900, 100, 50_000, now - timedelta(hours=10), now)
    assert m["velocity"] == 1000.0
    assert m["engagement_rate"] == 0.1
    assert m["outlier_ratio"] == 0.2


def test_compute_metrics_missing_audience_and_zero_views():
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    m = compute_metrics(0, None, None, None, now, now)
    assert m["outlier_ratio"] is None
    assert m["engagement_rate"] is None
    assert m["velocity"] == 0


def test_score_items_prefers_fast_outliers():
    items = [
        {"video_id": "big_slow", "views": 900, "metrics": {"velocity": 10, "outlier_ratio": 0.01}},
        {"video_id": "small_fast", "views": 100, "metrics": {"velocity": 500, "outlier_ratio": 5}},
        {"video_id": "hidden_subs", "views": 500, "metrics": {"velocity": 100, "outlier_ratio": None}},
    ]
    ranked = score_items(items)
    assert [i["video_id"] for i in ranked][0] == "small_fast"
    assert ranked[0]["metrics"]["score"] == 100.0
