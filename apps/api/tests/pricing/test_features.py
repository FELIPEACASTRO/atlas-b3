from atlas_api.pricing.features import put_call_ratio, skew_25d, vrp


def test_vrp_is_iv_minus_rv():
    assert vrp(0.30, 0.22) == 0.08
    assert vrp(0.20, 0.25) == -0.05


def test_vrp_none_when_missing():
    assert vrp(None, 0.2) is None
    assert vrp(0.2, None) is None
    assert vrp(0.2, float("nan")) is None


def test_put_call_ratio():
    assert put_call_ratio(1000.0, 500.0) == 0.5
    assert put_call_ratio(0.0, 500.0) is None  # no call volume
    assert put_call_ratio(None, 5.0) is None


def test_skew_picks_closest_to_25_delta_put():
    # puts at delta -0.10, -0.25, -0.50 with IVs; 25d put IV = 0.34
    puts = [(-0.10, 0.40), (-0.25, 0.34), (-0.50, 0.30)]
    assert skew_25d(puts, atm_iv=0.30) == round(0.34 - 0.30, 4)  # +0.04 OTM-put skew


def test_skew_none_without_puts_or_atm():
    assert skew_25d([], 0.30) is None
    assert skew_25d([(-0.25, 0.34)], None) is None
