"""Chat orchestrator — try the free LLM providers, fall back to the rule router.

One entry point per mode: ``answer`` (single-shot) and ``answer_stream`` (SSE).
If a free provider answers we're in mode 'ia'; if none is configured OR all are
busy this turn we degrade to the deterministic responder ('limitado'). Either
way the result carries the tools it used so the UI shows provenance — analysis,
never invention.
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

from atlas_api.agent import fallback, llm

_PROV_LABEL = {
    "openrouter": "via OpenRouter · modelo gratuito",
    "gemini": "via Gemini · gratuito",
    "anthropic": "via Claude",
}
_BUSY = ("Os modelos gratuitos estavam ocupados agora — respondi no modo simples. "
         "Tente de novo em instantes.")


@dataclass
class ChatResult:
    answer: str
    mode: str                       # "ia" | "limitado"
    tool_calls: list[dict] = field(default_factory=list)
    note: str | None = None


def answer(question: str, history: list, *, conn) -> ChatResult:
    question = (question or "").strip()
    if not question:
        return ChatResult(answer="Faça uma pergunta sobre opções ou ações (ex: \"como está a PETR4?\").",
                          mode="limitado")

    if llm.available():
        try:
            text, calls, prov = llm.run(question, history, conn=conn)
            return ChatResult(answer=text, mode="ia", tool_calls=calls, note=_PROV_LABEL.get(prov))
        except llm.ChatUnavailable:
            text, calls, _ = fallback.answer(question, conn)
            return ChatResult(answer=text, mode="limitado", tool_calls=calls, note=_BUSY)
        except Exception as e:  # unexpected provider failure — degrade, stay honest
            text, calls, _ = fallback.answer(question, conn)
            return ChatResult(answer=text, mode="limitado", tool_calls=calls,
                              note=f"A IA falhou ({type(e).__name__}); respondi no modo simples.")

    text, calls, note = fallback.answer(question, conn)
    return ChatResult(answer=text, mode="limitado", tool_calls=calls, note=note)


def answer_stream(question: str, history: list, *, conn) -> Iterator[dict]:
    """Streamed version of :func:`answer` (tool/delta events then done)."""
    question = (question or "").strip()
    if not question:
        yield {"type": "delta", "text": "Faça uma pergunta sobre opções ou ações (ex: \"como está a PETR4?\")."}
        yield {"type": "done", "mode": "limitado", "tool_calls": [], "note": None}
        return

    if llm.available():
        calls: list[dict] = []
        try:
            for ev in llm.stream(question, history, conn=conn):
                if ev["type"] == "tool":
                    calls.append({"name": ev["name"], "args": ev["args"]})
                    yield ev
                elif ev["type"] == "delta":
                    yield ev
                elif ev["type"] == "done":
                    yield {"type": "done", "mode": "ia",
                           "tool_calls": ev.get("tool_calls", calls),
                           "note": _PROV_LABEL.get(ev.get("provider"))}
            return
        except llm.ChatUnavailable:
            text, fcalls, _ = fallback.answer(question, conn)
            yield {"type": "delta", "text": text}
            yield {"type": "done", "mode": "limitado", "tool_calls": fcalls, "note": _BUSY}
            return
        except Exception as e:
            text, fcalls, _ = fallback.answer(question, conn)
            yield {"type": "delta", "text": text}
            yield {"type": "done", "mode": "limitado", "tool_calls": fcalls,
                   "note": f"A IA falhou ({type(e).__name__}); respondi no modo simples."}
            return

    text, fcalls, note = fallback.answer(question, conn)
    yield {"type": "delta", "text": text}
    yield {"type": "done", "mode": "limitado", "tool_calls": fcalls, "note": note}
