import {
  Radar,
  Filter,
  CandlestickChart,
  Briefcase,
  UserSearch,
  Search,
} from "lucide-react";

import { ScreenerTable } from "@/components/screener-table";

const modules = [
  { icon: Radar, label: "Radar", active: true },
  { icon: Filter, label: "Screener", active: false },
  { icon: CandlestickChart, label: "Opções", active: false },
  { icon: Briefcase, label: "Carteira", active: false },
  { icon: UserSearch, label: "Analista", active: false },
];

const metrics = [
  { label: "Ibovespa", value: "131.420", delta: "+0,5%", up: true },
  { label: "Dólar", value: "5,42", delta: "−0,3%", up: false },
  { label: "IV rica (heur.)", value: "8", sub: "/ 37", accent: true },
  { label: "Vol. do dia", value: "R$ 24 bi" },
];

export default function Home() {
  return (
    <div className="flex min-h-screen">
      <aside className="flex w-52 shrink-0 flex-col gap-1 border-r border-[var(--border-subtle)] p-3">
        <div className="mb-2 flex items-center gap-2 px-2 py-3">
          <div className="grid h-8 w-8 place-items-center rounded-lg bg-[var(--accent)] text-[var(--bg-base)]">
            <Radar size={18} />
          </div>
          <div>
            <div className="text-sm font-medium">ATLAS</div>
            <div className="text-[11px] text-[var(--text-tertiary)]">terminal B3</div>
          </div>
        </div>
        {modules.map((m) => {
          const Icon = m.icon;
          return (
            <button
              key={m.label}
              className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm ${
                m.active
                  ? "bg-[var(--bg-surface)] text-[var(--accent)]"
                  : "text-[var(--text-secondary)] hover:bg-[var(--bg-surface)]"
              }`}
            >
              <Icon size={17} /> {m.label}
            </button>
          );
        })}
      </aside>

      <main className="min-w-0 flex-1">
        <header className="flex h-14 items-center justify-between gap-3 border-b border-[var(--border-subtle)] px-5">
          <div className="flex w-72 items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-3 py-1.5 text-[13px] text-[var(--text-tertiary)]">
            <Search size={15} /> Buscar ou comando
            <span className="mono ml-auto rounded border border-[var(--border-subtle)] px-1.5 text-[11px]">⌘K</span>
          </div>
          <div className="flex items-center gap-2 text-[13px] text-[var(--text-secondary)]">
            <span className="h-2 w-2 rounded-full" style={{ background: "var(--up)" }} /> ao vivo · EOD 27/06
          </div>
        </header>

        <div className="p-5">
          <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">
            {metrics.map((m) => (
              <div key={m.label} className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4">
                <div className="text-[12px] text-[var(--text-secondary)]">{m.label}</div>
                <div className="flex items-baseline gap-1.5">
                  <span className={`mono text-xl font-medium ${m.accent ? "text-[var(--accent)]" : ""}`}>{m.value}</span>
                  {m.delta ? (
                    <span className="text-[12px]" style={{ color: m.up ? "var(--up)" : "var(--down)" }}>
                      {m.delta}
                    </span>
                  ) : null}
                  {m.sub ? <span className="text-[12px] text-[var(--text-tertiary)]">{m.sub}</span> : null}
                </div>
              </div>
            ))}
          </div>

          <ScreenerTable />
        </div>
      </main>
    </div>
  );
}
