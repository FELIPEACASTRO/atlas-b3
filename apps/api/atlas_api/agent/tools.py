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

from atlas_api.analyst.briefing import Setup, build_briefing
from atlas_api.analyst.option_analysis import OptionCtx
from atlas_api.analyst.option_analysis import analyze_option as _analyze_option
from atlas_api.data import store
from atlas_api.pricing.risk import SPOT_SHOCKS, payoff_at_expiry, payoff_grid, stress_pnl
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


def market_summary(conn) -> dict:
    """Panorama do dia (módulo Radar): quantos ativos têm sinal, quantos com vol
    cara/barata, liquidez total e o nível do BOVA11."""
    asof = store.get_meta(conn, "asof")
    rows = [r for r in store.query_screener(conn, limit=10000) if r["tipo"] == "acao"]
    sig = [r for r in rows if r.get("iv_vs_rv") in ("rico", "barato", "neutro")]
    return {
        "asof": asof,
        "n_acoes": len(rows),
        "com_sinal_iv_vs_rv": len(sig),
        "vol_cara_rico": sum(1 for r in sig if r["iv_vs_rv"] == "rico"),
        "vol_barata_barato": sum(1 for r in sig if r["iv_vs_rv"] == "barato"),
        "neutro": sum(1 for r in sig if r["iv_vs_rv"] == "neutro"),
        "liquidez_total_rs": _r(sum((r.get("liquidez") or 0.0) for r in rows), 0),
        "bova11": next((_r(r.get("ultimo"), 2) for r in rows if r["ticker"] == "BOVA11"), None),
    }


def term_structure(conn, *, ticker: str) -> dict:
    """Estrutura a termo (IV ATM por vencimento) + inclinação e skew — o que o
    módulo Opções mostra na superfície de volatilidade."""
    ticker = (ticker or "").upper().strip()
    inst = store.get_instrument(conn, ticker)
    spot = inst.get("ultimo") if inst else None
    asof = store.get_meta(conn, "asof")
    rows = store.query_chain(conn, ticker, limit=5000)
    if not spot or spot <= 0 or not rows:
        return {"error": f"sem dados suficientes de superfície para {ticker}."}
    by_venc: dict[str, list] = {}
    for r in rows:
        if r.get("iv") is None or r.get("strike") is None or not r.get("venc"):
            continue
        by_venc.setdefault(r["venc"], []).append(r)
    if not by_venc:
        return {"error": f"sem IV válida na cadeia de {ticker}."}
    expiries = []
    for venc in sorted(by_venc):
        opts = by_venc[venc]
        atm = min(opts, key=lambda o: abs(o["strike"] - spot))
        expiries.append({"venc": venc, "dte": _dte(venc, asof), "atm_iv": _r(atm["iv"])})
    slope = None
    if len(expiries) >= 2 and expiries[0]["atm_iv"] and expiries[-1]["atm_iv"]:
        slope = _r(expiries[-1]["atm_iv"] - expiries[0]["atm_iv"])
    feat = _features(conn, ticker)
    return {
        "asof": asof, "ticker": ticker, "spot": _r(spot, 2),
        "estrutura_a_termo": expiries[:8],
        "inclinacao_termo": slope,  # >0: vol sobe com o prazo (estrutura ascendente)
        "skew": _r(feat.get("skew")), "pc_ratio": _r(feat.get("pc_ratio")),
    }


def briefing(conn, *, underlying: str, capital: float = 50000.0) -> dict:
    """Briefing do Analista: monta uma trava de alta vendida (call spread) real do
    vencimento mais próximo e devolve os dois lados + sizing para 3 perfis."""
    underlying = (underlying or "").upper().strip()
    stocks = [r for r in store.query_screener(conn, limit=10000) if r["ticker"] == underlying]
    if not stocks:
        return {"error": f"{underlying} não encontrado na base."}
    spot = stocks[0].get("ultimo")
    closes = [c for (_d, c) in store.close_series(conn, underlying)]
    chain = store.query_chain(conn, underlying)
    asof = store.get_meta(conn, "asof")
    rv = realized_vol(closes) if len(closes) >= 3 else float("nan")
    calls = [o for o in chain if o["kind"] == "call" and o.get("iv") is not None
             and o.get("strike") and o.get("venc")]
    if spot is None or rv != rv or len(calls) < 2:
        return {"error": f"dados insuficientes para um briefing de {underlying} "
                         "(precisa de vol realizada + cadeia de calls com IV)."}
    near_venc = min(o["venc"] for o in calls)
    near = sorted((o for o in calls if o["venc"] == near_venc), key=lambda o: o["strike"])
    i = min(range(len(near)), key=lambda k: abs(near[k]["strike"] - spot))
    if i + 1 >= len(near):
        i = len(near) - 2
    short_leg, long_leg = near[i], near[i + 1]
    width = long_leg["strike"] - short_leg["strike"]
    credit = short_leg["last"] - long_leg["last"]
    dte = _dte(near_venc, asof) or 21
    b = build_briefing(Setup(
        ticker=short_leg["ticker"], underlying=underlying, structure="trava_alta_vendida",
        iv=short_leg["iv"], rv=round(rv, 4), max_gain_per_lot=round(max(credit, 0.0), 2),
        max_loss_per_lot=round(max(width - credit, 0.01), 2),
        breakeven=round(short_leg["strike"] + credit, 2), delta=short_leg.get("delta") or 0.3,
        liquidity_brl=stocks[0].get("liquidez") or 0.0, dte=max(dte, 1), capital=capital))
    return {
        "asof": asof, "ticker": b.ticker, "underlying": underlying,
        "estrutura": "trava de alta vendida (call spread de crédito), vencimento mais próximo",
        "fatos": b.setup_facts, "a_favor": b.case_for, "contra": b.case_against,
        "risco_retorno": {"ganho_max_por_lote": b.risk_reward.max_gain_per_lot,
                          "perda_max_por_lote": b.risk_reward.max_loss_per_lot,
                          "breakeven": b.risk_reward.breakeven, "razao": _r(b.risk_reward.ratio, 2)},
        "tamanho_por_perfil": {k: {"pct_capital": v.pct_capital, "lotes": v.lotes,
                                   "perda_max_rs": v.max_loss_brl} for k, v in b.sizing.items()},
        "invalidacao": b.invalidation, "confianca": b.confidence, "veredito": b.verdict,
    }


def portfolio(conn) -> dict:
    """Carteira: posições, gregas líquidas, valor, theta/dia, stress de mercado e
    faixa de payoff no vencimento. Tudo da tabela real de posições do usuário."""
    asof = store.get_meta(conn, "asof")
    poss = store.list_positions(conn)
    if not poss:
        return {"asof": asof, "n_posicoes": 0,
                "mensagem": "A carteira está vazia. Adicione posições (ações ou opções) no módulo "
                            "Carteira para ver risco líquido, stress e payoff."}
    positions, nd, ng, nv, nt, tv = [], 0.0, 0.0, 0.0, 0.0, 0.0
    stress_in, pay_in = [], []
    for ticker, qty in poss:
        inst = store.get_instrument(conn, ticker)
        if inst is None:
            positions.append({"ticker": ticker, "qty": qty, "obs": "mantida, sem cotação atual"})
            continue
        tipo, last = inst["tipo"], inst.get("ultimo")
        if tipo in ("call", "put"):
            opt = store.get_option(conn, ticker) or {}
            mult = 100
            d, g, v, th = (opt.get("delta") or 0.0, opt.get("gamma") or 0.0,
                           opt.get("vega") or 0.0, opt.get("theta") or 0.0)
            uspot = (store.get_instrument(conn, opt.get("underlying") or "") or {}).get("ultimo")
            strike, entry = opt.get("strike"), opt.get("last") or 0.0
        else:
            mult, d, g, v, th, uspot, strike, entry = 1, 1.0, 0.0, 0.0, 0.0, last, None, 0.0
        pd_, pg, pv, pt = qty * d * mult, qty * g * mult, qty * v * mult, qty * th * mult
        val = round(qty * last * mult, 2) if last is not None else None
        nd, ng, nv, nt, tv = nd + pd_, ng + pg, nv + pv, nt + pt, tv + (val or 0.0)
        positions.append({"ticker": ticker, "tipo": tipo, "qty": qty, "ultimo": _r(last, 2),
                          "valor": val, "delta": _r(pd_, 4), "theta_dia": _r(pt, 4)})
        if uspot is not None:
            stress_in.append((pd_, pg, pv, uspot))
            if tipo in ("call", "put") and strike is not None:
                pay_in.append((tipo, strike, uspot, qty, 100, entry))
            elif tipo not in ("call", "put"):
                pay_in.append((None, None, last or 0.0, qty, 1, 0.0))
    pay = [payoff_at_expiry(pay_in, s) for s in payoff_grid()] if pay_in else [0.0]
    return {
        "asof": asof, "n_posicoes": len(poss), "valor_total": round(tv, 2), "posicoes": positions,
        "gregas_liquidas": {"delta": _r(nd, 2), "gamma": _r(ng, 4), "vega": _r(nv, 2),
                            "theta_dia": _r(nt, 2)},
        "theta_dia_rs": _r(nt, 2), "pnl_se_vol_sobe_5_pontos": _r(nv * 0.05, 2),
        "stress_mercado": [{"var_pct": round(s * 100, 1), "pnl": stress_pnl(stress_in, s)}
                           for s in SPOT_SHOCKS],
        "payoff_vencimento": {"melhor": _r(max(pay), 2), "pior": _r(min(pay), 2), "faixa": "±30%"},
    }


def solution_overview(conn) -> dict:
    """What ATLAS is + what's in the base (live counts), so the chat can explain
    the solution itself — modules, data coverage, models, most-liquid names."""
    asof = store.get_meta(conn, "asof")
    hist = conn.execute(
        "SELECT COUNT(DISTINCT date) n, MIN(date) a, MAX(date) b FROM prices_daily").fetchone()
    n_acoes = conn.execute("SELECT COUNT(*) FROM instruments WHERE tipo='acao'").fetchone()[0]
    n_indices = conn.execute("SELECT COUNT(*) FROM instruments WHERE tipo='indice'").fetchone()[0]
    n_opcoes = conn.execute("SELECT COUNT(*) FROM options").fetchone()[0]
    liq = [r for r in store.query_screener(conn, limit=10000) if r["tipo"] in _UNDERLYING_TIPOS]
    liq.sort(key=lambda r: r.get("liquidez") or 0, reverse=True)
    mais_liquidos = [{"ticker": r["ticker"], "ultimo": _r(r.get("ultimo"), 2),
                      "liquidez": _r(r.get("liquidez"), 0)} for r in liq[:6]]
    return {
        "asof": asof,
        "o_que_e": ("ATLAS — terminal local de apoio à decisão para opções da B3. Mostra fatos e "
                    "análise transparente (cada número com proveniência e data 'asof'), nunca "
                    "profecia; não dá ordem de compra/venda — a decisão é sempre do usuário."),
        "modulos": [
            {"nome": "Radar / Screener", "descricao": "panorama do dia: IV, IV Rank, VRP, sinal "
             "IV-vs-RV (rico/barato), liquidez e filtros"},
            {"nome": "Opções", "descricao": "cadeia com IV e gregas, gráfico IV vs RV, superfície "
             "de volatilidade e um painel por opção (prós/contras, comprar vs vender)"},
            {"nome": "Carteira", "descricao": "posições, risco líquido (delta/gamma/vega/theta), "
             "stress de mercado e diagrama de payoff (hoje vs no vencimento)"},
            {"nome": "Analista", "descricao": "briefing honesto por ativo, com os dois lados e "
             "3 perfis de risco"},
            {"nome": "Chat", "descricao": "este assistente — responde em linguagem natural e "
             "alcança todas as telas: panorama do mercado, screener, cadeia e análise de opções, "
             "histórico e estrutura a termo de vol, briefing de operação e a sua carteira "
             "(risco/stress/payoff), sempre ancorado nestes mesmos dados reais"},
        ],
        "dados": {
            "fonte": "COTAHIST EOD (fechamento de mercado, B3)",
            "subjacentes": n_acoes + n_indices, "acoes": n_acoes, "indices": n_indices,
            "opcoes": n_opcoes, "sessoes_historico": hist["n"],
            "periodo": [hist["a"], hist["b"]],
        },
        "cobertura": ("opções sobre ações (americanas, modelo Bjerksund-Stensland) e sobre o "
                      "Ibovespa/IBOV (europeias). Fora de escopo: futuros (WIN/WDO/DI1) e intraday."),
        "modelos": ("Black-Scholes, IV com filtro econômico, gregas, vol realizada (Yang-Zhang/HAR), "
                    "VRP, IV Rank e risco de carteira (delta-gamma-vega)."),
        "mais_liquidos": mais_liquidos,
    }


# --- registry + schemas ----------------------------------------------------

_REGISTRY: dict[str, Callable[..., dict]] = {
    "screen_underlyings": screen_underlyings,
    "underlying_snapshot": underlying_snapshot,
    "search_options": search_options,
    "analyze_option": analyze_option,
    "vol_history": vol_history,
    "market_summary": market_summary,
    "term_structure": term_structure,
    "briefing": briefing,
    "portfolio": portfolio,
    "solution_overview": solution_overview,
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
    {
        "name": "market_summary",
        "description": "Panorama do mercado no dia (módulo Radar): quantas ações têm sinal, "
                       "quantas com vol cara (rico) vs barata (barato), liquidez total e o nível do "
                       "BOVA11. Use para 'como está o mercado hoje', 'resumo do dia', 'panorama'.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "term_structure",
        "description": "Estrutura a termo da volatilidade de um subjacente: a IV ATM por vencimento, "
                       "a inclinação (vol sobe ou cai com o prazo) e o skew. É a 'superfície de "
                       "volatilidade' do módulo Opções. Use para 'a vol da PETR4 sobe com o prazo?', "
                       "'como está a estrutura a termo / superfície da VALE3?'.",
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string", "description": "subjacente, ex: PETR4"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "briefing",
        "description": "Briefing do Analista para um subjacente: monta uma operação real de risco "
                       "definido (trava de alta vendida / call spread no vencimento mais próximo) e "
                       "devolve os fatos, os dois lados (a favor/contra), risco-retorno, breakeven, "
                       "tamanho de posição para 3 perfis (conservador/moderado/agressivo), "
                       "invalidação e um veredito honesto. Use para 'monte uma operação / um briefing "
                       "/ uma estratégia para a PETR4', 'que trava dá pra fazer na VALE3?'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "underlying": {"type": "string", "description": "subjacente, ex: PETR4"},
                "capital": {"type": "number", "description": "capital para o sizing (padrão 50000)"},
            },
            "required": ["underlying"],
        },
    },
    {
        "name": "portfolio",
        "description": "A carteira do usuário (módulo Carteira): posições, valor total, gregas "
                       "líquidas (delta/gamma/vega/theta), custo de theta por dia, sensibilidade a "
                       "+5 pontos de vol, o stress de mercado (P&L de -10% a +10% no spot) e a faixa "
                       "de payoff no vencimento. Use para 'como está minha carteira', 'qual meu "
                       "risco', 'meu delta/theta', 'e se o mercado cair 10%'.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "solution_overview",
        "description": "O que é o ATLAS e o que existe na base agora: módulos (Radar/Screener, "
                       "Opções, Carteira, Analista, Chat), dados (fonte, nº de ações/índices/opções, "
                       "quantos pregões de histórico e o período), cobertura, modelos usados e os "
                       "ativos mais líquidos. USE quando perguntarem sobre A PRÓPRIA SOLUÇÃO: o que "
                       "você faz, o que é o ATLAS, quais dados/ativos/opções existem, o que há de "
                       "'melhor/maior/mais líquido' na nossa base/solução, qual a cobertura, ou como "
                       "funciona. Não precisa de parâmetros.",
        "input_schema": {"type": "object", "properties": {}},
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
