"""UAE retail / cultural calendar used as context evidence for the LLM.

Islamic dates follow the lunar calendar and are confirmed by moon sighting, so they
are approximate (+/- 1-2 days). Extend EVENTS as new years are announced.
"""

from datetime import date, timedelta

EVENTS: list[tuple[str, date, date]] = [
    ("Ramadan", date(2025, 3, 1), date(2025, 3, 29)),
    ("Eid al-Fitr", date(2025, 3, 30), date(2025, 4, 1)),
    ("Eid al-Adha", date(2025, 6, 6), date(2025, 6, 8)),
    ("Ramadan", date(2026, 2, 18), date(2026, 3, 19)),
    ("Eid al-Fitr", date(2026, 3, 20), date(2026, 3, 22)),
    ("Eid al-Adha", date(2026, 5, 27), date(2026, 5, 29)),
    ("Ramadan", date(2027, 2, 8), date(2027, 3, 9)),
    ("Eid al-Fitr", date(2027, 3, 10), date(2027, 3, 12)),
    ("Eid al-Adha", date(2027, 5, 16), date(2027, 5, 18)),
]


def _white_friday(year: int) -> tuple[date, date]:
    """White Friday (the UAE's Black Friday): sales week ending on the Friday after US Thanksgiving."""
    nov1 = date(year, 11, 1)
    first_thursday = nov1 + timedelta(days=(3 - nov1.weekday()) % 7)
    friday = first_thursday + timedelta(weeks=3, days=1)
    return friday - timedelta(days=6), friday + timedelta(days=3)


def _yearly_events(year: int) -> list[tuple[str, date, date]]:
    wf_start, wf_end = _white_friday(year)
    return [
        ("White Friday sales", wf_start, wf_end),
        ("UAE National Day (Eid Al Etihad)", date(year, 12, 2), date(year, 12, 3)),
        ("Dubai Shopping Festival (approx.)", date(year, 12, 6), date(year + 1, 1, 12)),
    ]


def calendar_context(today: date, lookahead_days: int = 45, lookback_days: int = 14) -> list[dict]:
    """Events that are ongoing, upcoming within `lookahead_days`, or ended within `lookback_days`."""
    events = EVENTS + [e for y in (today.year - 1, today.year) for e in _yearly_events(y)]
    result = []
    for name, start, end in sorted(events, key=lambda e: e[1]):
        if start <= today <= end:
            status = f"ongoing (day {(today - start).days + 1} of {(end - start).days + 1})"
        elif today < start <= today + timedelta(days=lookahead_days):
            status = f"starts in {(start - today).days} days"
        elif end < today <= end + timedelta(days=lookback_days):
            status = f"ended {(today - end).days} days ago"
        else:
            continue
        result.append({"event": name, "start": start.isoformat(), "end": end.isoformat(), "status": status})
    return result
