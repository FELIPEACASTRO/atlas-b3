"""Composição ponta-a-ponta de build_decision no dado REAL — os invariantes-mestre do diferencial.

O produto (`build_decision`) só tinha testes das funções-folha isoladas; aqui exercitamos a
orquestração inteira sobre o atlas.db e travamos: teto de CVaR nunca estourado, abstenção zera
tudo, cartão bem-formado, gatilho de retorno coerente. Skip honesto se ATLAS_DB não está setado.
"""
import os

import pytest

from atlas_api.data import store
from atlas_api.predict.engine import build_decision
from atlas_api.predict.strategies import CVAR_BUDGET

_DB = os.environ.get("ATLAS_DB")
_VERDICTS = {"OPERAR", "OPERAR PEQUENO", "OBSERVAR", "EVITAR"}


@pytest.mark.skipif(not _DB, reason="ATLAS_DB não definido — teste de integração pula honestamente")
@pytest.mark.parametrize(
    ("ticker", "visao", "perfil"),
    [("PETR4", "alta", "moderado"), ("VALE3", "neutro", "agressivo"), ("PETR4", "baixa", "conservador")],
)
def test_build_decision_end_to_end_invariants(ticker, visao, perfil):
    conn = store.connect(_DB)
    inst = store.get_instrument(conn, ticker)
    spot = inst.get("ultimo") if inst else None
    ohlc = store.price_history(conn, ticker, limit=400)
    iv = store.iv_history(conn, ticker, limit=400)
    chain = store.query_chain(conn, ticker, limit=5000)
    asof = store.get_meta(conn, "asof")
    conn.close()
    closes = [b[3] for b in ohlc]
    capital = 20000.0
    d = build_decision(ticker=ticker, ohlc=ohlc, closes=closes, iv_history=iv, spot=spot,
                       chain=chain, asof=asof, visao=visao, capital=capital, prazo=30,
                       perfil=perfil, backtest_dsr=0.9)
    if not d.get("available"):
        return                                              # sem dado → sem cartão (honesto)
    conf = d["confidence"]
    assert 0.0 <= conf["score"] <= 100.0
    assert all(0.0 <= v <= 1.0 for v in conf["factors"].values())
    abstained = d["abstain"]["is_abstained"]
    for c in d["cards"]:
        assert c["verdict"] in _VERDICTS
        assert isinstance(c["sizing"]["lots"], int) and c["sizing"]["lots"] >= 0
        assert 0.0 <= c["decision_score"] <= 100.0
        # I1 PONTA-A-PONTA (o invariante do dinheiro): risco de cauda ≤ budget do perfil (folga de 1 lote)
        car = c["sizing"].get("cvar_at_risk", 0.0)
        assert car <= CVAR_BUDGET[perfil] * capital + abs(c["economics"]["cvar_lot"])
        # I7: abstenção → todo cartão zerado e EVITAR
        if abstained:
            assert c["sizing"]["lots"] == 0 and c["verdict"] == "EVITAR"
        # gatilho de retorno: None em OPERAR, presente no resto (a honestidade vira próximo-passo)
        assert (c.get("reactivate") is None) == (c["verdict"] == "OPERAR")
