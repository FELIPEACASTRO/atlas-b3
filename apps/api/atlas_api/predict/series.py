"""Adapter de dados: store → séries de entrada do forecast (pure-stdlib).

É o elo que o store não entrega pronto (review B2): uma série de RV diária, uma
série de Yang-Zhang rolante e os retornos negativos alinhados — todos REUSANDO
`pricing.rv` (review B1: a fórmula Yang-Zhang já existe em rv.py:45, não duplicar).

Nota de qualidade (medida: 13,5% das barras da base têm O=H=L=C colapsado): o
Yang-Zhang já trata barras colapsadas de forma honesta — quando O=H=L=C, o termo
overnight `log(o_t / c_{t-1})` recupera o retorno close-to-close, então o YZ
degrada graciosamente para a vol close-to-close em vez de cravar zero. O fallback
explícito só dispara quando o YZ é NaN (barra corrompida / janela degenerada).
"""
from __future__ import annotations

import math

from atlas_api.pricing.rv import realized_vol, yang_zhang

OHLC = tuple[float, float, float, float]


def rolling_yang_zhang(ohlc: list[OHLC], window: int) -> list[float]:
    """Yang-Zhang anualizado em cada janela deslizante de ``window`` barras.

    Reusa `rv.yang_zhang` — zero fórmula nova. Saída alinhada à direita:
    ``len == len(ohlc) - window + 1``.
    """
    if window < 2:
        raise ValueError("window must be >= 2")
    return [yang_zhang(ohlc[i : i + window]) for i in range(len(ohlc) - window + 1)]


def rv_series(ohlc: list[OHLC], window: int) -> list[float]:
    """Série de RV diária para o HAR, preferindo Yang-Zhang do OHLC real.

    Mais eficiente que close-to-close (AIForge §3, ~5×) e o dado já existe. Gate
    de qualidade: se o YZ da janela for NaN (barra corrompida/degenerada), cai
    para `realized_vol` close-to-close dos closes da janela — honesto, declarado.
    """
    if window < 2:
        raise ValueError("window must be >= 2")
    out: list[float] = []
    for i in range(len(ohlc) - window + 1):
        w = ohlc[i : i + window]
        yz = yang_zhang(w)
        if math.isnan(yz):
            closes = [bar[3] for bar in w]
            yz = realized_vol(closes, window=len(closes))
        out.append(yz)
    return out


def neg_return_series(closes: list[float]) -> list[float]:
    """Indicador de retorno negativo diário (input de leverage da Task 2).

    Log-retorno se ``r < 0`` senão ``0.0`` — indicador **estrito** ``r<0`` (não
    ``r<=0``). O caller extrai ``closes`` do OHLC (``bar[3]``). Alinhado à série RV.
    """
    rets = [math.log(closes[i + 1] / closes[i]) for i in range(len(closes) - 1)]
    return [r if r < 0.0 else 0.0 for r in rets]
