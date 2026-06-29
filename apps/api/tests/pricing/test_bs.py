import math

from atlas_api.pricing.bs import bs_greeks, bs_price


def test_bs_call_known_value():
    p = bs_price("call", 100, 100, 0.05, 0.0, 1.0, 0.20)
    assert abs(p - 10.450584) < 1e-3


def test_bs_put_call_parity():
    c = bs_price("call", 100, 95, 0.05, 0.0, 0.5, 0.25)
    p = bs_price("put", 100, 95, 0.05, 0.0, 0.5, 0.25)
    assert abs((c - p) - (100 - 95 * math.exp(-0.05 * 0.5))) < 1e-6


def test_call_greeks_sane():
    g = bs_greeks("call", 100, 100, 0.05, 0.0, 1.0, 0.20)
    assert 0 < g["delta"] < 1
    assert g["gamma"] > 0
    assert g["vega"] > 0


def test_put_greeks_sane():
    g = bs_greeks("put", 100, 100, 0.05, 0.0, 1.0, 0.20)
    assert -1 < g["delta"] < 0
    assert g["gamma"] > 0
    assert g["vega"] > 0


def test_theta_negative_typical_call():
    g = bs_greeks("call", 100, 100, 0.05, 0.0, 1.0, 0.20)
    assert g["theta"] < 0


def test_greeks_degenerate_at_expiry_no_crash():
    g = bs_greeks("call", 100, 100, 0.05, 0.0, 0.0, 0.20)
    assert g["gamma"] == 0.0 and g["vega"] == 0.0


def test_greeks_zero_sigma_no_crash():
    g = bs_greeks("call", 100, 100, 0.05, 0.0, 1.0, 0.0)
    assert g["vega"] == 0.0


def test_price_nonpositive_inputs_return_nan():
    assert math.isnan(bs_price("call", -1.0, 100, 0.05, 0.0, 1.0, 0.2))
    assert math.isnan(bs_price("call", 100, 0.0, 0.05, 0.0, 1.0, 0.2))
