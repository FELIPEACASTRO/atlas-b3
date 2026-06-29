from atlas_api.pricing.american import crr_price
from atlas_api.pricing.bs import bs_price


def test_crr_european_converges_to_bs():
    crr = crr_price("call", 100, 100, 0.05, 0.0, 1.0, 0.20, steps=500, american=False)
    assert abs(crr - bs_price("call", 100, 100, 0.05, 0.0, 1.0, 0.20)) < 0.03


def test_american_call_no_dividend_equals_european():
    amer = crr_price("call", 100, 100, 0.05, 0.0, 1.0, 0.20, steps=500, american=True)
    euro = crr_price("call", 100, 100, 0.05, 0.0, 1.0, 0.20, steps=500, american=False)
    assert abs(amer - euro) < 1e-9


def test_american_put_has_early_exercise_premium():
    amer = crr_price("put", 100, 100, 0.08, 0.0, 1.0, 0.30, steps=500, american=True)
    euro = crr_price("put", 100, 100, 0.08, 0.0, 1.0, 0.30, steps=500, american=False)
    assert amer > euro
