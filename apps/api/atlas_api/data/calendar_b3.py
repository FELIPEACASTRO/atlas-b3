"""B3 day-count: time-to-expiry in business days / 252 (the B3 options convention).

Using ACT/365 for T while annualizing vol with sqrt(252) is internally
inconsistent (AIForge finding: B3 options price on dias úteis / 252). Holidays
are the B3/ANBIMA national set, hardcoded for the data period; pass a wider set
for other years. Pure stdlib.
"""
from __future__ import annotations

from datetime import date, timedelta

TRADING_DAYS = 252

B3_HOLIDAYS: frozenset[date] = frozenset({
    # 2024
    date(2024, 1, 1), date(2024, 2, 12), date(2024, 2, 13), date(2024, 3, 29),
    date(2024, 4, 21), date(2024, 5, 1), date(2024, 5, 30), date(2024, 9, 7),
    date(2024, 10, 12), date(2024, 11, 2), date(2024, 11, 15), date(2024, 11, 20),
    date(2024, 12, 24), date(2024, 12, 25), date(2024, 12, 31),
    # 2025
    date(2025, 1, 1), date(2025, 3, 3), date(2025, 3, 4), date(2025, 4, 18),
    date(2025, 4, 21), date(2025, 5, 1), date(2025, 6, 19), date(2025, 9, 7),
    date(2025, 10, 12), date(2025, 11, 2), date(2025, 11, 15), date(2025, 11, 20),
    date(2025, 12, 24), date(2025, 12, 25), date(2025, 12, 31),
    # 2026
    date(2026, 1, 1), date(2026, 2, 16), date(2026, 2, 17), date(2026, 4, 3),
    date(2026, 4, 21), date(2026, 5, 1), date(2026, 6, 4), date(2026, 9, 7),
    date(2026, 10, 12), date(2026, 11, 2), date(2026, 11, 15), date(2026, 11, 20),
    date(2026, 12, 24), date(2026, 12, 25), date(2026, 12, 31),
})


def business_days(start: date, end: date, holidays: frozenset[date] = B3_HOLIDAYS) -> int:
    """Count B3 business days in the half-open interval (start, end]."""
    if end <= start:
        return 0
    count = 0
    day = start + timedelta(days=1)
    while day <= end:
        if day.weekday() < 5 and day not in holidays:
            count += 1
        day += timedelta(days=1)
    return count


def year_fraction(start: date, end: date, holidays: frozenset[date] = B3_HOLIDAYS) -> float:
    """Time to expiry as B3 business-days / 252, floored at one business day."""
    return max(business_days(start, end, holidays), 1) / TRADING_DAYS
