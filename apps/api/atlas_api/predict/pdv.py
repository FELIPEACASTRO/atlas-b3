"""Features PDV (Guyon-Lekeufack, SSRN 4174589) — pure-stdlib, Markovianas.

R₁ = média exponencial dos retornos (tendência recente); Σ = √(média exponencial dos
retornos²) (vol recente, trajetória). Ambas O(1) por update (EWMA recursiva), point-in-time.
São CANDIDATAS: entram no forecast só se baterem o HAR-Leverage pelo gate (spec; o dado decide).
"""
from __future__ import annotations

import math


def _alpha(halflife: float) -> float:
    if halflife <= 0:
        raise ValueError("halflife must be > 0")
    return 1.0 - 0.5 ** (1.0 / halflife)


def r1_trend(returns: list[float], halflife: float) -> list[float]:
    """Média exponencial dos retornos (feature de tendência R₁). EWMA recursiva."""
    a = _alpha(halflife)
    out: list[float] = []
    s: float | None = None
    for r in returns:
        s = r if s is None else (1.0 - a) * s + a * r
        out.append(s)
    return out


def sigma_path(returns: list[float], halflife: float) -> list[float]:
    """√(média exponencial dos retornos²) — feature de vol-trajetória Σ (≥ 0)."""
    a = _alpha(halflife)
    out: list[float] = []
    s: float | None = None
    for r in returns:
        v = r * r
        s = v if s is None else (1.0 - a) * s + a * v
        out.append(math.sqrt(s))
    return out
