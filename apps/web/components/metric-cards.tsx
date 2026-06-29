"use client";

import { useEffect, useState } from "react";

type Summary = {
  provenance: string;
  asof: string | null;
  underlyings: number;
  com_sinal: number;
  rico: number;
  barato: number;
  vol_total: number;
  bova11: number | null;
};

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function fmtVol(n: number): string {
  if (n >= 1e9) return `R$ ${(n / 1e9).toFixed(1)} bi`;
  if (n >= 1e6) return `R$ ${(n / 1e6).toFixed(0)} mi`;
  return `R$ ${n.toLocaleString("pt-BR", { maximumFractionDigits: 0 })}`;
}

export function MetricCards() {
  const [s, setS] = useState<Summary | null>(null);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    let alive = true;
    fetch(`${API}/summary`)
      .then((r) => r.json())
      .then((d: Summary) => alive && setS(d))
      .catch(() => alive && setOffline(true));
    return () => {
      alive = false;
    };
  }, []);

  const cards = [
    { label: "BOVA11 (ETF Ibov)", value: s?.bova11 != null ? s.bova11.toFixed(2) : "—" },
    { label: "IV rica (heur.)", value: s ? String(s.rico) : "—", sub: s ? `/ ${s.com_sinal}` : undefined, accent: true },
    { label: "IV barata (heur.)", value: s ? String(s.barato) : "—" },
    { label: "Vol. do dia", value: s ? fmtVol(s.vol_total) : "—" },
  ];

  return (
    <>
      <div className="mb-3 grid grid-cols-2 gap-3 md:grid-cols-4">
        {cards.map((c) => (
          <div key={c.label} className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4">
            <div className="text-[12px] text-[var(--text-secondary)]">{c.label}</div>
            <div className="flex items-baseline gap-1.5">
              <span className={`mono text-xl font-medium ${c.accent ? "text-[var(--accent)]" : ""}`}>{c.value}</span>
              {c.sub ? <span className="text-[12px] text-[var(--text-tertiary)]">{c.sub}</span> : null}
            </div>
          </div>
        ))}
      </div>
      <div className="mb-4 text-[11px] text-[var(--text-tertiary)]">
        fonte: {offline ? "API offline" : s?.provenance ?? "carregando…"}
      </div>
    </>
  );
}
