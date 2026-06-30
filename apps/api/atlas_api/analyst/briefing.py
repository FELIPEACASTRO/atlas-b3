"""Deterministic briefing assembler for the Analyst (consultant) module.

Turns a quantified ``Setup`` into a structured, two-sided briefing with sizing
for three risk profiles. Pure and deterministic — an LLM only rewrites this into
readable prose later (see writer.py). It NEVER emits a buy/sell call; the
case-against is always non-empty and the verdict is labeled as analysis.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import floor

from atlas_api.pricing.signal import classify

CONTRACT_MULTIPLIER = 100  # shares per equity option lot on B3
_PROFILE_PCT = {"conservador": 0.01, "moderado": 0.025, "agressivo": 0.05}
_SHORT_VOL = {"venda_premio", "trava_alta_vendida", "condor", "strangle_vendido"}


@dataclass
class Setup:
    ticker: str
    underlying: str
    structure: str
    iv: float
    rv: float
    max_gain_per_lot: float
    max_loss_per_lot: float
    breakeven: float
    delta: float | None        # None when the leg has no reliable stored delta
    liquidity_brl: float
    dte: int
    capital: float


@dataclass
class Sizing:
    pct_capital: float
    lotes: int
    max_loss_brl: float


@dataclass
class RiskReward:
    max_gain_per_lot: float
    max_loss_per_lot: float
    breakeven: float
    ratio: float | None


@dataclass
class Briefing:
    ticker: str
    setup_facts: str
    case_for: list[str]
    case_against: list[str]
    risk_reward: RiskReward
    sizing: dict[str, Sizing]
    invalidation: str
    confidence: str
    verdict: str


def _sizing(capital: float, max_loss_per_lot: float) -> dict[str, Sizing]:
    per_lot_loss = max_loss_per_lot * CONTRACT_MULTIPLIER
    out: dict[str, Sizing] = {}
    for name, pct in _PROFILE_PCT.items():
        lotes = max(0, floor((capital * pct) / per_lot_loss)) if per_lot_loss > 0 else 0
        out[name] = Sizing(pct_capital=pct, lotes=lotes, max_loss_brl=round(lotes * per_lot_loss, 2))
    return out


def _confidence(s: Setup) -> str:
    gap = abs(s.iv - s.rv)
    if s.liquidity_brl < 20_000_000 or gap < 0.04:
        return "baixa"
    if s.liquidity_brl >= 50_000_000 and gap >= 0.08:
        return "média"
    return "média-baixa"


def build_briefing(s: Setup) -> Briefing:
    label = classify(s.iv, s.rv)
    is_short_vol = s.structure in _SHORT_VOL

    delta_txt = f"|Δ| {abs(s.delta):.2f}, " if s.delta is not None else ""
    setup_facts = (
        f"{s.underlying}: IV {s.iv:.0%} vs RV {s.rv:.0%} ({label}); "
        f"liquidez R$ {s.liquidity_brl / 1e6:.0f} mi, {delta_txt}"
        f"{s.dte} dias até o vencimento."
    )

    case_for: list[str] = []
    case_against: list[str] = []
    if label == "rico":
        case_for.append("IV acima da RV: você vende volatilidade cara.")
    elif label == "barato":
        case_for.append("IV abaixo da RV: você compra volatilidade barata.")

    if is_short_vol:
        case_for.append("Estrutura de risco definido limita a perda máxima.")
        case_for.append("Theta a favor se o ativo ficar de lado.")
        case_against.append("É short-vol: você é pago por risco de cauda, não por uma ineficiência.")
        case_against.append("Gap/evento move a IV contra você rápido; o spread largo come parte do prêmio.")
    else:
        case_against.append("Comprar prêmio sangra por theta: precisa de movimento para pagar.")

    if not case_against:  # honesty invariant: never one-sided
        case_against.append("Todo trade tem risco; defina o que o invalida antes de entrar.")

    ratio = (s.max_gain_per_lot / s.max_loss_per_lot) if s.max_loss_per_lot > 0 else None
    rr = RiskReward(s.max_gain_per_lot, s.max_loss_per_lot, s.breakeven, ratio)

    verdict = (
        "Análise transparente, não um sinal: "
        + (
            "vender prêmio caro com risco definido — você é pago por carregar risco de cauda. "
            if is_short_vol
            else "exposição a volatilidade com theta contra. "
        )
        + "A decisão é sua."
    )

    return Briefing(
        ticker=s.ticker,
        setup_facts=setup_facts,
        case_for=case_for,
        case_against=case_against,
        risk_reward=rr,
        sizing=_sizing(s.capital, s.max_loss_per_lot),
        invalidation=f"IV cair abaixo da RV, ou {s.underlying} romper o nível de invalidação da estrutura.",
        confidence=_confidence(s),
        verdict=verdict,
    )
