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
    """Resumo do SDF: inclinação (com R² — só é 'aversão a risco' se o ajuste linear presta) e o
    pricing-kernel puzzle (Rosenberg-Engle) — que exige revés na cauda DIREITA, não skew de put.

    Correções de rigor: (1) o kernel é U/corcova; um fit LINEAR explica pouco (R² baixo), então o
    sinal do slope só é lido como aversão a risco quando R²≥0.5. (2) o puzzle é revés na cauda de
    ALTA — o mínimo deve ser interior E near-the-money, senão o M alto na cauda esquerda (puts de
    crash = skew normal) dispararia um falso puzzle.
    """
    u = np.array([math.log(r["moneyness"]) for r in kernel])
    m = np.array([r["m"] for r in kernel], dtype=float)
    mny = np.array([r["moneyness"] for r in kernel], dtype=float)
    slope, intercept = (float(v) for v in np.polyfit(u, m, 1))
    ss_res = float(np.sum((m - (slope * u + intercept)) ** 2))
    ss_tot = float(np.sum((m - m.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-9 else 0.0     # kernel plano (sem variação) → R²=0, não "confiável"
    i_min = int(np.argmin(m))
    span = float(m.max() - m.min()) + 1e-9
    min_ntm = bool(0.90 <= mny[i_min] <= 1.10)               # mínimo perto do dinheiro
    right_reversal = bool(i_min < len(m) - 1 and (m[-1] - m[i_min]) > 0.10 * span)   # sobe na cauda DIREITA
    return {
        "slope": round(slope, 3), "slope_r2": round(r2, 2),
        "risk_aversion_reliable": bool(r2 >= 0.5),           # só então o slope<0 vira "aversão a risco"
        "puzzle": bool(min_ntm and right_reversal),
        "m_min": round(float(m.min()), 3), "m_max": round(float(m.max()), 3),
        "m_min_moneyness": round(float(mny[i_min]), 3),
    }
