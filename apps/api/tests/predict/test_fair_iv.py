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


def test_max_gap_points_to_biggest_premium():
    T = 30 / 365
    # smile de put-skew: IV maior nas puts (k<0). Constrói variância crescente p/ k negativo.
    ks = [-0.2, -0.1, 0.0, 0.1, 0.2]
    ivs = [0.40, 0.34, 0.30, 0.29, 0.30]
    w = [iv * iv * T for iv in ivs]
    params = fit_svi(ks, w)
    out = fair_iv_smile(spot=100.0, forward=100.0, phys_vol=0.25, svi_params=params, T=T,
                        moneyness=[math.exp(k) for k in ks])
    # o maior gap deve estar na asa de put (strike mais baixo), onde a IV é maior
    assert out["max_gap"]["strike"] < 100.0
    assert out["max_gap"]["gap"] > 0.10                   # ~0.40 − 0.25
