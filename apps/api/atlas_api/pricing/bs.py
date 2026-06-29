"""Black-Scholes pricing and greeks (European), pure stdlib.

Continuous dividend yield ``q``. Normal CDF via ``math.erf`` so we carry no
third-party dependency in the quant core.
"""
from __future__ import annotations

import math

_SQRT2 = math.sqrt(2.0)
_SQRT2PI = math.sqrt(2.0 * math.pi)


def _pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / _SQRT2PI


def _cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / _SQRT2))


def _d1_d2(S: float, K: float, r: float, q: float, T: float, sigma: float):
    vsqrt = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / vsqrt
    return d1, d1 - vsqrt


def bs_price(kind: str, S: float, K: float, r: float, q: float, T: float, sigma: float) -> float:
    """Price a European call/put. Degenerates to intrinsic when T<=0 or sigma<=0."""
    if T <= 0 or sigma <= 0:
        return max(0.0, S - K) if kind == "call" else max(0.0, K - S)
    d1, d2 = _d1_d2(S, K, r, q, T, sigma)
    dq, dr = math.exp(-q * T), math.exp(-r * T)
    if kind == "call":
        return S * dq * _cdf(d1) - K * dr * _cdf(d2)
    if kind == "put":
        return K * dr * _cdf(-d2) - S * dq * _cdf(-d1)
    raise ValueError(f"kind must be 'call' or 'put', got {kind!r}")


def bs_greeks(kind: str, S: float, K: float, r: float, q: float, T: float, sigma: float) -> dict:
    """Return delta, gamma, vega (per 1.00 vol), theta (per year), rho."""
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
    elif kind == "put":
        delta = -dq * _cdf(-d1)
        theta = -S * dq * pdf * sigma / (2 * sqrtT) + r * K * dr * _cdf(-d2) - q * S * dq * _cdf(-d1)
        rho = -K * T * dr * _cdf(-d2)
    else:
        raise ValueError(f"kind must be 'call' or 'put', got {kind!r}")
    return {"delta": delta, "gamma": gamma, "vega": vega, "theta": theta, "rho": rho}
