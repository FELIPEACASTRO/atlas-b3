"""American option pricing via Cox-Ross-Rubinstein binomial tree — pure stdlib.

Captures the early-exercise premium for B3 American-style equity options, which
Black-Scholes (European) underprices. Converges to BS as ``steps`` grows; an
American call with no dividend equals its European value (early exercise is never
optimal there). This fills the gap flagged by the impartial research: our BS
core was pricing American series as European.
"""
from __future__ import annotations

import math


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
