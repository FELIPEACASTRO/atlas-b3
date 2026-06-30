import math

from atlas_api.pricing.american import (
    american_greeks,
    american_iv,
    bjerksund_stensland,
    crr_price,
)
from atlas_api.pricing.bs import bs_price


def test_deep_itm_negative_carry_never_below_intrinsic():
    # regression: the old beta>60 guard returned the European value (far below
    # intrinsic) for deep-ITM negative-carry options, underpricing 40-98%.
    # A plain American put on a non-dividend stock at the Selic rate must be >= 25.
    cases = [
        ("put", 75.0, 100.0, 0.105, 0.0, 1.0, 0.05),    # ~25 intrinsic
        ("call", 110.0, 100.0, 0.105, 0.20, 1.0, 0.05),  # ~10 intrinsic (q > r)
        ("call", 110.0, 100.0, 0.05, 0.30, 1.0, 0.09),   # ~10 intrinsic
    ]
    for kind, S, K, r, q, T, sigma in cases:
        intrinsic = max(0.0, S - K) if kind == "call" else max(0.0, K - S)
        price = bjerksund_stensland(kind, S, K, r, q, T, sigma)
        crr = crr_price(kind, S, K, r, q, T, sigma, steps=600)
        assert price >= intrinsic - 1e-6, (kind, S, K, price, intrinsic)
        assert abs(price - crr) <= 0.05 * max(crr, 1.0), (kind, price, crr)


def test_american_iv_nan_at_intrinsic_plateau():
    # on the immediate-exercise plateau the American value is flat in sigma, so a
    # quote at intrinsic has no implied vol — must be nan, not a fabricated number.
    intrinsic = 130.0 - 100.0
    assert math.isnan(american_iv("call", intrinsic, 130.0, 100.0, 0.05, 0.30, 0.5))


def test_bjerksund_agrees_with_crr_binomial():
    # the closed-form American price must track the binomial ground truth
    worst = 0.0
    for kind in ("call", "put"):
        for S in (90, 100, 110):
            for q in (0.0, 0.04, 0.10):
                for T in (0.25, 1.0):
                    a = bjerksund_stensland(kind, S, 100, 0.08, q, T, 0.30)
                    c = crr_price(kind, S, 100, 0.08, q, T, 0.30, steps=400)
                    if c > 1.0:
                        worst = max(worst, abs(a - c) / c)
    assert worst < 0.04  # within 4% of CRR across the grid


def test_bjerksund_call_no_dividend_equals_european():
    a = bjerksund_stensland("call", 100, 100, 0.08, 0.0, 1.0, 0.30)
    assert abs(a - bs_price("call", 100, 100, 0.08, 0.0, 1.0, 0.30)) < 1e-6


def test_bjerksund_american_put_above_european():
    a = bjerksund_stensland("put", 100, 110, 0.10, 0.0, 0.5, 0.30)
    assert a > bs_price("put", 100, 110, 0.10, 0.0, 0.5, 0.30)  # early-exercise premium


def test_american_iv_round_trips():
    for kind in ("call", "put"):
        price = bjerksund_stensland(kind, 100, 100, 0.08, 0.04, 0.5, 0.35)
        iv = american_iv(kind, price, 100, 100, 0.08, 0.04, 0.5)
        assert abs(iv - 0.35) < 1e-3


def test_american_iv_below_intrinsic_is_nan():
    assert math.isnan(american_iv("put", 0.5, 100, 120, 0.05, 0.0, 1.0))  # < intrinsic 20


def test_american_iv_below_european_iv_for_put():
    # American price >= European, so repricing it with the American model needs a
    # LOWER vol than the European solver would infer
    from atlas_api.pricing.iv import implied_vol
    price = bjerksund_stensland("put", 100, 105, 0.10, 0.0, 1.0, 0.40)
    assert american_iv("put", price, 100, 105, 0.10, 0.0, 1.0) <= implied_vol("put", price, 100, 105, 0.10, 0.0, 1.0)


def test_american_greeks_signs():
    g = american_greeks("call", 100, 100, 0.08, 0.0, 0.5, 0.30)
    assert 0 < g["delta"] < 1 and g["gamma"] > 0 and g["vega"] > 0 and g["theta"] < 0
    gp = american_greeks("put", 100, 100, 0.08, 0.0, 0.5, 0.30)
    assert -1 < gp["delta"] < 0 and gp["gamma"] > 0 and gp["vega"] > 0


def test_american_greeks_short_dated_theta_not_zero():
    # 1-day ATM option carries the LARGEST decay (rolls to intrinsic at expiry),
    # not 0 — regression for the old `else 0` that zeroed near-expiry theta.
    g = american_greeks("call", 100, 100, 0.08, 0.0, 1 / 252, 0.30)
    assert g["theta"] < 0
    g2 = american_greeks("put", 100, 100, 0.08, 0.0, 0.5 / 252, 0.30)
    assert g2["theta"] < 0


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


def test_crr_invalid_p_returns_nan():
    import math

    # high rate + low vol + few steps -> p out of [0,1] -> NaN, not a clamped
    # wrong number (audit A2: clamp produced errors up to ~95%)
    assert math.isnan(crr_price("call", 100, 90, 1.0, 0.0, 1.0, 0.02, steps=20))
