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

# Economic-validity gate for EOD-derived IV (separate from the numeric solver gate
# above). The solver can find a vol that reprices a near-intrinsic print with
# adequate vega, yet that vol is an artifact, not a market vol: deep ITM/OTM or
# stale EOD prints sit at parity (no extrinsic value to infer vol from), and the
# bisection then returns absurd vols (real data: PETRB930 = 464%). These are
# disclosed heuristics, not a model — see docs/LICOES-ERROS-E-ACERTOS.md.
_MAX_PLAUSIBLE_IV = 3.0   # 300% annualized; above this an EOD print is an artifact
_MIN_EXTRINSIC = 0.01     # R$ of time value; at/below intrinsic the IV is undefined


def extrinsic_value(kind: str, price: float, S: float, K: float) -> float:
    """Option price minus intrinsic value — the time value the IV is inferred from."""
    intrinsic = max(S - K, 0.0) if kind == "call" else max(K - S, 0.0)
    return price - intrinsic


def iv_is_reliable(kind: str, price: float, S: float, K: float, iv: float) -> bool:
    """Whether an EOD-derived IV is trustworthy enough to report.

    Trustworthy requires (1) a non-NaN, economically plausible vol and (2) a print
    that carries real extrinsic value. Without extrinsic value vega ~ 0 and the IV
    is mathematically undefined / explosive, so we report None rather than a number
    we cannot stand behind (honesty rule: no false analysis).
    """
    if iv != iv:  # NaN
        return False
    if not (0.0 < iv <= _MAX_PLAUSIBLE_IV):
        return False
    if extrinsic_value(kind, price, S, K) < _MIN_EXTRINSIC:
        return False
    return True


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
