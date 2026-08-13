from __future__ import annotations

from datetime import date, datetime, timedelta


def parse_date(value: str) -> date:
    value = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y%m%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Unsupported date format: {value}")


def iter_dates(start: date, end: date):
    if end < start:
        raise ValueError("End date cannot be before start date.")
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)

