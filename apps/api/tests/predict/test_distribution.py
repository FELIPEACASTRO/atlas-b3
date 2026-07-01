"""Densidade física da vol: Student-t (caudas) + ajuste via VRP + POP.

Distribuição dos log-retornos no horizonte T, centrada em 0 (drift=0 declarado),
escala t.q. o desvio-padrão = σ_fís·κ·√T, com σ_fís = rv + (1−λ)·vrp (κ = correção de cobertura).
"""
import math

import numpy as np
import pytest
from scipy import stats

from atlas_api.predict.distribution import physical_density, pop, quantiles


def test_vrp_shrinks_sigma():
    d = physical_density(spot=38.0, sigma_iv=0.31, rv=0.24, vrp=0.07, T=30 / 365, lam=0.5)
    assert d.sigma < 0.31 and d.sigma > 0.24          # σ_fís = 0.24 + 0.5*0.07 = 0.275


def test_pop_at_mean_is_half():
    d = physical_density(spot=38.0, sigma_iv=0.30, rv=0.30, vrp=0.0, T=30 / 365)
    assert abs(pop(d, target=38.0, side="above") - 0.5) < 0.02


def test_density_integrates_to_one():
    d = physical_density(spot=38.0, sigma_iv=0.30, rv=0.30, vrp=0.0, T=30 / 365)
    xs = np.linspace(-2.0, 2.0, 400000)               # ±2 em log-retorno = muitos σ
    area = float(np.trapezoid(d.logret_pdf(xs), xs))
    assert abs(area - 1.0) < 1e-3


def test_student_t_has_fatter_tail_than_normal():
    d = physical_density(spot=38.0, sigma_iv=0.30, rv=0.30, vrp=0.0, T=1.0, nu=5)
    hs = d.sigma * math.sqrt(1.0)                     # desvio no horizonte (T=1)
    p_t = 1.0 - d.logret_cdf(3.0 * hs)               # cauda da Student-t
    p_n = 1.0 - float(stats.norm.cdf(3.0 * hs, 0.0, hs))  # cauda da Normal de MESMO σ
    assert p_t > p_n                                  # t (ν finito) tem mais massa na cauda


def test_pop_above_below_complement():
    d = physical_density(spot=38.0, sigma_iv=0.30, rv=0.30, vrp=0.0, T=30 / 365)
    assert abs(pop(d, 40.0, "above") + pop(d, 40.0, "below") - 1.0) < 1e-9


def test_quantiles_monotonic_and_bracket_spot():
    d = physical_density(spot=38.0, sigma_iv=0.31, rv=0.24, vrp=0.07, T=30 / 365)
    q10, q50, q90 = quantiles(d, [0.10, 0.50, 0.90])
    assert q10 < q50 < q90
    assert abs(q50 - 38.0) < 1e-6                     # mediana da t centrada = spot


def test_kappa_widens_density_without_moving_sigma_or_median():
    # κ (correção de subcobertura) infla a LARGURA da densidade, não a previsão de vol nem a mediana
    base = physical_density(spot=38.0, sigma_iv=0.30, rv=0.30, vrp=0.0, T=30 / 365, kappa=1.0)
    wide = physical_density(spot=38.0, sigma_iv=0.30, rv=0.30, vrp=0.0, T=30 / 365, kappa=1.10)
    assert wide.sigma == base.sigma                              # σ_fís (E[RV]) intacto → VRP/painel não muda
    b = base.logret_ppf(0.90) - base.logret_ppf(0.10)
    w = wide.logret_ppf(0.90) - wide.logret_ppf(0.10)
    assert abs(w / b - 1.10) < 1e-9                              # largura do intervalo 80% cresce exatamente ×κ
    assert abs(wide.logret_ppf(0.5)) < 1e-12                     # mediana intacta (drift=0)


def test_physical_density_rejects_incoherent_vrp():
    # F6: vrp deve ser sigma_iv − rv; estados incoerentes são recusados
    with pytest.raises(ValueError):
        physical_density(spot=38.0, sigma_iv=0.40, rv=0.24, vrp=0.07, T=30 / 365)
