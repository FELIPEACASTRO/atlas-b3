"""Mapa de Prêmio (Edge Map) — o diferencial: prêmio físico-vs-risco-neutro por strike.

Para cada strike, compara P_mercado(S_T ≤ K) (risco-neutra, da smile SVI) com P_física(S_T ≤ K)
(nossa densidade calibrada). O gap = o prêmio que o mercado cobra sobre o justo, por moneyness.
É a decomposição do VRP ao longo da smile (pricing kernel). Verificado em cenário conhecido.
"""
import math

import numpy as np

from atlas_api.predict.edge import premium_map


def test_edge_positive_where_market_overprices_downside():
    # mercado (risco-neutra) MAIS LARGO que a física → precifica mais cauda; downside sobrevalorizado.
    spot = 100.0
    grid = np.linspace(-0.6, 0.6, 4000)
    rn = np.exp(-grid ** 2 / (2 * 0.20 ** 2))          # RN "densidade" ~ N(0, 0.20) (larga)
    rn = rn / np.trapezoid(rn, grid)
    phys_sd = 0.12                                       # física mais estreita (0.12)

    def phys_cdf(x):
        return 0.5 * (1.0 + math.erf(x / (phys_sd * math.sqrt(2))))

    m = premium_map(spot=spot, forward=spot, phys_cdf=phys_cdf, svi_k=grid, svi_density=rn,
                    moneyness=[0.90, 1.00, 1.10])
    by = {round(r["moneyness"], 2): r for r in m}
    # downside (K=90): mercado precifica mais prob de cair abaixo → edge>0 (sobrevalorizado, vender)
    assert by[0.90]["edge"] > 0.02
    # ATM (K=100): ambos ~0.5 → edge ~ 0
    assert abs(by[1.00]["edge"]) < 0.02
    # upside (K=110): P(S<=110) — mercado (largo) dá mais massa acima tb, mas P(S<=K) alto nos dois; edge pequeno
    assert "p_market" in by[1.10] and "p_physical" in by[1.10]


def test_edge_is_zero_when_densities_match():
    spot = 50.0
    grid = np.linspace(-0.5, 0.5, 3000)
    sd = 0.15
    dens = np.exp(-grid ** 2 / (2 * sd ** 2))
    dens = dens / np.trapezoid(dens, grid)

    def phys_cdf(x):
        return 0.5 * (1.0 + math.erf(x / (sd * math.sqrt(2))))

    m = premium_map(spot=spot, forward=spot, phys_cdf=phys_cdf, svi_k=grid, svi_density=dens,
                    moneyness=[0.9, 1.0, 1.1])
    for r in m:
        assert abs(r["edge"]) < 0.02                    # densidades iguais → sem edge


def test_premium_map_fields_and_monotone_cdfs():
    spot = 38.0
    grid = np.linspace(-0.5, 0.5, 2000)
    dens = np.exp(-grid ** 2 / (2 * 0.2 ** 2))
    dens /= np.trapezoid(dens, grid)
    m = premium_map(spot=spot, forward=spot, phys_cdf=lambda x: 0.5 * (1 + math.erf(x / (0.18 * math.sqrt(2)))),
                    svi_k=grid, svi_density=dens, moneyness=[0.85, 0.95, 1.0, 1.05, 1.15])
    strikes = [r["strike"] for r in m]
    pm = [r["p_market"] for r in m]
    assert strikes == sorted(strikes)
    assert all(0.0 <= x <= 1.0 for x in pm)
    assert pm == sorted(pm)                             # CDF de mercado é monotônica em K
