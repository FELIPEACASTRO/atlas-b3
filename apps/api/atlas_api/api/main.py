"""ATLAS API — FastAPI app wiring pricing + analyst + the EOD store.

Serves real COTAHIST-ingested data from the store at ``ATLAS_DB``. There is no
synthetic/fixture data path: when the store is absent or empty, data endpoints
return 503 instead of fabricating numbers. Every row carries provenance + asof.
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
from dataclasses import asdict
from datetime import date, datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from atlas_api.agent import chat as chat_agent
from atlas_api.analyst.option_analysis import OptionCtx, analyze_option
from atlas_api.analyst.setups import call_spread_briefing
from atlas_api.data import store
from atlas_api.models import (
    BriefingResponse,
    ChainRow,
    ChatRequest,
    ChatResponse,
    ChatToolCall,
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
from atlas_api.pricing.risk import SPOT_SHOCKS, payoff_at_expiry, payoff_grid, stress_pnl
from atlas_api.pricing.rv import realized_vol
from atlas_api.pricing.signal import iv_rank
from atlas_api.predict.engine import (
    build_calibration_health,
    build_edge_map,
    build_fair_iv,
    build_prediction,
    build_pricing_kernel,
    build_strategies,
)

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
        # corrupted / not a sqlite file -> treat as "no real data" (503), never fake
        return None


def _require_conn() -> sqlite3.Connection:
    """Connection to a populated store, or 503 — never a synthetic fallback."""
    conn = _store_conn()
    if conn is None:
        raise HTTPException(
            status_code=503,
            detail="sem dado de mercado — defina ATLAS_DB e rode a ingestão (python -m atlas_api.cli update)",
        )
    return conn


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "atlas-api"}


@app.get("/summary")
def summary() -> dict:
    """Real headline metrics for the dashboard (no hardcoded numbers)."""
    conn = _require_conn()
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
    conn = _require_conn()
    asof = store.get_meta(conn, "asof") or ""
    try:
        b, err = call_spread_briefing(conn, underlying, capital=capital)
    finally:
        conn.close()
    if err:
        raise HTTPException(status_code=404 if "não encontrado" in err else 422, detail=err)
    return BriefingResponse(
        ticker=b.ticker, setup_facts=b.setup_facts, case_for=b.case_for, case_against=b.case_against,
        risk_reward=RiskRewardOut(**vars(b.risk_reward)),
        sizing={k: SizingOut(**vars(v)) for k, v in b.sizing.items()},
        invalidation=b.invalidation, confidence=b.confidence, verdict=b.verdict,
        provenance=f"COTAHIST EOD {asof}" if asof else "COTAHIST EOD", asof=asof or _now(),
    )


@app.get("/screener", response_model=list[ScreenerRow])
def screener() -> list[ScreenerRow]:
    conn = _require_conn()
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
    conn = _require_conn()
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
    conn = _require_conn()
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


@app.get("/predict/{ticker}")
def predict(ticker: str, horizon: int = 30) -> dict:
    """Predição calibrada: σ forecast + densidade física (POP/quantis) + regime + calibração.

    Tudo sobre o dado real do store; honesto quando o histórico é curto (sem fabricar).
    """
    ticker = ticker.upper()
    conn = _require_conn()
    inst = store.get_instrument(conn, ticker)
    spot = inst.get("ultimo") if inst else None
    ohlc = store.price_history(conn, ticker, limit=400)
    iv_hist = store.iv_history(conn, ticker, limit=400)
    chain = store.query_chain(conn, ticker, limit=3000)
    asof = store.get_meta(conn, "asof")
    conn.close()
    closes = [bar[3] for bar in ohlc]            # closes do próprio OHLC: alinhamento garantido
    return build_prediction(ticker=ticker, ohlc=ohlc, closes=closes, iv_history=iv_hist,
                            spot=spot, chain=chain, asof=asof, T_days=horizon)


@app.get("/strategies/{ticker}")
def strategies(ticker: str, capital: float = 20000.0, prazo: int = 30, visao: str = "alta") -> dict:
    """Consultor de estratégias: catálogo de estruturas avaliadas por POP + valor esperado.

    ``capital`` = orçamento de risco; ``visao`` ∈ {alta, baixa, neutro, renda}. Análise sobre
    a densidade real do motor + a cadeia real; honesto quando falta dado. Nunca ordem.
    """
    ticker = ticker.upper()
    conn = _require_conn()
    inst = store.get_instrument(conn, ticker)
    spot = inst.get("ultimo") if inst else None
    ohlc = store.price_history(conn, ticker, limit=400)
    iv_hist = store.iv_history(conn, ticker, limit=400)
    chain = store.query_chain(conn, ticker, limit=5000)
    asof = store.get_meta(conn, "asof")
    conn.close()
    closes = [bar[3] for bar in ohlc]
    return build_strategies(ticker=ticker, ohlc=ohlc, closes=closes, iv_history=iv_hist,
                            spot=spot, chain=chain, asof=asof, capital=capital, prazo=prazo, visao=visao)


@app.get("/edge/{ticker}")
def edge(ticker: str, horizon: int = 30) -> dict:
    """Mapa de Prêmio: prob. RISCO-NEUTRA (mercado) vs FÍSICA calibrada, por strike — o diferencial.

    Mostra onde e por quanto o mercado sobrevaloriza/subvaloriza cada strike vs a nossa densidade
    validada. Honesto: recusa quando a smile de mercado não é confiável. Análise, não recomendação.
    """
    ticker = ticker.upper()
    conn = _require_conn()
    inst = store.get_instrument(conn, ticker)
    spot = inst.get("ultimo") if inst else None
    ohlc = store.price_history(conn, ticker, limit=400)
    iv_hist = store.iv_history(conn, ticker, limit=400)
    chain = store.query_chain(conn, ticker, limit=5000)
    asof = store.get_meta(conn, "asof")
    conn.close()
    closes = [bar[3] for bar in ohlc]
    return build_edge_map(ticker=ticker, ohlc=ohlc, closes=closes, iv_history=iv_hist,
                          spot=spot, chain=chain, asof=asof, T_days=horizon)


@app.get("/kernel/{ticker}")
def kernel(ticker: str, horizon: int = 30) -> dict:
    """Pricing kernel empírico M(S)=q/p — o SDF por nome (a forma teoricamente correta do Edge Map).

    O preço de estado por unidade de probabilidade: onde o mercado paga prêmio de risco. Só o ATLAS
    monta (exige a densidade física calibrada). Honesto: recusa quando a smile não é confiável.
    """
    ticker = ticker.upper()
    conn = _require_conn()
    inst = store.get_instrument(conn, ticker)
    spot = inst.get("ultimo") if inst else None
    ohlc = store.price_history(conn, ticker, limit=400)
    iv_hist = store.iv_history(conn, ticker, limit=400)
    chain = store.query_chain(conn, ticker, limit=5000)
    asof = store.get_meta(conn, "asof")
    conn.close()
    closes = [bar[3] for bar in ohlc]
    return build_pricing_kernel(ticker=ticker, ohlc=ohlc, closes=closes, iv_history=iv_hist,
                                spot=spot, chain=chain, asof=asof, T_days=horizon)


@app.get("/fair-iv/{ticker}")
def fair_iv(ticker: str, horizon: int = 30) -> dict:
    """Fair IV: a smile justa pela nossa vol física vs a smile de mercado — o VRP por strike em vol points.

    A língua do trader: quantos pontos de vol o mercado cobra acima do justo, por strike, e onde está a
    maior oportunidade. Honesto: recusa quando a smile de mercado não é confiável.
    """
    ticker = ticker.upper()
    conn = _require_conn()
    inst = store.get_instrument(conn, ticker)
    spot = inst.get("ultimo") if inst else None
    ohlc = store.price_history(conn, ticker, limit=400)
    iv_hist = store.iv_history(conn, ticker, limit=400)
    chain = store.query_chain(conn, ticker, limit=5000)
    asof = store.get_meta(conn, "asof")
    conn.close()
    closes = [bar[3] for bar in ohlc]
    return build_fair_iv(ticker=ticker, ohlc=ohlc, closes=closes, iv_history=iv_hist,
                         spot=spot, chain=chain, asof=asof, T_days=horizon)


@app.get("/calibration-health/{ticker}")
def calibration_health(ticker: str) -> dict:
    """Monitor de descalibração (PIT-break): a densidade ainda está confiável HOJE, e desde quando.

    Série rolante do p-valor do PIT — quando cai sob 0.05, o modelo perdeu o regime. Honestidade
    auditada como sinal: dá a saúde atual e há quantos pregões foi a última quebra.
    """
    ticker = ticker.upper()
    conn = _require_conn()
    ohlc = store.price_history(conn, ticker, limit=400)
    asof = store.get_meta(conn, "asof")
    conn.close()
    closes = [bar[3] for bar in ohlc]
    return build_calibration_health(ticker=ticker, ohlc=ohlc, closes=closes, asof=asof)


@app.get("/option/{ticker}", response_model=OptionAnalysisOut)
def option_panel(ticker: str) -> OptionAnalysisOut:
    """Didactic, two-sided decision panel for a single option series."""
    ticker = ticker.upper()
    conn = _require_conn()
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
    conn = _require_conn()
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
    """Per-position (kind, strike, spot, qty, mult, entry, iv, T, delta) for the payoff.

    iv/T let the 'today' curve be a full revaluation (exact, no Taylor divergence);
    ``delta`` is the linear fallback when IV/T are missing. None for a stock leg.
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
            out.append((inst["tipo"], opt["strike"], spot, qty, 100,
                        opt.get("last") or 0.0, opt.get("iv"), t, opt.get("delta")))
        else:
            out.append((None, None, inst["ultimo"] or 0.0, qty, 1, 0.0, None, None, None))  # stock leg
    return out


def _payoff_now(positions: list[tuple], shock: float, r: float) -> float:
    """Mark-to-market P&L today at a uniform spot ``shock`` — full revaluation.

    Options are repriced with Bjerksund-Stensland at the bumped spot (same IV/T);
    the difference is exactly 0 at shock 0 and captures convexity without Taylor
    divergence. When IV/T are unavailable (IV suppressed by the reliability gate),
    it falls back to a linear delta approximation rather than silently flatlining
    that leg; a leg with neither IV nor delta contributes 0 (and is, honestly,
    unknown today).
    """
    total = 0.0
    for kind, strike, spot, qty, mult, _entry, iv, t, delta in positions:
        s2 = (spot or 0.0) * (1.0 + shock)
        ds = s2 - (spot or 0.0)
        if kind is None:
            total += (qty or 0.0) * ds
        elif iv and t and t > 0:
            v2 = bjerksund_stensland(kind, s2, strike, r, 0.0, t, iv)
            v0 = bjerksund_stensland(kind, spot, strike, r, 0.0, t, iv)
            total += (qty or 0.0) * mult * (v2 - v0)
        elif delta is not None:  # IV/T missing -> linear delta fallback (documented)
            total += (qty or 0.0) * mult * delta * ds
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


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    """Natural-language Q&A about options and stocks, grounded in the real store.

    The LLM (or the deterministic fallback) may only report numbers a tool
    returned from this same EOD store — it cannot invent prices/IV/greeks.
    Analysis, not recommendation; every reply carries provenance + asof.
    """
    conn = _require_conn()
    asof = store.get_meta(conn, "asof")
    try:
        res = chat_agent.answer(req.question, req.history, conn=conn)
    finally:
        conn.close()
    return ChatResponse(
        answer=res.answer,
        mode=res.mode,
        tool_calls=[ChatToolCall(name=c["name"], args=c.get("args", {})) for c in res.tool_calls],
        provenance=f"COTAHIST EOD {asof}" if asof else "COTAHIST EOD",
        asof=asof,
        note=res.note,
    )


@app.post("/chat/stream")
def chat_stream(req: ChatRequest) -> StreamingResponse:
    """Same as /chat, but streamed (SSE): 'tool' / 'delta' events then 'done'.

    Lets the UI render the answer token-by-token and show which tools were
    consulted as they fire. Grounding is identical — numbers only from tools.
    """
    conn = _require_conn()
    asof = store.get_meta(conn, "asof")
    prov = f"COTAHIST EOD {asof}" if asof else "COTAHIST EOD"

    def gen():
        try:
            for ev in chat_agent.answer_stream(req.question, req.history, conn=conn):
                if ev.get("type") == "done":
                    ev = {**ev, "provenance": prov, "asof": asof}
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except Exception as e:  # never leak a raw stack into the stream
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        finally:
            conn.close()

    return StreamingResponse(gen(), media_type="text/event-stream")
