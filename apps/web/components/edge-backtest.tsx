"use client";

import { useEffect, useState } from "react";

type Name = { ticker: string; n: number; trades: number; sharpe_cond: number; sharpe_uncond: number; hit_rate: number };
type Resp = {
  ticker: string;
  available: boolean;
  n_names?: number;
  portfolio_days?: number;
  portfolio_sharpe_cond?: number;
  portfolio_sharpe_uncond?: number;
  deflated_sharpe?: number;
  significant?: boolean;
  borderline?: boolean;
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
  const bl = !!d.borderline;
  const col = sig ? "var(--up)" : bl ? "#d99a2b" : "var(--down)";
  const bandLabel = sig ? "CONFIRMADO pelo gate" : bl ? "LIMÍTROFE (quase confirma)" : "NÃO confirmado pelo gate";
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
          {bandLabel}
        </span>
        <span className="text-[11px] text-[var(--text-tertiary)]">Deflated Sharpe <b className="mono" style={{ color: "var(--text-primary)" }}>{d.deflated_sharpe}</b> <span className="text-[10px]">(P Sharpe&gt;0; &gt;0.95 = confirma)</span></span>
        <span className="text-[11px] text-[var(--text-tertiary)]">Sharpe portfólio <b className="mono" style={{ color: "var(--text-primary)" }}>{d.portfolio_sharpe_cond}</b> vs vender-sempre <b className="mono">{d.portfolio_sharpe_uncond}</b> {d.adds_value_vs_uncond ? <span style={{ color: "var(--up)" }}>(condicionar ajuda)</span> : null}</span>
      </div>
      {svg}
      <p className="mt-2 text-[11px] leading-relaxed text-[var(--text-tertiary)]">
        Walk-forward de “vender vol quando a nossa física diz que está cara” (VRP&gt;0) em {d.n_names} nomes líquidos; o
        <b> Deflated Sharpe</b> (López de Prado) é aplicado ao <b>portfólio</b> equal-weight ({d.portfolio_days} dias), o objeto negociável — desconta o multiple-testing sobre os nomes. {sig
          ? "O prêmio sobrevive — o edge é estatisticamente real."
          : bl
            ? "O prêmio é quase-significativo (limítrofe): com ~1 ano a evidência é sugestiva, não conclusiva. Honesto: não afirmamos um edge provado que o dado ainda não sustenta."
            : "O prêmio não sobrevive à deflação — registrado honestamente, como PDV e HARX."}
        {" "}Proxy grosseiro de prêmio de variância (não P&amp;L delta-hedgeado, sem custos; subestima o risco de cauda). Análise, não recomendação.
      </p>
    </div>
  );
}
