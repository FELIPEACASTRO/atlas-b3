"""Consultor — catálogo de estratégias montadas da cadeia real e ranqueadas por tese."""
from atlas_api.predict.distribution import physical_density
from atlas_api.predict.strategies import build_catalog


def _synth_chain(spot=38.0):
    chain = []
    for k in (32, 34, 36, 38, 40, 42, 44):
        chain.append({"kind": "call", "strike": float(k), "last": round(max(spot - k, 0) + 1.6 - 0.1 * (k - spot) * 0.05, 2), "iv": 0.30, "delta": 0.5})
        chain.append({"kind": "put", "strike": float(k), "last": round(max(k - spot, 0) + 1.6, 2), "iv": 0.30, "delta": -0.5})
    return [o for o in chain if o["last"] > 0]


def test_catalog_builds_and_ranks_for_bullish_view():
    d = physical_density(spot=38.0, sigma_iv=0.30, rv=0.30, vrp=0.0, T=30 / 365)
    cat = build_catalog(38.0, d, _synth_chain(), visao="alta", capital=50000)
    assert len(cat) >= 3
    s = cat[0]
    assert {"name", "thesis", "pop", "ev", "max_loss", "max_gain", "legs", "lots"} <= set(s)
    assert s["thesis"] == "alta"                       # visão de alta → estrutura de alta no topo


def test_catalog_neutral_view_surfaces_vol_structures():
    d = physical_density(spot=38.0, sigma_iv=0.30, rv=0.30, vrp=0.0, T=30 / 365)
    cat = build_catalog(38.0, d, _synth_chain(), visao="neutro", capital=50000)
    assert any(s["thesis"] == "neutro" for s in cat[:3])


def test_catalog_sizing_respects_capital_for_defined_risk():
    d = physical_density(spot=38.0, sigma_iv=0.30, rv=0.30, vrp=0.0, T=30 / 365)
    cat = build_catalog(38.0, d, _synth_chain(), visao="alta", capital=8000)
    for s in cat:
        if s.get("defined_risk") and s["lots"] > 0:
            assert abs(s["max_loss"]) <= 8000 + 1e-6   # risco definido cabe no capital


def test_catalog_legs_describe_the_structure():
    d = physical_density(spot=38.0, sigma_iv=0.30, rv=0.30, vrp=0.0, T=30 / 365)
    cat = build_catalog(38.0, d, _synth_chain(), visao="alta", capital=50000)
    legs = cat[0]["legs"]
    assert all({"kind", "action", "strike", "premium"} <= set(leg) for leg in legs)
