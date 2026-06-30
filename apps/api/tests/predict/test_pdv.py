"""Features PDV (Guyon-Lekeufack) — tendência R₁ e trajetória de vol Σ, Markovianas.

Path-dependent volatility: R₁ = média exponencial dos retornos (tendência); Σ = √(média
exponencial dos retornos²) (vol recente). O(1) por update. Entram no forecast SÓ se baterem
o HAR-Leverage pelo gate (testado em separado no dado real; resultado negativo é resultado).
"""
import math

import numpy as np

from atlas_api.predict.pdv import r1_trend, sigma_path


def test_r1_trend_follows_recent_returns():
    out = r1_trend([0.01] * 12, halflife=3)
    assert out[-1] > 0 and abs(out[-1] - 0.01) < 1e-3        # converge p/ o retorno constante
    out2 = r1_trend([0.01] * 6 + [-0.02] * 6, halflife=2)
    assert out2[-1] < 0                                       # tendência recente negativa


def test_sigma_path_nonneg_and_reacts_to_vol():
    out = sigma_path([0.0] * 5 + [0.05, -0.05] * 4, halflife=3)
    assert all(v >= 0.0 for v in out)                        # sempre ≥ 0
    assert out[-1] > out[0]                                   # sobe com a vol recente


def test_recursive_update_matches_batch():
    rng = np.random.default_rng(0)
    r = rng.normal(0, 0.02, 60).tolist()
    batch = r1_trend(r, halflife=5)
    a = 1.0 - 0.5 ** (1.0 / 5)                                # EWMA recursiva O(1)
    s = r[0]
    rec = [r[0]]
    for x in r[1:]:
        s = (1 - a) * s + a * x
        rec.append(s)
    assert np.allclose(batch, rec)


def test_sigma_path_equals_sqrt_ewma_of_squares():
    r = [0.01, -0.03, 0.02, -0.01, 0.04]
    a = 1.0 - 0.5 ** (1.0 / 3)
    s = r[0] ** 2
    for x in r[1:]:
        s = (1 - a) * s + a * x * x
    assert abs(sigma_path(r, halflife=3)[-1] - math.sqrt(s)) < 1e-12
