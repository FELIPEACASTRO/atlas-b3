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
    ingest_cotahist(FIXTURE, db)
    monkeypatch.setenv("ATLAS_DB", db)
    r = client.get("/screener")
    assert r.status_code == 200
    rows = r.json()
    assert any(row["ticker"] == "PETR4" for row in rows)
    assert all("COTAHIST EOD" in row["provenance"] for row in rows)
