"""Pré-DI risk-free curve: linear interpolation on a 252-business-day basis.

Flat extrapolation outside the observed range. Points are ``(business_days,
annual_rate)``. Selic-flat is a poor approximation in volatile-rate regimes
(spec §6), so option discounting should use the term structure per expiry.
"""
from __future__ import annotations


def rate_for(points: list[tuple[int, float]], du: int) -> float:
    if not points:
        raise ValueError("empty curve")
    pts = sorted(points)
    if du <= pts[0][0]:
        return pts[0][1]
    if du >= pts[-1][0]:
        return pts[-1][1]
    for i in range(1, len(pts)):
        x1, y1 = pts[i]
        if du <= x1:
            x0, y0 = pts[i - 1]
            return y0 + (y1 - y0) * (du - x0) / (x1 - x0)
    return pts[-1][1]
