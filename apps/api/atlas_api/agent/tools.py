"""Grounded data tools — the only way the chat sees a number.

Each tool is a pure function ``f(conn, **args) -> dict`` that queries the real
store (same SQLite the REST routes use) and returns compact, JSON-safe data.
The LLM (or the deterministic fallback) calls these; it cannot fabricate prices,
IV or greeks because the figures only ever come back from here.

``TOOL_SCHEMAS`` is the Anthropic ``tools`` array (JSON-schema inputs);
``dispatch`` runs a tool by name and turns any failure into ``{"error": ...}``
so the agent loop can report the gap honestly instead of crashing.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Any, Callable

from atlas_api.analyst.option_analysis import OptionCtx
from atlas_api.analyst.option_analysis import analyze_option as _analyze_option
from atlas_api.data import store
from atlas_api.pricing.rv import realized_vol

_UNDERLYING_TIPOS = ("acao", "indice")


def _r(x: Any, n: int = 4) -> Any:
    if x is None:
        return None
    if isinstance(x, float) and math.isnan(x):
        return None
    if isinstance(x, float):
        return round(x, n)
    return x


def _dte(venc: str | None, asof: str | None) -> int | None:
    if not venc or not asof:
        return None
    try:
        return (date.fromisoformat(venc) - date.fromisoformat(asof)).days
    except ValueError:
        return None


def _moneyness(kind: str, spot: float | None, strike: float | None) -> str:
    if not spot or spot <= 0 or strike is None:
        return "?"
    if abs(spot - strike) <= 0.02 * spot:
        return "ATM"
    if kind == "call":
        return "ITM" if spot > strike else "OTM"
    return "ITM" if spot < strike else "OTM"


def _trailing_rv(conn, ticker: str) -> float | None:
    closes = [c for (_d, c) in store.close_series(conn, ticker)]
    if len(closes) < 11:
        return None
    rv = realized_vol(closes[-21:])
    return _r(rv) if rv == rv else None


def _features(conn, ticker: str) -> dict:
    row = conn.execute(
        "SELECT vrp, pc_ratio, skew FROM underlying_features WHERE ticker = ?", (ticker,)
    ).fetchone()
    return dict(row) if row else {}


# --- tools -----------------------------------------------------------------

def screen_underlyings(conn, *, tipo: str | None = None, signal: str | None = None,
                       order: str | None = None, limit: int = 15) -> dict:
    """Underlyings (ações + índices) with IV / IV Rank / VRP, filterable and sorted."""
    limit = max(1, min(int(limit or 15), 50))
    rows = [r for r in store.query_screener(conn, limit=10000)
            if r["tipo"] in _UNDERLYING_TIPOS]
    wanted = {"acao", "indice"} if tipo in (None, "todos") else {tipo}
    rows = [r for r in rows if r["tipo"] in wanted]
    if signal:
        rows = [r for r in rows if r.get("iv_vs_rv") == signal]

    def _key(r, field):
        v = r.get(field)
        return v if isinstance(v, (int, float)) and not (isinstance(v, float) and math.isnan(v)) else -1e18

    if order == "iv_rank_desc":
        rows.sort(key=lambda r: _key(r, "iv_rank"), reverse=True)
    elif order == "iv_rank_asc":
        rows.sort(key=lambda r: -_key(r, "iv_rank"), reverse=True)
    elif order == "vrp_desc":
        rows.sort(key=lambda r: _key(r, "vrp"), reverse=True)
    else:  # default: most liquid first
        rows.sort(key=lambda r: _key(r, "liquidez"), reverse=True)

    out = [{
        "ticker": r["ticker"], "tipo": r["tipo"],
        "ultimo": _r(r.get("ultimo"), 2), "var_pct": _r(r.get("var_pct"), 2),
        "liquidez": _r(r.get("liquidez"), 0), "iv": _r(r.get("iv")),
        "iv_rank": _r(r.get("iv_rank"), 1), "sinal_iv_vs_rv": r.get("iv_vs_rv"),
        "vrp": _r(r.get("vrp")), "pc_ratio": _r(r.get("pc_ratio")), "skew": _r(r.get("skew")),
    } for r in rows[:limit]]
    return {"asof": store.get_meta(conn, "asof"), "n": len(out), "underlyings": out}


def underlying_snapshot(conn, *, ticker: str) -> dict:
    """One underlying: spot, IV, IV Rank, VRP, realized vol and how many options exist."""
    ticker = (ticker or "").upper().strip()
    inst = store.get_instrument(conn, ticker)
    if inst is None or inst["tipo"] not in _UNDERLYING_TIPOS:
        return {"error": f"{ticker} não é um subjacente conhecido na base (ações/índices)."}
    feat = _features(conn, ticker)
    chain = store.query_chain(conn, ticker, limit=5000)
    vencs = sorted({o["venc"] for o in chain if o.get("venc")})
    return {
        "asof": store.get_meta(conn, "asof"),
        "ticker": ticker, "tipo": inst["tipo"],
        "ultimo": _r(inst.get("ultimo"), 2), "var_pct": _r(inst.get("var_pct"), 2),
        "liquidez": _r(inst.get("liquidez"), 0),
        "iv_atm": _r(inst.get("iv")), "iv_rank": _r(inst.get("iv_rank"), 1),
        "rv_realizada": _trailing_rv(conn, ticker),
        "sinal_iv_vs_rv": inst.get("iv_vs_rv"),
        "vrp": _r(feat.get("vrp")), "pc_ratio": _r(feat.get("pc_ratio")), "skew": _r(feat.get("skew")),
        "n_opcoes": len(chain), "vencimentos": vencs[:8],
    }


def search_options(conn, *, underlying: str, kind: str | None = None,
                   moneyness: str | None = None, min_dte: int | None = None,
                   max_dte: int | None = None, order: str | None = None,
                   limit: int = 12) -> dict:
    """Options of an underlying, filterable by tipo/moneyness/prazo and sortable."""
    underlying = (underlying or "").upper().strip()
    inst = store.get_instrument(conn, underlying)
    spot = inst.get("ultimo") if inst else None
    asof = store.get_meta(conn, "asof")
    limit = max(1, min(int(limit or 12), 40))
    rows = store.query_chain(conn, underlying, limit=5000)
    if not rows:
        return {"error": f"sem cadeia de opções para {underlying} na base."}

    items = []
    for o in rows:
        if kind and o["kind"] != kind:
            continue
        d = _dte(o.get("venc"), asof)
        if min_dte is not None and (d is None or d < min_dte):
            continue
        if max_dte is not None and (d is None or d > max_dte):
            continue
        mny = _moneyness(o["kind"], spot, o.get("strike"))
        if moneyness and mny != moneyness:
            continue
        items.append({
            "ticker": o["ticker"], "kind": o["kind"], "strike": _r(o.get("strike"), 2),
            "venc": o.get("venc"), "dte": d, "ultimo": _r(o.get("last"), 2),
            "iv": _r(o.get("iv")), "delta": _r(o.get("delta"), 3),
            "theta_dia": _r(o.get("theta"), 4), "moneyness": mny,
        })

    def _num(v):
        return v if isinstance(v, (int, float)) else 1e18

    if order == "cheapest":
        items.sort(key=lambda x: _num(x["ultimo"]))
    elif order == "expensive":
        items.sort(key=lambda x: -_num(x["ultimo"]))
    elif order == "dte":
        items.sort(key=lambda x: _num(x["dte"]))
    elif order == "delta_desc":
        items.sort(key=lambda x: -abs(_num(x["delta"])))

    return {
        "asof": asof, "underlying": underlying,
        "spot": _r(spot, 2), "iv_rank": _r(inst.get("iv_rank"), 1) if inst else None,
        "n": min(len(items), limit), "total_encontradas": len(items),
        "opcoes": items[:limit],
    }


def analyze_option(conn, *, ticker: str) -> dict:
    """Full two-sided decision panel for one option series (the /option brain)."""
    ticker = (ticker or "").upper().strip()
    opt = store.get_option(conn, ticker)
    if not opt or not opt.get("strike"):
        return {"error": f"opção {ticker} não encontrada na base."}
    under = opt["underlying"]
    inst_u = store.get_instrument(conn, under or "") or {}
    spot = inst_u.get("ultimo")
    if spot is None:
        return {"error": f"sem preço do subjacente {under} para analisar {ticker}."}
    asof = store.get_meta(conn, "asof")
    dte = _dte(opt.get("venc"), asof) or 0
    ctx = OptionCtx(
        ticker=ticker, underlying=under, kind=opt["kind"], strike=opt["strike"],
        venc=opt.get("venc") or "", dte=dte, last=opt.get("last") or 0.0, spot=spot,
        iv=opt.get("iv"), delta=opt.get("delta"), gamma=opt.get("gamma"),
        vega=opt.get("vega"), theta=opt.get("theta"),
        iv_rank=inst_u.get("iv_rank"), rv=_trailing_rv(conn, under or ""),
    )
    a = _analyze_option(ctx)
    return {
        "asof": asof, "ticker": a.ticker, "underlying": a.underlying, "tipo": a.tipo_label,
        "strike": a.strike, "venc": a.venc, "dte": a.dte, "ultimo": a.last, "spot": a.spot,
        "moneyness": f"{a.moneyness} ({a.moneyness_txt})",
        "intrinseco": a.intrinsic, "valor_de_tempo": a.extrinsic,
        "iv": _r(a.iv), "iv_rank": _r(a.iv_rank, 1), "vrp": _r(a.vrp),
        "breakeven": a.breakeven, "perda_max_titular": a.max_perda_titular,
        "custo_theta_dia": a.custo_theta_dia,
        "resumo": a.resumo, "analogia": a.analogia, "micro": a.micro, "macro": a.macro,
        "pros": a.pros, "contras": a.contras,
        "se_comprar": a.comprar, "se_vender_ou_sair": a.vender_sair,
        "gregas": [{"nome": g.nome, "valor": g.valor, "explicacao": g.explicacao} for g in a.gregas],
        "veredito": a.veredito,
    }


def vol_history(conn, *, ticker: str, window: int = 21) -> dict:
    """Where current IV sits vs its own history, and IV vs realized vol (VRP)."""
    ticker = (ticker or "").upper().strip()
    series = store.iv_series(conn, ticker)
    if not series:
        return {"error": f"sem histórico de IV para {ticker} na base."}
    ivs = [v for (_d, v) in series]
    latest_iv = ivs[-1]
    lo, hi = min(ivs), max(ivs)
    rank = round((latest_iv - lo) / (hi - lo) * 100, 1) if hi > lo else None
    rv = _trailing_rv(conn, ticker)
    return {
        "asof": store.get_meta(conn, "asof"), "ticker": ticker,
        "n_sessoes": len(ivs), "primeira_data": series[0][0], "ultima_data": series[-1][0],
        "iv_atual": _r(latest_iv), "iv_min": _r(lo), "iv_max": _r(hi),
        "iv_rank_janela": rank, "rv_realizada": rv,
        "vrp": _r(latest_iv - rv) if rv is not None else None,
    }


# --- registry + schemas ----------------------------------------------------

_REGISTRY: dict[str, Callable[..., dict]] = {
    "screen_underlyings": screen_underlyings,
    "underlying_snapshot": underlying_snapshot,
    "search_options": search_options,
    "analyze_option": analyze_option,
    "vol_history": vol_history,
}

TOOL_SCHEMAS: list[dict] = [
    {
        "name": "screen_underlyings",
        "description": "Lista ações e índices da base com último preço, IV, IV Rank, VRP e o "
                       "sinal IV-vs-RV (rico/barato/neutro). Use para 'quais ativos têm vol cara/barata', "
                       "rankings e panorama. Não inventa: só retorna o que está na base EOD.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tipo": {"type": "string", "enum": ["acao", "indice", "todos"],
                         "description": "filtrar por tipo de subjacente (padrão: todos)"},
                "signal": {"type": "string", "enum": ["rico", "barato", "neutro"],
                           "description": "filtrar pelo sinal IV-vs-RV"},
                "order": {"type": "string",
                          "enum": ["liquidez", "iv_rank_desc", "iv_rank_asc", "vrp_desc"],
                          "description": "ordenação (padrão: liquidez)"},
                "limit": {"type": "integer", "description": "máx. de linhas (1-50, padrão 15)"},
            },
        },
    },
    {
        "name": "underlying_snapshot",
        "description": "Retrato de UM subjacente (ex: PETR4, VALE3, BOVA11): spot, variação, "
                       "IV ATM, IV Rank, VRP, vol realizada e quantas opções/vencimentos existem.",
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string", "description": "ticker do subjacente, ex: PETR4"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "search_options",
        "description": "Busca opções de um subjacente, com filtros de tipo (call/put), moneyness "
                       "(ITM/ATM/OTM), prazo (dte) e ordenação (mais baratas, por prazo, por delta). "
                       "Use para 'calls baratas da PETR4', 'puts ATM da VALE3 pra 30 dias', etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "underlying": {"type": "string", "description": "subjacente, ex: PETR4"},
                "kind": {"type": "string", "enum": ["call", "put"]},
                "moneyness": {"type": "string", "enum": ["ITM", "ATM", "OTM"]},
                "min_dte": {"type": "integer", "description": "prazo mínimo em dias corridos"},
                "max_dte": {"type": "integer", "description": "prazo máximo em dias corridos"},
                "order": {"type": "string", "enum": ["cheapest", "expensive", "dte", "delta_desc"]},
                "limit": {"type": "integer", "description": "máx. de opções (1-40, padrão 12)"},
            },
            "required": ["underlying"],
        },
    },
    {
        "name": "analyze_option",
        "description": "Painel de decisão completo e dos dois lados para UMA opção (ex: PETRA38): "
                       "resumo, analogia do dia a dia, prós, contras, breakeven, perda máxima, gregas "
                       "traduzidas, o que olhar pra comprar (titular) vs vender/sair (lançador) e um "
                       "veredito honesto. Use quando perguntarem se vale a pena uma opção específica.",
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string", "description": "código da opção, ex: PETRA38"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "vol_history",
        "description": "Onde a IV atual de um subjacente está frente ao próprio histórico (IV Rank "
                       "da janela) e a IV vs vol realizada (VRP). Use para 'a vol da PETR4 está alta?'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "subjacente, ex: PETR4"},
                "window": {"type": "integer", "description": "janela da RV em sessões (padrão 21)"},
            },
            "required": ["ticker"],
        },
    },
]


def dispatch(conn, name: str, args: dict | None) -> dict:
    """Run a tool by name; never raises — failures come back as {'error': ...}."""
    fn = _REGISTRY.get(name)
    if fn is None:
        return {"error": f"ferramenta desconhecida: {name}"}
    try:
        return fn(conn, **(args or {}))
    except TypeError as e:
        return {"error": f"argumentos inválidos para {name}: {e}"}
    except Exception as e:  # store/quant failure — report, don't crash the chat
        return {"error": f"falha ao executar {name}: {e}"}
