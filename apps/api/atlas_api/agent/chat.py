"""Chat orchestrator — try the grounded LLM, fall back to the rule router.

One entry point: ``answer(question, history, conn)``. If a provider is
configured it runs the tool-use loop; if not (or if the call errors) it degrades
to the deterministic responder. Either way the result carries the tools it used
so the UI can show provenance — analysis, never invention.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from atlas_api.agent import fallback, llm


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
            text, calls = llm.run(question, history, conn=conn)
            return ChatResult(answer=text, mode="ia", tool_calls=calls)
        except llm.ChatUnavailable:
            pass
        except Exception as e:  # network/API failure — degrade, stay honest
            text, calls, _ = fallback.answer(question, conn)
            return ChatResult(answer=text, mode="limitado", tool_calls=calls,
                              note=f"A IA falhou ({type(e).__name__}); respondi no modo limitado.")

    text, calls, note = fallback.answer(question, conn)
    return ChatResult(answer=text, mode="limitado", tool_calls=calls, note=note)
