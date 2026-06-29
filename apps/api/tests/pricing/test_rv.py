import math
import statistics

import pytest

from atlas_api.pricing.rv import har_components, realized_vol, yang_zhang


def test_rv_constant_series_is_zero():
    assert realized_vol([10.0] * 30) == 0.0


def test_rv_matches_manual():
    closes = [100, 101, 100, 102, 101, 103]
    lr = [math.log(closes[i + 1] / closes[i]) for i in range(len(closes) - 1)]
    expected = statistics.stdev(lr) * math.sqrt(252)
    assert abs(realized_vol(closes, window=5) - expected) < 1e-9


def test_har_components_keys():
    closes = [100 + (i % 3) for i in range(40)]
    h = har_components(closes)
    assert set(h) == {"rv_d", "rv_w", "rv_m"}


def test_realized_vol_invalid_window_raises():
    with pytest.raises(ValueError):
        realized_vol([100, 101, 102], window=0)


def test_yang_zhang_constant_is_zero():
    bars = [(10.0, 10.0, 10.0, 10.0)] * 20
    assert yang_zhang(bars) == 0.0


def test_yang_zhang_positive_and_finite():
    bars = []
    for i in range(30):
        op = 100 + (i % 5) * 0.5
        cl = op + (0.7 if i % 2 == 0 else -0.7)
        hi = max(op, cl) + 0.5
        lo = min(op, cl) - 0.5
        bars.append((op, hi, lo, cl))
    v = yang_zhang(bars)
    assert math.isfinite(v) and v > 0


def test_yang_zhang_short_series_is_nan():
    assert math.isnan(yang_zhang([(10.0, 10.0, 10.0, 10.0)]))
