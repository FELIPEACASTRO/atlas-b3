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


def rationale(s: dict, *, market_iv: float | None, physical: float | None) -> str:
    """O 'porquê' humano de uma estratégia: tese, vol implícita×física, edge e risco.

    Determinístico (não inventa): cruza a direção da tese com o fato da vol (cara/barata vs
    nossa estimativa) e o sinal do valor esperado sob a densidade. Análise, não recomendação.
    """
    rich = market_iv is not None and physical is not None and market_iv > physical + 0.005
    cheap = market_iv is not None and physical is not None and market_iv < physical - 0.005
    pop = round(s["pop"] * 100)
    selling = s.get("vol_stance") == "vender"
    dirw = {"alta": "de alta", "baixa": "de baixa", "neutro": "neutra (preço na faixa)"}.get(s["thesis"], "")
    vol_note = (
        "a vol implícita está acima da nossa estimativa física (prêmio caro)" if rich
        else "a vol implícita está abaixo da nossa estimativa física (prêmio barato)" if cheap
        else "vol implícita e física estão próximas"
    )
    if selling:
        edge = ("você VENDE essa vol cara — tempo e queda de vol jogam a seu favor" if rich
                else "você vende prêmio, mas a vol não está especialmente cara aqui")
    else:
        edge = ("você COMPRA prêmio caro, então o valor esperado fica negativo sob a nossa densidade" if rich
                else "você compra prêmio; com a vol barata, comprar tende a favorecer" if cheap
                else "você compra prêmio a preço próximo do justo pela nossa densidade")
    risk = "risco limitado às asas" if s.get("defined_risk") else "⚠ risco ilimitado (perna a descoberto)"
    return f"Tese {dirw}: {vol_note}; {edge}. POP {pop}%, {risk}."


# ---- Catálogo de estratégias (build_catalog) ----

# perfis de risco = fração do capital arriscada por trade (sizing; o usuário escolhe a postura)
_PROFILES = {"conservador": 0.25, "moderado": 0.5, "agressivo": 1.0}


def _nearest(opts: list[dict], target: float) -> dict | None:
    return min(opts, key=lambda o: abs(o["strike"] - target)) if opts else None


def _leg_of(o: dict, action: str) -> Leg:
    return Leg(o["kind"], action, float(o["strike"]), float(o["last"]))


def _recipes(spot: float, calls: list[dict], puts: list[dict]) -> list[tuple]:
    """(nome, tese, defined_risk, legs|None) p/ as estruturas montáveis da cadeia real."""
    ac, ap = _nearest(calls, spot), _nearest(puts, spot)               # ATM
    c5, c12 = _nearest(calls, spot * 1.05), _nearest(calls, spot * 1.12)
    p5, p12 = _nearest(puts, spot * 0.95), _nearest(puts, spot * 0.88)

    def spread(a, b, a_act, b_act, *, need_lt):
        if a is None or b is None or a["strike"] == b["strike"]:
            return None
        if need_lt and not (a["strike"] < b["strike"]):
            return None
        return [_leg_of(a, a_act), _leg_of(b, b_act)]

    out: list[tuple] = []
    if ac:
        out.append(("Compra de call", "alta", False, [_leg_of(ac, "long")]))
    out.append(("Trava de alta (call debit)", "alta", True, spread(ac, c5, "long", "short", need_lt=True)))
    out.append(("Trava de alta (put credit)", "alta", True, spread(p12, p5, "long", "short", need_lt=True)))
    if ap:
        out.append(("Compra de put", "baixa", False, [_leg_of(ap, "long")]))
    out.append(("Trava de baixa (put debit)", "baixa", True, spread(p5, ap, "long", "short", need_lt=True)))
    out.append(("Trava de baixa (call credit)", "baixa", True, spread(ac, c5, "short", "long", need_lt=True)))
    if ac and ap:
        out.append(("Compra de straddle", "neutro", False, [_leg_of(ac, "long"), _leg_of(ap, "long")]))
    if c5 and p5:
        out.append(("Compra de strangle", "neutro", False, [_leg_of(c5, "long"), _leg_of(p5, "long")]))
    if c5 and c12 and p5 and p12 and c5["strike"] < c12["strike"] and p12["strike"] < p5["strike"]:
        out.append(("Condor de ferro", "neutro", True,
                    [_leg_of(c5, "short"), _leg_of(c12, "long"), _leg_of(p5, "short"), _leg_of(p12, "long")]))
    if c5 and p5:
        out.append(("Strangle vendido", "neutro", False, [_leg_of(c5, "short"), _leg_of(p5, "short")]))
    if p5:
        out.append(("Venda de put (renda)", "alta", False, [_leg_of(p5, "short")]))
    return [(n, t, d, legs) for (n, t, d, legs) in out if legs]


def build_catalog(spot: float, dens: Density, chain: list[dict], *, visao: str,
                  capital: float, mult: int = 100) -> list[dict]:
    """Catálogo de estratégias da cadeia real, avaliadas por POP/EV e ordenadas pela tese.

    ``visao`` ∈ {alta, baixa, neutro, renda}. Sizing: risco definido cabe no ``capital``;
    naked (risco ilimitado) é sinalizado e dimensionado por margem aproximada. EV usa a
    densidade física → ranqueia por edge real (estruturas de venda sobem quando a vol é cara).
    """
    calls = sorted([o for o in chain if o.get("kind") == "call" and o.get("strike") and o.get("last") and o["last"] > 0], key=lambda o: o["strike"])
    puts = sorted([o for o in chain if o.get("kind") == "put" and o.get("strike") and o.get("last") and o["last"] > 0], key=lambda o: o["strike"])
    want = "neutro" if visao == "renda" else visao
    results: list[dict] = []
    for name, thesis, defined, legs in _recipes(spot, calls, puts):
        e1 = evaluate(legs, dens, spot, mult=mult, lots=1)          # métricas por lote
        # risco por lote: a perda máxima (definido) ou uma margem aproximada (naked, sem cap de
        # liquidez — a base EOD não traz volume/contratos em aberto)
        risk_per_lot = abs(e1["max_loss"]) if defined else spot * mult * 0.20
        if risk_per_lot <= 0:
            continue
        sizing = {p: int((capital * frac) // risk_per_lot) for p, frac in _PROFILES.items()}
        lots = sizing["moderado"]                                   # default = moderado
        if lots < 1:
            continue
        results.append({
            "name": name, "thesis": thesis, "defined_risk": defined, "lots": lots, "sizing": sizing,
            "vol_stance": "vender" if any(leg.action == "short" for leg in legs) and e1["cost"] <= 0 else "comprar",
            "legs": [{"kind": leg.kind, "action": leg.action, "strike": leg.strike, "premium": leg.premium} for leg in legs],
            "pop": e1["pop"], "breakevens": e1["breakevens"],       # independentes do nº de lotes
            "cost": round(e1["cost"] * lots, 2), "max_loss": round(e1["max_loss"] * lots, 2),
            "max_gain": round(e1["max_gain"] * lots, 2), "ev": round(e1["ev"] * lots, 2),
        })
    # ranqueia: estruturas que casam com a tese primeiro, depois maior valor esperado
    results.sort(key=lambda s: (s["thesis"] == want, s["ev"]), reverse=True)
    return results
