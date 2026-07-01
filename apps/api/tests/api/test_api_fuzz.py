"""Fuzz da borda da API: input degenerado deve dar 422 (validação), nunca 500 (crash)."""
from fastapi.testclient import TestClient

from atlas_api.api.main import app

client = TestClient(app)


def test_numeric_params_reject_degenerate_with_422():
    # a validação de Query (gt=0, le=...) dispara ANTES do handler → 422 mesmo sem store
    for url in (
        "/predict/PETR4?horizon=0", "/predict/PETR4?horizon=-5", "/predict/PETR4?horizon=99999",
        "/kernel/PETR4?horizon=0", "/edge/PETR4?horizon=-1", "/fair-iv/PETR4?horizon=0",
        "/strategies/PETR4?capital=0", "/strategies/PETR4?prazo=-1", "/strategies/PETR4?prazo=0",
        "/decision/PETR4?prazo=0", "/decision/PETR4?capital=-100",
        "/briefing/PETR4?capital=0",
    ):
        r = client.get(url)
        assert r.status_code == 422, f"{url} -> {r.status_code} (esperado 422, nunca 500)"


def test_empty_ticker_position_not_500():
    r = client.post("/positions", json={"ticker": "   ", "qty": 1.0})
    assert r.status_code in (422, 503)          # 422 (ticker vazio) ou 503 (sem ATLAS_DB) — nunca 500/persistir


def test_odd_ticker_never_500():
    # ticker estranho/injeção: o store é parametrizado → 404/503/200 honesto, nunca 500 nem SQL executado
    for tk in ("''; DROP TABLE instruments;--", "%2e%2e", "___naoexiste___"):
        r = client.get(f"/predict/{tk}")
        assert r.status_code != 500, f"{tk} -> 500"
