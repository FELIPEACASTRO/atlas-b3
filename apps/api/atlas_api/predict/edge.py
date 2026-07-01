"""Mapa de Prêmio (Edge Map) — o diferencial do ATLAS.

Compara, strike a strike, a probabilidade RISCO-NEUTRA (o que o mercado precifica, da smile
SVI) com a probabilidade FÍSICA calibrada (a nossa, com PIT auditado). O gap é o prêmio que
o mercado cobra sobre o justo, por moneyness — a decomposição do VRP ao longo da smile, i.e.
o pricing kernel tornado acionável. Nenhuma plataforma de varejo mostra *onde* e *por quanto*
o mercado está errado com uma densidade física validada.

``edge(K) = P_mercado(S_T ≤ K) − P_física(S_T ≤ K)``  → edge>0: mercado sobrevaloriza aquele
strike (vender lá tem +EV pela nossa densidade); edge<0: subvaloriza (comprar).
"""
from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np


def _rn_cdf(svi_k: np.ndarray, svi_density: np.ndarray) -> Callable[[float], float]:
    """CDF risco-neutra a partir da densidade SVI em log-moneyness (integral acumulada, normalizada)."""
    k = np.asarray(svi_k, dtype=float)
    d = np.maximum(np.asarray(svi_density, dtype=float), 0.0)
    total = float(np.trapezoid(d, k)) or 1.0
    cum = np.concatenate([[0.0], np.cumsum((d[1:] + d[:-1]) / 2.0 * np.diff(k))]) / total
    return lambda kq: float(np.clip(np.interp(kq, k, cum), 0.0, 1.0))


def premium_map(
    *, spot: float, forward: float, phys_cdf: Callable[[float], float],
    svi_k: np.ndarray, svi_density: np.ndarray, moneyness: list[float],
) -> list[dict]:
    """Para cada nível de moneyness, ``P_mercado(S≤K)`` (RN/SVI) vs ``P_física(S≤K)`` e o edge.

    ``phys_cdf`` é a CDF do log-retorno físico, centrada no SPOT (drift=0). ``svi_k``/``svi_density``
    é a densidade risco-neutra em ``k=log(K/forward)`` (centrada no forward). Retorna a lista
    ordenada por strike.
    """
    if spot <= 0 or forward <= 0:
        raise ValueError("spot/forward must be > 0")
    rn_cdf = _rn_cdf(svi_k, svi_density)
    out: list[dict] = []
    for mny in moneyness:
        strike = spot * mny
        # CADA densidade no seu próprio centro: a RN tem mediana no forward → avalia em log(K/forward);
        # a física declara drift=0 (mediana no spot) → avalia em log(K/spot). Referenciar a física ao
        # forward INTRODUZ um viés de −r·T (não é apples-to-apples quando r≠0). O edge é a diferença
        # HONESTA de P(S_T ≤ K) entre as duas medidas; o carry (r·T) entra corretamente e é ~0 na B3.
        p_market = rn_cdf(math.log(strike / forward))
        p_phys = float(np.clip(phys_cdf(math.log(strike / spot)), 0.0, 1.0))
        out.append({
            "moneyness": round(mny, 4), "strike": round(strike, 2),
            "p_market": round(p_market, 4), "p_physical": round(p_phys, 4),
            "edge": round(p_market - p_phys, 4),            # >0: mercado sobrevaloriza (vender lá)
        })
    out.sort(key=lambda r: r["strike"])
    return out
