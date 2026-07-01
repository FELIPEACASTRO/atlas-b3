"use client";

import { useEffect, useState } from "react";

type Resp = {
  ticker: string;
  window?: number;
  available: boolean;
  n?: number;
  series?: number[];
  current_p?: number;
  calibrated_now?: boolean;
  ever_broke?: boolean;
  n_breaks?: number;
  last_break_days_ago?: number | null;
  note?: string;
};

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

export function CalibrationHealth({ ticker }: { ticker: string }) {
  const [d, setD] = useState<Resp | null>(null);

  useEffect(() => {
    let alive = true;
    fetch(`${API}/calibration-health/${ticker}`)
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
        <span className="text-[12px] font-medium text-[var(--text-secondary)]">Saúde da calibração</span>
        <span className="rounded px-1.5 py-0.5 text-[10px]" style={{ background: "color-mix(in oklch, var(--accent) 14%, transparent)", color: "var(--accent)" }}>
          a densidade ainda é confiável hoje?
        </span>
      </div>
      {inner}
    </div>
  );

  if (!d.available || !d.series || d.series.length < 3) {
    return wrap(<p className="text-[11.5px] text-[var(--text-tertiary)]">{d.note ?? "histórico curto para monitorar a calibração."}</p>);
  }

  const s = d.series;
  const ok = !!d.calibrated_now;
  const W = 720, H = 84, padL = 26, padR = 10, padT = 8, padB = 14;
  const x = (i: number) => padL + (i / (s.length - 1)) * (W - padL - padR);
  const y = (p: number) => padT + (1 - p) * (H - padT - padB);
  const line = s.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p).toFixed(1)}`).join(" ");
  const col = ok ? "var(--up)" : "var(--down)";

  return wrap(
    <>
      <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1">
        <span className="rounded-md px-2 py-0.5 text-[11px] font-medium" style={{ background: `color-mix(in oklch, ${col} 16%, transparent)`, color: col }}>
          {ok ? "Calibrada agora" : "Descalibrada — modelo perdeu o regime"}
        </span>
        <span className="text-[11px] text-[var(--text-tertiary)]">p-valor atual <b className="mono" style={{ color: "var(--text-primary)" }}>{d.current_p}</b> <span className="text-[10px]">(&gt;0.05 = ok)</span></span>
        <span className="text-[11px] text-[var(--text-tertiary)]">
          {d.last_break_days_ago == null
            ? "sem quebras no histórico"
            : d.last_break_days_ago === 0
              ? <>quebra em curso · {d.n_breaks} episódio{d.n_breaks === 1 ? "" : "s"} no histórico</>
              : <>{d.n_breaks} episódio{d.n_breaks === 1 ? "" : "s"} · última há <b className="mono" style={{ color: "var(--text-secondary)" }}>{d.last_break_days_ago}</b> pregões</>}
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: "auto" }} role="img" aria-label={`Saúde da calibração de ${ticker}`}>
        {[0.05, 0.5, 1.0].map((g) => (
          <g key={g}>
            <line x1={padL} x2={W - padR} y1={y(g)} y2={y(g)} stroke={g === 0.05 ? "var(--down)" : "var(--border-subtle)"} strokeWidth="0.5" strokeDasharray={g === 0.05 ? "4 3" : undefined} />
            <text x={padL - 3} y={y(g) + 3} textAnchor="end" fontSize="8" fill={g === 0.05 ? "var(--down)" : "var(--text-tertiary)"}>{g === 0.05 ? "0.05" : g.toFixed(1)}</text>
          </g>
        ))}
        <path d={line} fill="none" stroke="var(--accent)" strokeWidth="1.4" />
        {s.map((p, i) => (p < 0.05 ? <circle key={i} cx={x(i)} cy={y(p)} r="1.6" fill="var(--down)" /> : null))}
        <text x={padL} y={H - 2} fontSize="8" fill="var(--text-tertiary)">{d.n} pregões</text>
        <text x={W - padR} y={H - 2} textAnchor="end" fontSize="8" fill="var(--text-tertiary)">hoje →</text>
      </svg>
      <p className="mt-2 text-[11px] leading-relaxed text-[var(--text-tertiary)]">
        Cada ponto é o p-valor do teste de uniformidade do PIT numa janela rolante de {d.window} pregões. Abaixo de <b style={{ color: "var(--down)" }}>0.05</b> (pontos vermelhos), a densidade servida deixou de ser estatisticamente confiável naquele momento — o modelo perdeu o regime. É a nossa própria honestidade auditada, em série temporal. Análise, não recomendação.
      </p>
    </>,
  );
}
