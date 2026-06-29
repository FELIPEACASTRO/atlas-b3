"""Implied volatility solver: NaN-safe bisection + reprice/min-vega validation.

Returns an explicit nan when the price violates no-arbitrage bounds, no root
exists, or the solved vol does not actually reprice the input within a relative
tolerance / sits where vega is negligible (deep ITM/OTM, tiny T). The validation
gate prevents the bisection from stopping early on a plausible-but-false vol
(audit finding A1: a false ~0.31 IV and a 1e-6 floor were reaching the screen).
"""
from __future__ import annotations

import math

from atlas_api.pricing.bs import bs_greeks, bs_price

_LOW = 1e-6
_HIGH = 5.0
_TOL = 1e-8
_MAXIT = 200
_ARB_EPS = 1e-10
_MIN_VEGA = 1e-6
_REPRICE_RTOL = 1e-3
_PRICE_FLOOR = 0.01  # one B3 tick


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
        candidate = _LOW
    elif f_hi == 0.0:
        candidate = _HIGH
    elif (f_lo < 0) == (f_hi < 0):
        return float("nan")
    else:
        lo, hi = _LOW, _HIGH
        candidate = 0.5 * (lo + hi)
        for _ in range(_MAXIT):
            candidate = 0.5 * (lo + hi)
            f_mid = bs_price(kind, S, K, r, q, T, candidate) - price
            if abs(f_mid) < _TOL or 0.5 * (hi - lo) < _TOL:
                break
            if (f_lo < 0) != (f_mid < 0):
                hi = candidate
            else:
                lo, f_lo = candidate, f_mid

    # validation gate: the vol must reprice the quote AND have non-negligible vega
    vega = bs_greeks(kind, S, K, r, q, T, candidate)["vega"]
    model = bs_price(kind, S, K, r, q, T, candidate)
    if vega < _MIN_VEGA or abs(model - price) > _REPRICE_RTOL * max(abs(price), _PRICE_FLOOR):
        return float("nan")
    return candidate
