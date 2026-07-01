"use client";

import { useEffect, useState } from "react";

type Name = { ticker: string; n: number; trades: number; sharpe_cond: number; sharpe_uncond: number; hit_rate: number };
type Resp = {
  ticker: string;
  available: boolean;
  n_names?: number;
  pooled_days?: number;
  pooled_sharpe_cond?: number;
  pooled_sharpe_uncond?: number;
  deflated_sharpe?: number;
  significant?: boolean;
  adds_value_vs_uncond?: boolean;
  equity_curve?: number[] | null;
  per_name?: Name[];
  verdict?: string;
  note?: string;
};

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

export function EdgeBacktest({ ticker }: { ticker: string }) {
  const [d, setD] = useState<Resp | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset while refetching per ticker
    setLoading(true);
    fetch(`${API}/edge-backtest/${ticker}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => alive && (setD(j), setLoading(false)))
      .catch(() => alive && (setD(null), setLoading(false)));
    return () => {
      alive = false;
    };
  }, [ticker]);

  const head = (
    <div className="mb-1 flex items-center gap-2">
      <span className="text-[12px] font-medium text-[var(--text-secondary)]">Backtest do edge (gate)</span>
      <span className="rounded px-1.5 py-0.5 text-[10px]" style={{ background: "color-mix(in oklch, var(--accent) 14%, transparent)", color: "var(--accent)" }}>
        o sinal de VRP sobrevive à deflação?
      </span>
    </div>
  );

  if (loading) return <div className="mt-4 rounded-xl border border-[var(--border-subtle)] p-4">{head}<p className="text-[11.5px] text-[var(--text-tertiary)]">rodando o walk-forward no universo…</p></div>;
  if (!d) return null;
  if (!d.available) {
    return <div className="mt-4 rounded-xl border border-[var(--border-subtle)] p-4">{head}<p className="text-[11.5px] text-[var(--text-tertiary)]">{d.note ?? "universo insuficiente para o backtest."}</p></div>;
  }

  const sig = !!d.significant;
  const col = sig ? "var(--up)" : "#d99a2b";
  const curve = d.equity_curve ?? [];
  const W = 720, H = 120, padL = 30, padR = 10, padT = 10, padB = 16;
  let svg: React.ReactNode = null;
  if (curve.length > 3) {
    const lo = Math.min(0, ...curve), hi = Math.max(0, ...curve);
    const x = (i: number) => padL + (i / (curve.length - 1)) * (W - padL - padR);
    const y = (v: number) => padT + (1 - (v - lo) / (hi - lo || 1)) * (H - padT - padB);
    const line = curve.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
    svg = (
      <svg viewBox={`0 0 ${W} ${H}`} className="mt-2 w-full" style={{ height: "auto" }} role="img" aria-label={`Curva de equity do edge de ${ticker}`}>
        <line x1={padL} x2={W - padR} y1={y(0)} y2={y(0)} stroke="var(--border-subtle)" strokeWidth="0.6" strokeDasharray="4 3" />
        <text x={padL - 3} y={y(0) + 3} textAnchor="end" fontSize="8" fill="var(--text-tertiary)">0</text>
        <path d={line} fill="none" stroke="var(--accent)" strokeWidth="1.5" />
        <text x={padL} y={H - 2} fontSize="8" fill="var(--text-tertiary)">P&amp;L acumulado do sinal em {ticker} (proxy de prêmio de vol)</text>
      </svg>
    );
  }

  return (
    <div className="mt-4 rounded-xl border border-[var(--border-subtle)] p-4">
      {head}
      <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1">
        <span className="rounded-md px-2 py-0.5 text-[11px] font-medium" style={{ background: `color-mix(in oklch, ${col} 16%, transparent)`, color: col }}>
          {sig ? "CONFIRMADO pelo gate" : "NÃO confirmado pelo gate"}
        </span>
        <span className="text-[11px] text-[var(--text-tertiary)]">Deflated Sharpe <b className="mono" style={{ color: "var(--text-primary)" }}>{d.deflated_sharpe}</b> <span className="text-[10px]">(P Sharpe&gt;0; &gt;0.95 = confirma)</span></span>
        <span className="text-[11px] text-[var(--text-tertiary)]">Sharpe condicional <b className="mono" style={{ color: "var(--text-primary)" }}>{d.pooled_sharpe_cond}</b> vs incondicional <b className="mono">{d.pooled_sharpe_uncond}</b> {d.adds_value_vs_uncond ? <span style={{ color: "var(--up)" }}>(o físico agrega valor)</span> : null}</span>
      </div>
      {svg}
      <p className="mt-2 text-[11px] leading-relaxed text-[var(--text-tertiary)]">
        Walk-forward de “vender vol quando a nossa física diz que está cara” (VRP&gt;0) em {d.n_names} nomes líquidos, {d.pooled_days} dias-pool. O
        <b> Deflated Sharpe</b> (López de Prado) desconta o multiple-testing sobre o universo. {sig
          ? "O sinal sobrevive — o edge é estatisticamente real."
          : "O condicionamento pelo físico agrega valor sobre vender vol sempre, mas o sinal ainda NÃO sobrevive à deflação com ~1 ano de dado — registrado honestamente, como PDV e HARX. O gate está fazendo o trabalho: não vendemos um edge que ele não confirmou."}
        {" "}Proxy de prêmio de vol (não P&amp;L de opção delta-hedgeada, sem custos). Análise, não recomendação.
      </p>
    </div>
  );
}
