"""ATLAS API — FastAPI app wiring pricing + analyst into the typed contract.

Data here is synthetic (fixture) and labeled as such via ``provenance`` until
the COTAHIST ingestion lands. The honesty rule holds even for fixtures.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from fastapi import FastAPI

from atlas_api.analyst.briefing import Setup, build_briefing
from atlas_api.models import (
    BriefingResponse,
    ChainRow,
    RiskRewardOut,
    ScreenerRow,
    SizingOut,
)
from atlas_api.pricing.bs import bs_greeks, bs_price
from atlas_api.pricing.iv import implied_vol

_FIXTURE = "fixture (sintético) — sem dado real de mercado ainda"

app = FastAPI(title="ATLAS API", version="0.1.0")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _nan_to_none(x: float) -> float | None:
    return None if x is None or math.isnan(x) else x


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "atlas-api"}


def _sample_setup() -> Setup:
    return Setup(
        ticker="PETRG38", underlying="PETR4", structure="venda_premio",
        iv=0.42, rv=0.33, max_gain_per_lot=0.62, max_loss_per_lot=0.38,
        breakeven=38.62, delta=0.30, liquidity_brl=88_000_000, dte=24, capital=60_000,
    )


@app.get("/briefing/sample", response_model=BriefingResponse)
def briefing_sample() -> BriefingResponse:
    b = build_briefing(_sample_setup())
    return BriefingResponse(
        ticker=b.ticker,
        setup_facts=b.setup_facts,
        case_for=b.case_for,
        case_against=b.case_against,
        risk_reward=RiskRewardOut(**vars(b.risk_reward)),
        sizing={k: SizingOut(**vars(v)) for k, v in b.sizing.items()},
        invalidation=b.invalidation,
        confidence=b.confidence,
        verdict=b.verdict,
        provenance=_FIXTURE,
        asof=_now(),
    )


@app.get("/screener", response_model=list[ScreenerRow])
def screener() -> list[ScreenerRow]:
    now = _now()
    return [
        ScreenerRow(ticker="PETR4", tipo="acao", ultimo=38.42, var_pct=1.2,
                    liquidez=1.2e9, provenance=_FIXTURE, asof=now),
        ScreenerRow(ticker="PETRG38", tipo="call", ultimo=1.15, var_pct=4.5,
                    liquidez=88e6, iv=0.42, iv_vs_rv="rico", provenance=_FIXTURE, asof=now),
        ScreenerRow(ticker="VALE3", tipo="acao", ultimo=61.30, var_pct=-0.8,
                    liquidez=9.8e8, provenance=_FIXTURE, asof=now),
    ]


@app.get("/chain/{underlying}", response_model=list[ChainRow])
def chain(underlying: str) -> list[ChainRow]:
    now = _now()
    spot, r, q, T, sigma = 38.42, 0.105, 0.0, 24 / 252, 0.40
    rows: list[ChainRow] = []
    for strike in (36.0, 38.0, 40.0):
        for kind in ("call", "put"):
            last = bs_price(kind, spot, strike, r, q, T, sigma)
            iv = implied_vol(kind, last, spot, strike, r, q, T)
            g = bs_greeks(kind, spot, strike, r, q, T, sigma)
            rows.append(ChainRow(
                ticker=f"{underlying}{kind[0].upper()}{int(strike)}",
                kind=kind, strike=strike, last=round(last, 2),
                iv=_nan_to_none(iv), delta=_nan_to_none(g["delta"]),
                gamma=_nan_to_none(g["gamma"]), vega=_nan_to_none(g["vega"]),
                provenance=_FIXTURE, asof=now,
            ))
    return rows
