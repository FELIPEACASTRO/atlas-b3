"use client";

import { useEffect, useRef, useState } from "react";
import { Sparkles, Send, Bot, User, Wrench, Loader2 } from "lucide-react";

type ToolCall = { name: string; args: Record<string, unknown> };
type Msg = {
  role: "user" | "assistant";
  content: string;
  mode?: string;
  tool_calls?: ToolCall[];
  provenance?: string;
  asof?: string | null;
  note?: string | null;
};

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const SUGGESTIONS = [
  "Como está a volatilidade da PETR4?",
  "Calls mais baratas da VALE3 para uns 30 dias",
  "Vale a pena a PETRA38?",
  "Quais ações estão com a vol mais cara agora?",
];

// minimal formatter: keep line breaks, render **bold** without raw HTML
function fmt(text: string) {
  return text.split("\n").map((line, i) => (
    <span key={i} className="block min-h-[2px]">
      {line.split(/(\*\*[^*]+\*\*)/g).map((seg, j) =>
        seg.startsWith("**") && seg.endsWith("**") ? (
          <b key={j} style={{ color: "var(--text-primary)" }}>{seg.slice(2, -2)}</b>
        ) : (
          <span key={j}>{seg}</span>
        ),
      )}
    </span>
  ));
}

const TOOL_LABEL: Record<string, string> = {
  screen_underlyings: "rastreou ativos",
  underlying_snapshot: "retrato do ativo",
  search_options: "buscou opções",
  analyze_option: "analisou a opção",
  vol_history: "histórico de vol",
};

export function Chat() {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [msgs, busy]);

  async function send(text: string) {
    const q = text.trim();
    if (!q || busy) return;
    setErr("");
    const history = msgs.map((m) => ({ role: m.role, content: m.content }));
    const next = [...msgs, { role: "user", content: q } as Msg];
    setMsgs(next);
    setInput("");
    setBusy(true);
    try {
      const r = await fetch(`${API}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q, history }),
      });
      if (!r.ok) {
        const detail = r.status === 503
          ? "sem base de dados carregada — rode a ingestão (ATLAS_DB)"
          : `erro ${r.status} ao consultar o ATLAS`;
        throw new Error(detail);
      }
      const d = await r.json();
      setMsgs([...next, {
        role: "assistant", content: d.answer, mode: d.mode,
        tool_calls: d.tool_calls, provenance: d.provenance, asof: d.asof, note: d.note,
      }]);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "falha na conexão com o ATLAS");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex h-[calc(100vh-7rem)] max-w-3xl flex-col">
      <div className="mb-3 flex items-center gap-2.5">
        <div className="grid h-9 w-9 place-items-center rounded-xl" style={{ background: "color-mix(in oklch, var(--accent) 18%, transparent)", color: "var(--accent)" }}>
          <Sparkles size={18} />
        </div>
        <div>
          <h1 className="text-[15px] font-medium">Chat com o ATLAS</h1>
          <p className="text-[11.5px] text-[var(--text-tertiary)]">
            pergunte qualquer coisa sobre opções e ações — respondo com os números reais da base, nunca inventados
          </p>
        </div>
      </div>

      <div className="atlas-card flex-1 overflow-y-auto rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4">
        {msgs.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
            <div className="grid h-12 w-12 place-items-center rounded-2xl" style={{ background: "color-mix(in oklch, var(--accent) 12%, transparent)", color: "var(--accent)" }}>
              <Bot size={22} />
            </div>
            <p className="max-w-sm text-[13px] text-[var(--text-secondary)]">
              Sou um assistente honesto: explico IV, gregas, prós e contras de uma opção, e mostro os dois lados.
              Análise, não recomendação. Comece por um exemplo:
            </p>
            <div className="grid w-full max-w-md gap-2 sm:grid-cols-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="atlas-row rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-3 py-2.5 text-left text-[12.5px] text-[var(--text-secondary)] hover:border-[color-mix(in_oklch,var(--accent)_40%,var(--border-subtle))]"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {msgs.map((m, i) => (
              <Bubble key={i} m={m} />
            ))}
            {busy ? (
              <div className="flex items-center gap-2 text-[12.5px] text-[var(--text-tertiary)]">
                <Loader2 size={14} className="animate-spin" style={{ color: "var(--accent)" }} /> consultando a base…
              </div>
            ) : null}
            <div ref={endRef} />
          </div>
        )}
      </div>

      {err ? <p className="mt-2 text-[12px]" style={{ color: "var(--down)" }}>{err}</p> : null}

      <form
        onSubmit={(e) => { e.preventDefault(); send(input); }}
        className="mt-3 flex items-end gap-2 rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-2"
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); }
          }}
          rows={1}
          placeholder="Pergunte sobre uma ação ou opção (ex: a vol da VALE3 está alta?)…"
          className="max-h-32 min-h-[40px] flex-1 resize-none bg-transparent px-2 py-2 text-[13.5px] outline-none placeholder:text-[var(--text-tertiary)]"
          style={{ color: "var(--text-primary)" }}
        />
        <button
          type="submit"
          disabled={busy || !input.trim()}
          aria-label="enviar"
          className="grid h-10 w-10 shrink-0 place-items-center rounded-xl transition-colors disabled:opacity-40"
          style={{ background: "var(--accent)", color: "var(--bg-base)" }}
        >
          {busy ? <Loader2 size={17} className="animate-spin" /> : <Send size={17} />}
        </button>
      </form>
      <p className="mt-1.5 px-1 text-[10.5px] text-[var(--text-tertiary)]">
        dados de fechamento (EOD) · o ATLAS não prevê o futuro nem dá ordem de compra/venda
      </p>
    </div>
  );
}

function Bubble({ m }: { m: Msg }) {
  if (m.role === "user") {
    return (
      <div className="flex justify-end gap-2.5">
        <div className="max-w-[80%] rounded-2xl rounded-tr-sm px-3.5 py-2.5 text-[13px] leading-relaxed" style={{ background: "color-mix(in oklch, var(--accent) 16%, transparent)", color: "var(--text-primary)" }}>
          {m.content}
        </div>
        <div className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-[var(--bg-elevated)] text-[var(--text-secondary)]">
          <User size={14} />
        </div>
      </div>
    );
  }
  const live = m.mode === "ia";
  return (
    <div className="flex gap-2.5">
      <div className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-lg" style={{ background: "color-mix(in oklch, var(--accent) 14%, transparent)", color: "var(--accent)" }}>
        <Bot size={14} />
      </div>
      <div className="min-w-0 max-w-[84%] space-y-2">
        <div className="rounded-2xl rounded-tl-sm border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-3.5 py-2.5 text-[13px] leading-relaxed text-[var(--text-secondary)]">
          {fmt(m.content)}
        </div>
        {m.note ? (
          <p className="text-[11px]" style={{ color: "var(--accent)" }}>{m.note}</p>
        ) : null}
        <div className="flex flex-wrap items-center gap-1.5">
          <span
            className="rounded-md px-1.5 py-0.5 text-[10px]"
            style={live
              ? { background: "color-mix(in oklch, var(--up) 16%, transparent)", color: "var(--up)" }
              : { background: "var(--bg-surface)", color: "var(--text-tertiary)" }}
          >
            {live ? "IA ao vivo" : "modo simples"}
          </span>
          {(m.tool_calls ?? []).map((c, i) => (
            <span key={i} className="flex items-center gap-1 rounded-md bg-[var(--bg-surface)] px-1.5 py-0.5 text-[10px] text-[var(--text-tertiary)]">
              <Wrench size={9} /> {TOOL_LABEL[c.name] ?? c.name}
            </span>
          ))}
          {m.provenance ? (
            <span className="text-[10px] text-[var(--text-tertiary)]">· {m.provenance}</span>
          ) : null}
        </div>
      </div>
    </div>
  );
}
