import math

import pytest

from atlas_api.pricing.bs import bs_price
from atlas_api.pricing.iv import implied_vol


def test_iv_recovers_sigma():
    price = bs_price("call", 100, 100, 0.05, 0.0, 1.0, 0.20)
    iv = implied_vol("call", price, 100, 100, 0.05, 0.0, 1.0)
    assert abs(iv - 0.20) < 1e-4


def test_iv_put_recovers_sigma():
    price = bs_price("put", 100, 100, 0.05, 0.0, 1.0, 0.30)
    iv = implied_vol("put", price, 100, 100, 0.05, 0.0, 1.0)
    assert abs(iv - 0.30) < 1e-4


def test_iv_deep_otm_recovers():
    price = bs_price("call", 100, 150, 0.05, 0.0, 0.5, 0.40)
    iv = implied_vol("call", price, 100, 150, 0.05, 0.0, 0.5)
    assert abs(iv - 0.40) < 1e-4


def test_iv_nan_below_intrinsic():
    iv = implied_vol("call", 0.01, 100, 50, 0.05, 0.0, 1.0)
    assert math.isnan(iv)


def test_iv_nan_above_upper_bound():
    iv = implied_vol("call", 100.5, 100, 100, 0.05, 0.0, 1.0)
    assert math.isnan(iv)


def test_iv_near_lower_bracket_not_garbage():
    # near-zero time value must NOT yield a false ~5.0 vol (review finding #1)
    price = bs_price("call", 100, 100, 0.05, 0.0, 1.0, 1e-6)
    iv = implied_vol("call", price, 100, 100, 0.05, 0.0, 1.0)
    assert math.isnan(iv) or iv < 0.01


def test_iv_invalid_kind_raises():
    with pytest.raises(ValueError):
        implied_vol("foo", 0.0, 100, 100, 0.05, 0.0, 1.0)


def test_iv_vega_near_zero_returns_nan_not_false_value():
    # deep OTM short-dated put: vega ~ 0 -> no reliable IV (audit A1, was ~0.31)
    price = bs_price("put", 100, 50, 0.0, 0.0, 0.05, 0.40)
    assert math.isnan(implied_vol("put", price, 100, 50, 0.0, 0.0, 0.05))


def test_iv_deep_itm_returns_nan_not_floor():
    # deep ITM low-vol call: vega ~ 0 -> NaN, not the 1e-6 floor (audit A1)
    price = bs_price("call", 300, 100, 0.10, 0.0, 2.0, 0.05)
    assert math.isnan(implied_vol("call", price, 300, 100, 0.10, 0.0, 2.0))
