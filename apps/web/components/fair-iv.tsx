"use client";

import { useEffect, useState } from "react";

type Pt = { moneyness: number; strike: number; iv_market: number; iv_fair: number; gap: number };
type Resp = {
  ticker: string;
  spot: number | null;
  dte?: number;
  smile: Pt[] | null;
  level_gap?: number;
  skew_premium?: number;
  put_wing_strike?: number;
  note?: string;
};

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";
const vp = (v: number) => `${(v * 100).toFixed(1)}%`;

export function FairIv({ ticker }: { ticker: string }) {
  const [d, setD] = useState<Resp | null>(null);

  useEffect(() => {
    let alive = true;
    fetch(`${API}/fair-iv/${ticker}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => alive && setD(j))
      .catch(() => alive && setD(null));
    return () => {
      alive = false;
    };
  }, [ticker]);

  if (!d) return null;

  const wrap = (inner: React.ReactNode) => (
    <div className="mb-4 rounded-xl border border-[var(--border-subtle)] p-4">
      <div className="mb-1 flex items-center gap-2">
        <span className="text-[12px] font-medium text-[var(--text-secondary)]">Fair IV</span>
        <span className="rounded px-1.5 py-0.5 text-[10px]" style={{ background: "color-mix(in oklch, var(--accent) 14%, transparent)", color: "var(--accent)" }}>
          smile de mercado vs vol física justa — VRP em vol points
        </span>
      </div>
      {inner}
    </div>
  );

  if (!d.smile || d.smile.length < 3) {
    return wrap(<p className="text-[11.5px] text-[var(--text-tertiary)]">{d.note ?? "sem fair IV para este ativo."}</p>);
  }

  const pts = d.smile;
  const W = 720, H = 240, padL = 34, padR = 12, padT = 16, padB = 26;
  const mnyLo = pts[0].moneyness, mnyHi = pts[pts.length - 1].moneyness;
  const ivs = pts.flatMap((p) => [p.iv_market, p.iv_fair]);
  const yLo = Math.max(0, Math.min(...ivs) - 0.03), yHi = Math.max(...ivs) + 0.03;
  const x = (m: number) => padL + ((m - mnyLo) / (mnyHi - mnyLo)) * (W - padL - padR);
  const y = (v: number) => padT + (1 - (v - yLo) / (yHi - yLo)) * (H - padT - padB);
  const lineMkt = pts.map((p, i) => `${i ? "L" : "M"}${x(p.moneyness).toFixed(1)},${y(p.iv_market).toFixed(1)}`).join(" ");
  const fairY = y(pts[0].iv_fair);
  const gapArea =
    pts.map((p, i) => `${i ? "L" : "M"}${x(p.moneyness).toFixed(1)},${y(p.iv_market).toFixed(1)}`).join(" ") +
    ` L${x(pts[pts.length - 1].moneyness).toFixed(1)},${fairY.toFixed(1)} L${x(pts[0].moneyness).toFixed(1)},${fairY.toFixed(1)} Z`;

  return wrap(
    <>
      <div className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-[var(--text-tertiary)]">
        <span className="flex items-center gap-1.5"><i className="inline-block h-1.5 w-3 rounded-full" style={{ background: "var(--accent)" }} /> IV de mercado</span>
        <span className="flex items-center gap-1.5"><i className="inline-block h-1.5 w-3 rounded-full" style={{ background: "var(--text-primary)" }} /> vol física justa {vp(pts[0].iv_fair)}</span>
        {d.level_gap != null ? <span>· VRP de nível <b className="mono" style={{ color: "var(--accent)" }}>{(d.level_gap * 100).toFixed(1)}pp</b></span> : null}
        {d.skew_premium != null ? <span>· prêmio de skew <b className="mono" style={{ color: "var(--accent)" }}>{(d.skew_premium * 100).toFixed(1)}pp</b> (put)</span> : null}
        {d.dte ? <span>· {d.dte}d</span> : null}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: "auto" }} role="img" aria-label={`Fair IV de ${ticker}`}>
        {[0.25, 0.5, 0.75].map((f) => {
          const v = yLo + f * (yHi - yLo);
          return (
            <g key={f}>
              <line x1={padL} x2={W - padR} y1={y(v)} y2={y(v)} stroke="var(--border-subtle)" strokeWidth="0.5" />
              <text x={padL - 4} y={y(v) + 3} textAnchor="end" fontSize="9" fill="var(--text-tertiary)">{vp(v)}</text>
            </g>
          );
        })}
        <path d={gapArea} fill="color-mix(in oklch, var(--accent) 11%, transparent)" stroke="none" />
        <line x1={padL} x2={W - padR} y1={fairY} y2={fairY} stroke="var(--text-primary)" strokeWidth="1.4" strokeDasharray="5 3" />
        <path d={lineMkt} fill="none" stroke="var(--accent)" strokeWidth="1.8" />
        <line x1={x(1)} x2={x(1)} y1={padT} y2={H - padB} stroke="var(--text-tertiary)" strokeWidth="0.6" strokeDasharray="3 3" />
        <text x={x(1)} y={H - padB + 12} textAnchor="middle" fontSize="9" fill="var(--text-tertiary)">spot</text>
        <text x={padL} y={H - padB + 12} fontSize="9" fill="var(--text-tertiary)">{`${(mnyLo * 100 - 100).toFixed(0)}%`}</text>
        <text x={W - padR} y={H - padB + 12} textAnchor="end" fontSize="9" fill="var(--text-tertiary)">{`+${(mnyHi * 100 - 100).toFixed(0)}%`}</text>
      </svg>
      <div className="mt-2 rounded-lg px-3 py-2 text-[11.5px] leading-relaxed" style={{ background: "color-mix(in oklch, var(--accent) 7%, transparent)", color: "var(--text-secondary)" }}>
        <b style={{ color: "var(--text-primary)" }}>O que isso diz: </b>
        a curva é a vol que o mercado cobra por strike; a linha tracejada é a vol <b>justa</b> pela nossa densidade física.
        A área é o prêmio de vol (VRP) por strike — no ATM é o nível; nas asas, o skew.
        {" "}Nossa física é <b>simétrica</b>, então a linha justa é plana: o gap de nível é leitura limpa; o skew do gap indica o prêmio de skew do mercado (que pode embutir skew físico real que não modelamos). Análise, não recomendação.
      </div>
    </>,
  );
}
