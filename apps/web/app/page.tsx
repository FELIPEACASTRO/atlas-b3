import {
  Radar,
  Filter,
  CandlestickChart,
  Briefcase,
  UserSearch,
  Search,
} from "lucide-react";

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

const rows = [
  { t: "PETR4", tipo: "Ação", last: "38,42", v: "+1,2%", up: true, liq: "R$ 1,2 bi", iv: "—", sig: "—" },
  { t: "PETRG38", tipo: "Call", last: "1,15", v: "+4,5%", up: true, liq: "R$ 88 mi", iv: "42%", sig: "rico" },
  { t: "VALE3", tipo: "Ação", last: "61,30", v: "−0,8%", up: false, liq: "R$ 980 mi", iv: "—", sig: "—" },
  { t: "BBASF28", tipo: "Call", last: "0,73", v: "+6,0%", up: true, liq: "R$ 22 mi", iv: "35%", sig: "barato" },
];

function SigBadge({ sig }: { sig: string }) {
  if (sig === "rico") {
    return (
      <span
        className="text-[11px] px-2 py-0.5 rounded"
        style={{ background: "color-mix(in oklch, var(--accent) 18%, transparent)", color: "var(--accent)" }}
      >
        Rico
      </span>
    );
  }
  if (sig === "barato") {
    return (
      <span
        className="text-[11px] px-2 py-0.5 rounded"
        style={{ background: "color-mix(in oklch, var(--up) 18%, transparent)", color: "var(--up)" }}
      >
        Barato
      </span>
    );
  }
  return <span className="text-[var(--text-tertiary)]">—</span>;
}

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

          <div className="overflow-hidden rounded-xl border border-[var(--border-subtle)]">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="bg-[var(--bg-surface)] text-left text-[var(--text-secondary)]">
                  <th className="px-4 py-2.5 font-normal">Ativo</th>
                  <th className="px-3 py-2.5 font-normal">Tipo</th>
                  <th className="px-3 py-2.5 text-right font-normal">Último</th>
                  <th className="px-3 py-2.5 text-right font-normal">Var %</th>
                  <th className="px-3 py-2.5 text-right font-normal">Liquidez</th>
                  <th className="px-3 py-2.5 text-right font-normal">IV</th>
                  <th className="px-4 py-2.5 text-right font-normal">IV vs RV</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.t} className="border-t border-[var(--border-subtle)]">
                    <td className="mono px-4 py-2.5 font-medium">{r.t}</td>
                    <td className="px-3 py-2.5 text-[var(--text-secondary)]">{r.tipo}</td>
                    <td className="mono px-3 py-2.5 text-right">{r.last}</td>
                    <td className="mono px-3 py-2.5 text-right" style={{ color: r.up ? "var(--up)" : "var(--down)" }}>
                      {r.v}
                    </td>
                    <td className="mono px-3 py-2.5 text-right">{r.liq}</td>
                    <td className="mono px-3 py-2.5 text-right">{r.iv}</td>
                    <td className="px-4 py-2.5 text-right">
                      <SigBadge sig={r.sig} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-3 flex items-center gap-4 text-[11.5px] text-[var(--text-tertiary)]">
            <span className="flex items-center gap-1.5">
              <i className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: "var(--accent)" }} /> Rico = IV &gt; RV
            </span>
            <span className="flex items-center gap-1.5">
              <i className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: "var(--up)" }} /> Barato = IV &lt; RV
            </span>
            <span>Dados EOD · heurística, não recomendação</span>
          </div>
        </div>
      </main>
    </div>
  );
}
