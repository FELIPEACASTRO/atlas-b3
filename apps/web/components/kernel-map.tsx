"use client";

import { useEffect, useState } from "react";

type Pt = { moneyness: number; strike: number; m: number };
type Shape = { slope: number; puzzle: boolean; m_min: number; m_max: number };
type Resp = {
  ticker: string;
  spot: number | null;
  dte?: number;
  shape?: Shape;
  kernel: Pt[] | null;
  note?: string;
};

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

export function KernelMap({ ticker }: { ticker: string }) {
  const [d, setD] = useState<Resp | null>(null);

  useEffect(() => {
    let alive = true;
    fetch(`${API}/kernel/${ticker}`)
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
        <span className="text-[12px] font-medium text-[var(--text-secondary)]">Pricing Kernel (SDF)</span>
        <span className="rounded px-1.5 py-0.5 text-[10px]" style={{ background: "color-mix(in oklch, var(--accent) 14%, transparent)", color: "var(--accent)" }}>
          razão risco-neutra ÷ física — preço do risco por estado
        </span>
      </div>
      {inner}
    </div>
  );

  if (!d.kernel || d.kernel.length < 3 || !d.shape) {
    return wrap(<p className="text-[11.5px] text-[var(--text-tertiary)]">{d.note ?? "sem pricing kernel para este ativo."}</p>);
  }

  const pts = d.kernel;
  const sh = d.shape;
  const W = 720, H = 240, padL = 30, padR = 12, padT = 16, padB = 26;
  const mnyLo = pts[0].moneyness, mnyHi = pts[pts.length - 1].moneyness;
  const yMax = Math.max(1.6, sh.m_max * 1.06);
  const x = (m: number) => padL + ((m - mnyLo) / (mnyHi - mnyLo)) * (W - padL - padR);
  const y = (v: number) => padT + (1 - v / yMax) * (H - padT - padB);
  const path = pts.map((p, i) => `${i ? "L" : "M"}${x(p.moneyness).toFixed(1)},${y(p.m).toFixed(1)}`).join(" ");
  // área entre a curva e M=1: acima = estado caro (prêmio de risco)
  const area = `M${x(pts[0].moneyness).toFixed(1)},${y(1).toFixed(1)} ` +
    pts.map((p) => `L${x(p.moneyness).toFixed(1)},${y(p.m).toFixed(1)}`).join(" ") +
    ` L${x(pts[pts.length - 1].moneyness).toFixed(1)},${y(1).toFixed(1)} Z`;

  return wrap(
    <>
      <div className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-[var(--text-tertiary)]">
        <span>inclinação <b className="mono" style={{ color: sh.slope < 0 ? "var(--up)" : "var(--down)" }}>{sh.slope > 0 ? "+" : ""}{sh.slope}</b> <span className="text-[10px]">({sh.slope < 0 ? "aversão a risco padrão" : "anômala"})</span></span>
        {sh.puzzle ? <span className="rounded px-1.5 py-0.5 text-[10px]" style={{ background: "color-mix(in oklch, var(--down) 16%, transparent)", color: "var(--down)" }}>pricing-kernel puzzle (U)</span> : null}
        {d.dte ? <span>· horizonte {d.dte}d</span> : null}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: "auto" }} role="img" aria-label={`Pricing kernel de ${ticker}`}>
        {[0.5, 1.0, 1.5, 2.0].filter((g) => g <= yMax).map((g) => (
          <g key={g}>
            <line x1={padL} x2={W - padR} y1={y(g)} y2={y(g)} stroke="var(--border-subtle)" strokeWidth={g === 1 ? 1 : 0.5} strokeDasharray={g === 1 ? "4 3" : undefined} />
            <text x={padL - 4} y={y(g) + 3} textAnchor="end" fontSize="9" fill={g === 1 ? "var(--text-secondary)" : "var(--text-tertiary)"}>{g.toFixed(1)}</text>
          </g>
        ))}
        <text x={W - padR} y={y(1) - 4} textAnchor="end" fontSize="9" fill="var(--text-secondary)">M=1 (sem prêmio)</text>
        <line x1={x(1)} x2={x(1)} y1={padT} y2={H - padB} stroke="var(--text-tertiary)" strokeWidth="0.6" strokeDasharray="3 3" />
        <text x={x(1)} y={H - padB + 12} textAnchor="middle" fontSize="9" fill="var(--text-tertiary)">spot</text>
        <path d={area} fill="color-mix(in oklch, var(--accent) 11%, transparent)" stroke="none" />
        <path d={path} fill="none" stroke="var(--accent)" strokeWidth="1.8" />
        <text x={padL} y={H - padB + 12} fontSize="9" fill="var(--text-tertiary)">{`${(mnyLo * 100 - 100).toFixed(0)}%`}</text>
        <text x={W - padR} y={H - padB + 12} textAnchor="end" fontSize="9" fill="var(--text-tertiary)">{`+${(mnyHi * 100 - 100).toFixed(0)}%`}</text>
      </svg>
      <div className="mt-2 rounded-lg px-3 py-2 text-[11.5px] leading-relaxed" style={{ background: "color-mix(in oklch, var(--accent) 7%, transparent)", color: "var(--text-secondary)" }}>
        <b style={{ color: "var(--text-primary)" }}>O que isso diz: </b>
        M(preço) é quanto o mercado paga por R$1 de payoff em cada desfecho, dividido pela probabilidade real (nossa densidade calibrada).
        Onde <b>M &gt; 1</b>, aquele estado é <b style={{ color: "var(--accent)" }}>caro</b> — o mercado embute prêmio de risco (tipicamente a queda: seguro contra crash).
        {sh.puzzle
          ? <> Aqui o kernel sobe também na ponta de alta (forma em U): é o <b>pricing-kernel puzzle</b> — prêmio nas duas caudas, que a aversão a risco padrão não explica.</>
          : <> A forma decrescente reflete aversão a risco padrão (estados de queda mais caros).</>}
        {" "}É o SDF empírico — só construível porque temos a densidade física validada. Análise, não recomendação.
      </div>
    </>,
  );
}
