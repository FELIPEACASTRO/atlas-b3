"""Underlying-level option features (pure stdlib): VRP, put/call ratio, skew.

These are labeled, point-in-time descriptors built from the same EOD chain the
rest of the engine uses — never recommendations. Each returns None when its
inputs are missing rather than fabricating a number (honesty rule).
"""
from __future__ import annotations

import math

_PUT_25D = -0.25  # the 25-delta put used as the OTM skew reference


def _ok(x) -> bool:
    return x is not None and not (isinstance(x, float) and math.isnan(x))


def vrp(atm_iv: float | None, rv: float | None) -> float | None:
    """Variance-risk-premium proxy in vol units: ATM IV minus realized vol.

    Positive => implied richer than realized (you are paid to sell variance);
    this is the number behind the rico/barato/neutro label, surfaced explicitly.
    """
    if not (_ok(atm_iv) and _ok(rv)):
        return None
    return round(atm_iv - rv, 4)


def put_call_ratio(call_volume: float | None, put_volume: float | None) -> float | None:
    """Put/call volume ratio for an underlying; None when there is no call volume."""
    if not (_ok(call_volume) and _ok(put_volume)) or call_volume <= 0:
        return None
    return round(put_volume / call_volume, 3)


def skew_25d(put_deltas: list[tuple[float, float]], atm_iv: float | None) -> float | None:
    """OTM-put skew: (25-delta put IV) minus ATM IV, in vol points.

    ``put_deltas`` is a list of (delta, iv) for the underlying's puts (delta<0).
    Picks the put whose delta is closest to -0.25. A steep positive skew means
    crash insurance is bid. None when no put or no ATM IV is available.
    """
    if not _ok(atm_iv):
        return None
    candidates = [(d, iv) for d, iv in put_deltas if _ok(d) and _ok(iv)]
    if not candidates:
        return None
    _, put_iv = min(candidates, key=lambda di: abs(di[0] - _PUT_25D))
    return round(put_iv - atm_iv, 4)
