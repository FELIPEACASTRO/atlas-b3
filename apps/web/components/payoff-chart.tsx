"use client";

import { useEffect, useRef, useState } from "react";

type Pt = { shock_pct: number; pnl_now: number; pnl_expiry: number };
type Payoff = { points: Pt[]; provenance: string };

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const brl0 = (n: number) =>
  (n >= 0 ? "+" : "") + n.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });

export function PayoffChart() {
  const [d, setD] = useState<Payoff | null>(null);
  const [hi, setHi] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    let alive = true;
    fetch(`${API}/portfolio/payoff`)
      .then((r) => (r.ok ? r.json() : null))
      .then((x) => alive && setD(x))
      .catch(() => alive && setD(null));
    return () => { alive = false; };
  }, []);

  const pts = d?.points ?? [];
  if (pts.length < 3) return null;
  const ys = pts.flatMap((p) => [p.pnl_now, p.pnl_expiry]);
  const yLo = Math.min(...ys, 0), yHi = Math.max(...ys, 0);
  const W = 760, H = 240, padL = 52, padR = 12, padT = 14, padB = 24;
  const x = (i: number) => padL + (i / (pts.length - 1)) * (W - padL - padR);
  const y = (v: number) => padT + (1 - (v - yLo) / (yHi - yLo || 1)) * (H - padT - padB);
  const line = (k: "pnl_now" | "pnl_expiry") => pts.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p[k]).toFixed(1)}`).join(" ");
  const zeroY = y(0);
  const hp = hi != null ? pts[hi] : null;
  // breakevens: where the at-expiry P&L crosses zero
  const bes: number[] = [];
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i - 1].pnl_expiry, b = pts[i].pnl_expiry;
    if ((a <= 0 && b > 0) || (a >= 0 && b < 0)) bes.push(i);
  }

  return (
    <div className="mb-4 rounded-xl border border-[var(--border-subtle)] p-4">
      <div className="mb-1 flex items-center justify-between">
        <div className="text-[12px] text-[var(--text-secondary)]">
          Payoff da carteira — <span style={{ color: "var(--accent)" }}>no vencimento</span> vs{" "}
          <span style={{ color: "var(--text-secondary)" }}>hoje</span> · P&amp;L por movimento do ativo
        </div>
        {hp ? (
          <div className="mono text-[12px] text-[var(--text-tertiary)]">
            {hp.shock_pct > 0 ? "+" : ""}{hp.shock_pct}% · venc {brl0(hp.pnl_expiry)} · hoje {brl0(hp.pnl_now)}
          </div>
        ) : null}
      </div>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        style={{ height: "auto" }}
        role="img"
        aria-label="Diagrama de payoff da carteira"
        onMouseMove={(e) => {
          const r = svgRef.current?.getBoundingClientRect();
          if (!r) return;
          const fx = (e.clientX - r.left) / r.width;
          setHi(Math.max(0, Math.min(pts.length - 1, Math.round(fx * (pts.length - 1)))));
        }}
        onMouseLeave={() => setHi(null)}
      >
        <line x1={padL} x2={W - padR} y1={zeroY} y2={zeroY} stroke="var(--border-subtle)" strokeWidth="1" />
        <text x={padL - 6} y={zeroY + 3} textAnchor="end" fontSize="9" fill="var(--text-tertiary)">R$0</text>
        <text x={padL - 6} y={y(yHi) + 7} textAnchor="end" fontSize="9" fill="var(--text-tertiary)">{brl0(yHi)}</text>
        <text x={padL - 6} y={y(yLo) - 2} textAnchor="end" fontSize="9" fill="var(--text-tertiary)">{brl0(yLo)}</text>
        {bes.map((i, k) => (
          <line key={k} x1={x(i)} x2={x(i)} y1={padT} y2={H - padB} stroke="var(--up)" strokeWidth="0.6" strokeDasharray="3 3" opacity="0.6" />
        ))}
        <path d={line("pnl_now")} fill="none" stroke="var(--text-secondary)" strokeWidth="1.2" opacity="0.65" />
        <path d={line("pnl_expiry")} fill="none" stroke="var(--accent)" strokeWidth="1.8" />
        {hi != null ? (
          <g>
            <line x1={x(hi)} x2={x(hi)} y1={padT} y2={H - padB} stroke="var(--accent)" strokeWidth="0.6" opacity="0.5" />
            <circle cx={x(hi)} cy={y(pts[hi].pnl_expiry)} r="2.8" fill="var(--accent)" />
            <circle cx={x(hi)} cy={y(pts[hi].pnl_now)} r="2.2" fill="var(--text-secondary)" />
          </g>
        ) : null}
        <text x={padL} y={H - 7} fontSize="9" fill="var(--text-tertiary)">{pts[0].shock_pct}%</text>
        <text x={(padL + W - padR) / 2} y={H - 7} textAnchor="middle" fontSize="9" fill="var(--text-tertiary)">0%</text>
        <text x={W - padR} y={H - 7} textAnchor="end" fontSize="9" fill="var(--text-tertiary)">+{pts[pts.length - 1].shock_pct}%</text>
      </svg>
      <div className="mt-1 text-[11px] text-[var(--text-tertiary)]">
        linha tracejada = breakeven no vencimento · P&amp;L vs marca atual · fonte: {d?.provenance}
      </div>
    </div>
  );
}
