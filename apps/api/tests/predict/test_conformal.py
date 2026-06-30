"""Conformal — cobertura marginal GARANTIDA, distribution-free (a maior alavanca de honestidade).

split_conformal padroniza o resíduo por σ e usa o quantil empírico com correção finita,
então a cobertura ≥ 1−α mesmo com a densidade-base mal especificada. aci_update adapta α
ao regime (Gibbs-Candès) com clamp obrigatório em [0,1].
"""
import numpy as np

from atlas_api.predict.conformal import aci_update, split_conformal


def test_conformal_guarantees_coverage_under_misspecification():
    rng = np.random.default_rng(1)
    y = rng.standard_t(4, 2000) * 0.05                      # cauda gorda real
    mu = np.zeros_like(y)
    sigma = np.full_like(y, 0.03)                           # σ SUBestimada de propósito
    lo, hi = split_conformal(y[:1000], mu[:1000], sigma[:1000], mu[1000:], sigma[1000:], alpha=0.2)
    cov = np.mean((y[1000:] >= lo) & (y[1000:] <= hi))
    assert cov >= 0.79                                      # garante ≥ 1−α−1/(n+1) ≈ 0.799


def test_conformal_coverage_under_heteroscedastic_sigma():
    rng = np.random.default_rng(3)
    sig = np.linspace(0.02, 0.08, 2000)                     # σ cresce (heterocedástico)
    y = rng.standard_normal(2000) * sig
    lo, hi = split_conformal(y[:1000], np.zeros(1000), sig[:1000], np.zeros(1000), sig[1000:], alpha=0.2)
    assert np.mean((y[1000:] >= lo) & (y[1000:] <= hi)) >= 0.79  # padronização por σ mantém cobertura


def test_aci_reacts_to_shift_and_stays_bounded():
    a = 0.2
    for _ in range(8):
        a = aci_update(a, covered=False, gamma=0.02)        # série de "não cobriu"
    assert 0.0 < a < 0.2                                     # α desce (alarga) SEM divergir (clamp [0,1])


def test_aci_recovers_when_covered():
    a = 0.05
    for _ in range(100):
        a = aci_update(a, covered=True, gamma=0.02)          # série de "cobriu" → α sobe (aperta)
    assert a > 0.05 and a <= 1.0
