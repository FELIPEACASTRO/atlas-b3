"""ATLAS API — FastAPI app wiring pricing + analyst + the EOD store.

Serves real COTAHIST-ingested data when ``ATLAS_DB`` points at a populated
store; otherwise falls back to clearly-labeled fixture data. Honesty holds
either way: every row carries provenance + asof.
"""
from __future__ import annotations

import math
import os
import sqlite3
from dataclasses import asdict
from datetime import date, datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from atlas_api.analyst.briefing import Setup, build_briefing
from atlas_api.analyst.option_analysis import OptionCtx, analyze_option
from atlas_api.data import store
from atlas_api.models import (
    BriefingResponse,
    ChainRow,
    HistoryPoint,
    HistoryResponse,
    OptionAnalysisOut,
    PayoffPoint,
    PayoffResponse,
    PortfolioSummary,
    PositionIn,
    PositionRow,
    RiskRewardOut,
    ScreenerRow,
    SizingOut,
    StressPoint,
    StressResponse,
    SurfaceExpiry,
    SurfacePoint,
    SurfaceResponse,
)
from atlas_api.data.calendar_b3 import year_fraction
from atlas_api.pricing.american import bjerksund_stensland
from atlas_api.pricing.bs import bs_greeks, bs_price
from atlas_api.pricing.iv import implied_vol
from atlas_api.pricing.risk import SPOT_SHOCKS, payoff_at_expiry, payoff_grid, stress_pnl
from atlas_api.pricing.rv import realized_vol
from atlas_api.pricing.signal import iv_rank

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
    try:
        conn = store.connect(path)
        if store.count(conn) == 0:
            conn.close()
            return None
        return conn
    except sqlite3.DatabaseError:
        # corrupted / not a sqlite file -> fall back to the labeled fixture
        return None


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


@app.get("/summary")
def summary() -> dict:
    """Real headline metrics for the dashboard (no hardcoded numbers)."""
    conn = _store_conn()
    if conn is None:
        return {"provenance": _FIXTURE, "asof": None, "underlyings": 0,
                "com_sinal": 0, "rico": 0, "barato": 0, "vol_total": 0.0, "bova11": None}
    rows = store.query_screener(conn, tipo="acao", min_liq=0, limit=10000)
    asof = store.get_meta(conn, "asof") or ""
    conn.close()
    sig = [r for r in rows if r["iv_vs_rv"] in ("rico", "barato", "neutro")]
    return {
        "provenance": f"COTAHIST EOD {asof}" if asof else "COTAHIST EOD",
        "asof": asof or None,
        "underlyings": len(rows),
        "com_sinal": len(sig),
        "rico": sum(1 for r in sig if r["iv_vs_rv"] == "rico"),
        "barato": sum(1 for r in sig if r["iv_vs_rv"] == "barato"),
        "vol_total": sum((r["liquidez"] or 0.0) for r in rows),
        "bova11": next((r["ultimo"] for r in rows if r["ticker"] == "BOVA11"), None),
    }


@app.get("/briefing/{underlying}", response_model=BriefingResponse)
def briefing(underlying: str, capital: float = 50000.0) -> BriefingResponse:
    """Real briefing for a real underlying: a defined-risk call spread built from
    two adjacent strikes of the nearest expiry, with real premiums/IV/RV."""
    underlying = underlying.upper()
    conn = _store_conn()
    if conn is None:
        raise HTTPException(status_code=503, detail="sem store real — defina ATLAS_DB e ingira COTAHIST")
    stocks = [r for r in store.query_screener(conn, tipo="acao", min_liq=0, limit=10000)
              if r["ticker"] == underlying]
    closes = [c for (_o, _h, _l, c) in store.price_history(conn, underlying)]
    chain = store.query_chain(conn, underlying)
    asof = store.get_meta(conn, "asof") or ""
    conn.close()

    if not stocks:
        raise HTTPException(status_code=404, detail=f"{underlying} não encontrado")
    spot = stocks[0]["ultimo"]
    rv = realized_vol(closes) if len(closes) >= 3 else float("nan")
    calls = [o for o in chain if o["kind"] == "call" and o["iv"] is not None and o["strike"] and o["venc"]]
    if spot is None or rv != rv or len(calls) < 2:
        raise HTTPException(status_code=422,
                            detail=f"dados insuficientes para briefing de {underlying} (precisa RV + cadeia de calls)")

    near_venc = min(o["venc"] for o in calls)
    near = sorted((o for o in calls if o["venc"] == near_venc), key=lambda o: o["strike"])
    i = min(range(len(near)), key=lambda k: abs(near[k]["strike"] - spot))
    if i + 1 >= len(near):
        i = len(near) - 2
    short_leg, long_leg = near[i], near[i + 1]
    width = long_leg["strike"] - short_leg["strike"]
    credit = short_leg["last"] - long_leg["last"]
    dte = (date.fromisoformat(near_venc) - date.fromisoformat(asof)).days if asof else 21

    setup = Setup(
        ticker=short_leg["ticker"], underlying=underlying, structure="trava_alta_vendida",
        iv=short_leg["iv"], rv=round(rv, 4),
        max_gain_per_lot=round(max(credit, 0.0), 2),
        max_loss_per_lot=round(max(width - credit, 0.01), 2),
        breakeven=round(short_leg["strike"] + credit, 2),
        delta=short_leg["delta"] or 0.3,
        liquidity_brl=stocks[0]["liquidez"] or 0.0,
        dte=max(dte, 1), capital=capital,
    )
    b = build_briefing(setup)
    return BriefingResponse(
        ticker=b.ticker, setup_facts=b.setup_facts, case_for=b.case_for, case_against=b.case_against,
        risk_reward=RiskRewardOut(**vars(b.risk_reward)),
        sizing={k: SizingOut(**vars(v)) for k, v in b.sizing.items()},
        invalidation=b.invalidation, confidence=b.confidence, verdict=b.verdict,
        provenance=f"COTAHIST EOD {asof}" if asof else "COTAHIST EOD", asof=asof or _now(),
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
            ticker=r["ticker"], tipo=r["tipo"],
            ultimo=_nan_to_none(r["ultimo"]),
            var_pct=_nan_to_none(r["var_pct"]),
            liquidez=_nan_to_none(r["liquidez"]),
            iv=_nan_to_none(r["iv"]), iv_vs_rv=r["iv_vs_rv"],
            iv_rank=_nan_to_none(r["iv_rank"]),
            vrp=_nan_to_none(r["vrp"]), pc_ratio=_nan_to_none(r["pc_ratio"]),
            skew=_nan_to_none(r["skew"]),
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
                    theta=_nan_to_none(g["theta"] / 252),
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
            theta=_nan_to_none(r["theta"]),
            provenance=prov, asof=asof_val,
        )
        for r in store_rows
    ]


def _open_writable() -> sqlite3.Connection:
    path = os.environ.get("ATLAS_DB")
    if not path:
        raise HTTPException(status_code=503, detail="defina ATLAS_DB para usar a carteira")
    return store.connect(path)


def _enrich_positions(conn) -> list[PositionRow]:
    out: list[PositionRow] = []
    for ticker, qty in store.list_positions(conn):
        inst = store.get_instrument(conn, ticker)
        if inst is None:
            out.append(PositionRow(ticker=ticker, qty=qty))  # held but no current quote
            continue
        tipo, last = inst["tipo"], inst["ultimo"]
        if tipo in ("call", "put"):
            opt = store.get_option(conn, ticker) or {}
            mult = 100
            d, g, v, th = opt.get("delta"), opt.get("gamma"), opt.get("vega"), opt.get("theta")
        else:
            mult, d, g, v, th = 1, 1.0, 0.0, 0.0, 0.0  # stock: delta=qty, no greeks/decay
        value = round(qty * last * mult, 2) if last is not None else None
        out.append(PositionRow(
            ticker=ticker, tipo=tipo, qty=qty, last=last, value=value,
            delta=round(qty * (d or 0.0) * mult, 4),
            gamma=round(qty * (g or 0.0) * mult, 6),
            vega=round(qty * (v or 0.0) * mult, 4),
            theta=round(qty * (th or 0.0) * mult, 4),
        ))
    return out


@app.get("/positions", response_model=list[PositionRow])
def get_positions() -> list[PositionRow]:
    conn = _open_writable()
    rows = _enrich_positions(conn)
    conn.close()
    return rows


@app.post("/positions", response_model=list[PositionRow])
def add_position(pos: PositionIn) -> list[PositionRow]:
    conn = _open_writable()
    store.set_position(conn, pos.ticker.upper().strip(), pos.qty)
    conn.commit()
    rows = _enrich_positions(conn)
    conn.close()
    return rows


@app.delete("/positions/{ticker}")
def delete_position(ticker: str) -> dict:
    conn = _open_writable()
    store.remove_position(conn, ticker.upper())
    conn.commit()
    conn.close()
    return {"status": "removed", "ticker": ticker.upper()}


@app.get("/portfolio", response_model=PortfolioSummary)
def portfolio() -> PortfolioSummary:
    conn = _open_writable()
    rows = _enrich_positions(conn)
    asof = store.get_meta(conn, "asof")
    conn.close()
    return PortfolioSummary(
        n_positions=len(rows),
        total_value=round(sum(r.value or 0.0 for r in rows), 2),
        net_delta=round(sum(r.delta or 0.0 for r in rows), 2),
        net_gamma=round(sum(r.gamma or 0.0 for r in rows), 4),
        net_vega=round(sum(r.vega or 0.0 for r in rows), 2),
        net_theta=round(sum(r.theta or 0.0 for r in rows), 2),
        provenance=f"COTAHIST EOD {asof}" if asof else "sem dado de mercado",
        asof=asof or None,
    )


def _stress_inputs(conn) -> list[tuple[float, float, float, float]]:
    """Per-position (delta, gamma, vega, underlying_spot) for the Taylor stress."""
    out: list[tuple[float, float, float, float]] = []
    for ticker, qty in store.list_positions(conn):
        inst = store.get_instrument(conn, ticker)
        if inst is None:
            continue
        if inst["tipo"] in ("call", "put"):
            opt = store.get_option(conn, ticker) or {}
            u = store.get_instrument(conn, opt.get("underlying") or "") or {}
            spot = u.get("ultimo")
            if spot is None:
                continue  # cannot shock without the underlying's spot
            out.append((qty * (opt.get("delta") or 0.0) * 100, qty * (opt.get("gamma") or 0.0) * 100,
                        qty * (opt.get("vega") or 0.0) * 100, spot))
        else:
            out.append((qty, 0.0, 0.0, inst["ultimo"] or 0.0))  # stock: delta=qty
    return out


@app.get("/history/{ticker}", response_model=HistoryResponse)
def history(ticker: str, window: int = 21) -> HistoryResponse:
    """Time series of ATM implied vol vs trailing realized vol for an underlying."""
    ticker = ticker.upper()
    conn = _store_conn()
    if conn is None:
        return HistoryResponse(ticker=ticker, points=[], provenance=_FIXTURE, asof=None)
    closes = store.close_series(conn, ticker)
    ivs = dict(store.iv_series(conn, ticker))
    asof = store.get_meta(conn, "asof")
    conn.close()
    points: list[HistoryPoint] = []
    for i, (d, _c) in enumerate(closes):
        rv = None
        if i >= 10:  # enough closes for a trailing estimate
            w = [c2 for (_dt, c2) in closes[max(0, i - window + 1): i + 1]]
            rvv = realized_vol(w)
            rv = round(rvv, 4) if rvv == rvv else None
        iv = round(ivs[d], 4) if d in ivs else None
        points.append(HistoryPoint(date=d, iv=iv, rv=rv))
    iv_vals = [p.iv for p in points if p.iv is not None]
    rank = iv_rank(iv_vals, iv_vals[-1]) if iv_vals else None
    prov = f"COTAHIST EOD {asof}" if asof else "COTAHIST EOD"
    return HistoryResponse(ticker=ticker, points=points, iv_rank=rank, provenance=prov, asof=asof)


@app.get("/option/{ticker}", response_model=OptionAnalysisOut)
def option_panel(ticker: str) -> OptionAnalysisOut:
    """Didactic, two-sided decision panel for a single option series."""
    ticker = ticker.upper()
    conn = _store_conn()
    if conn is None:
        raise HTTPException(status_code=404, detail="sem dado de mercado — defina ATLAS_DB e rode a ingestão")
    opt = store.get_option(conn, ticker)
    if not opt or not opt.get("strike"):
        conn.close()
        raise HTTPException(status_code=404, detail=f"opção {ticker} não encontrada na base")
    under = opt["underlying"]
    inst_u = store.get_instrument(conn, under or "") or {}
    spot = inst_u.get("ultimo")
    asof = store.get_meta(conn, "asof")
    closes = [c for (_d, c) in store.close_series(conn, under or "")]
    conn.close()
    if spot is None:
        raise HTTPException(status_code=422, detail=f"sem preço do subjacente {under} para analisar a opção")
    rv = realized_vol(closes[-21:]) if len(closes) >= 11 else float("nan")
    rv = None if rv != rv else rv
    dte = (date.fromisoformat(opt["venc"]) - date.fromisoformat(asof)).days if (opt.get("venc") and asof) else 0
    ctx = OptionCtx(
        ticker=ticker, underlying=under, kind=opt["kind"], strike=opt["strike"], venc=opt.get("venc") or "",
        dte=dte, last=opt.get("last") or 0.0, spot=spot, iv=opt.get("iv"), delta=opt.get("delta"),
        gamma=opt.get("gamma"), vega=opt.get("vega"), theta=opt.get("theta"),
        iv_rank=inst_u.get("iv_rank"), rv=rv,
    )
    prov = f"COTAHIST EOD {asof}" if asof else "COTAHIST EOD"
    return OptionAnalysisOut(**asdict(analyze_option(ctx)), provenance=prov, asof=asof)


@app.get("/surface/{ticker}", response_model=SurfaceResponse)
def surface(ticker: str) -> SurfaceResponse:
    """IV term structure (ATM IV per maturity) + the full smile x maturity grid."""
    ticker = ticker.upper()
    conn = _store_conn()
    if conn is None:
        return SurfaceResponse(ticker=ticker, expiries=[], points=[], provenance=_FIXTURE)
    rows = store.query_chain(conn, ticker, limit=3000)
    inst = store.get_instrument(conn, ticker)
    asof = store.get_meta(conn, "asof")
    conn.close()
    spot = inst["ultimo"] if inst else None
    prov = f"COTAHIST EOD {asof}" if asof else "COTAHIST EOD"
    if not spot or spot <= 0:
        return SurfaceResponse(ticker=ticker, spot=spot, expiries=[], points=[], provenance=prov, asof=asof)
    asof_d = date.fromisoformat(asof) if asof else None
    by_venc: dict[str, list] = {}
    for r in rows:
        if r["iv"] is None or r["strike"] is None or not r["venc"]:
            continue
        by_venc.setdefault(r["venc"], []).append(r)
    expiries: list[SurfaceExpiry] = []
    points: list[SurfacePoint] = []
    for venc in sorted(by_venc):
        opts = by_venc[venc]
        atm = min(opts, key=lambda o: abs(o["strike"] - spot))
        dte = (date.fromisoformat(venc) - asof_d).days if asof_d else 0
        expiries.append(SurfaceExpiry(venc=venc, dte=dte, atm_iv=round(atm["iv"], 4)))
        for o in opts:
            points.append(SurfacePoint(venc=venc, strike=o["strike"],
                                       moneyness=round(o["strike"] / spot, 4), iv=round(o["iv"], 4)))
    return SurfaceResponse(ticker=ticker, spot=spot, expiries=expiries, points=points, provenance=prov, asof=asof)


@app.get("/portfolio/stress", response_model=StressResponse)
def portfolio_stress() -> StressResponse:
    conn = _open_writable()
    inputs = _stress_inputs(conn)
    rows = _enrich_positions(conn)
    asof = store.get_meta(conn, "asof")
    conn.close()
    return StressResponse(
        scenarios=[StressPoint(shock_pct=round(s * 100, 1), pnl=stress_pnl(inputs, s)) for s in SPOT_SHOCKS],
        pnl_vol_up=round(sum(r.vega or 0.0 for r in rows) * 0.05, 2),  # IV +5 vol points
        theta_per_day=round(sum(r.theta or 0.0 for r in rows), 2),
        provenance=f"COTAHIST EOD {asof}" if asof else "sem dado de mercado",
        asof=asof or None,
    )


def _payoff_inputs(conn, asof: str | None) -> list[tuple]:
    """Per-position (kind, strike, spot, qty, mult, entry, iv, T) for the payoff.

    iv/T let the 'today' curve be a full revaluation (exact, no Taylor divergence);
    None for a stock leg.
    """
    asof_d = date.fromisoformat(asof) if asof else None
    out: list[tuple] = []
    for ticker, qty in store.list_positions(conn):
        inst = store.get_instrument(conn, ticker)
        if inst is None:
            continue
        if inst["tipo"] in ("call", "put"):
            opt = store.get_option(conn, ticker) or {}
            u = store.get_instrument(conn, opt.get("underlying") or "") or {}
            spot = u.get("ultimo")
            if spot is None or opt.get("strike") is None:
                continue
            t = year_fraction(asof_d, date.fromisoformat(opt["venc"])) if (asof_d and opt.get("venc")) else None
            out.append((inst["tipo"], opt["strike"], spot, qty, 100, opt.get("last") or 0.0, opt.get("iv"), t))
        else:
            out.append((None, None, inst["ultimo"] or 0.0, qty, 1, 0.0, None, None))  # stock leg
    return out


def _payoff_now(positions: list[tuple], shock: float, r: float) -> float:
    """Mark-to-market P&L today at a uniform spot ``shock`` — full revaluation.

    Options are repriced with Bjerksund-Stensland at the bumped spot (same IV/T);
    the difference is exactly 0 at shock 0 and captures convexity without Taylor
    divergence. Falls back to delta-only if IV/T are unavailable.
    """
    total = 0.0
    for kind, strike, spot, qty, mult, _entry, iv, t in positions:
        s2 = (spot or 0.0) * (1.0 + shock)
        if kind is None:
            total += (qty or 0.0) * (s2 - (spot or 0.0))
        elif iv and t and t > 0:
            v2 = bjerksund_stensland(kind, s2, strike, r, 0.0, t, iv)
            v0 = bjerksund_stensland(kind, spot, strike, r, 0.0, t, iv)
            total += (qty or 0.0) * mult * (v2 - v0)
    return round(total, 2)


@app.get("/portfolio/payoff", response_model=PayoffResponse)
def portfolio_payoff() -> PayoffResponse:
    """Risk graph: P&L today (full revaluation) vs at expiry (intrinsic) across spot."""
    conn = _open_writable()
    asof = store.get_meta(conn, "asof")
    try:
        r = float(store.get_meta(conn, "rate") or 0.14)
    except ValueError:
        r = 0.14
    p_in = _payoff_inputs(conn, asof)
    conn.close()
    pts = [
        PayoffPoint(shock_pct=round(s * 100, 1), pnl_now=_payoff_now(p_in, s, r), pnl_expiry=payoff_at_expiry(p_in, s))
        for s in payoff_grid()
    ]
    return PayoffResponse(
        points=pts,
        provenance=f"COTAHIST EOD {asof}" if asof else "sem dado de mercado",
        asof=asof or None,
    )
