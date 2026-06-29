from fastapi.testclient import TestClient

from atlas_api.api.main import app

client = TestClient(app)


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


def test_screener_rows_have_provenance_and_asof():
    r = client.get("/screener")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) >= 1
    assert all(row["provenance"] and row["asof"] for row in rows)


def test_chain_has_iv_and_greeks():
    r = client.get("/chain/PETR4")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) >= 1
    assert all(row["iv"] is not None and row["delta"] is not None for row in rows)
