"""LLM brain for the chat — grounded tool-use loop over the real store.

Provider-pluggable (default: Anthropic / Claude). The model only ever *narrates*;
every number comes from a tool in ``tools.py``. We run the agentic loop manually
so the grounding system prompt and the tool dispatch stay under our control.

No key / package? ``available()`` returns False and the caller uses the
deterministic fallback instead — the chat degrades, it never lies.
"""
from __future__ import annotations

import json
import os

from atlas_api.agent import tools

MAX_ITERS = 6
_DEFAULT_MODEL = "claude-opus-4-8"

SYSTEM = (
    "Você é o ATLAS, um assistente que responde perguntas sobre OPÇÕES e AÇÕES da B3 "
    "usando exclusivamente os dados reais da base EOD (COTAHIST) deste terminal.\n\n"
    "REGRAS INVIOLÁVEIS:\n"
    "1. Todo número (preço, IV, IV Rank, VRP, grego, breakeven, prazo) deve vir de uma "
    "ferramenta. NUNCA invente, estime de cabeça nem chute valores. Se uma ferramenta "
    "retornar {\"error\": ...} ou vier vazia, diga honestamente que não há esse dado na base.\n"
    "2. Isto é ANÁLISE e educação, não recomendação. Nunca dê uma ordem de 'compre' ou 'venda'; "
    "mostre os dois lados (titular vs lançador, prós e contras) e termine com 'a decisão é sua'.\n"
    "3. Cite a procedência: os dados são de fechamento (EOD) na data 'asof' que as ferramentas "
    "retornam — deixe claro que não é tempo real e que você não prevê o futuro.\n"
    "4. Responda em português do Brasil, didático e direto. Use uma analogia do dia a dia quando "
    "ajudar a explicar. Não despeje JSON cru: traduza os números em frases claras.\n\n"
    "Tickers: subjacentes são como PETR4, VALE3, BOVA11; opções como PETRA38. Chame as "
    "ferramentas quantas vezes precisar antes de responder."
)


class ChatUnavailable(RuntimeError):
    """Raised when no usable LLM provider is configured."""


def provider() -> str:
    return os.environ.get("ATLAS_CHAT_PROVIDER", "anthropic").lower()


def model() -> str:
    return os.environ.get("ATLAS_CHAT_MODEL", _DEFAULT_MODEL)


def available() -> bool:
    if provider() != "anthropic":
        return False
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def _to_messages(history: list, question: str) -> list[dict]:
    msgs: list[dict] = []
    for m in (history or [])[-8:]:
        role = getattr(m, "role", None) or (m.get("role") if isinstance(m, dict) else None)
        content = getattr(m, "content", None) or (m.get("content") if isinstance(m, dict) else None)
        if role in ("user", "assistant") and content:
            msgs.append({"role": role, "content": str(content)})
    msgs.append({"role": "user", "content": question})
    return msgs


def run(question: str, history: list, *, conn, client=None) -> tuple[str, list[dict]]:
    """Run the grounded tool loop; returns (answer_text, tool_calls).

    ``client`` is injectable for tests (a stub exposing ``messages.create``);
    in production it defaults to ``anthropic.Anthropic()``.
    """
    if client is None:
        if not available():
            raise ChatUnavailable("sem provedor de IA configurado (ANTHROPIC_API_KEY / pacote anthropic)")
        import anthropic
        client = anthropic.Anthropic()

    messages = _to_messages(history, question)
    tool_calls: list[dict] = []

    for _ in range(MAX_ITERS):
        resp = client.messages.create(
            model=model(),
            max_tokens=4096,
            system=SYSTEM,
            thinking={"type": "adaptive"},
            tools=tools.TOOL_SCHEMAS,
            messages=messages,
        )
        if getattr(resp, "stop_reason", None) == "refusal":
            return ("Não consigo responder a esse pedido específico. Posso ajudar com IV, "
                    "gregas, opções e ações da base.", tool_calls)

        if resp.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for block in resp.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                out = tools.dispatch(conn, block.name, dict(block.input or {}))
                tool_calls.append({"name": block.name, "args": dict(block.input or {})})
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(out, ensure_ascii=False),
                })
            messages.append({"role": "user", "content": results})
            continue

        text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text")
        return (text.strip() or "(sem resposta)", tool_calls)

    return ("Precisei de etapas demais para responder com segurança — refaça a pergunta de forma "
            "mais direta (ex: cite um ticker).", tool_calls)
