"""Black-Scholes pricing and greeks (European), pure stdlib.

Continuous dividend yield ``q``. Normal CDF via ``math.erf`` so the quant core
carries no third-party dependency. Domain guards return ``nan`` (price) or an
all-``nan`` dict (greeks) for non-positive S/K, and degenerate values at
expiry/zero-vol, rather than raising on dirty EOD inputs.
"""
from __future__ import annotations

import math

_SQRT2 = math.sqrt(2.0)
_SQRT2PI = math.sqrt(2.0 * math.pi)
_NAN = float("nan")
_GREEK_KEYS = ("delta", "gamma", "vega", "theta", "rho")


def _pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / _SQRT2PI


def _cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / _SQRT2))


def _check_kind(kind: str) -> None:
    if kind not in ("call", "put"):
        raise ValueError(f"kind must be 'call' or 'put', got {kind!r}")


def _d1_d2(S: float, K: float, r: float, q: float, T: float, sigma: float):
    vsqrt = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / vsqrt
    return d1, d1 - vsqrt


def bs_price(kind: str, S: float, K: float, r: float, q: float, T: float, sigma: float) -> float:
    """Price a European call/put. ``nan`` for S<=0 or K<=0; intrinsic at T<=0 or sigma<=0."""
    _check_kind(kind)
    if S <= 0 or K <= 0:
        return _NAN
    if T <= 0 or sigma <= 0:
        return max(0.0, S - K) if kind == "call" else max(0.0, K - S)
    d1, d2 = _d1_d2(S, K, r, q, T, sigma)
    dq, dr = math.exp(-q * T), math.exp(-r * T)
    if kind == "call":
        return S * dq * _cdf(d1) - K * dr * _cdf(d2)
    return K * dr * _cdf(-d2) - S * dq * _cdf(-d1)


def bs_greeks(kind: str, S: float, K: float, r: float, q: float, T: float, sigma: float) -> dict:
    """Delta, gamma, vega (per 1.00 vol), theta (per year), rho. Degenerate-safe."""
    _check_kind(kind)
    if S <= 0 or K <= 0:
        return dict.fromkeys(_GREEK_KEYS, _NAN)
    if T <= 0 or sigma <= 0:
        itm = (S > K) if kind == "call" else (S < K)
        sign = 1.0 if kind == "call" else -1.0
        return {"delta": sign if itm else 0.0, "gamma": 0.0, "vega": 0.0, "theta": 0.0, "rho": 0.0}
    d1, d2 = _d1_d2(S, K, r, q, T, sigma)
    sqrtT = math.sqrt(T)
    dq, dr = math.exp(-q * T), math.exp(-r * T)
    pdf = _pdf(d1)
    gamma = dq * pdf / (S * sigma * sqrtT)
    vega = S * dq * pdf * sqrtT
    if kind == "call":
        delta = dq * _cdf(d1)
        theta = -S * dq * pdf * sigma / (2 * sqrtT) - r * K * dr * _cdf(d2) + q * S * dq * _cdf(d1)
        rho = K * T * dr * _cdf(d2)
    else:
        delta = -dq * _cdf(-d1)
        theta = -S * dq * pdf * sigma / (2 * sqrtT) + r * K * dr * _cdf(-d2) - q * S * dq * _cdf(-d1)
        rho = -K * T * dr * _cdf(-d2)
    return {"delta": delta, "gamma": gamma, "vega": vega, "theta": theta, "rho": rho}
