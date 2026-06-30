"""Consultor de estratégias — avaliador de estruturas de opções (núcleo).

Dada a densidade física REAL do motor (`/predict`) e as pernas de uma estrutura, computa:
payoff no vencimento, **POP** (prob. de lucro), **valor esperado** (∫payoff·densidade),
risco máximo, retorno máximo e breakevens. É o que torna o consultor probabilístico — não
chute. Análise, nunca ordem de compra/venda.

Convenção: payoff em R$ por ``lots`` lotes de ``mult`` (B3 = 100). Prêmios e strikes em R$.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .distribution import Density


@dataclass(frozen=True)
class Leg:
    """Uma perna: ``kind`` ('call'|'put'), ``action`` ('long'|'short'), strike, prêmio (R$)."""

    kind: str
    action: str
    strike: float
    premium: float


def _leg_pnl(leg: Leg, s):
    intrinsic = np.maximum(s - leg.strike, 0.0) if leg.kind == "call" else np.maximum(leg.strike - s, 0.0)
    sign = 1.0 if leg.action == "long" else -1.0
    return sign * (intrinsic - leg.premium)        # long: paga prêmio, recebe intrínseco; short: o oposto


def payoff(legs: list[Leg], s, *, mult: int = 100, lots: int = 1):
    """P&L da estrutura no vencimento ao preço terminal ``s`` (escalar ou array)."""
    total = sum(_leg_pnl(leg, np.asarray(s, dtype=float)) for leg in legs)
    return total * mult * lots


def net_cost(legs: list[Leg], *, mult: int = 100, lots: int = 1) -> float:
    """Custo líquido (débito > 0 = paga; crédito < 0 = recebe), em R$."""
    return sum((1.0 if leg.action == "long" else -1.0) * leg.premium for leg in legs) * mult * lots


def _breakevens(s_grid: np.ndarray, pnl: np.ndarray) -> list[float]:
    out: list[float] = []
    sign = np.sign(pnl)
    for i in range(1, len(sign)):
        if sign[i - 1] != 0 and sign[i] != 0 and sign[i - 1] != sign[i]:   # cruzou o zero
            s0, s1, p0, p1 = s_grid[i - 1], s_grid[i], pnl[i - 1], pnl[i]
            out.append(float(s0 - p0 * (s1 - s0) / (p1 - p0)))             # interpolação linear
    return out


def evaluate(legs: list[Leg], dens: Density, spot: float, *, mult: int = 100, lots: int = 1,
             n: int = 6000) -> dict:
    """Avalia a estrutura sobre a densidade física: POP, valor esperado, risco, breakevens.

    Integra numericamente em log-retorno (a densidade vive em log-retorno; ``S_T = spot·e^x``).
    ``max_loss``/``max_gain`` sobre uma grade larga (±~10σ); estruturas ilimitadas terão o
    extremo na borda — o caller pode sinalizar "ilimitado" pela ausência de perna que trava.
    """
    span = 10.0 * dens.sigma * math.sqrt(dens.T) + 0.05
    x = np.linspace(-span, span, n)
    s = spot * np.exp(x)
    pnl = payoff(legs, s, mult=mult, lots=lots)
    pdf = dens.logret_pdf(x)
    area = float(np.trapezoid(pdf, x)) or 1.0          # normaliza resíduo de truncamento da grade
    ev = float(np.trapezoid(pnl * pdf, x) / area)
    pop = float(np.trapezoid(np.where(pnl > 0.0, pdf, 0.0), x) / area)
    return {
        "cost": round(net_cost(legs, mult=mult, lots=lots), 2),
        "max_loss": round(float(pnl.min()), 2),
        "max_gain": round(float(pnl.max()), 2),
        "ev": round(ev, 2),
        "pop": round(pop, 4),
        "breakevens": [round(b, 2) for b in _breakevens(s, pnl)],
    }
