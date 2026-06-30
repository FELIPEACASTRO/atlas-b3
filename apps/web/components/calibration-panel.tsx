"use client";

import { useEffect, useState } from "react";

type PopTarget = { moneyness: number; price: number; above: number; below: number };
type Prediction = {
  ticker: string;
  provenance: string;
  asof: string | null;
  sigma: number | null;
  note?: string;
  market_vs_physical?: { iv: number | null; physical: number; vrp: number };
  dist?: {
    sigma_phys: number;
    nu: number;
    horizon_days: number;
    pop_targets: PopTarget[];
    quantiles: { p10: number; p25: number; p50: number; p75: number; p90: number };
  } | null;
  regime?: { regime: string; bias: string; iv_rank: number | null; term_slope: number | null };
  calibration: {
    available: boolean;
    reason?: string;
    coverage?: number;
    nominal: number;
    pit_p?: number;
    pit_ok?: boolean;
    n_test?: number;
  };
};

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";
const pct = (v: number | null | undefined) => (v == null ? "—" : `${(v * 100).toFixed(1)}%`);
const prob = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v * 100)}%`);

function Card({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-4 rounded-xl border border-[var(--border-subtle)] p-4">
      <div className="mb-2 flex items-center gap-2">
        <span className="text-[12px] font-medium text-[var(--text-secondary)]">Predição calibrada</span>
        <span
          className="rounded px-1.5 py-0.5 text-[10px]"
          style={{ background: "color-mix(in oklch, var(--accent) 14%, transparent)", color: "var(--accent)" }}
        >
          cenário-alvo, não profecia
        </span>
      </div>
      {children}
    </div>
  );
}

export function CalibrationPanel({ ticker }: { ticker: string }) {
  const [d, setD] = useState<Prediction | null>(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset loading when the ticker changes
    setLoading(true);
    setErr("");
    fetch(`${API}/predict/${ticker}`)
      .then(async (r) => {
        if (!r.ok)
          throw new Error(
            r.status === 503
              ? "Ainda não há dados de mercado carregados no terminal."
              : `Não consegui calcular a predição agora (erro ${r.status}).`,
          );
        return (await r.json()) as Prediction;
      })
      .then((j) => alive && (setD(j), setLoading(false)))
      .catch((e) => alive && (setErr(e instanceof Error ? e.message : "falha ao consultar"), setLoading(false)));
    return () => {
      alive = false;
    };
  }, [ticker]);

  if (loading)
    return (
      <Card>
        <p className="text-[12px] text-[var(--text-tertiary)]">calculando a predição de {ticker}…</p>
      </Card>
    );
  if (err)
    return (
      <Card>
        <p className="text-[12px]" style={{ color: "var(--down)" }}>{err}</p>
      </Card>
    );
  if (!d) return null;

  // histórico curto → honesto, sem fabricar
  if (d.sigma == null || !d.dist || !d.market_vs_physical) {
    return (
      <Card>
        <p className="text-[12px] text-[var(--text-secondary)]">
          Histórico insuficiente para uma predição calibrada de <b style={{ color: "var(--text-primary)" }}>{ticker}</b>.
          {d.note ? <> {d.note}.</> : null}
        </p>
      </Card>
    );
  }

  const mvp = d.market_vs_physical;
  const cal = d.calibration;
  const dist = d.dist;
  const up5 = dist.pop_targets.find((t) => t.moneyness === 1.05);
  const down5 = dist.pop_targets.find((t) => t.moneyness === 0.95);
  const vrpRich = mvp.vrp > 0;
  const covPct = cal.available && cal.coverage != null ? cal.coverage : null;
  const covScale = (v: number) => `${Math.min(100, Math.max(0, v * 100))}%`;

  return (
    <Card>
      {/* mercado vs nós */}
      <div className="grid gap-2 sm:grid-cols-2">
        <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-3 py-2.5">
          <div className="text-[10.5px] text-[var(--text-tertiary)]">o mercado cobra (IV implícita)</div>
          <div className="mono text-[18px]" style={{ color: "var(--accent)" }}>{pct(mvp.iv)}</div>
        </div>
        <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-3 py-2.5">
          <div className="text-[10.5px] text-[var(--text-tertiary)]">nossa estimativa (vol física, {dist.horizon_days}d)</div>
          <div className="mono text-[18px]" style={{ color: "var(--text-primary)" }}>{pct(mvp.physical)}</div>
        </div>
      </div>
      <p className="mt-2 rounded-lg px-3 py-2 text-[11.5px] leading-relaxed"
        style={{ background: "color-mix(in oklch, var(--accent) 7%, transparent)", color: "var(--text-secondary)" }}>
        <b style={{ color: "var(--text-primary)" }}>O gap (VRP {pct(mvp.vrp)}): </b>
        {vrpRich ? (
          <>o mercado embute <b style={{ color: "var(--accent)" }}>mais</b> vol do que estimamos — prêmio &ldquo;gordo&rdquo;, tende a favorecer quem <b>vende/lança</b>.</>
        ) : (
          <>o mercado embute <b style={{ color: "var(--up)" }}>menos</b> vol do que estimamos — prêmio &ldquo;magro&rdquo;, tende a favorecer quem <b>compra</b>.</>
        )}
      </p>

      {/* cenários (POP) */}
      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1 text-[11.5px]">
        <span className="text-[var(--text-tertiary)]">em {dist.horizon_days} dias:</span>
        <span className="text-[var(--text-secondary)]">
          P(subir +5% → R${up5?.price.toFixed(2)}) <b className="mono" style={{ color: "var(--up)" }}>{prob(up5?.above)}</b>
        </span>
        <span className="text-[var(--text-secondary)]">
          P(cair −5% → R${down5?.price.toFixed(2)}) <b className="mono" style={{ color: "var(--down)" }}>{prob(down5?.below)}</b>
        </span>
      </div>

      {/* calibração */}
      <div className="mt-3 rounded-lg border border-[var(--border-subtle)] px-3 py-2.5">
        <div className="mb-1.5 flex items-center justify-between">
          <span className="text-[11.5px] font-medium text-[var(--text-secondary)]">
            Calibração {cal.available && cal.n_test ? <span className="text-[var(--text-tertiary)]">· últimos {cal.n_test} pregões</span> : null}
          </span>
          {cal.available ? (
            <span className="rounded px-2 py-0.5 text-[10px]"
              style={cal.pit_ok
                ? { background: "color-mix(in oklch, var(--up) 16%, transparent)", color: "var(--up)" }
                : { background: "color-mix(in oklch, var(--accent) 16%, transparent)", color: "var(--accent)" }}>
              {cal.pit_ok ? "forma bem calibrada" : "forma imperfeita (ν fixo)"}
            </span>
          ) : (
            <span className="text-[10px] text-[var(--text-tertiary)]">série curta para auditar</span>
          )}
        </div>
        {covPct != null ? (
          <>
            <div className="relative h-2 rounded-full" style={{ background: "var(--bg-surface)" }}>
              <div className="absolute inset-y-0 left-0 rounded-full" style={{ width: covScale(covPct), background: "var(--accent)" }} />
              <div className="absolute inset-y-[-2px] w-px" style={{ left: covScale(cal.nominal), background: "var(--text-primary)" }} title="meta" />
            </div>
            <div className="mt-1 flex justify-between text-[10.5px] text-[var(--text-tertiary)]">
              <span>cobertura real <b className="mono" style={{ color: "var(--text-secondary)" }}>{prob(covPct)}</b></span>
              <span>meta {prob(cal.nominal)}</span>
            </div>
          </>
        ) : (
          <p className="text-[11px] text-[var(--text-tertiary)]">{cal.reason ?? "sem backtest disponível"}</p>
        )}
        <p className="mt-1.5 text-[10.5px] leading-relaxed text-[var(--text-tertiary)]">
          quando o intervalo de {prob(cal.nominal)} cobre ~{prob(cal.nominal)} dos dias e o teste de forma (PIT) passa, a distribuição está honesta — não é acerto garantido, é probabilidade auditada.
        </p>
      </div>

      {d.regime ? (
        <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px]">
          <span className="rounded-md px-1.5 py-0.5 text-[10px]" style={{ background: "var(--bg-surface)", color: "var(--text-secondary)" }}>
            regime: {d.regime.regime}
          </span>
          <span className="text-[var(--text-tertiary)]">{d.regime.bias}</span>
        </div>
      ) : null}

      <div className="mt-2 text-[10.5px] text-[var(--text-tertiary)]">
        fonte: {d.provenance} · fechamento (EOD) · análise, não recomendação de compra/venda
      </div>
    </Card>
  );
}
