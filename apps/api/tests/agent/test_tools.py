from atlas_api.agent import tools
from atlas_api.data import store


def test_screen_underlyings_excludes_options_and_carries_signal(conn):
    res = tools.screen_underlyings(conn)
    tickers = {u["ticker"] for u in res["underlyings"]}
    assert "PETR4" in tickers
    assert "PETRA38" not in tickers and "PETRA40" not in tickers  # options are not underlyings
    petr = next(u for u in res["underlyings"] if u["ticker"] == "PETR4")
    assert petr["iv_rank"] == 56.6 and petr["sinal_iv_vs_rv"] == "rico"
    assert petr["vrp"] == 0.07  # joined from underlying_features
    assert res["asof"] == "2024-01-15"


def test_underlying_snapshot_real_numbers(conn):
    s = tools.underlying_snapshot(conn, ticker="petr4")
    assert s["ultimo"] == 38.3 and s["tipo"] == "acao"
    assert s["iv_rank"] == 56.6 and s["n_opcoes"] == 2
    assert s["rv_realizada"] is not None  # 15 closes -> trailing RV available
    assert tools.underlying_snapshot(conn, ticker="ZZZZ9")["error"]


def test_search_options_cheapest_first_with_dte_and_moneyness(conn):
    res = tools.search_options(conn, underlying="PETR4", kind="call", order="cheapest")
    assert res["spot"] == 38.3 and res["total_encontradas"] == 2
    first = res["opcoes"][0]
    assert first["ticker"] == "PETRA40" and first["ultimo"] == 0.40  # cheaper than PETRA38
    assert first["dte"] == 32 and first["moneyness"] in ("ITM", "ATM", "OTM")


def test_analyze_option_two_sided_and_breakeven(conn):
    a = tools.analyze_option(conn, ticker="PETRA38")
    assert a["breakeven"] == 39.10 and a["perda_max_titular"] == 110.0
    assert a["pros"] and a["contras"]            # never one-sided
    assert "decisão é sua" in a["veredito"].lower()
    assert tools.analyze_option(conn, ticker="NADA99")["error"]


def test_vol_history_window(conn):
    v = tools.vol_history(conn, ticker="PETR4")
    assert v["n_sessoes"] == 15
    assert v["iv_atual"] >= v["iv_min"] and v["iv_atual"] <= v["iv_max"]
    assert v["iv_rank_janela"] is not None      # latest IV is the max -> ~100


def test_market_summary_counts_signals(conn):
    m = tools.market_summary(conn)
    assert m["n_acoes"] >= 1 and m["com_sinal_iv_vs_rv"] >= 1
    assert m["vol_cara_rico"] >= 1  # PETR4 seeded as 'rico'


def test_term_structure_atm_iv_by_expiry(conn):
    t = tools.term_structure(conn, ticker="petr4")
    assert t["spot"] == 38.3 and t["estrutura_a_termo"]
    assert t["estrutura_a_termo"][0]["atm_iv"] is not None
    assert tools.term_structure(conn, ticker="ZZZZ9")["error"]


def test_briefing_is_two_sided(conn):
    b = tools.briefing(conn, underlying="PETR4")
    assert b["underlying"] == "PETR4" and b["a_favor"] and b["contra"]
    assert set(b["tamanho_por_perfil"]) == {"conservador", "moderado", "agressivo"}
    assert "decisão é sua" in b["veredito"].lower()
    assert b["risco_retorno"]["breakeven"] > 0


def test_portfolio_empty_then_populated(conn):
    assert tools.portfolio(conn)["n_posicoes"] == 0  # carteira vazia -> mensagem
    store.set_position(conn, "PETR4", 100)
    conn.commit()
    p = tools.portfolio(conn)
    assert p["n_posicoes"] == 1 and p["valor_total"] == 3830.0     # 100 x 38.30
    assert p["gregas_liquidas"]["delta"] == 100.0                   # stock delta = qty
    z = next(s for s in p["stress_mercado"] if s["var_pct"] == 0.0)
    assert z["pnl"] == 0.0
    up = next(s for s in p["stress_mercado"] if s["var_pct"] == 10.0)
    assert up["pnl"] == round(100 * 0.10 * 38.3, 2)                 # +383


def test_solution_overview_describes_the_base(conn):
    s = tools.solution_overview(conn)
    assert s["dados"]["acoes"] >= 1 and s["dados"]["opcoes"] == 2  # PETR4 + 2 calls
    assert s["dados"]["sessoes_historico"] == 15                    # 15 seeded sessions
    assert any(m["nome"] == "Chat" for m in s["modulos"])           # describes its own modules
    assert s["mais_liquidos"][0]["ticker"] == "PETR4"              # most liquid first
    assert "Bjerksund" in s["cobertura"] and "IBOV" in s["cobertura"]


def test_dispatch_unknown_and_bad_args_never_raise(conn):
    assert "error" in tools.dispatch(conn, "nope", {})
    assert "error" in tools.dispatch(conn, "underlying_snapshot", {"bogus": 1})
