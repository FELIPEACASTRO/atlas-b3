"""Regime de volatilidade → viés de ESTRUTURA (alimenta o consultor; spec §97).

Análise, não recomendação: classifica o ambiente (vol cara/barata, prêmio, estrutura
a termo) e sugere o TIPO de estrutura coerente, sempre com os gates da B3. Os limiares
de IVR são parâmetros de modelo convencionais (estilo tastytrade), não dados — tunáveis.
"""
from __future__ import annotations

# Limiares convencionais de IV Rank (model params, não dados fabricados — cf. signal.band).
IVR_HIGH = 60.0   # acima: vol cara vs história própria → favorece vender prêmio
IVR_LOW = 30.0    # abaixo: vol barata → favorece comprar (débito)


def regime(iv_rank, vrp, term_slope, skew=None) -> str:
    """Rótulo de regime a partir de IV Rank, VRP e inclinação da estrutura a termo.

    Prioridade: **backwardation** (`term_slope<0`, stress de curto prazo) vem primeiro —
    gestão de risco antes de prêmio. ``skew`` é suplementar (enriquece a nota humana; não
    é load-bearing no rótulo grosso do ML-1). ``None`` em qualquer entrada essencial →
    ``"indisponivel"`` (honesto, nunca fabrica).
    """
    if iv_rank is None or vrp is None or term_slope is None:
        return "indisponivel"
    if term_slope < 0:                       # backwardation: medo no curto prazo
        return "parar venda a descoberto"
    if iv_rank >= IVR_HIGH and vrp > 0:       # vol cara + prêmio + contango (term_slope>=0)
        return "vender prêmio"
    if iv_rank <= IVR_LOW:                     # vol barata
        return "comprar/debit"
    return "neutro"


_BIAS = {
    "vender prêmio": {
        "bias": "vender volatilidade (estruturas de crédito, theta a favor)",
        "examples": ["trava de alta vendida (bull put spread)", "iron condor"],
    },
    "comprar/debit": {
        "bias": "comprar volatilidade (estruturas de débito, vega/gamma a favor)",
        "examples": ["trava de alta comprada (bull call spread)", "compra de straddle/strangle"],
    },
    "parar venda a descoberto": {
        "bias": "evitar venda a descoberto; defender/rolar posições short vol",
        "examples": ["fechar ou rolar shorts a descoberto", "travar risco com asas (verticais/condors)"],
    },
    "neutro": {
        "bias": "sem viés forte de vol; selecionar por nome, liquidez e tese",
        "examples": ["estruturas delta-neutras seletivas"],
    },
    "indisponivel": {"bias": "dados insuficientes para classificar o regime", "examples": []},
}

_B3_GATES = [
    "liquidez: restringir a nomes com cadeia líquida (PETR4, VALE3, grandes bancos, BOVA11)",
    "exercício antecipado: opções de AÇÃO na B3 são americanas — short ITM pode ser exercido",
]


def strategy_bias(regime_label: str) -> dict:
    """Viés de estrutura + gates B3 para um regime. Análise (dois lados), nunca ordem."""
    base = _BIAS.get(regime_label, _BIAS["indisponivel"])
    gates = [] if regime_label == "indisponivel" else list(_B3_GATES)
    return {
        "regime": regime_label,
        "bias": base["bias"],
        "examples": list(base["examples"]),
        "b3_gates": gates,
    }
