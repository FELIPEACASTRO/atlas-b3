"""ATLAS API — FastAPI app wiring pricing + analyst + the EOD store.

Serves real COTAHIST-ingested data when ``ATLAS_DB`` points at a populated
store; otherwise falls back to clearly-labeled fixture data. Honesty holds
either way: every row carries provenance + asof.
"""
from __future__ import annotations

import math
import os
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from atlas_api.analyst.briefing import Setup, build_briefing
from atlas_api.data import store
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _nan_to_none(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else x


def _store_conn():
    """Return a connection to a populated store, or None to use the fixture."""
    path = os.environ.get("ATLAS_DB")
    if not path or not os.path.exists(path):
        return None
    conn = store.connect(path)
    if store.count(conn) == 0:
        conn.close()
        return None
    return conn


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
    conn = _store_conn()
    if conn is None:
        now = _now()
        return [
            ScreenerRow(ticker="PETR4", tipo="acao", ultimo=38.42, var_pct=1.2,
                        liquidez=1.2e9, provenance=_FIXTURE, asof=now),
            ScreenerRow(ticker="PETRG38", tipo="call", ultimo=1.15, var_pct=4.5,
                        liquidez=88e6, iv=0.42, iv_vs_rv="rico", provenance=_FIXTURE, asof=now),
            ScreenerRow(ticker="VALE3", tipo="acao", ultimo=61.30, var_pct=-0.8,
                        liquidez=9.8e8, provenance=_FIXTURE, asof=now),
        ]
    rows = store.query_screener(conn, limit=200)
    asof = store.get_meta(conn, "asof") or ""
    conn.close()
    prov = f"COTAHIST EOD {asof}" if asof else "COTAHIST EOD"
    asof_val = asof if asof else _now()
    return [
        ScreenerRow(
            ticker=r["ticker"], tipo=r["tipo"], ultimo=r["ultimo"],
            var_pct=r["var_pct"] or 0.0, liquidez=r["liquidez"] or 0.0,
            iv=_nan_to_none(r["iv"]), iv_vs_rv=r["iv_vs_rv"],
            provenance=prov, asof=asof_val,
        )
        for r in rows
    ]


@app.get("/chain/{underlying}", response_model=list[ChainRow])
def chain(underlying: str) -> list[ChainRow]:
    conn = _store_conn()
    if conn is None:
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
    store_rows = store.query_chain(conn, underlying)
    asof = store.get_meta(conn, "asof") or ""
    conn.close()
    prov = f"COTAHIST EOD {asof}" if asof else "COTAHIST EOD"
    asof_val = asof if asof else _now()
    return [
        ChainRow(
            ticker=r["ticker"], kind=r["kind"], strike=r["strike"], last=r["last"],
            iv=_nan_to_none(r["iv"]), delta=_nan_to_none(r["delta"]),
            gamma=_nan_to_none(r["gamma"]), vega=_nan_to_none(r["vega"]),
            provenance=prov, asof=asof_val,
        )
        for r in store_rows
    ]
