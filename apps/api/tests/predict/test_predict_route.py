"""Rota GET /predict/{ticker}: 503 honesto sem store; 200 calibrado sobre dado real."""
from datetime import date, timedelta

import numpy as np
from fastapi.testclient import TestClient

from atlas_api.api.main import app
from atlas_api.data import store

client = TestClient(app)


def _seed_predict_store(db: str, n: int = 60) -> None:
    rng = np.random.default_rng(0)
    conn = store.connect(db)
    prices, ivs = [], []
    c = 30.0
    d0 = date(2026, 4, 1)
    for i in range(n):
        c2 = c * float(np.exp(rng.normal(0, 0.02)))
        o = c * float(np.exp(rng.normal(0, 0.005)))
        hi = max(o, c2) * float(np.exp(abs(rng.normal(0, 0.01))))
        lo = min(o, c2) * float(np.exp(-abs(rng.normal(0, 0.01))))
        dt = (d0 + timedelta(days=i)).isoformat()
        prices.append(("PETR4", dt, o, hi, lo, c2))
        ivs.append(("PETR4", dt, 0.30 + float(rng.normal(0, 0.02))))
        c = c2
    asof = prices[-1][1]
    store.upsert_prices(conn, prices)
    store.upsert_iv_daily(conn, ivs)
    store.insert_instruments(conn, [("PETR4", "acao", round(c, 2), 1.2, 1e9, 0.31, "rico", 64.0, asof)])
    store.insert_options(conn, [
        ("PETR4", "PETRG310", "call", 31.0, "2026-07-17", 1.0, 0.30, 0.5, 0.04, 1.5, -0.03, asof),
        ("PETR4", "PETRS290", "put", 29.0, "2026-07-17", 0.8, 0.33, -0.25, 0.03, 1.2, -0.02, asof),
        ("PETR4", "PETRH310", "call", 31.0, "2026-08-21", 1.3, 0.315, 0.5, 0.03, 1.1, -0.02, asof),
    ])
    store.set_meta(conn, "asof", asof)
    conn.commit()
    conn.close()


def test_predict_without_store_returns_503(monkeypatch):
    monkeypatch.delenv("ATLAS_DB", raising=False)
    assert client.get("/predict/PETR4").status_code == 503   # sem dado → erro honesto, nunca fabrica


def test_predict_from_real_store(tmp_path, monkeypatch):
    db = str(tmp_path / "p.db")
    _seed_predict_store(db, n=60)
    monkeypatch.setenv("ATLAS_DB", db)
    r = client.get("/predict/PETR4")
    assert r.status_code == 200
    d = r.json()
    assert d["sigma"] is not None and d["sigma"] > 0
    assert set(d["dist"]["quantiles"]) == {"p10", "p25", "p50", "p75", "p90"}
    assert "COTAHIST EOD" in d["provenance"]
    assert d["calibration"]["available"] is True
    assert d["regime"]["regime"] != "indisponivel"           # term_slope/skew reais da cadeia


def test_predict_short_history_is_honest(tmp_path, monkeypatch):
    db = str(tmp_path / "q.db")
    _seed_predict_store(db, n=12)                             # poucas barras
    monkeypatch.setenv("ATLAS_DB", db)
    d = client.get("/predict/PETR4").json()
    assert d["sigma"] is None                                 # não prevê sem histórico
    assert d["calibration"]["available"] is False
