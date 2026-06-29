"""Pydantic contract models shared with the web app.

Every row carries ``provenance`` and ``asof`` — the honesty fields. The web app
renders these so a number is never shown without where/when it came from.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class SizingOut(BaseModel):
    pct_capital: float
    lotes: int
    max_loss_brl: float


class RiskRewardOut(BaseModel):
    max_gain_per_lot: float
    max_loss_per_lot: float
    breakeven: float
    ratio: float | None = None


class BriefingResponse(BaseModel):
    ticker: str
    setup_facts: str
    case_for: list[str]
    case_against: list[str]
    risk_reward: RiskRewardOut
    sizing: dict[str, SizingOut]
    invalidation: str
    confidence: str
    verdict: str
    provenance: str
    asof: datetime


class ScreenerRow(BaseModel):
    ticker: str
    tipo: str
    ultimo: float | None = None
    var_pct: float | None = None
    liquidez: float | None = None
    iv: float | None = None
    iv_vs_rv: str | None = None
    provenance: str
    asof: datetime


class ChainRow(BaseModel):
    ticker: str
    kind: str
    strike: float
    last: float
    iv: float | None = None
    delta: float | None = None
    gamma: float | None = None
    vega: float | None = None
    provenance: str
    asof: datetime
