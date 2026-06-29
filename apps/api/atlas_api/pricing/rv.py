"""Realized volatility (close-to-close) and HAR components, pure stdlib."""
from __future__ import annotations

import math
import statistics

TRADING_DAYS = 252


def _log_returns(closes: list[float]) -> list[float]:
    return [math.log(closes[i + 1] / closes[i]) for i in range(len(closes) - 1)]


def realized_vol(closes: list[float], window: int = 21) -> float:
    """Annualized close-to-close realized vol over the last ``window`` returns."""
    if len(closes) < 2:
        return float("nan")
    window_returns = _log_returns(closes)[-window:]
    if len(window_returns) < 2:
        return float("nan")
    return statistics.stdev(window_returns) * math.sqrt(TRADING_DAYS)


def har_components(closes: list[float]) -> dict:
    """HAR-style daily/weekly/monthly realized-vol components."""
    return {
        "rv_d": realized_vol(closes, window=2),
        "rv_w": realized_vol(closes, window=5),
        "rv_m": realized_vol(closes, window=21),
    }
