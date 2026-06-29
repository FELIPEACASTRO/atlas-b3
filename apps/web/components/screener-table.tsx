"use client";

import { useEffect, useState } from "react";

type Row = {
  ticker: string;
  tipo: string;
  ultimo: number;
  var_pct: number;
  liquidez: number;
  iv: number | null;
  iv_vs_rv: string | null;
  provenance: string;
  asof: string;
};

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const FALLBACK: Row[] = [
  { ticker: "PETR4", tipo: "acao", ultimo: 38.42, var_pct: 1.2, liquidez: 1.2e9, iv: null, iv_vs_rv: null, provenance: "fixture", asof: "" },
  { ticker: "PETRG38", tipo: "call", ultimo: 1.15, var_pct: 4.5, liquidez: 88e6, iv: 0.42, iv_vs_rv: "rico", provenance: "fixture", asof: "" },
  { ticker: "VALE3", tipo: "acao", ultimo: 61.3, var_pct: -0.8, liquidez: 9.8e8, iv: null, iv_vs_rv: null, provenance: "fixture", asof: "" },
];

function fmtLiq(n: number): string {
  if (n >= 1e9) return `R$ ${(n / 1e9).toFixed(1)} bi`;
  if (n >= 1e6) return `R$ ${(n / 1e6).toFixed(0)} mi`;
  return `R$ ${n.toLocaleString("pt-BR", { maximumFractionDigits: 0 })}`;
}

function tipoLabel(t: string): string {
  return t === "acao" ? "Ação" : t === "call" ? "Call" : t === "put" ? "Put" : t;
}

function SigBadge({ sig }: { sig: string | null }) {
  if (sig === "rico")
    return (
      <span className="rounded px-2 py-0.5 text-[11px]" style={{ background: "color-mix(in oklch, var(--accent) 18%, transparent)", color: "var(--accent)" }}>
        Rico
      </span>
    );
  if (sig === "barato")
    return (
      <span className="rounded px-2 py-0.5 text-[11px]" style={{ background: "color-mix(in oklch, var(--up) 18%, transparent)", color: "var(--up)" }}>
        Barato
      </span>
    );
  return <span className="text-[var(--text-tertiary)]">—</span>;
}

export function ScreenerTable() {
  const [rows, setRows] = useState<Row[]>(FALLBACK);
  const [provenance, setProvenance] = useState<string>("fixture (API offline)");
  const [query, setQuery] = useState("");

  useEffect(() => {
    let alive = true;
    fetch(`${API}/screener`)
      .then((r) => r.json())
      .then((data: Row[]) => {
        if (alive && Array.isArray(data) && data.length) {
          setRows(data);
          setProvenance(data[0].provenance);
        }
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  const filtered = rows
    .filter((r) => r.ticker.toUpperCase().includes(query.toUpperCase()))
    .slice(0, 40);

  return (
    <div>
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="filtrar ativos…"
        className="mb-3 w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-3 py-2 text-[13px] outline-none"
        style={{ color: "var(--text-primary)" }}
      />
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
            {filtered.map((r) => (
              <tr key={r.ticker} className="border-t border-[var(--border-subtle)]">
                <td className="mono px-4 py-2.5 font-medium">{r.ticker}</td>
                <td className="px-3 py-2.5 text-[var(--text-secondary)]">{tipoLabel(r.tipo)}</td>
                <td className="mono px-3 py-2.5 text-right">
                  {r.ultimo.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </td>
                <td className="mono px-3 py-2.5 text-right" style={{ color: r.var_pct >= 0 ? "var(--up)" : "var(--down)" }}>
                  {r.var_pct >= 0 ? "+" : ""}
                  {r.var_pct.toFixed(1)}%
                </td>
                <td className="mono px-3 py-2.5 text-right">{fmtLiq(r.liquidez)}</td>
                <td className="mono px-3 py-2.5 text-right">{r.iv != null ? `${(r.iv * 100).toFixed(0)}%` : "—"}</td>
                <td className="px-4 py-2.5 text-right">
                  <SigBadge sig={r.iv_vs_rv} />
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
        <span>fonte: {provenance} · heurística, não recomendação</span>
      </div>
    </div>
  );
}
