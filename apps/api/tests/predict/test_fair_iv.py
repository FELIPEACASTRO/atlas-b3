"""Fair IV: smile de mercado (SVI) vs vol física justa, gap em vol points por strike."""
import math

from atlas_api.predict.fair_iv import fair_iv_smile
from atlas_api.predict.ssvi import fit_svi


def _flat_svi_at(vol: float, T: float):
    # ajusta um SVI a uma smile PLANA na vol `vol` → variância total constante vol²·T
    ks = [-0.2, -0.1, 0.0, 0.1, 0.2]
    w = [vol * vol * T for _ in ks]
    return fit_svi(ks, w)


def test_gap_is_market_minus_physical_vol():
    T = 30 / 365
    params = _flat_svi_at(0.30, T)                        # mercado plano em 30%
    out = fair_iv_smile(spot=100.0, forward=100.0, phys_vol=0.24, svi_params=params, T=T,
                        moneyness=[0.9, 1.0, 1.1])
    atm = [r for r in out["smile"] if r["moneyness"] == 1.0][0]
    assert abs(atm["iv_market"] - 0.30) < 0.02            # recupera a IV de mercado
    assert atm["iv_fair"] == 0.24                          # linha justa = vol física
    assert abs(atm["gap"] - (atm["iv_market"] - 0.24)) < 1e-9   # gap = mercado − física


def test_decomposes_level_vrp_and_skew():
    T = 30 / 365
    # smile de put-skew: IV maior nas puts (k<0). Constrói variância crescente p/ k negativo.
    ks = [-0.2, -0.1, 0.0, 0.1, 0.2]
    ivs = [0.40, 0.34, 0.30, 0.29, 0.30]
    w = [iv * iv * T for iv in ivs]
    params = fit_svi(ks, w)
    out = fair_iv_smile(spot=100.0, forward=100.0, phys_vol=0.25, svi_params=params, T=T,
                        moneyness=[math.exp(k) for k in ks])
    # NÍVEL (VRP near-the-money) ≈ IV ATM (0.30) − física (0.25) = ~0.05 — a leitura limpa
    assert 0.02 < out["level_gap"] < 0.08
    # SKEW: a put funda excede o nível → componente de skew positivo e material, na asa de put
    assert out["skew_premium"] > 0.05
    assert out["put_wing_strike"] < 100.0                   # ~0.40 − 0.25
