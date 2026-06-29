from atlas_api.data.corp_actions import adjust_strike


def test_strike_reduced_by_cash_dividend_factor():
    assert abs(adjust_strike(38.00, 0.9742) - 37.02) < 0.01


def test_no_adjustment_when_factor_is_one():
    assert adjust_strike(38.00, 1.0) == 38.00
