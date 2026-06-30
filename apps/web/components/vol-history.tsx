"use client";

import { useEffect, useRef, useState } from "react";

type Pt = { date: string; iv: number | null; rv: number | null };
type Hist = { ticker: string; points: Pt[]; iv_rank: number | null; provenance: string };

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const pct = (v: number | null) => (v == null ? "—" : `${(v * 100).toFixed(0)}%`);

export function VolHistory({ ticker }: { ticker: string }) {
  const [h, setH] = useState<Hist | null>(null);
  const [hi, setHi] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    let alive = true;
    fetch(`${API}/history/${ticker}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => alive && setH(d))
      .catch(() => alive && setH(null));
    return () => {
      alive = false;
    };
  }, [ticker]);

  if (!h || h.points.length < 5) return null;
  const pts = h.points;
  const vals = pts.flatMap((p) => [p.iv, p.rv]).filter((x): x is number => x != null);
  if (!vals.length) return null;
  const yLo = Math.min(...vals) * 0.92;
  const yHi = Math.max(...vals) * 1.08;
  const W = 760, H = 200, padL = 36, padR = 10, padT = 12, padB = 22;
  const x = (i: number) => padL + (i / (pts.length - 1)) * (W - padL - padR);
  const y = (v: number) => padT + (1 - (v - yLo) / (yHi - yLo)) * (H - padT - padB);
  const path = (key: "iv" | "rv") => {
    let d = "", pen = false;
    pts.forEach((p, i) => {
      const v = p[key];
      if (v == null) { pen = false; return; }
      d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)} `;
      pen = true;
    });
    return d.trim();
  };
  const last = pts[pts.length - 1];
  const gridYs = [yLo + (yHi - yLo) * 0.25, yLo + (yHi - yLo) * 0.5, yLo + (yHi - yLo) * 0.75];
  const rank = h.iv_rank;
  const rankColor = rank == null ? "var(--text-tertiary)" : rank >= 50 ? "var(--accent)" : "var(--up)";

  return (
    <div className="mb-4 rounded-xl border border-[var(--border-subtle)] p-4">
      <div className="mb-1 flex items-center justify-between">
        <div className="text-[12px] text-[var(--text-secondary)]">
          Volatilidade — <span style={{ color: "var(--accent)" }}>IV implícita</span> vs{" "}
          <span style={{ color: "var(--text-primary)" }}>RV realizada</span> · {pts.length} pregões
        </div>
        <div className="flex items-center gap-3 text-[12px]">
          <span className="text-[var(--text-tertiary)]">IV {pct(last.iv)} · RV {pct(last.rv)}</span>
          {rank != null ? (
            <span className="rounded px-2 py-0.5 mono text-[11px]" style={{ background: "color-mix(in oklch, " + rankColor + " 16%, transparent)", color: rankColor }}>
              IV Rank {rank.toFixed(0)}
            </span>
          ) : null}
        </div>
      </div>
      <div className="relative">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${W} ${H}`}
          className="w-full"
          style={{ height: "auto" }}
          role="img"
          aria-label={`Histórico de IV e RV de ${ticker}`}
          onMouseMove={(e) => {
            const r = svgRef.current?.getBoundingClientRect();
            if (!r) return;
            const fx = (e.clientX - r.left) / r.width;
            setHi(Math.max(0, Math.min(pts.length - 1, Math.round(fx * (pts.length - 1)))));
          }}
          onMouseLeave={() => setHi(null)}
        >
          {gridYs.map((gv, i) => (
            <g key={i}>
              <line x1={padL} x2={W - padR} y1={y(gv)} y2={y(gv)} stroke="var(--border-subtle)" strokeWidth="0.5" />
              <text x={padL - 6} y={y(gv) + 3} textAnchor="end" fontSize="9" fill="var(--text-tertiary)">{(gv * 100).toFixed(0)}%</text>
            </g>
          ))}
          <path d={path("rv")} fill="none" stroke="var(--text-secondary)" strokeWidth="1.2" opacity="0.7" />
          <path d={path("iv")} fill="none" stroke="var(--accent)" strokeWidth="1.6" />
          {hi != null ? (
            <g>
              <line x1={x(hi)} x2={x(hi)} y1={padT} y2={H - padB} stroke="var(--accent)" strokeWidth="0.6" opacity="0.5" />
              {pts[hi].rv != null ? <circle cx={x(hi)} cy={y(pts[hi].rv!)} r="2.4" fill="var(--text-secondary)" /> : null}
              {pts[hi].iv != null ? <circle cx={x(hi)} cy={y(pts[hi].iv!)} r="2.6" fill="var(--accent)" /> : null}
            </g>
          ) : null}
          <text x={padL} y={H - 6} fontSize="9" fill="var(--text-tertiary)">{pts[0].date}</text>
          <text x={W - padR} y={H - 6} textAnchor="end" fontSize="9" fill="var(--text-tertiary)">{last.date}</text>
        </svg>
        {hi != null ? (
          <div
            className="pointer-events-none absolute top-0 rounded-lg border px-2.5 py-1.5 text-[11px]"
            style={{
              left: `${Math.min(92, Math.max(8, (x(hi) / W) * 100))}%`,
              transform: "translateX(-50%)",
              background: "var(--bg-elevated)",
              borderColor: "var(--border-subtle)",
              boxShadow: "0 8px 20px -8px rgba(0,0,0,.6)",
            }}
          >
            <div className="mono mb-0.5 text-[var(--text-tertiary)]">{pts[hi].date}</div>
            <div className="flex gap-3">
              <span style={{ color: "var(--accent)" }}>IV {pct(pts[hi].iv)}</span>
              <span style={{ color: "var(--text-secondary)" }}>RV {pct(pts[hi].rv)}</span>
            </div>
          </div>
        ) : null}
      </div>
      <div className="mt-1 text-[11px] text-[var(--text-tertiary)]">
        IV Rank = posição da IV de hoje na faixa min–max da janela · fonte: {h.provenance}
      </div>
    </div>
  );
}
