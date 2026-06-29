from atlas_api.analyst.briefing import Setup, build_briefing


def _setup() -> Setup:
    return Setup(
        ticker="PETRG38",
        underlying="PETR4",
        structure="venda_premio",
        iv=0.42,
        rv=0.33,
        max_gain_per_lot=0.62,
        max_loss_per_lot=0.38,
        breakeven=38.62,
        delta=0.30,
        liquidity_brl=88_000_000,
        dte=24,
        capital=60_000,
    )


def test_briefing_has_both_sides_and_three_profiles():
    b = build_briefing(_setup())
    assert b.setup_facts
    assert len(b.case_for) >= 1
    assert len(b.case_against) >= 1  # honesty: never one-sided
    assert set(b.sizing) == {"conservador", "moderado", "agressivo"}


def test_sizing_scales_with_boldness():
    b = build_briefing(_setup())
    assert (
        b.sizing["conservador"].max_loss_brl
        < b.sizing["moderado"].max_loss_brl
        < b.sizing["agressivo"].max_loss_brl
    )


def test_short_vol_flags_tail_risk():
    b = build_briefing(_setup())
    assert any("cauda" in c.lower() for c in b.case_against)


def test_risk_reward_ratio():
    b = build_briefing(_setup())
    assert abs(b.risk_reward.ratio - (0.62 / 0.38)) < 1e-6


def test_verdict_is_honest_not_a_call():
    b = build_briefing(_setup())
    low = b.verdict.lower()
    assert "a decisão é sua" in low
    assert "garantido" not in low and "recomendo" not in low
