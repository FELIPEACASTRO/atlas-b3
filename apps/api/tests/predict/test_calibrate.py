"""Recalibração isotônica (PAVA pure-Python) — motivada pela medição do ML-1.

O PIT do ML-1 flagrou forma imperfeita (ν=5 fixo) em nomes reais. A recalibração de
Kuleshov ajusta uma função isotônica R (o ECDF dos PIT de calibração) tal que R∘CDF
fique uniforme. Validação honesta: ajusta numa metade, melhora a uniformidade na outra.
"""
import numpy as np
from scipy import stats

from atlas_api.predict.calibrate import IsotonicRecalibrator, online_recalibrator, pava


def test_pava_idempotent_on_monotone():
    y = np.array([0.1, 0.2, 0.3, 0.5])
    assert np.allclose(pava(y), y)                          # já não-decrescente → inalterado


def test_pava_enforces_monotonicity_and_preserves_mean():
    y = np.array([0.3, 0.1, 0.2, 0.9])
    out = pava(y)
    assert np.all(np.diff(out) >= -1e-12)                  # saída não-decrescente
    assert abs(out.mean() - y.mean()) < 1e-9               # PAVA (L2) preserva a média


def test_isotonic_recalibration_improves_pit_uniformity_out_of_sample():
    rng = np.random.default_rng(0)
    y = rng.normal(0, 0.05, 4000)
    pit = stats.norm.cdf(y, 0, 0.03)                       # modelo subdisperso → PIT em U
    cal, test = pit[:2000], pit[2000:]
    rec = IsotonicRecalibrator().fit(cal)
    p_before = stats.kstest(test, "uniform").pvalue
    p_after = stats.kstest(rec.apply(test), "uniform").pvalue
    assert p_after > p_before                              # recalibração melhora a uniformidade
    assert p_after > 0.05                                  # e passa no KS (forma calibrada)


def test_recalibrator_is_monotone_and_bounded():
    rng = np.random.default_rng(1)
    rec = IsotonicRecalibrator().fit(rng.uniform(0, 1, 500))
    grid = np.linspace(0, 1, 50)
    out = rec.apply(grid)
    assert np.all(np.diff(out) >= -1e-9)                   # R é monotônica
    assert out.min() >= 0.0 and out.max() <= 1.0           # e mapeia em [0,1]


def test_inverse_round_trips_with_apply():
    rng = np.random.default_rng(2)
    rec = IsotonicRecalibrator().fit(rng.uniform(0, 1, 1000))
    qs = np.linspace(0.1, 0.9, 9)
    assert np.allclose(rec.apply(rec.inverse(qs)), qs, atol=0.05)   # R(R⁻¹(q)) ≈ q


def test_online_recalibrator_needs_window():
    assert online_recalibrator(np.zeros(10), window=60) is None    # janela insuficiente → None
    rng = np.random.default_rng(3)
    rec = online_recalibrator(rng.uniform(0, 1, 100), window=60)
    assert rec is not None
    assert 0.0 <= float(rec.apply(0.5)) <= 1.0
