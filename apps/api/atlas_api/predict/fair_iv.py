"""Fair IV — a smile "justa" pela nossa densidade física vs a smile de mercado, em VOL POINTS.

O Edge Map fala em probabilidade e o pricing kernel em preço de estado; o operador de opções
pensa em VOL. Aqui o mesmo prêmio aparece na língua dele: para cada strike, a IV que o mercado
cobra (da smile SVI) vs a IV "justa" pela nossa vol física — o gap é o VRP decomposto por strike,
em pontos de vol, e aponta o strike de maior oportunidade.

Honestidade: a nossa densidade física é SIMÉTRICA (Student-t, drift=0 declarado — não modelamos
skew físico), então a linha justa é ~plana na vol física. Logo, o SKEW do gap embute o prêmio de
skew do mercado, mas também qualquer skew físico real que o nosso modelo não captura — a leitura
honesta é de NÍVEL (VRP) forte e skew "indicativo", não uma medida limpa de skew físico.
"""
from __future__ import annotations

import math

import numpy as np

from .ssvi import svi_total_variance


def fair_iv_smile(*, spot: float, forward: float, phys_vol: float, svi_params, T: float,
                  moneyness: list[float]) -> dict:
    """Para cada moneyness: IV de mercado (SVI) vs IV justa (vol física) e o gap em vol points.

    ``phys_vol`` é a vol física anualizada (E[RV], sem κ — κ é largura da densidade, não nível).
    Retorna ``{smile, max_gap}`` onde ``max_gap`` é o strike de maior |gap| (oportunidade).
    """
    if spot <= 0 or forward <= 0 or T <= 0:
        raise ValueError("spot/forward/T must be > 0")
    smile: list[dict] = []
    for mny in moneyness:
        strike = spot * mny
        k = math.log(strike / forward)
        w = float(svi_total_variance(svi_params, k))
        mkt = math.sqrt(max(w, 0.0) / T)
        smile.append({
            "moneyness": round(mny, 4), "strike": round(strike, 2),
            "iv_market": round(mkt, 4), "iv_fair": round(phys_vol, 4),
            "gap": round(mkt - phys_vol, 4),               # >0: mercado cobra prêmio de vol aqui
        })
    smile.sort(key=lambda r: r["strike"])
    # Decomposição HONESTA (não reportar max|gap|, que é SEMPRE a put mais funda por causa do skew):
    #  - level_gap = leitura de NÍVEL (VRP) perto do dinheiro (|mny−1|≤0.05) — o gap "limpo".
    #  - skew_premium = quanto a asa de put excede o nível — componente de SKEW de mercado (não VRP puro;
    #    a nossa física é simétrica, então isto embute skew físico real que não modelamos).
    ntm = [r for r in smile if abs(r["moneyness"] - 1.0) <= 0.05]
    level_gap = float(np.mean([r["gap"] for r in ntm])) if ntm else smile[len(smile) // 2]["gap"]
    put_wing = min(smile, key=lambda r: r["moneyness"])
    return {
        "smile": smile,
        "level_gap": round(level_gap, 4),                  # VRP de nível (near-the-money)
        "skew_premium": round(put_wing["gap"] - level_gap, 4),   # extra da asa de put além do nível
        "put_wing_strike": put_wing["strike"],
    }
