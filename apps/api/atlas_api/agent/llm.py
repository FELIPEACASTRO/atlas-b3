"""LLM brain for the chat — grounded tool-use loop, FREE providers first.

The model only *narrates*; every number comes from a tool in ``tools.py``. We run
the agentic loop manually so the grounding system prompt and tool dispatch stay
under our control.

Providers (free-first, no paid default):
  - ``openrouter`` — OpenAI-compatible; tries a ranked list of ``:free`` models
    with failover (free pools are flaky — when one is rate-limited upstream the
    next is tried).
  - ``gemini`` — Google Generative Language free tier (gemini-2.5-flash), native
    function calling, tries each key until one is valid.
  - ``anthropic`` — paid; only when ``ATLAS_CHAT_PROVIDER=anthropic`` is forced.

Keys resolve from env first, then a local gitignored keys file (``CHAVE.txt`` by
default) so local dev "just works" without exporting anything. Nothing is ever
written to a tracked file. If no provider is usable, ``available()`` is False and
the caller degrades to the deterministic fallback — the chat never invents.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Iterator

from atlas_api.agent import tools

MAX_ITERS = 6

SYSTEM = (
    "Você é o ATLAS — um especialista de classe mundial em opções e mercados da B3, rigoroso como "
    "um profissional de mesa e, ao mesmo tempo, didático para quem está começando AGORA a investir. "
    "Responde perguntas sobre OPÇÕES e AÇÕES usando exclusivamente os dados reais da base EOD "
    "(COTAHIST) deste terminal.\n\n"
    "REGRAS INVIOLÁVEIS:\n"
    "1. Todo número (preço, IV, IV Rank, VRP, grego, breakeven, prazo) deve vir de uma "
    "ferramenta. NUNCA invente nem chute valores. Se uma ferramenta retornar {\"error\": ...} "
    "ou vier vazia, diga honestamente que não há esse dado na base.\n"
    "2. Isto é ANÁLISE e educação, não recomendação. Nunca dê ordem de 'compre' ou 'venda'; "
    "mostre os dois lados (titular vs lançador, prós e contras) e termine lembrando que a "
    "decisão é do usuário.\n"
    "3. Os dados são de fechamento (EOD) na data 'asof' que as ferramentas retornam — deixe "
    "claro que não é tempo real e que você não prevê o futuro.\n\n"
    "SOBRE A SOLUÇÃO: você faz parte do ATLAS, um terminal de apoio à decisão para opções da "
    "B3, e tem ferramentas que cobrem TODAS as telas — use a certa para cada pergunta:\n"
    "- panorama do mercado no dia → market_summary;\n"
    "- rastrear/ranquear ativos por IV, IV Rank, VRP, sinal → screen_underlyings;\n"
    "- retrato de um ativo (spot, IV, IV Rank, VRP, vol) → underlying_snapshot;\n"
    "- buscar opções (calls/puts, moneyness, prazo, mais baratas) → search_options;\n"
    "- analisar uma opção específica dos dois lados → analyze_option;\n"
    "- histórico de IV vs RV → vol_history; estrutura a termo/superfície de vol → term_structure;\n"
    "- montar uma operação/briefing (trava, risco-retorno, sizing por perfil) → briefing;\n"
    "- a carteira do usuário (posições, gregas líquidas, stress, payoff) → portfolio;\n"
    "- o que significam as COLUNAS/valores de uma tela (ex: a tabela do screener) → screen_guide;\n"
    "- o que é/significa um CONCEITO (IV, RV, VRP, delta, skew, breakeven, moneyness…) → glossary;\n"
    "- o que é o ATLAS / o que você faz / quais dados-ativos existem / cobertura / o melhor da "
    "base → solution_overview.\n"
    "Nunca invente módulos, contagens ou posições — use a ferramenta. Se a pergunta for ampla ou "
    "ambígua, dê primeiro um resumo do que dá para fazer (e, se útil, chame solution_overview) e "
    "ofereça próximos passos, em vez de só pedir esclarecimento.\n\n"
    "COMO ESCREVER (sempre):\n"
    "- Português do Brasil, claro, detalhado e intuitivo. ADAPTE-SE AO NÍVEL da pergunta: se for "
    "básica, explique do zero com uma analogia; se for técnica/avançada, vá fundo (skew, estrutura "
    "a termo, gregas de 2ª ordem) com precisão e sem encher linguiça.\n"
    "- Explique TODA sigla ou jargão na primeira vez, em palavras simples e entre parênteses: "
    "ex. 'IV (volatilidade implícita — o 'nervosismo' que o mercado espera)', 'strike (preço "
    "combinado)', 'breakeven (ponto onde você empata)', 'IV Rank (onde a vol está hoje frente "
    "ao próprio histórico)', 'VRP (vol implícita menos a realizada)'. Nunca jogue uma sigla "
    "solta.\n"
    "- Estrutura: comece com a RESPOSTA DIRETA em uma frase; depois explique o PORQUÊ com os "
    "números reais; use uma ANALOGIA do dia a dia quando ajudar; encerre com os dois lados "
    "(o que olhar para comprar/titular vs vender/sair/lançador) e lembrando que a decisão é "
    "do usuário.\n"
    "- Seja completo, mas sem encher linguiça: cada frase deve agregar. Não despeje JSON nem "
    "tabelas cruas — traduza os números em frases. Pode usar **negrito** e listas com '•'.\n\n"
    "Tickers: subjacentes como PETR4, VALE3, BOVA11; opções como PETRA38. Chame as "
    "ferramentas quantas vezes precisar antes de responder."
)

_OPENROUTER_BASE = os.environ.get("ATLAS_OPENROUTER_BASE", "https://openrouter.ai/api/v1")
_DEFAULT_OR_MODELS = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "qwen/qwen3-coder:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "openai/gpt-oss-120b:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "openrouter/free",
]
_GEMINI_MODEL = os.environ.get("ATLAS_GEMINI_MODEL", "gemini-2.5-flash")


class ChatUnavailable(RuntimeError):
    """No usable provider, or every provider failed this turn."""


class _ProviderError(RuntimeError):
    def __init__(self, code, detail):
        super().__init__(f"HTTP {code}: {detail}")
        self.code = code


# --- key resolution (env first, then local gitignored keys file) -----------

def _keys_file() -> str:
    return os.environ.get("ATLAS_KEYS_FILE", "CHAVE.txt")


def _file_values(prefix: str) -> list[str]:
    path = _keys_file()
    if not os.path.exists(path):
        return []
    out = []
    try:
        for line in open(path, encoding="utf-8"):
            left, _, right = line.partition("=")
            if "=" in line and left.strip().upper().startswith(prefix):
                v = right.strip()
                if v:
                    out.append(v)
    except OSError:
        return []
    return out


def _openrouter_key() -> str | None:
    return os.environ.get("OPENROUTER_API_KEY") or next(iter(_file_values("OPENROUTER")), None)


def _gemini_keys() -> list[str]:
    env = [k for k in (os.environ.get("GEMINI_API_KEY"), os.environ.get("GOOGLE_API_KEY")) if k]
    return env + _file_values("GOOGLE/GEMINI")


def _anthropic_key() -> str | None:
    return os.environ.get("ANTHROPIC_API_KEY") or next(iter(_file_values("ANTHROPIC")), None)


def _anthropic_ready() -> bool:
    if not _anthropic_key():
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def provider_chain() -> list[str]:
    """Ordered providers to try. 'auto' is FREE-only (openrouter -> gemini)."""
    sel = os.environ.get("ATLAS_CHAT_PROVIDER", "auto").lower()
    avail = {
        "openrouter": bool(_openrouter_key()),
        "gemini": bool(_gemini_keys()),
        "anthropic": _anthropic_ready(),
    }
    order = ["openrouter", "gemini"] if sel == "auto" else [sel]
    return [p for p in order if avail.get(p)]


def available() -> bool:
    return bool(provider_chain())


# --- HTTP (stdlib only) ----------------------------------------------------

def _post(url: str, payload: dict, headers: dict, timeout: int = 120) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, method="POST", headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        try:
            detail = json.loads(body).get("error", {}).get("message") or body[:200]
        except (ValueError, AttributeError):
            detail = body[:200]
        raise _ProviderError(e.code, detail) from None


def _history(history: list) -> list[dict]:
    out = []
    for m in (history or [])[-8:]:
        role = getattr(m, "role", None) or (m.get("role") if isinstance(m, dict) else None)
        content = getattr(m, "content", None) or (m.get("content") if isinstance(m, dict) else None)
        if role in ("user", "assistant") and content:
            out.append({"role": role, "content": str(content)})
    return out


# --- OpenRouter (OpenAI-compatible) ----------------------------------------

def _oai_tools() -> list[dict]:
    return [{"type": "function", "function": {
        "name": t["name"], "description": t["description"], "parameters": t["input_schema"]}}
        for t in tools.TOOL_SCHEMAS]


def _run_openai(model: str, key: str, question: str, history: list, *, conn) -> tuple[str, list[dict]]:
    messages = [{"role": "system", "content": SYSTEM}, *_history(history),
                {"role": "user", "content": question}]
    headers = {"Authorization": f"Bearer {key}",
               "HTTP-Referer": "http://localhost:3000", "X-Title": "ATLAS"}
    tool_calls: list[dict] = []
    for _ in range(MAX_ITERS):
        data = _post(f"{_OPENROUTER_BASE}/chat/completions", {
            "model": model, "messages": messages, "tools": _oai_tools(),
            "temperature": 0, "max_tokens": 1024}, headers)
        choices = data.get("choices") or []
        if not choices:
            raise _ProviderError(502, f"resposta sem choices ({list(data)})")
        msg = choices[0]["message"]
        tcs = msg.get("tool_calls") or []
        if tcs:
            messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": tcs})
            for c in tcs:
                name = c["function"]["name"]
                try:
                    args = json.loads(c["function"].get("arguments") or "{}")
                except ValueError:
                    args = {}
                out = tools.dispatch(conn, name, args)
                tool_calls.append({"name": name, "args": args})
                messages.append({"role": "tool", "tool_call_id": c["id"],
                                 "content": json.dumps(out, ensure_ascii=False)})
            continue
        return (msg.get("content") or "").strip() or "(sem resposta)", tool_calls
    return "Precisei de etapas demais — refaça a pergunta de forma mais direta.", tool_calls


def _run_openrouter(question, history, *, conn) -> tuple[str, list[dict]]:
    key = _openrouter_key()
    models = [m.strip() for m in os.environ.get("ATLAS_OPENROUTER_MODELS", "").split(",") if m.strip()] \
        or _DEFAULT_OR_MODELS
    last = None
    for model in models:
        try:
            return _run_openai(model, key, question, history, conn=conn)
        except _ProviderError as e:
            last = e
            if e.code in (401, 403):  # bad/again key — every model fails the same; bail now
                break
            continue  # free pool busy / model offline -> try the next model
    raise ChatUnavailable(f"OpenRouter gratuito indisponível ({last})")


# --- Gemini (Google Generative Language, free tier) ------------------------

def _gemini_tools() -> list[dict]:
    return [{"function_declarations": [
        {"name": t["name"], "description": t["description"][:1024], "parameters": t["input_schema"]}
        for t in tools.TOOL_SCHEMAS]}]


def _gemini_history(history: list) -> list[dict]:
    out = []
    for m in _history(history):
        out.append({"role": "model" if m["role"] == "assistant" else "user",
                    "parts": [{"text": m["content"]}]})
    return out


def _run_gemini_one(model: str, key: str, question: str, history: list, *, conn) -> tuple[str, list[dict]]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    contents = [*_gemini_history(history), {"role": "user", "parts": [{"text": question}]}]
    payload_base = {"system_instruction": {"parts": [{"text": SYSTEM}]}, "tools": _gemini_tools()}
    tool_calls: list[dict] = []
    for _ in range(MAX_ITERS):
        data = _post(url, {**payload_base, "contents": contents}, {})
        cands = data.get("candidates") or []
        if not cands:
            raise _ProviderError(502, f"Gemini sem candidates ({data.get('promptFeedback')})")
        parts = (cands[0].get("content") or {}).get("parts") or []
        fcs = [p["functionCall"] for p in parts if "functionCall" in p]
        if fcs:
            contents.append({"role": "model", "parts": parts})
            resps = []
            for fc in fcs:
                name = fc["name"]
                args = dict(fc.get("args") or {})
                out = tools.dispatch(conn, name, args)
                tool_calls.append({"name": name, "args": args})
                resps.append({"functionResponse": {"name": name, "response": {"result": out}}})
            contents.append({"role": "user", "parts": resps})
            continue
        text = "".join(p.get("text", "") for p in parts if "text" in p)
        return text.strip() or "(sem resposta)", tool_calls
    return "Precisei de etapas demais — refaça a pergunta de forma mais direta.", tool_calls


def _run_gemini(question, history, *, conn) -> tuple[str, list[dict]]:
    last = None
    for key in _gemini_keys():
        try:
            return _run_gemini_one(_GEMINI_MODEL, key, question, history, conn=conn)
        except _ProviderError as e:  # invalid/exhausted key (400/403/429) -> next key
            last = e
            continue
    raise ChatUnavailable(f"Gemini gratuito indisponível ({last})")


# --- Anthropic (paid; only when forced) ------------------------------------

def _run_anthropic(question: str, history: list, *, conn, client=None) -> tuple[str, list[dict]]:
    if client is None:
        import anthropic
        client = anthropic.Anthropic(api_key=_anthropic_key())
    messages = [*_history(history), {"role": "user", "content": question}]
    tool_calls: list[dict] = []
    for _ in range(MAX_ITERS):
        resp = client.messages.create(
            model=os.environ.get("ATLAS_CHAT_MODEL", "claude-opus-4-8"),
            max_tokens=4096, system=SYSTEM, thinking={"type": "adaptive"},
            tools=tools.TOOL_SCHEMAS, messages=messages)
        if getattr(resp, "stop_reason", None) == "refusal":
            return "Não consigo responder a esse pedido específico.", tool_calls
        if resp.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for block in resp.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                args = dict(block.input or {})
                out = tools.dispatch(conn, block.name, args)
                tool_calls.append({"name": block.name, "args": args})
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": json.dumps(out, ensure_ascii=False)})
            messages.append({"role": "user", "content": results})
            continue
        text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text")
        return text.strip() or "(sem resposta)", tool_calls
    return "Precisei de etapas demais — refaça a pergunta de forma mais direta.", tool_calls


_RUNNERS = {"openrouter": _run_openrouter, "gemini": _run_gemini, "anthropic": _run_anthropic}


def run(question: str, history: list, *, conn) -> tuple[str, list[dict], str]:
    """Try each available provider in order; return (text, tool_calls, provider).

    Raises ChatUnavailable if no provider is configured or all fail this turn.
    """
    chain = provider_chain()
    if not chain:
        raise ChatUnavailable("nenhum provedor de IA configurado")
    last = None
    for prov in chain:
        try:
            text, calls = _RUNNERS[prov](question, history, conn=conn)
            return text, calls, prov
        except Exception as e:  # flaky free providers — fail over to the next
            last = e
            continue
    raise ChatUnavailable(str(last) if last else "todos os provedores falharam")


def stream(question: str, history: list, *, conn) -> Iterator[dict]:
    """Streamed events: 'tool' as each fires, 'delta' text, then 'done'.

    Only Anthropic streams token-by-token; OpenRouter/Gemini run to completion and
    emit tool events + a single delta (still shows which tools were consulted).
    Raises ChatUnavailable if nothing is configured / all fail.
    """
    chain = provider_chain()
    if not chain:
        raise ChatUnavailable("nenhum provedor de IA configurado")
    last = None
    for prov in chain:
        try:
            if prov == "anthropic":
                yield from _stream_anthropic(question, history, conn=conn)
            else:
                text, calls = _RUNNERS[prov](question, history, conn=conn)
                for c in calls:
                    yield {"type": "tool", "name": c["name"], "args": c["args"]}
                yield {"type": "delta", "text": text}
                yield {"type": "done", "tool_calls": calls, "provider": prov}
            return
        except Exception as e:  # flaky free providers — fail over to the next
            last = e
            continue
    raise ChatUnavailable(str(last) if last else "todos os provedores falharam")


def _stream_anthropic(question: str, history: list, *, conn, client=None) -> Iterator[dict]:
    if client is None:
        import anthropic
        client = anthropic.Anthropic(api_key=_anthropic_key())
    messages = [*_history(history), {"role": "user", "content": question}]
    tool_calls: list[dict] = []
    for _ in range(MAX_ITERS):
        with client.messages.stream(
            model=os.environ.get("ATLAS_CHAT_MODEL", "claude-opus-4-8"),
            max_tokens=4096, system=SYSTEM, thinking={"type": "adaptive"},
            tools=tools.TOOL_SCHEMAS, messages=messages,
        ) as st:
            for text in st.text_stream:
                yield {"type": "delta", "text": text}
            final = st.get_final_message()
        if getattr(final, "stop_reason", None) == "refusal":
            yield {"type": "delta", "text": "Não consigo responder a esse pedido específico."}
            yield {"type": "done", "tool_calls": tool_calls, "provider": "anthropic"}
            return
        if final.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": final.content})
            results = []
            for block in final.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                args = dict(block.input or {})
                yield {"type": "tool", "name": block.name, "args": args}
                out = tools.dispatch(conn, block.name, args)
                tool_calls.append({"name": block.name, "args": args})
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": json.dumps(out, ensure_ascii=False)})
            messages.append({"role": "user", "content": results})
            continue
        yield {"type": "done", "tool_calls": tool_calls, "provider": "anthropic"}
        return
    yield {"type": "done", "tool_calls": tool_calls, "provider": "anthropic"}
