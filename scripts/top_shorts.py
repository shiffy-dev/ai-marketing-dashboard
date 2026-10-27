"""Top UAE YouTube Shorts (30-60s) from the official YouTube Data API, saved to CSV.

Candidates: the official UAE trending chart (mostPopular, regionCode=AE), all 200 videos, plus the
per-category UAE charts (--main-only skips them). Optional --search adds search.list results
(only "viewable in the UAE", so mostly global). Kept: 30-60 second videos. Ranked like the dashboard
(percentile of views/hour + views/subscribers).

Quota: ~1 unit per chart page (~50 per run); --search adds 100 per page. Free tier is 10,000/day.

Usage (from the repo root):
  python scripts/top_shorts.py                    # top 50 Shorts from the UAE trending charts
  python scripts/top_shorts.py --include-music --search 3
"""

import argparse
import asyncio
import csv
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.config import MARKET, NOISE_CATEGORY_IDS, YOUTUBE_CATEGORIES, settings  # noqa: E402
from app.metrics import compute_metrics, score_items  # noqa: E402
from app.trending import is_short  # noqa: E402
from app.youtube import YouTubeClient, YouTubeError, parse_duration, parse_ts  # noqa: E402


async def collect(search_pages: int, days: int, include_music: bool, with_categories: bool) -> tuple[list[dict], int]:
    client = YouTubeClient()
    chart = await client.chart(MARKET.country)
    chart_rank = {v["id"]: r for r, v in enumerate(chart, start=1)}
    seen = {v["id"]: v for v in chart}
    categories = [c for c in YOUTUBE_CATEGORIES if include_music or c not in NOISE_CATEGORY_IDS]
    for cat in categories if with_categories else []:
        try:
            for v in await client.chart(MARKET.country, cat):
                seen.setdefault(v["id"], v)
        except YouTubeError:
            pass  # not every category has a chart in every region
    if search_pages:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        ids = await client.search_short_ids(MARKET.country, since, pages=search_pages)
        for v in await client.video_details([i for i in ids if i not in seen]):
            seen[v["id"]] = v
    candidates = list(seen.values())
    shorts = [v for v in candidates if is_short(v)]
    if not include_music:
        shorts = [v for v in shorts if v["snippet"].get("categoryId") not in NOISE_CATEGORY_IDS]
    subs = await client.channel_subscribers([v["snippet"]["channelId"] for v in shorts])

    now = datetime.now(timezone.utc)
    items = []
    for v in shorts:
        sn, st = v["snippet"], v.get("statistics", {})
        views = int(st.get("viewCount", 0))
        likes = int(st["likeCount"]) if "likeCount" in st else None
        comments = int(st["commentCount"]) if "commentCount" in st else None
        audience = subs.get(sn["channelId"])
        items.append(
            {
                "video_id": v["id"],
                "url": f"https://www.youtube.com/shorts/{v['id']}",
                "title": sn.get("title", ""),
                "channel": sn.get("channelTitle", ""),
                "category": YOUTUBE_CATEGORIES.get(sn.get("categoryId"), sn.get("categoryId")),
                "duration_s": parse_duration(v["contentDetails"].get("duration")),
                "published_at": sn.get("publishedAt"),
                "views": views,
                "likes": likes,
                "comments": comments,
                "subscribers": audience,
                "chart_rank": chart_rank.get(v["id"]),
                "metrics": compute_metrics(views, likes, comments, audience, parse_ts(sn.get("publishedAt")), now),
            }
        )
    return score_items(items), len(candidates)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--top", type=int, default=50)
    ap.add_argument("--main-only", action="store_true", help="skip the per-category UAE charts")
    ap.add_argument("--search", type=int, default=0, help="also add N search pages of 50 (100 quota units each)")
    ap.add_argument(
        "--days", type=int, default=settings.shorts_search_days, help="--search only: published in the last N days"
    )
    ap.add_argument("--include-music", action="store_true", help="keep Music and Gaming categories")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "top_shorts_uae.csv")
    args = ap.parse_args()

    try:
        items, scanned = asyncio.run(collect(args.search, args.days, args.include_music, not args.main_only))
    except YouTubeError as exc:
        sys.exit(f"YouTube API error: {exc}")
    top = items[: args.top]

    cols = [
        "rank",
        "score",
        "views_per_hour",
        "outlier_ratio",
        "engagement_rate",
        "duration_s",
        "views",
        "likes",
        "comments",
        "subscribers",
        "chart_rank",
        "category",
        "channel",
        "title",
        "published_at",
        "url",
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for rank, i in enumerate(top, start=1):
            m = i["metrics"]
            w.writerow(
                {
                    **i,
                    "rank": rank,
                    "score": m["score"],
                    "views_per_hour": m["velocity"],
                    "outlier_ratio": m["outlier_ratio"],
                    "engagement_rate": m["engagement_rate"],
                }
            )

    print(
        f"Scanned {scanned} videos; {len(items)} are "
        f"{settings.shorts_min_seconds}-{settings.shorts_max_seconds}s Shorts."
    )
    print(f"Top {len(top)} saved to {args.out}\n")
    print(f"{'#':>3} {'score':>5} {'views/h':>9} {'outlier':>8} {'dur':>4}  title")
    for rank, i in enumerate(top, start=1):
        m = i["metrics"]
        out = f"{m['outlier_ratio']:.2f}x" if m["outlier_ratio"] is not None else "-"
        print(
            f"{rank:>3} {m['score']:>5} {m['velocity'] or 0:>9,.0f} {out:>8} {i['duration_s']:>3}s  {i['title'][:60]}"
        )


if __name__ == "__main__":
    main()
