"""Agent loop + orchestrator, exercised offline (no network, no API key).

A stub client stands in for ``anthropic.Anthropic()`` so we can prove the
tool-use loop: it asks for a tool, our dispatcher runs it against the real
seeded store, the real result is fed back, and the model produces a final answer.
"""
from atlas_api.agent import chat as chat_agent
from atlas_api.agent import llm


class _Block:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Resp:
    def __init__(self, stop_reason, content):
        self.stop_reason = stop_reason
        self.content = content


class StubClient:
    """First create() asks for analyze_option; second returns the final text."""

    def __init__(self):
        self.seen = []
        self.messages = self  # client.messages.create(...) -> create(...)

    def create(self, **kw):
        self.seen.append(kw["messages"])
        if len(self.seen) == 1:
            return _Resp("tool_use", [
                _Block(type="tool_use", id="t1", name="analyze_option", input={"ticker": "PETRA38"}),
            ])
        return _Resp("end_turn", [_Block(type="text", text="A PETRA38 tem breakeven em R$ 39,10.")])


def test_loop_runs_tool_and_grounds_answer(conn):
    stub = StubClient()
    text, calls = llm.run("vale a pena a PETRA38?", [], conn=conn, client=stub)
    assert text == "A PETRA38 tem breakeven em R$ 39,10."
    assert calls == [{"name": "analyze_option", "args": {"ticker": "PETRA38"}}]
    # the second request must carry a tool_result with REAL data from the store
    second = stub.seen[1]
    tool_result = second[-1]["content"][0]
    assert tool_result["type"] == "tool_result"
    assert '"breakeven": 39.1' in tool_result["content"]  # grounded, not invented


def test_loop_handles_refusal(conn):
    class Refuse(StubClient):
        def create(self, **kw):
            return _Resp("refusal", [])

    text, calls = llm.run("...", [], conn=conn, client=Refuse())
    assert "não consigo" in text.lower() and calls == []


def test_orchestrator_falls_back_without_key(conn, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert llm.available() is False
    res = chat_agent.answer("como está a PETR4?", [], conn=conn)
    assert res.mode == "limitado"
    assert "PETR4" in res.answer and res.tool_calls


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
    """First stream asks for a tool; second streams the final answer in chunks."""

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


def test_run_stream_emits_tool_then_deltas(conn):
    events = list(llm.run_stream("a vol da PETR4 está alta?", [], conn=conn, client=StubStreamClient()))
    kinds = [e["type"] for e in events]
    assert "tool" in kinds and kinds[-1] == "done"
    tool_ev = next(e for e in events if e["type"] == "tool")
    assert tool_ev["name"] == "vol_history" and tool_ev["args"] == {"ticker": "PETR4"}
    text = "".join(e["text"] for e in events if e["type"] == "delta")
    assert text == "A IV da PETR4 está no topo da janela."
    assert events[-1]["tool_calls"] == [{"name": "vol_history", "args": {"ticker": "PETR4"}}]
