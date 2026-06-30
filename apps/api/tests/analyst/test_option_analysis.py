from atlas_api.analyst.option_analysis import OptionCtx, analyze_option


def _ctx(**kw):
    base = dict(
        ticker="PETRA38", underlying="PETR4", kind="call", strike=38.0, venc="2026-07-17",
        dte=21, last=1.10, spot=38.5, iv=0.30, delta=0.55, gamma=0.04, vega=1.5,
        theta=-0.03, iv_rank=25.0, rv=0.22,
    )
    base.update(kw)
    return OptionCtx(**base)


def test_analysis_is_two_sided_and_labeled():
    a = analyze_option(_ctx())
    assert a.pros and a.contras            # never one-sided
    assert "decisão é sua" in a.veredito.lower()
    assert a.comprar and a.vender_sair
    assert len(a.gregas) == 4              # delta/gamma/vega/theta explained


def test_breakeven_and_max_loss():
    a = analyze_option(_ctx(kind="call", strike=38.0, last=1.10))
    assert a.breakeven == 39.10            # call: strike + premium
    assert a.max_perda_titular == 110.0    # premium x100
    p = analyze_option(_ctx(kind="put", strike=38.0, last=1.10, spot=37.5, delta=-0.45))
    assert p.breakeven == 36.90            # put: strike - premium


def test_low_iv_rank_flags_cheap_vol_pro():
    a = analyze_option(_ctx(iv_rank=15.0))
    assert any("barata" in p.lower() for p in a.pros)


def test_high_iv_rank_flags_expensive_vol_con():
    a = analyze_option(_ctx(iv_rank=85.0))
    assert any("cara" in c.lower() for c in a.contras)


def test_handles_missing_greeks_gracefully():
    a = analyze_option(_ctx(iv=None, delta=None, gamma=None, vega=None, theta=None, iv_rank=None, rv=None))
    assert a.gregas == [] and a.contras  # no greeks, still two-sided and useful
    assert a.max_perda_titular == 110.0
