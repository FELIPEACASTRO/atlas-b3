"use client";

import { useEffect, useState } from "react";

type Expiry = { venc: string; dte: number; atm_iv: number };
type Point = { venc: string; strike: number; moneyness: number; iv: number };
type Surf = { ticker: string; spot: number | null; expiries: Expiry[]; points: Point[]; provenance: string };

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const EDGES = [0.8, 0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15, 1.2]; // 8 moneyness buckets
// thermal ramp: low IV cool (blue), high IV hot (red) — the vol-surface convention
const thermal = (t: number) => `oklch(0.66 0.15 ${250 - Math.max(0, Math.min(1, t)) * 225})`;

export function IvSurface({ ticker }: { ticker: string }) {
  const [s, setS] = useState<Surf | null>(null);

  useEffect(() => {
    let alive = true;
    fetch(`${API}/surface/${ticker}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => alive && setS(d))
      .catch(() => alive && setS(null));
    return () => { alive = false; };
  }, [ticker]);

  if (!s || s.expiries.length < 2 || !s.spot) return null;

  const exps = s.expiries.slice(0, 9);
  const grid = exps.map((e) => {
    const pts = s.points.filter((p) => p.venc === e.venc);
    return EDGES.slice(0, -1).map((lo, ci) => {
      const inb = pts.filter((p) => p.moneyness >= lo && p.moneyness < EDGES[ci + 1]).map((p) => p.iv);
      return inb.length ? inb.reduce((a, b) => a + b, 0) / inb.length : null;
    });
  });
  const allIv = grid.flat().filter((x): x is number => x != null);
  if (!allIv.length) return null;
  const lo = Math.min(...allIv), hi = Math.max(...allIv);

  // term-structure mini-chart
  const tW = 300, tH = 132, tp = 22;
  const dtes = exps.map((e) => e.dte);
  const minD = Math.min(...dtes), maxD = Math.max(...dtes);
  const tiv = exps.map((e) => e.atm_iv);
  const tLo = Math.min(...tiv) * 0.94, tHi = Math.max(...tiv) * 1.06;
  const tx = (d: number) => tp + ((d - minD) / (maxD - minD || 1)) * (tW - 2 * tp);
  const ty = (v: number) => tp + (1 - (v - tLo) / (tHi - tLo || 1)) * (tH - 2 * tp);
  const tPath = exps.map((e, i) => `${i ? "L" : "M"}${tx(e.dte).toFixed(1)},${ty(e.atm_iv).toFixed(1)}`).join(" ");

  return (
    <div className="mb-4 rounded-xl border border-[var(--border-subtle)] p-4">
      <div className="mb-3 text-[12px] text-[var(--text-secondary)]">
        Superfície de volatilidade — IV por <span style={{ color: "var(--text-primary)" }}>moneyness</span> × <span style={{ color: "var(--text-primary)" }}>vencimento</span>
      </div>
      <div className="grid gap-5 lg:grid-cols-[300px_1fr]">
        <div>
          <div className="mb-1 text-[11px] text-[var(--text-tertiary)]">Estrutura a termo (ATM IV vs prazo)</div>
          <svg viewBox={`0 0 ${tW} ${tH}`} className="w-full" style={{ height: "auto" }}>
            {[0.25, 0.5, 0.75].map((f, i) => {
              const v = tLo + (tHi - tLo) * f;
              return (
                <g key={i}>
                  <line x1={tp} x2={tW - tp} y1={ty(v)} y2={ty(v)} stroke="var(--border-subtle)" strokeWidth="0.5" />
                  <text x={tp - 4} y={ty(v) + 3} textAnchor="end" fontSize="8" fill="var(--text-tertiary)">{(v * 100).toFixed(0)}%</text>
                </g>
              );
            })}
            <path d={tPath} fill="none" stroke="var(--accent)" strokeWidth="1.6" />
            {exps.map((e, i) => <circle key={i} cx={tx(e.dte)} cy={ty(e.atm_iv)} r="2" fill="var(--accent)" />)}
            <text x={tp} y={tH - 5} fontSize="8" fill="var(--text-tertiary)">{minD}d</text>
            <text x={tW - tp} y={tH - 5} textAnchor="end" fontSize="8" fill="var(--text-tertiary)">{maxD}d</text>
          </svg>
        </div>

        <div>
          <div className="mb-1 text-[11px] text-[var(--text-tertiary)]">Smile × prazo · cor = IV (frio→quente)</div>
          <div className="overflow-x-auto">
            <table className="w-full border-separate" style={{ borderSpacing: "2px" }}>
              <thead>
                <tr>
                  <th className="px-1 text-right text-[9px] font-normal text-[var(--text-tertiary)]">prazo \ K/S</th>
                  {EDGES.slice(0, -1).map((lo2, ci) => (
                    <th key={ci} className="mono text-center text-[9px] font-normal text-[var(--text-tertiary)]">
                      {((lo2 + EDGES[ci + 1]) / 2).toFixed(2)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {exps.map((e, ri) => (
                  <tr key={e.venc}>
                    <td className="mono pr-1 text-right text-[10px] text-[var(--text-tertiary)]">{e.dte}d</td>
                    {grid[ri].map((iv, ci) => (
                      <td
                        key={ci}
                        title={iv != null ? `${e.dte}d · K/S ${((EDGES[ci] + EDGES[ci + 1]) / 2).toFixed(2)} · IV ${(iv * 100).toFixed(0)}%` : ""}
                        className="mono h-7 rounded text-center text-[9px]"
                        style={{
                          background: iv != null ? thermal((iv - lo) / (hi - lo || 1)) : "var(--bg-surface)",
                          color: iv != null ? "oklch(0.18 0.02 265)" : "transparent",
                        }}
                      >
                        {iv != null ? (iv * 100).toFixed(0) : ""}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-2 flex items-center gap-2 text-[10px] text-[var(--text-tertiary)]">
            <span>{(lo * 100).toFixed(0)}%</span>
            <span className="h-2 w-24 rounded" style={{ background: `linear-gradient(90deg, ${thermal(0)}, ${thermal(0.5)}, ${thermal(1)})` }} />
            <span>{(hi * 100).toFixed(0)}%</span>
            <span className="ml-auto">K/S = strike ÷ spot · {s.points.length} séries</span>
          </div>
        </div>
      </div>
    </div>
  );
}
