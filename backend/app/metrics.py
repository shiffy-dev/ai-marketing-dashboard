from datetime import datetime

MIN_HOURS = 1.0


def hours_between(start: datetime | None, end: datetime) -> float | None:
    if start is None:
        return None
    return max((end - start).total_seconds() / 3600, MIN_HOURS)


def compute_metrics(
    views: int, likes: int | None, comments: int | None, audience: int | None, published_at, as_of
) -> dict:
    hours = hours_between(published_at, as_of)
    velocity = views / hours if hours else None
    engagement = ((likes or 0) + (comments or 0)) / views if views else None
    outlier = views / audience if audience else None
    return {
        "hours_since_published": round(hours, 1) if hours else None,
        "velocity": round(velocity, 1) if velocity is not None else None,
        "engagement_rate": round(engagement, 4) if engagement is not None else None,
        "outlier_ratio": round(outlier, 3) if outlier is not None else None,
    }


def _percentile_ranks(values: list[float | None]) -> list[float]:
    """Percentile rank in [0, 1]; missing values get 0."""
    present = sorted(v for v in values if v is not None)
    n = len(present)
    if n == 0:
        return [0.0] * len(values)
    ranks = []
    for v in values:
        if v is None:
            ranks.append(0.0)
        elif n == 1:
            ranks.append(1.0)
        else:
            below = sum(1 for p in present if p < v)
            equal = sum(1 for p in present if p == v)
            ranks.append((below + (equal - 1) / 2) / (n - 1))
    return ranks


def score_items(items: list[dict], velocity_weight: float = 0.5) -> list[dict]:
    """Adds metrics.score (0-100): weighted percentile rank of velocity and outlier_ratio, then sorts."""
    v_ranks = _percentile_ranks([i["metrics"]["velocity"] for i in items])
    o_ranks = _percentile_ranks([i["metrics"]["outlier_ratio"] for i in items])
    for item, v, o in zip(items, v_ranks, o_ranks, strict=True):
        item["metrics"]["score"] = round(100 * (velocity_weight * v + (1 - velocity_weight) * o), 1)
    return sorted(items, key=lambda i: (i["metrics"]["score"], i["views"]), reverse=True)
