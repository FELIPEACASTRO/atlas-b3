"""Monitor de descalibração (PIT-break): série rolante do p-valor do PIT + detecção de quebra."""
import math
import random

from atlas_api.predict.engine import build_calibration_health


def _gbm(n: int, sigma: float = 0.02, seed: int = 7):
    random.seed(seed)
    px = 100.0
    ohlc: list[tuple] = []
    closes: list[float] = []
    for _ in range(n):
        c = px * math.exp(random.gauss(0.0, sigma))
        ohlc.append((px, max(px, c) * 1.001, min(px, c) * 0.999, c))
        closes.append(c)
        px = c
    return ohlc, closes


def test_health_structure_and_break_fields():
    ohlc, closes = _gbm(220)
    out = build_calibration_health(ticker="TEST", ohlc=ohlc, closes=closes, asof="2026-06-26", window=40)
    assert out["available"] is True
    assert len(out["series"]) == out["n"] and out["n"] > 0
    assert 0.0 <= out["current_p"] <= 1.0
    assert all(0.0 <= p <= 1.0 for p in out["series"])          # p-valores válidos
    assert isinstance(out["calibrated_now"], bool)
    # coerência do detector de quebra: calibrated_now ⇔ current_p ≥ 0.05; break só existe se houve p<0.05
    assert out["calibrated_now"] == (out["current_p"] >= 0.05)
    assert out["ever_broke"] == (out["last_break_days_ago"] is not None)
    if out["last_break_days_ago"] is not None:
        assert 0 <= out["last_break_days_ago"] < out["n"]


def test_health_refuses_when_history_is_short():
    ohlc, closes = _gbm(50)
    out = build_calibration_health(ticker="TEST", ohlc=ohlc, closes=closes, asof="2026-06-26", window=40)
    assert out["available"] is False                            # recusa honesta, não fabrica
