import math

from atlas_api.pricing.bs import bs_price, bs_greeks


def test_bs_call_known_value():
    # S=100, K=100, r=0.05, q=0, T=1, sigma=0.2 -> call ~= 10.450584
    p = bs_price("call", 100, 100, 0.05, 0.0, 1.0, 0.20)
    assert abs(p - 10.450584) < 1e-3


def test_bs_put_call_parity():
    c = bs_price("call", 100, 95, 0.05, 0.0, 0.5, 0.25)
    p = bs_price("put", 100, 95, 0.05, 0.0, 0.5, 0.25)
    assert abs((c - p) - (100 - 95 * math.exp(-0.05 * 0.5))) < 1e-6


def test_greeks_sane():
    g = bs_greeks("call", 100, 100, 0.05, 0.0, 1.0, 0.20)
    assert 0 < g["delta"] < 1
    assert g["gamma"] > 0
    assert g["vega"] > 0
