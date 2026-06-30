from atlas_api.pricing.risk import payoff_at_expiry, payoff_grid, stress_pnl


def test_stock_pnl_is_linear_in_spot():
    # 100 shares (delta=100), spot 40, +5% -> +R$200
    assert stress_pnl([(100.0, 0.0, 0.0, 40.0)], 0.05) == 200.0
    assert stress_pnl([(100.0, 0.0, 0.0, 40.0)], -0.05) == -200.0


def test_gamma_adds_convexity():
    # long gamma helps on both sides: delta=0, gamma=10, spot=40, shock=10% -> dS=4
    # pnl = 0.5*10*16 = 80, symmetric
    assert stress_pnl([(0.0, 10.0, 0.0, 40.0)], 0.10) == 80.0
    assert stress_pnl([(0.0, 10.0, 0.0, 40.0)], -0.10) == 80.0


def test_vega_pnl_on_vol_move():
    # vega=500 (position, per 1.00 vol), +5 vol points = +0.05 -> +25
    assert stress_pnl([(0.0, 0.0, 500.0, 40.0)], 0.0, dvol=0.05) == 25.0


def test_mixed_book_sums_per_underlying_spot():
    # shock applies to each position's own spot
    pos = [(100.0, 0.0, 0.0, 40.0), (50.0, 0.0, 0.0, 80.0)]  # +10% each
    assert stress_pnl(pos, 0.10) == round(100 * 4 + 50 * 8, 2)  # 400 + 400 = 800


def test_zero_shock_is_zero():
    assert stress_pnl([(100.0, 5.0, 200.0, 40.0)], 0.0) == 0.0


def test_payoff_long_call_caps_loss_at_premium():
    # long 1 call, K=100, spot=100, premium 5, mult 100
    pos = [("call", 100.0, 100.0, 1.0, 100, 5.0)]
    assert payoff_at_expiry(pos, 0.0) == -500.0     # all time value lost at expiry, ATM
    assert payoff_at_expiry(pos, -0.20) == -500.0   # downside loss capped at the premium
    assert payoff_at_expiry(pos, 0.20) == 1500.0    # 20 intrinsic - 5 premium, x100


def test_payoff_short_put_keeps_premium_until_struck():
    pos = [("put", 90.0, 100.0, -1.0, 100, 4.0)]   # short 1 put
    assert payoff_at_expiry(pos, 0.0) == 400.0      # keep the 4.00 premium x100 if unmoved
    assert payoff_at_expiry(pos, -0.20) == -600.0   # spot 80 -> intrinsic 10; -1*100*(10-4)


def test_payoff_stock_leg_is_linear():
    assert payoff_at_expiry([(None, None, 40.0, 100.0, 1, 0.0)], 0.10) == 400.0


def test_payoff_grid_spans_range():
    g = payoff_grid()
    assert len(g) == 41 and abs(g[0] + 0.30) < 1e-9 and abs(g[-1] - 0.30) < 1e-9
