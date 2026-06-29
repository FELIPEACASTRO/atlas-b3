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


def yang_zhang(ohlc: list[tuple[float, float, float, float]]) -> float:
    """Annualized Yang-Zhang realized vol from ``(open, high, low, close)`` bars.

    Gap-robust (handles overnight jumps) and drift-independent — more efficient
    than close-to-close for daily B3 bars, and it uses the OHLC we already parse
    from COTAHIST. Needs >= 2 bars; returns NaN otherwise or on non-positive
    prices. (AIForge research finding: Yang-Zhang for B3 over close-to-close.)
    """
    n = len(ohlc)
    if n < 2:
        return float("nan")
    overnight: list[float] = []
    open_close: list[float] = []
    rs: list[float] = []
    for i in range(1, n):
        o, h, low, c = ohlc[i]
        prev_close = ohlc[i - 1][3]
        if min(o, h, low, c, prev_close) <= 0:
            return float("nan")
        overnight.append(math.log(o / prev_close))
        open_close.append(math.log(c / o))
        rs.append(math.log(h / c) * math.log(h / o) + math.log(low / c) * math.log(low / o))
    m = len(overnight)
    if m < 2:
        return float("nan")
    o_mean = sum(overnight) / m
    c_mean = sum(open_close) / m
    var_o = sum((x - o_mean) ** 2 for x in overnight) / (m - 1)
    var_c = sum((x - c_mean) ** 2 for x in open_close) / (m - 1)
    var_rs = sum(rs) / m
    k = 0.34 / (1.34 + (m + 1) / (m - 1))
    var_yz = var_o + k * var_c + (1.0 - k) * var_rs
    return math.sqrt(max(var_yz, 0.0)) * math.sqrt(TRADING_DAYS)
