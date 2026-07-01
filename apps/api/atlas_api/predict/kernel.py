"""Pricing kernel empírico (SDF) — o diferencial teoricamente correto do ATLAS.

O *stochastic discount factor* é, por definição, a razão entre a densidade RISCO-NEUTRA e a
FÍSICA: ``M(S_T) ∝ q(S_T)/p(S_T)`` (a menos do desconto e^{-rT}, um nível). É o preço de estado
por unidade de probabilidade — quanto o mercado paga a mais por R$1 de payoff em cada desfecho.
Só é construível com uma densidade física CALIBRADA (a nossa, PIT-auditada); toda plataforma
tem apenas ``q``. A FORMA revela o *pricing-kernel puzzle* (Rosenberg-Engle; Aït-Sahalia-Lo):
``M`` decrescente = aversão a risco padrão; ``M`` em U (sobe na cauda direita) = prêmio de
crash/melt-up que a utilidade padrão não explica. O Edge Map compara CDFs (diferença); o kernel
é a RAZÃO de densidades — a forma teoricamente correta do mesmo objeto.
"""
from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np


def pricing_kernel(
    *, spot: float, forward: float, phys_pdf: Callable[[float], float],
    svi_k: np.ndarray, svi_density: np.ndarray, moneyness: list[float],
) -> list[dict]:
    """``M(S_T)=q(S_T)/p(S_T)`` por moneyness. Ambas as densidades no MESMO preço.

    ``phys_pdf`` é a densidade física do log-retorno (centro no spot). ``svi_k``/``svi_density``
    é a densidade RN em ``k=log(K/forward)``. Alinhamos as duas em ``u=log(S/spot)`` deslocando a
    RN por ``log(forward/spot)`` (translação, sem jacobiano). A razão q/p já é o SDF (E_p[M]=1 no
    suporte completo, pois ∫(q/p)·p = ∫q = 1); não renormalizamos na janela truncada.
    """
    if spot <= 0 or forward <= 0:
        raise ValueError("spot/forward must be > 0")
    k = np.asarray(svi_k, dtype=float)
    q = np.maximum(np.asarray(svi_density, dtype=float), 0.0)
    shift = math.log(forward / spot)                          # u = k + shift (RN centrada no forward)
    out: list[dict] = []
    for mny in moneyness:
        u = math.log(mny)                                     # log-retorno físico do strike (centro no spot)
        q_u = float(np.interp(u - shift, k, q, left=0.0, right=0.0))
        p_u = max(float(phys_pdf(u)), 1e-12)
        out.append({"moneyness": round(mny, 4), "strike": round(spot * mny, 2),
                    "m": round(q_u / p_u, 4)})                # M>1: estado caro (mercado paga prêmio aqui)
    out.sort(key=lambda r: r["strike"])
    return out


def kernel_shape(kernel: list[dict]) -> dict:
    """Resumo do SDF: inclinação (aversão a risco) e se é não-monotônico (o puzzle)."""
    u = np.array([math.log(r["moneyness"]) for r in kernel])
    m = np.array([r["m"] for r in kernel], dtype=float)
    slope = float(np.polyfit(u, m, 1)[0])                     # dM/d(logS): <0 = aversão a risco padrão
    i_min = int(np.argmin(m))
    span = float(m.max() - m.min()) + 1e-9
    # puzzle: mínimo INTERIOR e M sobe de novo na cauda direita (≥5% do range) — U-shape
    puzzle = bool(0 < i_min < len(m) - 1 and (m[-1] - m[i_min]) > 0.05 * span)
    return {"slope": round(slope, 3), "puzzle": puzzle,
            "m_min": round(float(m.min()), 3), "m_max": round(float(m.max()), 3)}
