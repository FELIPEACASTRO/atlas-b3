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
