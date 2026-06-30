import json

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


def test_chat_stream_emits_sse_done_with_provenance(seeded_db, monkeypatch):
    monkeypatch.setenv("ATLAS_DB", seeded_db)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with client.stream("POST", "/chat/stream", json={"question": "vale a pena a PETRA38?"}) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        body = "".join(r.iter_text())
    events = [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]
    assert events[-1]["type"] == "done" and events[-1]["mode"] == "limitado"
    assert events[-1]["asof"] == "2024-01-15" and "COTAHIST EOD" in events[-1]["provenance"]
    delta = "".join(e["text"] for e in events if e["type"] == "delta")
    assert "39.10" in delta  # streamed answer carries the real breakeven
