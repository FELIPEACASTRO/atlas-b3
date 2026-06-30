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
    iv_rank: float | None = None
    vrp: float | None = None
    pc_ratio: float | None = None
    skew: float | None = None
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
    theta: float | None = None
    provenance: str
    asof: datetime


class PositionIn(BaseModel):
    ticker: str
    qty: float


class PositionRow(BaseModel):
    ticker: str
    tipo: str | None = None
    qty: float
    last: float | None = None
    value: float | None = None
    delta: float | None = None
    gamma: float | None = None
    vega: float | None = None
    theta: float | None = None


class PortfolioSummary(BaseModel):
    n_positions: int
    total_value: float
    net_delta: float
    net_gamma: float
    net_vega: float
    net_theta: float
    provenance: str
    asof: datetime | None = None


class StressPoint(BaseModel):
    shock_pct: float  # uniform spot move applied to each underlying
    pnl: float        # approximate P&L (delta-gamma), constant vol


class StressResponse(BaseModel):
    scenarios: list[StressPoint]
    pnl_vol_up: float    # P&L if IV rises +5 vol points (vega leg)
    theta_per_day: float  # daily decay carried by the book
    provenance: str
    asof: datetime | None = None


class HistoryPoint(BaseModel):
    date: str
    iv: float | None = None   # ATM implied vol that session
    rv: float | None = None   # trailing realized vol (close-to-close)


class HistoryResponse(BaseModel):
    ticker: str
    points: list[HistoryPoint]
    iv_rank: float | None = None  # where the latest IV sits in the shown window
    provenance: str
    asof: str | None = None
