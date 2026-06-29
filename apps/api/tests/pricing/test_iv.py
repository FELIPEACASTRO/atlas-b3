import math

from atlas_api.pricing.bs import bs_price
from atlas_api.pricing.iv import implied_vol


def test_iv_recovers_sigma():
    price = bs_price("call", 100, 100, 0.05, 0.0, 1.0, 0.20)
    iv = implied_vol("call", price, 100, 100, 0.05, 0.0, 1.0)
    assert abs(iv - 0.20) < 1e-4


def test_iv_nan_below_intrinsic():
    # price far below the no-arbitrage lower bound has no root -> NaN, not garbage
    iv = implied_vol("call", 0.01, 100, 50, 0.05, 0.0, 1.0)
    assert math.isnan(iv)
