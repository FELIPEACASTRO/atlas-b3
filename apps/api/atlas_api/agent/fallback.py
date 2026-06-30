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
