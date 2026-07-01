"""American option pricing via the Bjerksund-Stensland 1993 closed form — pure stdlib.

Captures the early-exercise premium for B3 American-style equity options, which
Black-Scholes (European) underprices. Fast enough to invert for IV across the whole
chain (the CRR binomial `crr_price` here is only the validation ground-truth). An
American call with no dividend equals its European value (early exercise is never
optimal there). The price is floored at max(intrinsic, European) — the BS93 body can
underprice deep-ITM under negative carry (0<q<r), and an American is never worth less.
"""
from __future__ import annotations

import math

_SQRT2 = math.sqrt(2.0)


def _cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / _SQRT2))


def _euro_call_carry(S: float, K: float, r: float, b: float, T: float, sigma: float) -> float:
    """European call with cost-of-carry b (= r - q). exp((b-r)T) = exp(-qT)."""
    sqrtT = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (b + 0.5 * sigma * sigma) * T) / sqrtT
    d2 = d1 - sqrtT
    return S * math.exp((b - r) * T) * _cdf(d1) - K * math.exp(-r * T) * _cdf(d2)


def _phi(S: float, T: float, gamma: float, H: float, I: float, r: float, b: float, sigma: float) -> float:  # noqa: E741 (I = fronteira-gatilho, notação Bjerksund-Stensland)
    sigsq = sigma * sigma
    lam = (-r + gamma * b + 0.5 * gamma * (gamma - 1.0) * sigsq) * T
    kappa = 2.0 * b / sigsq + (2.0 * gamma - 1.0)
    sqrtT = sigma * math.sqrt(T)
    d = -(math.log(S / H) + (b + (gamma - 0.5) * sigsq) * T) / sqrtT
    return math.exp(lam) * S**gamma * (_cdf(d) - (I / S) ** kappa * _cdf(d - 2.0 * math.log(I / S) / sqrtT))


def _bs_call(S: float, K: float, r: float, b: float, T: float, sigma: float) -> float:
    """Bjerksund-Stensland (1993) American call with cost-of-carry b."""
    if b >= r:  # early exercise never optimal (q <= 0) -> European
        return _euro_call_carry(S, K, r, b, T, sigma)
    sigsq = sigma * sigma
    beta = (0.5 - b / sigsq) + math.sqrt((b / sigsq - 0.5) ** 2 + 2.0 * r / sigsq)
    b_inf = beta / (beta - 1.0) * K
    b0 = max(K, r / (r - b) * K)
    # exp(ht) can overflow only at extreme beta (very low vol, negative carry); there
    # the early-exercise region dominates and S >= trigger returns intrinsic below.
    try:
        exp_ht = math.exp(-(b * T + 2.0 * sigma * math.sqrt(T)) * b0 / (b_inf - b0))
    except OverflowError:
        exp_ht = math.inf
    trigger = b0 + (b_inf - b0) * (1.0 - exp_ht)
    if S >= trigger:
        return S - K  # immediate exercise — the DOMINANT value for deep-ITM negative carry
    alpha = (trigger - K) * trigger ** (-beta)
    euro = _euro_call_carry(S, K, r, b, T, sigma)
    try:
        v = (
            alpha * S**beta
            - alpha * _phi(S, T, beta, trigger, trigger, r, b, sigma)
            + _phi(S, T, 1.0, trigger, trigger, r, b, sigma)
            - _phi(S, T, 1.0, K, trigger, r, b, sigma)
            - K * _phi(S, T, 0.0, trigger, trigger, r, b, sigma)
            + K * _phi(S, T, 0.0, K, trigger, r, b, sigma)
        )
    except OverflowError:                        # genuíno só em beta extremo
        v = euro
    # A americana NUNCA vale menos que o intrínseco nem que a europeia. O corpo fechado BS93
    # subprecifica deep-ITM com carry negativo (0<q<r) — medido: 22 casos abaixo do intrínseco, 1
    # American<European, 50+ vega<0. O piso zera as violações sem overshoot vs CRR (validado).
    return max(v, S - K, euro)


def bjerksund_stensland(kind: str, S: float, K: float, r: float, q: float, T: float, sigma: float) -> float:
    """Closed-form American option price (Bjerksund-Stensland 1993), pure stdlib.

    Fast enough to invert for IV across the whole chain (the CRR tree is not).
    Puts use the BS put-call transformation P(S,K,r,b) = C(K,S,r-b,-b). Validated
    against ``crr_price`` (the binomial ground truth) in the tests.
    """
    if kind not in ("call", "put"):
        raise ValueError(f"kind must be 'call' or 'put', got {kind!r}")
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return max(0.0, S - K) if kind == "call" else max(0.0, K - S)
    b = r - q
    if kind == "call":
        return _bs_call(S, K, r, b, T, sigma)
    return _bs_call(K, S, r - b, -b, T, sigma)  # put via transformation


_IV_LOW, _IV_HIGH, _IV_TOL, _IV_MAXIT = 1e-4, 5.0, 1e-7, 100


def american_iv(kind: str, price: float, S: float, K: float, r: float, q: float, T: float) -> float:
    """Implied vol that reprices an American quote under Bjerksund-Stensland.

    American price is monotone increasing in sigma, so a sign-bracketed bisection
    is robust. Returns nan when the quote is below intrinsic (impossible for an
    American option) or no vol in (0, 5] reprices it. The economic-reliability
    gate (extrinsic value, plausible band) is applied by the caller, as for the
    European solver.
    """
    if kind not in ("call", "put"):
        raise ValueError(f"kind must be 'call' or 'put', got {kind!r}")
    if price <= 0 or T <= 0 or S <= 0 or K <= 0:
        return float("nan")
    intrinsic = max(0.0, S - K) if kind == "call" else max(0.0, K - S)
    # at/under intrinsic the American value is flat in sigma -> IV is undefined; don't
    # let bisection return an arbitrary point on the immediate-exercise plateau.
    if price <= intrinsic + 1e-7:
        return float("nan")
    f_lo = bjerksund_stensland(kind, S, K, r, q, T, _IV_LOW) - price
    f_hi = bjerksund_stensland(kind, S, K, r, q, T, _IV_HIGH) - price
    if (f_lo < 0) == (f_hi < 0):
        return float("nan")  # quote not bracketed in (0, 5]
    lo, hi = _IV_LOW, _IV_HIGH
    mid = 0.5 * (lo + hi)
    for _ in range(_IV_MAXIT):
        mid = 0.5 * (lo + hi)
        f_mid = bjerksund_stensland(kind, S, K, r, q, T, mid) - price
        if abs(f_mid) < _IV_TOL or 0.5 * (hi - lo) < _IV_TOL:
            break
        if (f_lo < 0) != (f_mid < 0):
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return mid


def american_greeks(kind: str, S: float, K: float, r: float, q: float, T: float, sigma: float) -> dict:
    """Finite-difference greeks on the Bjerksund-Stensland price.

    delta/gamma (central bump of spot, 1%), vega (central bump of vol, 1 vol pt),
    theta (per *day*, one B3 session of 1/252yr). Pure stdlib; degenerate-safe.
    """
    nan = float("nan")
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return {"delta": nan, "gamma": nan, "vega": nan, "theta": nan}
    h = S * 0.01
    p = bjerksund_stensland(kind, S, K, r, q, T, sigma)
    pu = bjerksund_stensland(kind, S + h, K, r, q, T, sigma)
    pd = bjerksund_stensland(kind, S - h, K, r, q, T, sigma)
    vega = (bjerksund_stensland(kind, S, K, r, q, T, sigma + 0.01)
            - bjerksund_stensland(kind, S, K, r, q, T, sigma - 0.01)) / 0.02
    dt = 1.0 / 252.0
    # one-day decay; for T <= 1 day the value rolls to intrinsic at expiry, which is
    # the LARGEST decay (not 0 — the old `else 0` zeroed near-expiry theta).
    theta = bjerksund_stensland(kind, S, K, r, q, max(T - dt, 0.0), sigma) - p
    return {"delta": (pu - pd) / (2 * h), "gamma": (pu - 2 * p + pd) / (h * h), "vega": vega, "theta": theta}


def crr_price(
    kind: str,
    S: float,
    K: float,
    r: float,
    q: float,
    T: float,
    sigma: float,
    *,
    steps: int = 200,
    american: bool = True,
) -> float:
    if kind not in ("call", "put"):
        raise ValueError(f"kind must be 'call' or 'put', got {kind!r}")
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0 or steps < 1:
        return max(0.0, S - K) if kind == "call" else max(0.0, K - S)

    dt = T / steps
    u = math.exp(sigma * math.sqrt(dt))
    d = 1.0 / u
    disc = math.exp(-r * dt)
    p = (math.exp((r - q) * dt) - d) / (u - d)
    if not 0.0 <= p <= 1.0:
        # risk-neutral prob outside [0,1]: the tree can't represent the drift at
        # this step size -> the discretization is invalid (audit finding A2).
        # Clamping here silently produced errors up to ~95%.
        return float("nan")

    values = []
    for i in range(steps + 1):
        st = S * u ** (steps - i) * d ** i
        values.append(max(0.0, st - K) if kind == "call" else max(0.0, K - st))

    for step in range(steps - 1, -1, -1):
        for i in range(step + 1):
            cont = disc * (p * values[i] + (1.0 - p) * values[i + 1])
            if american:
                st = S * u ** (step - i) * d ** i
                ex = max(0.0, st - K) if kind == "call" else max(0.0, K - st)
                values[i] = cont if cont > ex else ex
            else:
                values[i] = cont
    return values[0]
