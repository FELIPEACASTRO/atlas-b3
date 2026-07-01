"""Auditoria da distribuição: CRPS (forma fechada) + PIT (uniformidade) + cobertura.

"Mais perto da vida real" = a distribuição que passa no PIT e tem cobertura no nominal
— não a mais complexa, a mais CALIBRADA (spec).
"""
import numpy as np
from scipy import stats

from atlas_api.predict.validate import coverage, crps_gaussian, pit, pit_uniformity


def test_crps_matches_numeric_over_grid():
    for mu, sigma, y in [(0, 1, 0.5), (0.2, 0.3, 0.0), (-1, 2, 3.0)]:
        grid = np.linspace(mu - 12 * sigma, mu + 12 * sigma, 400000)  # grid fino (review N-A)
        cdf = stats.norm.cdf(grid, mu, sigma)
        numeric = np.trapezoid((cdf - (grid >= y)) ** 2, grid)         # def. integral do CRPS
        assert abs(crps_gaussian(y, mu, sigma) - numeric) < 1e-4


def test_crps_zero_scale_limit_is_abs_error():
    # σ→0: CRPS → |y−μ| (massa pontual em μ)
    assert abs(crps_gaussian(2.0, 0.0, 1e-9) - 2.0) < 1e-6


def test_pit_flags_underdispersion_honestly():
    rng = np.random.default_rng(2)
    sigma_real, sigma_model = 0.05, 0.03
    y = rng.normal(0.0, sigma_real, 4000)
    pit_vals = stats.norm.cdf(y, 0.0, sigma_model)                     # modelo ESTREITO demais
    assert pit_uniformity(pit_vals) < 0.05                            # U-shape => rejeita uniformidade
    pit_ok = stats.norm.cdf(y, 0.0, sigma_real)                       # modelo bem calibrado
    assert pit_uniformity(pit_ok) > 0.05                             # uniforme => não rejeita


def test_pit_helper_applies_cdf():
    y = np.array([-1.0, 0.0, 1.0])
    vals = pit(y, lambda x: stats.norm.cdf(x, 0.0, 1.0))
    assert np.allclose(vals, stats.norm.cdf(y))
    assert abs(float(vals[1]) - 0.5) < 1e-12


def test_coverage_counts_fraction_in_band():
    y = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    lo = np.full(5, 0.5)
    hi = np.full(5, 3.5)
    assert abs(coverage(y, lo, hi) - 0.6) < 1e-12                     # 1,2,3 dentro => 3/5
