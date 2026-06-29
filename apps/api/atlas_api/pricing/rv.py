"""Realized volatility (close-to-close) and HAR components, pure stdlib."""
from __future__ import annotations

import math
import statistics

TRADING_DAYS = 252


def _log_returns(closes: list[float]) -> list[float]:
    return [math.log(closes[i + 1] / closes[i]) for i in range(len(closes) - 1)]


def realized_vol(closes: list[float], window: int = 21) -> float:
    """Annualized close-to-close realized vol over the last ``window`` returns.

    Returns ``nan`` when there are fewer than 2 returns available. Raises on an
    invalid ``window`` (``< 2``) so a ``window=0`` slicing bug can't silently
    consume the whole series.
    """
    if window < 2:
        raise ValueError("window must be >= 2")
    if len(closes) < 2:
        return float("nan")
    window_returns = _log_returns(closes)[-window:]
    if len(window_returns) < 2:
        return float("nan")
    return statistics.stdev(window_returns) * math.sqrt(TRADING_DAYS)


def har_components(closes: list[float]) -> dict:
    """HAR-style daily/weekly/monthly components from EOD closes.

    Honest caveat: with EOD close-to-close data, ``rv_d`` (window=2) is a noisy
    proxy for the daily HAR component — true HAR (Corsi 2009) uses intraday
    realized variance, which is a paid/plug-in data source (spec §6).
    """
    return {
        "rv_d": realized_vol(closes, window=2),
        "rv_w": realized_vol(closes, window=5),
        "rv_m": realized_vol(closes, window=21),
    }
