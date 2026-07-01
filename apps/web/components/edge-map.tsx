"use client";

import { useEffect, useState } from "react";

type Pt = { moneyness: number; strike: number; p_market: number; p_physical: number; edge: number };
type Resp = {
  ticker: string;
  spot: number | null;
  dte?: number;
  recalibrated?: boolean;
  market_vs_physical?: { iv: number | null; physical: number; market_smile?: { atm_vol: number } | null };
  edge: Pt[] | null;
  note?: string;
};

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";
const pct = (v: number | null | undefined) => (v == null ? "—" : `${(v * 100).toFixed(0)}%`);

export function EdgeMap({ ticker }: { ticker: string }) {
  const [d, setD] = useState<Resp | null>(null);

  useEffect(() => {
    let alive = true;
    fetch(`${API}/edge/${ticker}`)
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
        <span className="text-[12px] font-medium text-[var(--text-secondary)]">Mapa de Prêmio</span>
        <span className="rounded px-1.5 py-0.5 text-[10px]" style={{ background: "color-mix(in oklch, var(--accent) 14%, transparent)", color: "var(--accent)" }}>
          mercado vs nossa densidade calibrada
        </span>
      </div>
      {inner}
    </div>
  );

  if (!d.edge || d.edge.length < 3) {
    return wrap(
      <p className="text-[11.5px] text-[var(--text-tertiary)]">
        {d.note ?? "sem mapa de prêmio para este ativo (cadeia de opções não confiável)."}
      </p>,
    );
  }

  const pts = d.edge;
  const mvp = d.market_vs_physical;
  const W = 720, H = 240, padL = 34, padR = 12, padT = 14, padB = 26;
  const mnyLo = pts[0].moneyness, mnyHi = pts[pts.length - 1].moneyness;
  const x = (m: number) => padL + ((m - mnyLo) / (mnyHi - mnyLo)) * (W - padL - padR);
  const y = (p: number) => padT + (1 - p) * (H - padT - padB);
  const line = (key: "p_market" | "p_physical") =>
    pts.map((p, i) => `${i ? "L" : "M"}${x(p.moneyness).toFixed(1)},${y(p[key]).toFixed(1)}`).join(" ");
  // área do gap (entre as duas curvas)
  const gap =
    pts.map((p, i) => `${i ? "L" : "M"}${x(p.moneyness).toFixed(1)},${y(p.p_market).toFixed(1)}`).join(" ") +
    " " +
    [...pts].reverse().map((p) => `L${x(p.moneyness).toFixed(1)},${y(p.p_physical).toFixed(1)}`).join(" ") +
    " Z";
  const maxEdge = pts.reduce((a, p) => Math.max(a, Math.abs(p.edge)), 0);
  const sell = pts.filter((p) => p.edge > 0.02);
  const buy = pts.filter((p) => p.edge < -0.02);

  return wrap(
    <>
      <div className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-[var(--text-tertiary)]">
        <span className="flex items-center gap-1.5"><i className="inline-block h-1.5 w-3 rounded-full" style={{ background: "var(--accent)" }} /> mercado (risco-neutra) {mvp?.market_smile ? pct(mvp.market_smile.atm_vol) : ""}</span>
        <span className="flex items-center gap-1.5"><i className="inline-block h-1.5 w-3 rounded-full" style={{ background: "var(--text-primary)" }} /> nossa física (calibrada) {mvp ? pct(mvp.physical) : ""}</span>
        {d.dte ? <span>· horizonte {d.dte}d</span> : null}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: "auto" }} role="img" aria-label={`Mapa de prêmio de ${ticker}`}>
        {[0.25, 0.5, 0.75].map((g) => (
          <g key={g}>
            <line x1={padL} x2={W - padR} y1={y(g)} y2={y(g)} stroke="var(--border-subtle)" strokeWidth="0.5" />
            <text x={padL - 5} y={y(g) + 3} textAnchor="end" fontSize="9" fill="var(--text-tertiary)">{pct(g)}</text>
          </g>
        ))}
        <line x1={x(1)} x2={x(1)} y1={padT} y2={H - padB} stroke="var(--text-tertiary)" strokeWidth="0.6" strokeDasharray="3 3" />
        <text x={x(1)} y={H - padB + 12} textAnchor="middle" fontSize="9" fill="var(--text-tertiary)">spot</text>
        <path d={gap} fill="color-mix(in oklch, var(--accent) 12%, transparent)" stroke="none" />
        <path d={line("p_market")} fill="none" stroke="var(--accent)" strokeWidth="1.6" strokeDasharray="4 3" />
        <path d={line("p_physical")} fill="none" stroke="var(--text-primary)" strokeWidth="1.6" />
        <text x={padL} y={H - padB + 12} fontSize="9" fill="var(--text-tertiary)">{`${(mnyLo * 100 - 100).toFixed(0)}%`}</text>
        <text x={W - padR} y={H - padB + 12} textAnchor="end" fontSize="9" fill="var(--text-tertiary)">{`+${(mnyHi * 100 - 100).toFixed(0)}%`}</text>
      </svg>
      <div className="mt-2 rounded-lg px-3 py-2 text-[11.5px] leading-relaxed" style={{ background: "color-mix(in oklch, var(--accent) 7%, transparent)", color: "var(--text-secondary)" }}>
        <b style={{ color: "var(--text-primary)" }}>O que isso diz: </b>
        cada ponto compara <b>P(preço ≤ strike)</b> — o que o mercado precifica (risco-neutra) vs a nossa densidade calibrada.
        {sell.length ? <> Onde a curva do mercado fica <b style={{ color: "var(--accent)" }}>acima</b> da nossa, o <b>put</b> daquele strike está rico → favorece <b>vender</b>.</> : null}
        {buy.length ? <> Onde fica <b>abaixo</b>, a <b>call</b> está rica → vender call / comprar put.</> : null}
        {" "}Maior divergência: <b className="mono">{(maxEdge * 100).toFixed(1)} pp</b>. É a decomposição do prêmio de risco por strike — análise, não recomendação.
      </div>
    </>,
  );
}
