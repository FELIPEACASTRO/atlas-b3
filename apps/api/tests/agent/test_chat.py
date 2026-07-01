"""Agent loops + orchestrator, fully offline (no network, no keys).

OpenRouter/Gemini paths are exercised by monkeypatching ``llm._post`` so the
real tool dispatch runs against the seeded store and we can assert the model is
fed REAL numbers (not invented). Anthropic path uses an injected stub client.
"""
from atlas_api.agent import chat as chat_agent
from atlas_api.agent import llm


# --- Anthropic (injected stub) ---------------------------------------------

class _Block:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Resp:
    def __init__(self, stop_reason, content):
        self.stop_reason = stop_reason
        self.content = content


class StubClient:
    def __init__(self):
        self.seen = []
        self.messages = self

    def create(self, **kw):
        self.seen.append(kw["messages"])
        if len(self.seen) == 1:
            return _Resp("tool_use", [
                _Block(type="tool_use", id="t1", name="analyze_option", input={"ticker": "PETRA38"})])
        return _Resp("end_turn", [_Block(type="text", text="A PETRA38 tem breakeven em R$ 39,10.")])


def test_anthropic_loop_grounds_answer(conn):
    text, calls = llm._run_anthropic("vale a pena a PETRA38?", [], conn=conn, client=StubClient())
    assert text == "A PETRA38 tem breakeven em R$ 39,10."
    assert calls == [{"name": "analyze_option", "args": {"ticker": "PETRA38"}}]


# --- OpenRouter / Gemini (monkeypatched HTTP) ------------------------------

def _fake_post_factory(provider):
    """Returns a fake _post that simulates a tool call then a final answer,
    capturing the second-round payload so we can assert grounding."""
    state = {"n": 0, "payloads": []}

    def fake_post(url, payload, headers, timeout=120):
        state["n"] += 1
        state["payloads"].append(payload)
        if provider == "openrouter":
            if state["n"] == 1:
                return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
                    {"id": "c1", "type": "function",
                     "function": {"name": "analyze_option", "arguments": '{"ticker": "PETRA38"}'}}]}}]}
            return {"choices": [{"message": {"content": "A PETRA38 tem breakeven em R$ 39,10."}}]}
        # gemini
        if state["n"] == 1:
            return {"candidates": [{"content": {"parts": [
                {"functionCall": {"name": "analyze_option", "args": {"ticker": "PETRA38"}}}]}}]}
        return {"candidates": [{"content": {"parts": [{"text": "A PETRA38 tem breakeven em R$ 39,10."}]}}]}

    return fake_post, state


def test_openrouter_loop_is_grounded(conn, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    fake, state = _fake_post_factory("openrouter")
    monkeypatch.setattr(llm, "_post", fake)
    text, calls, prov = llm.run("vale a pena a PETRA38?", [], conn=conn)
    assert prov == "openrouter" and "39" in text
    assert calls == [{"name": "analyze_option", "args": {"ticker": "PETRA38"}}]
    tool_msg = state["payloads"][1]["messages"][-1]  # the tool result fed back
    assert tool_msg["role"] == "tool" and '"breakeven": 39.1' in tool_msg["content"]


def test_openrouter_fails_over_to_next_model(conn, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("ATLAS_OPENROUTER_MODELS", "model-a:free,model-b:free")
    calls_seen = {"models": []}

    def fake_post(url, payload, headers, timeout=120):
        calls_seen["models"].append(payload["model"])
        if payload["model"] == "model-a:free":
            raise llm._ProviderError(429, "rate-limited upstream")
        return {"choices": [{"message": {"content": "ok do modelo B"}}]}

    monkeypatch.setattr(llm, "_post", fake_post)
    text, _calls, prov = llm.run("oi", [], conn=conn)
    assert text == "ok do modelo B" and prov == "openrouter"
    assert calls_seen["models"] == ["model-a:free", "model-b:free"]  # failed over


def test_gemini_loop_is_grounded(conn, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-test")
    fake, state = _fake_post_factory("gemini")
    monkeypatch.setattr(llm, "_post", fake)
    text, calls, prov = llm.run("vale a pena a PETRA38?", [], conn=conn)
    assert prov == "gemini" and "39" in text
    assert calls == [{"name": "analyze_option", "args": {"ticker": "PETRA38"}}]
    fresp = state["payloads"][1]["contents"][-1]["parts"][0]["functionResponse"]  # fed back
    assert fresp["response"]["result"]["breakeven"] == 39.10  # real value, not invented


def test_auto_chain_is_free_only(monkeypatch):
    # even with a paid Anthropic key present, 'auto' must not select it
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assert llm.provider_chain() == ["openrouter"]


def test_all_free_busy_degrades_to_limited(conn, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")

    def always_429(url, payload, headers, timeout=120):
        raise llm._ProviderError(429, "rate-limited upstream")

    monkeypatch.setattr(llm, "_post", always_429)
    res = chat_agent.answer("como está a PETR4?", [], conn=conn)
    assert res.mode == "limitado" and "PETR4" in res.answer  # grounded, not broken


def test_orchestrator_limited_without_any_provider(conn):
    assert llm.available() is False  # autouse fixture cleared all keys
    res = chat_agent.answer("como está a PETR4?", [], conn=conn)
    assert res.mode == "limitado" and res.tool_calls


# --- streaming (Anthropic stub via internal fn) ----------------------------

class _StreamCtx:
    def __init__(self, texts, final):
        self._texts, self._final = texts, final

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    @property
    def text_stream(self):
        return iter(self._texts)

    def get_final_message(self):
        return self._final


class StubStreamClient:
    def __init__(self):
        self.n = 0
        self.messages = self

    def stream(self, **kw):
        self.n += 1
        if self.n == 1:
            return _StreamCtx([], _Resp("tool_use", [
                _Block(type="tool_use", id="t1", name="vol_history", input={"ticker": "PETR4"})]))
        return _StreamCtx(["A IV da PETR4 ", "está no topo da janela."],
                          _Resp("end_turn", [_Block(type="text", text="A IV da PETR4 está no topo da janela.")]))


def test_stream_anthropic_emits_tool_then_deltas(conn):
    events = list(llm._stream_anthropic("a vol da PETR4 está alta?", [], conn=conn, client=StubStreamClient()))
    kinds = [e["type"] for e in events]
    assert "tool" in kinds and kinds[-1] == "done"
    assert next(e for e in events if e["type"] == "tool")["name"] == "vol_history"
    assert "".join(e["text"] for e in events if e["type"] == "delta") == "A IV da PETR4 está no topo da janela."


def test_stream_openrouter_emits_single_delta_with_tool(conn, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    fake, _state = _fake_post_factory("openrouter")
    monkeypatch.setattr(llm, "_post", fake)
    events = list(chat_agent.answer_stream("vale a pena a PETRA38?", [], conn=conn))
    assert any(e["type"] == "tool" and e["name"] == "analyze_option" for e in events)
    done = events[-1]
    assert done["type"] == "done" and done["mode"] == "ia"
    assert "39" in "".join(e["text"] for e in events if e["type"] == "delta")
