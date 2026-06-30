import os

from fastapi.testclient import TestClient

from atlas_api.api.main import app
from atlas_api.data.ingest import ingest_cotahist

client = TestClient(app)

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "data", "fixtures", "cotahist_sample.txt")


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_briefing_sample_three_profiles_and_provenance():
    r = client.get("/briefing/sample")
    assert r.status_code == 200
    d = r.json()
    assert set(d["sizing"]) == {"conservador", "moderado", "agressivo"}
    assert len(d["case_against"]) >= 1  # honesty: never one-sided
    assert d["provenance"] and d["asof"]


def test_screener_fixture_fallback_has_provenance(monkeypatch):
    monkeypatch.delenv("ATLAS_DB", raising=False)
    r = client.get("/screener")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) >= 1
    assert all(row["provenance"] and row["asof"] for row in rows)


def test_chain_fixture_fallback_has_iv_and_greeks(monkeypatch):
    monkeypatch.delenv("ATLAS_DB", raising=False)
    r = client.get("/chain/PETR4")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) >= 1
    assert all(row["iv"] is not None and row["delta"] is not None for row in rows)


def test_screener_from_real_store(tmp_path, monkeypatch):
    db = str(tmp_path / "atlas.db")
    ingest_cotahist(FIXTURE, db, rate=0.1165)
    monkeypatch.setenv("ATLAS_DB", db)
    r = client.get("/screener")
    assert r.status_code == 200
    rows = r.json()
    assert any(row["ticker"] == "PETR4" for row in rows)
    assert all("COTAHIST EOD" in row["provenance"] for row in rows)


def test_screener_handles_null_ultimo(tmp_path, monkeypatch):
    from atlas_api.data import store

    db = str(tmp_path / "n.db")
    conn = store.connect(db)
    store.insert_instruments(conn, [("XXXX3", "acao", None, None, None, None, None, None, "2024-01-02")])
    conn.commit()
    conn.close()
    monkeypatch.setenv("ATLAS_DB", db)
    r = client.get("/screener")
    assert r.status_code == 200  # a null ultimo must not 500 the whole endpoint
    assert r.json()[0]["ultimo"] is None


def test_corrupt_db_falls_back_to_fixture(tmp_path, monkeypatch):
    bad = tmp_path / "bad.db"
    bad.write_text("not a sqlite file")
    monkeypatch.setenv("ATLAS_DB", str(bad))
    r = client.get("/screener")
    assert r.status_code == 200
    assert any(row["provenance"].startswith("fixture") for row in r.json())


def _seed_real_store(db: str) -> None:
    from atlas_api.data import store

    conn = store.connect(db)
    store.upsert_prices(conn, [
        ("PETR4", "2024-01-02", 37.4, 37.9, 37.4, 37.8),
        ("PETR4", "2024-01-03", 37.8, 38.2, 37.6, 38.0),
        ("PETR4", "2024-01-04", 38.0, 38.5, 37.9, 38.3),
    ])
    store.insert_instruments(conn, [
        ("PETR4", "acao", 38.3, 1.2, 1e9, 0.30, "rico", None, "2024-01-04"),
        ("PETRA38", "call", 1.10, None, 1e6, 0.30, None, None, "2024-01-04"),
        ("PETRA40", "call", 0.40, None, 1e6, 0.32, None, None, "2024-01-04"),
    ])
    store.insert_options(conn, [
        ("PETR4", "PETRA38", "call", 38.0, "2024-01-19", 1.10, 0.30, 0.55, 0.04, 1.5, -0.03, "2024-01-04"),
        ("PETR4", "PETRA40", "call", 40.0, "2024-01-19", 0.40, 0.32, 0.30, 0.03, 1.2, -0.02, "2024-01-04"),
    ])
    store.set_meta(conn, "asof", "2024-01-04")
    conn.commit()
    conn.close()


def test_summary_from_real_store(tmp_path, monkeypatch):
    db = str(tmp_path / "s.db")
    _seed_real_store(db)
    monkeypatch.setenv("ATLAS_DB", db)
    s = client.get("/summary").json()
    assert s["com_sinal"] >= 1
    assert "COTAHIST EOD" in s["provenance"]  # real, not fixture


def test_briefing_by_ticker_is_real(tmp_path, monkeypatch):
    db = str(tmp_path / "b.db")
    _seed_real_store(db)
    monkeypatch.setenv("ATLAS_DB", db)
    r = client.get("/briefing/PETR4")
    assert r.status_code == 200
    d = r.json()
    assert d["ticker"].startswith("PETR")
    assert set(d["sizing"]) == {"conservador", "moderado", "agressivo"}
    assert "COTAHIST EOD" in d["provenance"]  # built from real data, not the fixture sample


def test_positions_crud_and_portfolio_risk(tmp_path, monkeypatch):
    db = str(tmp_path / "pf.db")
    _seed_real_store(db)
    monkeypatch.setenv("ATLAS_DB", db)
    client.post("/positions", json={"ticker": "PETR4", "qty": 100})
    rows = client.post("/positions", json={"ticker": "PETRA38", "qty": -5}).json()
    assert {r["ticker"] for r in rows} == {"PETR4", "PETRA38"}
    stock = next(r for r in rows if r["ticker"] == "PETR4")
    assert stock["value"] == 3830.0  # qty * last * 1 (stock), rounded
    assert stock["delta"] == 100.0  # stock delta = qty
    pf = client.get("/portfolio").json()
    assert pf["n_positions"] == 2
    # net delta = stock(100) + short 5 calls(-5*0.55*100=-275)
    assert pf["net_delta"] == round(100 + (-5 * 0.55 * 100), 2)
    # short 5 calls earns decay: net theta = -5 * (-0.03) * 100 = +15
    assert pf["net_theta"] == round(-5 * -0.03 * 100, 2)
    client.delete("/positions/PETR4")
    assert client.get("/portfolio").json()["n_positions"] == 1


def test_history_iv_vs_rv_series(tmp_path, monkeypatch):
    import datetime as dt

    from atlas_api.data import store

    db = str(tmp_path / "hist.db")
    conn = store.connect(db)
    base = dt.date(2026, 1, 1)
    prices, ivs = [], []
    for i in range(30):  # 30 sessions -> rolling RV and IV Rank both available
        d = (base + dt.timedelta(days=i)).isoformat()
        prices.append(("PETR4", d, 38.0, 38.6, 37.4, 38.0 + 0.15 * (i % 5 - 2)))
        ivs.append(("PETR4", d, 0.28 + 0.002 * i))
    store.upsert_prices(conn, prices)
    store.upsert_iv_daily(conn, ivs)
    store.insert_instruments(conn, [("PETR4", "acao", 38.0, None, 1e9, 0.30, None, 56.6, "2026-01-30")])
    store.set_meta(conn, "asof", "2026-01-30")
    conn.commit()
    conn.close()
    monkeypatch.setenv("ATLAS_DB", db)
    d = client.get("/history/PETR4").json()
    assert len(d["points"]) == 30
    assert any(p["iv"] is not None for p in d["points"])
    assert any(p["rv"] is not None for p in d["points"])  # trailing RV after >=10 closes
    assert d["iv_rank"] is not None  # 30 >= MIN_IV_HISTORY


def test_option_panel_endpoint(tmp_path, monkeypatch):
    db = str(tmp_path / "op.db")
    _seed_real_store(db)  # PETR4 spot 38.3 + PETRA38 call (strike 38, last 1.10, greeks)
    monkeypatch.setenv("ATLAS_DB", db)
    d = client.get("/option/PETRA38").json()
    assert d["ticker"] == "PETRA38" and d["underlying"] == "PETR4"
    assert d["breakeven"] == 39.10 and d["max_perda_titular"] == 110.0
    assert d["pros"] and d["contras"]            # always two-sided
    assert d["comprar"] and d["vender_sair"]
    assert "decisão é sua" in d["veredito"].lower()
    assert client.get("/option/NAOEXISTE99").status_code == 404


def test_surface_term_structure_and_grid(tmp_path, monkeypatch):
    db = str(tmp_path / "surf.db")
    _seed_real_store(db)  # PETR4 spot 38.3 + PETRA38/PETRA40 calls (2 strikes, same venc)
    monkeypatch.setenv("ATLAS_DB", db)
    d = client.get("/surface/PETR4").json()
    assert d["spot"] == 38.3
    assert len(d["expiries"]) >= 1  # one maturity (2024-01-19)
    e = d["expiries"][0]
    assert e["dte"] > 0 and 0 < e["atm_iv"] < 3
    assert len(d["points"]) == 2  # two strikes with IV
    assert all(p["moneyness"] > 0 for p in d["points"])


def test_portfolio_stress_delta_gamma(tmp_path, monkeypatch):
    db = str(tmp_path / "st.db")
    _seed_real_store(db)
    monkeypatch.setenv("ATLAS_DB", db)
    client.post("/positions", json={"ticker": "PETR4", "qty": 100})  # 100 shares @ 38.3
    s = client.get("/portfolio/stress").json()
    assert len(s["scenarios"]) == 7
    z = next(p for p in s["scenarios"] if p["shock_pct"] == 0.0)
    assert z["pnl"] == 0.0
    up = next(p for p in s["scenarios"] if p["shock_pct"] == 10.0)
    assert up["pnl"] == round(100 * 0.10 * 38.3, 2)  # stock P&L = qty * dS = +383
    dn = next(p for p in s["scenarios"] if p["shock_pct"] == -10.0)
    assert dn["pnl"] == round(100 * -0.10 * 38.3, 2)  # -383
    client.delete("/positions/PETR4")
