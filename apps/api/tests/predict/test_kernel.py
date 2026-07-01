"""Pricing kernel empírico (SDF): M(S)=q(S)/p(S) das duas densidades.

M≡1 quando risco-neutra = física (sem prêmio); M decrescente quando o mercado paga
prêmio pela queda (aversão a risco); flag de puzzle quando M sobe na cauda direita.
"""
import math

import numpy as np

from atlas_api.predict.kernel import kernel_shape, pricing_kernel


def _normal_pdf(s):
    return lambda u: math.exp(-u * u / (2 * s * s)) / (s * math.sqrt(2 * math.pi))


def test_kernel_is_flat_when_densities_match():
    # q == p (mesma densidade) → M ≡ 1 (nenhum prêmio de risco em nenhum estado)
    s = 0.1
    grid = np.linspace(-0.5, 0.5, 401)
    dens = np.exp(-grid ** 2 / (2 * s * s)) / (s * math.sqrt(2 * math.pi))
    out = pricing_kernel(spot=100.0, forward=100.0, phys_pdf=_normal_pdf(s),
                         svi_k=grid, svi_density=dens, moneyness=[0.9, 0.95, 1.0, 1.05, 1.1])
    for r in out:
        assert abs(r["m"] - 1.0) < 0.02


def test_kernel_slopes_down_when_market_prices_more_downside():
    # RN deslocada p/ a queda (skew de put) vs física simétrica → M alto embaixo, baixo em cima
    s = 0.1
    grid = np.linspace(-0.6, 0.6, 601)
    q = np.exp(-((grid + 0.03) ** 2) / (2 * s * s)) / (s * math.sqrt(2 * math.pi))
    out = pricing_kernel(spot=100.0, forward=100.0, phys_pdf=_normal_pdf(s),
                         svi_k=grid, svi_density=q, moneyness=[0.9, 0.95, 1.0, 1.05, 1.1])
    ms = [r["m"] for r in out]
    assert ms[0] > ms[-1]                                    # M decresce com S (aversão a risco)
    assert kernel_shape(out)["slope"] < 0


def test_kernel_detects_puzzle_when_kernel_is_u_shaped():
    # M em U (sobe nas duas caudas) — o pricing-kernel puzzle
    kernel = [{"moneyness": m, "strike": 100 * m, "m": v}
              for m, v in zip([0.9, 0.95, 1.0, 1.05, 1.1], [1.4, 1.0, 0.8, 1.0, 1.5])]
    assert kernel_shape(kernel)["puzzle"] is True
    mono = [{"moneyness": m, "strike": 100 * m, "m": v}
            for m, v in zip([0.9, 0.95, 1.0, 1.05, 1.1], [1.6, 1.3, 1.0, 0.8, 0.6])]
    assert kernel_shape(mono)["puzzle"] is False
