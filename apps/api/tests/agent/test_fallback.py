from atlas_api.agent import fallback


def test_option_ticker_routes_to_decision_panel(conn):
    text, calls, _ = fallback.answer("vale a pena comprar a PETRA38?", conn)
    assert "PETRA38" in text and "39.10" in text          # real breakeven, not invented
    assert calls and calls[0]["name"] == "analyze_option"


def test_underlying_ticker_routes_to_snapshot(conn):
    text, calls, _ = fallback.answer("como está a PETR4 hoje?", conn)
    assert "PETR4" in text and "IV Rank" in text
    assert {c["name"] for c in calls} == {"underlying_snapshot", "search_options"}


def test_vol_cara_routes_to_ranking(conn):
    text, calls, _ = fallback.answer("quais ativos estão com a vol mais cara?", conn)
    assert "PETR4" in text
    assert calls[0]["name"] == "screen_underlyings"


def test_solution_question_routes_to_overview(conn):
    # the exact phrasing from the bug report ("os melhores disponíveis em nossa solução")
    text, calls, _ = fallback.answer("quero saber os melhores disponiveis em nossa solucao", conn)
    assert calls and calls[0]["name"] == "solution_overview"
    assert "Módulos" in text and "Chat" in text and "COTAHIST" in text


def test_unparseable_question_returns_help_with_key_hint(conn):
    text, calls, note = fallback.answer("oi, tudo certo por aí?", conn)
    assert "gratuita" in text and ("OpenRouter" in text or "Gemini" in text)
    assert calls == [] and note  # no tools fired, but it's honest about the limit
