from fastapi.testclient import TestClient

from atlas_api.api.main import app

client = TestClient(app)


def test_chat_endpoint_limited_mode_is_grounded(seeded_db, monkeypatch):
    monkeypatch.setenv("ATLAS_DB", seeded_db)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)  # force the deterministic path
    r = client.post("/chat", json={"question": "vale a pena a PETRA38?"})
    assert r.status_code == 200
    d = r.json()
    assert d["mode"] == "limitado"
    assert "39.10" in d["answer"]                      # real breakeven from the store
    assert "COTAHIST EOD" in d["provenance"] and d["asof"] == "2024-01-15"
    assert any(c["name"] == "analyze_option" for c in d["tool_calls"])


def test_chat_endpoint_requires_store(monkeypatch):
    monkeypatch.delenv("ATLAS_DB", raising=False)
    r = client.post("/chat", json={"question": "olá"})
    assert r.status_code == 503  # no real data -> refuse rather than fabricate
