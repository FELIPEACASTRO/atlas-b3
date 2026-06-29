"""Implied volatility solver: NaN-safe, bracketed bisection.

Returns an explicit ``nan`` when the price violates the no-arbitrage bounds or
no root exists in the bracket, rather than a plausible-but-false number.
"""
from __future__ import annotations

import math

from atlas_api.pricing.bs import bs_price

_LOW = 1e-6
_HIGH = 5.0
_TOL = 1e-8
_MAXIT = 200


def implied_vol(kind: str, price: float, S: float, K: float, r: float, q: float, T: float) -> float:
    if price <= 0 or T <= 0:
        return float("nan")
    dq, dr = math.exp(-q * T), math.exp(-r * T)
    if kind == "call":
        lower, upper = max(0.0, S * dq - K * dr), S * dq
    elif kind == "put":
        lower, upper = max(0.0, K * dr - S * dq), K * dr
    else:
        raise ValueError(f"kind must be 'call' or 'put', got {kind!r}")

    if price < lower - 1e-10 or price > upper + 1e-10:
        return float("nan")

    f_lo = bs_price(kind, S, K, r, q, T, _LOW) - price
    f_hi = bs_price(kind, S, K, r, q, T, _HIGH) - price
    if f_lo * f_hi > 0:
        return float("nan")

    lo, hi = _LOW, _HIGH
    for _ in range(_MAXIT):
        mid = 0.5 * (lo + hi)
        f_mid = bs_price(kind, S, K, r, q, T, mid) - price
        if abs(f_mid) < _TOL:
            return mid
        if f_lo * f_mid < 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return 0.5 * (lo + hi)
