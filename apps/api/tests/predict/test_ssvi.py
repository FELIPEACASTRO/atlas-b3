"""Smile SVI (Gatheral) + densidade risco-neutra (Breeden-Litzenberger) — densidade de MERCADO.

Para o painel "mercado vs físico": a smile real dá a densidade risco-neutra do retorno;
comparamos com a nossa densidade física. Checagem de no-arbitragem de butterfly: g(k) ≥ 0.
"""
import numpy as np

from atlas_api.predict.ssvi import (
    fit_market_smile,
    fit_svi,
    risk_neutral_density,
    svi_total_variance,
)


def test_svi_fit_recovers_the_smile():
    true = (0.04, 0.10, -0.3, 0.0, 0.10)               # a,b,rho,m,s
    k = np.linspace(-0.5, 0.5, 41)
    w = svi_total_variance(true, k)
    params = fit_svi(k, w)
    assert np.max(np.abs(svi_total_variance(params, k) - w)) < 1e-3


def test_density_integrates_to_one_and_nonneg_when_arbfree():
    params = (0.04, 0.10, -0.3, 0.0, 0.20)
    k = np.linspace(-2.0, 2.0, 8000)
    rnd = risk_neutral_density(params, k)
    assert rnd["arbitrage_free"] is True
    p = rnd["density"]
    assert np.all(p >= -1e-9)                           # densidade ≥ 0
    assert abs(np.trapezoid(p, k) - 1.0) < 1e-2         # integra ≈ 1


def test_density_flags_butterfly_arbitrage():
    bad = (0.005, 0.9, -0.8, 0.0, 0.02)                 # asas íngremes + s pequeno → g(k) < 0
    k = np.linspace(-1.0, 1.0, 4000)
    assert risk_neutral_density(bad, k)["arbitrage_free"] is False


def test_fit_market_smile_gates_on_liquidity():
    spot, T = 38.0, 30 / 365
    # poucos strikes → recusa honesta
    assert fit_market_smile([37.0, 38.0], [0.30, 0.31], spot=spot, T=T) is None
    # smile sintética com strikes suficientes → ajusta e devolve ATM + densidade
    ks = np.linspace(-0.4, 0.4, 21)
    strikes = (spot * np.exp(ks)).tolist()
    ivs = np.sqrt(svi_total_variance((0.04, 0.1, -0.3, 0.0, 0.1), ks) / T).tolist()
    out = fit_market_smile(strikes, ivs, spot=spot, T=T)
    assert out is not None
    assert out["atm_vol"] > 0
    assert out["usable"] is True and out["arbitrage_free"] is True   # smile limpa → confiável
    assert out["rmse"] < 0.01                                        # recupera a smile SVI
