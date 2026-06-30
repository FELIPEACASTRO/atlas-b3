"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Radar,
  Filter,
  CandlestickChart,
  Briefcase,
  UserSearch,
  MessageSquare,
  Search,
  CornerDownLeft,
  TrendingUp,
} from "lucide-react";

type Cmd = {
  id: string;
  label: string;
  hint: string;
  icon: React.ComponentType<{ size?: number }>;
  run: (r: ReturnType<typeof useRouter>) => void;
};

const MODULES: Cmd[] = [
  { id: "radar", label: "Radar", hint: "panorama do mercado", icon: Radar, run: (r) => r.push("/") },
  { id: "screener", label: "Screener", hint: "filtrar ativos por IV / VRP", icon: Filter, run: (r) => r.push("/") },
  { id: "opcoes", label: "Opções", hint: "cadeia + volatilidade", icon: CandlestickChart, run: (r) => r.push("/opcoes") },
  { id: "carteira", label: "Carteira", hint: "risco e stress consolidados", icon: Briefcase, run: (r) => r.push("/carteira") },
  { id: "analista", label: "Analista", hint: "briefing honesto", icon: UserSearch, run: (r) => r.push("/analista") },
  { id: "chat", label: "Chat com o ATLAS", hint: "pergunte sobre opções e ações", icon: MessageSquare, run: (r) => r.push("/chat") },
];

export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  // a typed B3 ticker becomes a "open chain" action
  const tickerish = /^[A-Z]{4}\d{1,2}$/.test(q.trim().toUpperCase());
  const commands = useMemo<Cmd[]>(() => {
    const ql = q.trim().toLowerCase();
    const mods = MODULES.filter((c) => !ql || c.label.toLowerCase().includes(ql) || c.hint.includes(ql));
    if (tickerish) {
      const t = q.trim().toUpperCase();
      return [
        { id: "chain", label: `Abrir cadeia de ${t}`, hint: "Opções + IV/RV", icon: TrendingUp, run: (r) => r.push(`/opcoes?t=${t}`) },
        ...mods,
      ];
    }
    return mods;
  }, [q, tickerish]);

  const close = useCallback(() => { setOpen(false); setQ(""); setSel(0); }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      } else if (e.key === "Escape") {
        close();
      }
    };
    const onOpen = () => setOpen(true);
    window.addEventListener("keydown", onKey);
    window.addEventListener("atlas:open-command", onOpen);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("atlas:open-command", onOpen);
    };
  }, [close]);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 0);
  }, [open]);
  useEffect(() => { setSel(0); }, [q]);

  if (!open) return null;

  const choose = (i: number) => {
    const c = commands[i];
    if (!c) return;
    close();
    c.run(router);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[18vh]"
      style={{ background: "color-mix(in oklch, var(--bg-base) 55%, transparent)", backdropFilter: "blur(6px)" }}
      onClick={close}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="atlas-pop w-[min(92vw,560px)] overflow-hidden rounded-2xl border"
        style={{
          background: "var(--bg-elevated)",
          borderColor: "color-mix(in oklch, var(--accent) 30%, var(--border-subtle))",
          boxShadow: "0 24px 64px -16px rgba(0,0,0,.6), 0 0 0 1px color-mix(in oklch, var(--accent) 10%, transparent)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2.5 border-b border-[var(--border-subtle)] px-4 py-3">
          <Search size={17} style={{ color: "var(--accent)" }} />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(s + 1, commands.length - 1)); }
              else if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
              else if (e.key === "Enter") { e.preventDefault(); choose(sel); }
            }}
            placeholder="Buscar módulo ou digitar um ticker (ex: PETR4)…"
            className="w-full bg-transparent text-[14px] outline-none placeholder:text-[var(--text-tertiary)]"
            style={{ color: "var(--text-primary)" }}
          />
          <span className="mono rounded border border-[var(--border-subtle)] px-1.5 py-0.5 text-[10px] text-[var(--text-tertiary)]">esc</span>
        </div>

        <div className="max-h-[44vh] overflow-y-auto p-1.5">
          {commands.length === 0 ? (
            <div className="px-3 py-6 text-center text-[13px] text-[var(--text-tertiary)]">nada encontrado</div>
          ) : (
            commands.map((c, i) => {
              const Icon = c.icon;
              const on = i === sel;
              return (
                <button
                  key={c.id}
                  onMouseEnter={() => setSel(i)}
                  onClick={() => choose(i)}
                  className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors"
                  style={{ background: on ? "var(--bg-surface)" : "transparent" }}
                >
                  <span
                    className="grid h-8 w-8 shrink-0 place-items-center rounded-lg"
                    style={{ background: on ? "color-mix(in oklch, var(--accent) 18%, transparent)" : "var(--bg-surface)", color: on ? "var(--accent)" : "var(--text-secondary)" }}
                  >
                    <Icon size={16} />
                  </span>
                  <span className="min-w-0">
                    <span className="block text-[13.5px] font-medium" style={{ color: "var(--text-primary)" }}>{c.label}</span>
                    <span className="block text-[11.5px] text-[var(--text-tertiary)]">{c.hint}</span>
                  </span>
                  {on ? <CornerDownLeft size={14} className="ml-auto text-[var(--text-tertiary)]" /> : null}
                </button>
              );
            })
          )}
        </div>

        <div className="flex items-center gap-4 border-t border-[var(--border-subtle)] px-4 py-2 text-[11px] text-[var(--text-tertiary)]">
          <span className="mono">↑↓</span> navegar
          <span className="mono">↵</span> abrir
          <span className="ml-auto">ATLAS · ⌘K</span>
        </div>
      </div>
    </div>
  );
}
