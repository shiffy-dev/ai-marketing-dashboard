import asyncio
import json
from dataclasses import replace
from unittest.mock import patch

import httpx

from app import apify, db, trending

RAW = {
    "id": "111_222",
    "url": "https://www.instagram.com/reel/abc/",
    "createdAt": "2026-10-26T16:17:40.000Z",
    "caption": "Furniture Fest at Dragon Mart",
    "likeCount": 45,
    "commentCount": 2,
    "isVideo": True,
    "owner": {"username": "dubaifestivals", "followerCount": 612696},
    "video": {"playCount": 12000, "duration": 26},
    "source": {"type": "reels", "input": "https://www.instagram.com/dubaifestivals/reels/"},
}
RUN_INPUT = {"directUrls": ["https://www.instagram.com/dubaifestivals/reels/"]}


def _handler(calls):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-apify"
        path = request.url.path
        calls.append(path)
        if path == "/v2/actor-runs":
            return httpx.Response(200, json={"data": {"items": [{"id": "run1", "actId": "act1"}]}})
        if path == "/v2/actor-runs/run1":
            return httpx.Response(200, json={"data": {"defaultKeyValueStoreId": "kv1"}})
        if path == "/v2/key-value-stores/kv1/records/INPUT":
            return httpx.Response(200, json=RUN_INPUT)
        if path == "/v2/acts/act1/run-sync-get-dataset-items":
            assert json.loads(request.content) == RUN_INPUT
            assert request.url.params["maxItems"] == "30"
            return httpx.Response(201, json=[RAW, {"id": "photo", "isVideo": False}])
        return httpx.Response(404)

    return handler


async def _refresh(transport):
    with db.SessionLocal() as s:
        await apify.refresh_instagram(s, transport)


def test_refresh_reruns_last_actor_and_loads_reels(fake, tmp_path):
    calls = []
    out = tmp_path / "instagram_reels.json"
    with (
        patch.object(apify, "settings", replace(apify.settings, apify_token="test-apify")),
        patch.object(apify, "DATASET_FILE", out),
        patch.object(apify, "RAW_FILE", tmp_path / "raw.json"),
    ):
        asyncio.run(_refresh(httpx.MockTransport(_handler(calls))))
    assert "/v2/acts/act1/run-sync-get-dataset-items" in calls
    dataset = json.loads(out.read_text(encoding="utf-8"))
    assert [r["id"] for r in dataset["reels"]] == ["111_222"]  # non-video items dropped
    with db.SessionLocal() as s:
        items = trending.list_trending(s, trending.INSTAGRAM)
    assert items[0]["video_id"] == "111_222" and items[0]["views"] == 12000


def test_refresh_endpoint_without_token_or_data_returns_502(fake):
    with patch.object(apify, "settings", replace(apify.settings, apify_token="")):
        resp = fake.client.post("/api/refresh/instagram")
    assert resp.status_code == 502 and "APIFY_TOKEN" in resp.json()["detail"]
