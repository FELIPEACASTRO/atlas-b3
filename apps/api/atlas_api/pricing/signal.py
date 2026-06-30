"""IV-vs-RV heuristic classifier (rico / barato / neutro / indisponivel).

A labeled heuristic, never a recommendation: it states whether implied vol sits
above or below realized vol by more than ``band``. Missing data (``nan``) is
surfaced as ``indisponivel`` rather than silently masked as ``neutro``.
"""
from __future__ import annotations

import math

# IV Rank needs enough trailing history to be meaningful; below this we honestly
# report None rather than a rank computed off 2-3 noisy points.
MIN_IV_HISTORY = 20


def iv_rank(history: list[float], current: float, *, min_history: int = MIN_IV_HISTORY) -> float | None:
    """Tastytrade-style IV Rank in [0,100]: where ``current`` sits between the
    trailing min and max IV. None when history is too short or degenerate (flat).

    ``history`` is the trailing ATM-IV window (may include ``current``); a flat
    window (max==min) has no meaningful rank.
    """
    vals = [h for h in history if h is not None and not math.isnan(h)]
    if current is None or math.isnan(current) or len(vals) < min_history:
        return None
    lo, hi = min(vals), max(vals)
    if hi <= lo:
        return None
    return round(100.0 * (current - lo) / (hi - lo), 1)


def classify(iv: float, rv: float, band: float = 0.10) -> str:
    if math.isnan(iv) or math.isnan(rv):
        return "indisponivel"
    if rv <= 0:
        return "neutro"
    if iv > rv * (1 + band):
        return "rico"
    if iv < rv * (1 - band):
        return "barato"
    return "neutro"
