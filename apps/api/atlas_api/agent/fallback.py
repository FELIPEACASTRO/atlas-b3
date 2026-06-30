"""Deterministic fallback — answers common questions without any LLM key.

When ``ANTHROPIC_API_KEY`` is absent (or the LLM call fails), the chat still
works for the high-value patterns by routing the question to the same real
tools and formatting a plain-Portuguese answer. It never invents numbers; for
anything it can't parse it says so and points at how to unlock free-form Q&A.

Returns ``(text, tool_calls, note)`` so the orchestrator can wrap it uniformly.
"""
from __future__ import annotations

import re

from atlas_api.agent import tools
from atlas_api.data import store

# underlyings are 4 letters + digit (PETR4); B3 option codes are 5 letters + strike (PETRA38)
_TICKER_RE = re.compile(r"\b[A-Z]{4,6}\d{1,4}\b")
_CHEAP_WORDS = ("barat", "barao", "baratas", "baratos")
_RICH_WORDS = ("cara", "caro", "caras", "caros", "rica", "rico")
_SOLUTION_WORDS = (
    "soluç", "soluc", "atlas", "cobertura", "o que voc", "o que vc", "o que você", "o que vocês",
    "como funciona", "quais ativ", "quais aç", "quantos ativ", "quantas opç", "quantas aç",
    "disponiv", "disponív", "na base", "nossa", "do sistema", "da plataforma", "no sistema",
    "o que tem", "o que da pra", "o que dá pra", "o que sabe", "módulos", "modulos",
)
_BRIEF_WORDS = ("briefing", "trava", "monte uma", "monta uma", "operaç", "estratég", "call spread")
_TERM_WORDS = ("estrutura a termo", "superfic", "superfíc", " a termo", "sobe com o prazo",
               "term structure", "smile")
_PORTFOLIO_WORDS = ("carteira", "minha posi", "minhas posi", "meu risco", "meu portf",
                    "meu portfólio", "minha exposi", "meu delta", "meu theta", "meu vega",
                    "meu book", "stress", "payoff")
_PANORAMA_WORDS = ("panorama", "mercado hoje", "resumo do dia", "como esta o mercado",
                   "como está o mercado", "como anda o mercado", "visão geral do mercado",
                   "como esta o dia", "como está o dia")
_HELP = (
    "Posso responder com os números reais da base (COTAHIST EOD). Exemplos do que entendo agora:\n"
    "• \"como está a PETR4?\" — retrato do ativo (IV, IV Rank, VRP, vol)\n"
    "• \"calls baratas da VALE3\" — opções filtradas e ordenadas\n"
    "• \"vale a pena a PETRA38?\" — painel de decisão dos dois lados\n"
    "• \"quais ativos têm vol cara?\" — ranking por IV Rank\n\n"
    "Para perguntas livres em linguagem natural, configure uma chave de IA gratuita "
    "(OpenRouter ou Gemini) — aí o chat passa a entender qualquer pergunta, "
    "sempre ancorado nestes mesmos dados reais."
)


def _f(x, suf="", n=2):
    return "—" if x is None else f"{x:.{n}f}{suf}"


def _pct(x):
    return "—" if x is None else f"{x * 100:.0f}%"


def _snapshot_text(conn, ticker: str, calls: list[dict]) -> str:
    s = tools.underlying_snapshot(conn, ticker=ticker)
    if "error" in s:
        return s["error"]
    sinal = {"rico": "vol CARA (IV > RV)", "barato": "vol BARATA (IV < RV)",
             "neutro": "vol neutra"}.get(s.get("sinal_iv_vs_rv"), "sem sinal")
    lines = [
        f"**{ticker}** — R$ {_f(s['ultimo'])} ({_f(s['var_pct'], '%')} no dia)",
        f"IV ATM {_pct(s['iv_atm'])} · IV Rank {_f(s['iv_rank'], n=0)} · VRP {_f(s.get('vrp'), n=2)} → {sinal}",
        f"Vol realizada {_pct(s.get('rv_realizada'))} · {s['n_opcoes']} opções na base.",
    ]
    if calls:
        legs = ", ".join(f"{c['ticker']} (strike {_f(c['strike'])}, R$ {_f(c['ultimo'])})" for c in calls[:3])
        lines.append(f"Calls mais baratas: {legs}.")
    return "\n".join(lines)


def _option_text(conn, ticker: str) -> str:
    a = tools.analyze_option(conn, ticker=ticker)
    if "error" in a:
        return a["error"]
    pro = a["pros"][0] if a["pros"] else "—"
    contra = a["contras"][0] if a["contras"] else "—"
    return "\n".join([
        f"**{a['ticker']}** — {a['tipo']} de {a['underlying']}, strike {_f(a['strike'])}, {a['dte']} dias.",
        a["resumo"],
        f"Breakeven R$ {_f(a['breakeven'])} · perda máx. (titular) R$ {_f(a['perda_max_titular'])} · "
        f"θ/dia R$ {_f(a['custo_theta_dia'], n=0)}.",
        f"A favor: {pro}",
        f"Contra: {contra}",
        a["veredito"],
    ])


def _solution_text(conn) -> str:
    s = tools.solution_overview(conn)
    d = s["dados"]
    mods = "\n".join(f"• **{m['nome']}** — {m['descricao']}" for m in s["modulos"])
    liq = ", ".join(m["ticker"] for m in s["mais_liquidos"][:5])
    return "\n".join([
        s["o_que_e"],
        f"\n**Dados** ({d['fonte']}): {d['subjacentes']} subjacentes "
        f"({d['acoes']} ações + {d['indices']} índices) e {d['opcoes']} opções; "
        f"{d['sessoes_historico']} pregões de histórico ({d['periodo'][0]} a {d['periodo'][1]}).",
        f"**Cobertura**: {s['cobertura']}",
        f"**Mais líquidos hoje**: {liq}.",
        "\n**Módulos:**", mods,
        "\nPode pedir, por exemplo: \"calls baratas da PETR4\", \"vale a pena a PETRA38?\" "
        "ou \"a vol da VALE3 está cara?\".",
    ])


def _panorama_text(conn) -> str:
    m = tools.market_summary(conn)
    lines = [
        f"**Panorama do dia** ({m['asof']}): {m['n_acoes']} ações na base, "
        f"{m['com_sinal_iv_vs_rv']} com sinal de IV-vs-RV.",
        f"Vol CARA (IV > RV): {m['vol_cara_rico']} ativos · vol BARATA: {m['vol_barata_barato']} "
        f"· neutro: {m['neutro']}.",
    ]
    if m.get("bova11") is not None:
        lines.append(f"BOVA11 (ETF do Ibovespa): R$ {_f(m['bova11'])}.")
    return "\n".join(lines)


def _portfolio_text(conn) -> str:
    p = tools.portfolio(conn)
    if p.get("n_posicoes", 0) == 0:
        return p["mensagem"]
    g = p["gregas_liquidas"]
    pos = ", ".join(f"{x['ticker']} ({x['qty']:+g})" for x in p["posicoes"][:6])
    dn = next((s["pnl"] for s in p["stress_mercado"] if s["var_pct"] == -10.0), None)
    up = next((s["pnl"] for s in p["stress_mercado"] if s["var_pct"] == 10.0), None)
    return "\n".join([
        f"**Sua carteira** — {p['n_posicoes']} posições, valor R$ {_f(p['valor_total'])}.",
        f"Posições: {pos}.",
        f"Gregas líquidas: Δ {_f(g['delta'])} · Γ {_f(g['gamma'], n=4)} · vega {_f(g['vega'])} "
        f"· θ/dia R$ {_f(g['theta_dia'], n=0)}.",
        f"Stress: se o mercado cair 10% → R$ {_f(dn)}; subir 10% → R$ {_f(up)}.",
        f"Payoff no vencimento (faixa ±30%): melhor R$ {_f(p['payoff_vencimento']['melhor'])}, "
        f"pior R$ {_f(p['payoff_vencimento']['pior'])}.",
    ])


def _briefing_text(conn, ticker: str) -> str:
    b = tools.briefing(conn, underlying=ticker)
    if "error" in b:
        return b["error"]
    rr = b["risco_retorno"]
    mod = b["tamanho_por_perfil"]["moderado"]
    return "\n".join([
        f"**Briefing {b['underlying']}** — {b['estrutura']} (perna curta {b['ticker']}).",
        b["fatos"],
        f"Risco-retorno: ganho máx R$ {_f(rr['ganho_max_por_lote'])}/lote · "
        f"perda máx R$ {_f(rr['perda_max_por_lote'])}/lote · breakeven R$ {_f(rr['breakeven'])}.",
        f"A favor: {b['a_favor'][0] if b['a_favor'] else '—'}",
        f"Contra: {b['contra'][0] if b['contra'] else '—'}",
        f"Perfil moderado: {mod['lotes']} lotes (risco R$ {_f(mod['perda_max_rs'])}). "
        f"Confiança: {b['confianca']}.",
        b["veredito"],
    ])


def _term_text(conn, ticker: str) -> str:
    t = tools.term_structure(conn, ticker=ticker)
    if "error" in t:
        return t["error"]
    pts = ", ".join(f"{e['dte']}d {_pct(e['atm_iv'])}" for e in t["estrutura_a_termo"][:5])
    incl = t.get("inclinacao_termo") or 0.0
    txt = ("sobe com o prazo (estrutura ascendente)" if incl > 0
           else "cai com o prazo (descendente)" if incl < 0 else "está plana")
    return "\n".join([
        f"**Estrutura a termo de {t['ticker']}** (spot R$ {_f(t['spot'])}): "
        f"IV ATM por prazo — {pts}.",
        f"A volatilidade {txt}. Skew {_f(t.get('skew'), n=2)} · "
        f"razão put/call {_f(t.get('pc_ratio'), n=2)}.",
    ])


def _screen_text(conn, signal: str | None) -> str:
    order = "iv_rank_desc" if signal == "rico" else "iv_rank_asc" if signal == "barato" else "iv_rank_desc"
    res = tools.screen_underlyings(conn, signal=signal, order=order, limit=8)
    rows = res["underlyings"]
    if not rows:
        return "Nenhum ativo com esse sinal na base agora."
    head = {"rico": "Ativos com vol mais CARA (IV alta vs histórico):",
            "barato": "Ativos com vol mais BARATA:"}.get(signal, "Ativos por IV Rank:")
    body = "\n".join(
        f"• {r['ticker']} — IV {_pct(r['iv'])}, IV Rank {_f(r['iv_rank'], n=0)}, "
        f"VRP {_f(r.get('vrp'), n=2)}" for r in rows
    )
    return f"{head}\n{body}"


def answer(question: str, conn) -> tuple[str, list[dict], str | None]:
    q = (question or "").strip()
    ql = q.lower()
    up = q.upper()
    tool_calls: list[dict] = []
    note = ("Modo simples (sem chave de IA): respondo padrões comuns. "
            "Configure uma chave gratuita (OpenRouter/Gemini) para perguntas livres.")

    tickers = _TICKER_RE.findall(up)
    underlyings = [t for t in tickers if (store.get_instrument(conn, t) or {}).get("tipo")
                   in ("acao", "indice")]

    # briefing / operation on an underlying
    if any(w in ql for w in _BRIEF_WORDS) and underlyings:
        tool_calls.append({"name": "briefing", "args": {"underlying": underlyings[0]}})
        return _briefing_text(conn, underlyings[0]), tool_calls, note
    # term structure / surface on an underlying
    if any(w in ql for w in _TERM_WORDS) and underlyings:
        tool_calls.append({"name": "term_structure", "args": {"ticker": underlyings[0]}})
        return _term_text(conn, underlyings[0]), tool_calls, note

    # an explicit option code (it resolves in the options table) -> decision panel
    for t in tickers:
        if store.get_option(conn, t):
            tool_calls.append({"name": "analyze_option", "args": {"ticker": t}})
            return _option_text(conn, t), tool_calls, note
    # an underlying -> snapshot (+ cheapest calls)
    for t in tickers:
        inst = store.get_instrument(conn, t)
        if inst and inst["tipo"] in ("acao", "indice"):
            calls = tools.search_options(conn, underlying=t, kind="call", order="cheapest", limit=3)
            tool_calls.append({"name": "underlying_snapshot", "args": {"ticker": t}})
            if "opcoes" in calls:
                tool_calls.append({"name": "search_options",
                                   "args": {"underlying": t, "kind": "call", "order": "cheapest"}})
            return _snapshot_text(conn, t, calls.get("opcoes", [])), tool_calls, note

    # the user's portfolio (no ticker needed)
    if any(w in ql for w in _PORTFOLIO_WORDS):
        tool_calls.append({"name": "portfolio", "args": {}})
        return _portfolio_text(conn), tool_calls, note
    # market panorama
    if any(w in ql for w in _PANORAMA_WORDS):
        tool_calls.append({"name": "market_summary", "args": {}})
        return _panorama_text(conn), tool_calls, note

    # vol cara / barata ranking
    if any(w in ql for w in _CHEAP_WORDS):
        tool_calls.append({"name": "screen_underlyings", "args": {"signal": "barato"}})
        return _screen_text(conn, "barato"), tool_calls, note
    if any(w in ql for w in _RICH_WORDS):
        tool_calls.append({"name": "screen_underlyings", "args": {"signal": "rico"}})
        return _screen_text(conn, "rico"), tool_calls, note

    # questions about the solution itself (what is ATLAS, coverage, what's in the base)
    if any(w in ql for w in _SOLUTION_WORDS):
        tool_calls.append({"name": "solution_overview", "args": {}})
        return _solution_text(conn), tool_calls, note

    return _HELP, tool_calls, note
