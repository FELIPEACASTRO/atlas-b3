from atlas_api.pricing.risk import stress_pnl


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
