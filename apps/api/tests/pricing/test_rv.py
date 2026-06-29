import math
import statistics

import pytest

from atlas_api.pricing.rv import har_components, realized_vol


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
