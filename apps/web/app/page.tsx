import { Shell } from "@/components/shell";
import { ScreenerTable } from "@/components/screener-table";

const metrics = [
  { label: "Ibovespa", value: "131.420", delta: "+0,5%", up: true },
  { label: "Dólar", value: "5,42", delta: "−0,3%", up: false },
  { label: "IV rica (heur.)", value: "8", sub: "/ 37", accent: true },
  { label: "Vol. do dia", value: "R$ 24 bi" },
];

export default function Home() {
  return (
    <Shell active="Radar">
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
    </Shell>
  );
}
