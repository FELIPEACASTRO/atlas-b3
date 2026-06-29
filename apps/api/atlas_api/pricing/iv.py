"""Implied volatility solver: NaN-safe, sign-robust bracketed bisection.

Returns an explicit ``nan`` when the price violates no-arbitrage bounds or no
root exists in the bracket — never a plausible-but-false number. The bisection
branches on the *sign* of the residuals (not their product), which would fail
silently when a residual is exactly ``0.0`` (review finding: near-bracket false
positive returning ~5.0).
"""
from __future__ import annotations

import math

from atlas_api.pricing.bs import bs_price

_LOW = 1e-6
_HIGH = 5.0
_TOL = 1e-8
_MAXIT = 200
_ARB_EPS = 1e-10


def implied_vol(kind: str, price: float, S: float, K: float, r: float, q: float, T: float) -> float:
    if kind not in ("call", "put"):
        raise ValueError(f"kind must be 'call' or 'put', got {kind!r}")
    if price <= 0 or T <= 0 or S <= 0 or K <= 0:
        return float("nan")

    dq, dr = math.exp(-q * T), math.exp(-r * T)
    if kind == "call":
        lower, upper = max(0.0, S * dq - K * dr), S * dq
    else:
        lower, upper = max(0.0, K * dr - S * dq), K * dr
    if price < lower - _ARB_EPS or price > upper + _ARB_EPS:
        return float("nan")

    f_lo = bs_price(kind, S, K, r, q, T, _LOW) - price
    f_hi = bs_price(kind, S, K, r, q, T, _HIGH) - price
    if f_lo == 0.0:
        return _LOW
    if f_hi == 0.0:
        return _HIGH
    if (f_lo < 0) == (f_hi < 0):  # no sign change in the bracket -> no root
        return float("nan")

    lo, hi = _LOW, _HIGH
    for _ in range(_MAXIT):
        mid = 0.5 * (lo + hi)
        f_mid = bs_price(kind, S, K, r, q, T, mid) - price
        if abs(f_mid) < _TOL or 0.5 * (hi - lo) < _TOL:
            return mid
        if (f_lo < 0) != (f_mid < 0):
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return 0.5 * (lo + hi)
