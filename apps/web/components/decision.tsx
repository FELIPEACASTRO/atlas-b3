"use client";

import { useEffect, useState } from "react";

type Sizing = { lots: number; kelly_frac?: number; binding?: string; cvar_at_risk?: number; reason?: string };
type Why = { tese: string; sinais: string; ressalva: string; concordam: string[]; divergem: string[] };
type Econ = { pop: number; ev_lot: number; cvar_lot: number; max_loss_lot: number; max_gain_lot: number };
type Inval = { price_stop: number | null; vol_stop: string | null; days_stop: number; calib_stop: string };
type Leg = { kind: string; action: string; strike: number; premium: number };
type Card = {
  name: string; thesis: string; defined_risk: boolean; vol_stance: string; legs: Leg[]; breakevens: number[];
  verdict: string; decision_score: number; sizing: Sizing; economics: Econ; why: Why; invalidation: Inval;
  reactivate?: string | null;
};
type Conf = { score: number; band: string; factors: Record<string, number> };
type Resp = {
  ticker: string; spot: number | null; perfil: string; available: boolean;
  confidence?: Conf; abstain?: { is_abstained: boolean; reason: string | null };
  signals?: { consensus: number; agree_frac: number; n_signals: number };
  market_view?: { iv: number | null; physical: number | null; vrp: number | null; regime: string; bias: string; iv_rank: number | null };
  cards?: Card[]; note?: string; liquidez_caveat?: string;
};

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";
const VIEWS = [{ id: "alta", label: "Alta" }, { id: "baixa", label: "Baixa" }, { id: "neutro", label: "Neutro" }, { id: "renda", label: "Renda" }];
const PERFIS = ["conservador", "moderado", "agressivo"] as const;
const brl = (v: number) => `R$ ${Math.round(v).toLocaleString("pt-BR")}`;
const pct = (v: number | null | undefined) => (v == null ? "—" : `${(v * 100).toFixed(0)}%`);
const legText = (l: Leg) => `${l.action === "long" ? "compra" : "venda"} ${l.kind === "call" ? "call" : "put"} ${l.strike}`;

const VERDICT: Record<string, { c: string; label: string }> = {
  OPERAR: { c: "var(--up)", label: "OPERAR" },
  "OPERAR PEQUENO": { c: "var(--accent)", label: "OPERAR PEQUENO" },
  OBSERVAR: { c: "var(--text-tertiary)", label: "OBSERVAR" },
  EVITAR: { c: "var(--down)", label: "EVITAR" },
};
const bandColor = (b: string) => (b === "verde" ? "var(--up)" : b === "amarelo" ? "#d99a2b" : "var(--down)");

export function Decision() {
  const [ticker, setTicker] = useState("PETR4");
  const [input, setInput] = useState("PETR4");
  const [capital, setCapital] = useState(20000);
  const [prazo, setPrazo] = useState(30);
  const [visao, setVisao] = useState("alta");
  const [perfil, setPerfil] = useState<(typeof PERFIS)[number]>("moderado");
  const [d, setD] = useState<Resp | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  useEffect(() => {
    let alive = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset while refetching
    setLoading(true);
    setErr("");
    fetch(`${API}/decision/${ticker}?visao=${visao}&capital=${capital}&prazo=${prazo}&perfil=${perfil}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`erro ${r.status}`))))
      .then((j: Resp) => alive && (setD(j), setLoading(false)))
      .catch((e) => alive && (setErr(e instanceof Error ? e.message : "falha"), setLoading(false)));
    return () => { alive = false; };
  }, [ticker, capital, prazo, visao, perfil]);

  const conf = d?.confidence;
  const mv = d?.market_view;

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-1 flex items-center gap-2.5">
        <h1 className="text-[16px] font-medium">Cartão de Decisão</h1>
        <span className="rounded px-1.5 py-0.5 text-[10px]" style={{ background: "color-mix(in oklch, var(--accent) 14%, transparent)", color: "var(--accent)" }}>
          o quê · por quê · quanto · com que confiança
        </span>
      </div>
      <p className="mb-3 text-[12px] text-[var(--text-tertiary)]">
        a síntese de todos os sinais numa decisão — que sabe dizer <b>&ldquo;fique de fora&rdquo;</b> quando a densidade perde o regime. Análise, nunca ordem.
      </p>

      {/* inputs */}
      <form onSubmit={(e) => { e.preventDefault(); setTicker(input.toUpperCase().trim() || "PETR4"); }}
        className="mb-4 grid gap-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-3 sm:grid-cols-[1fr_1fr_1fr_auto]">
        <label className="text-[11px] text-[var(--text-tertiary)]">Ativo
          <input value={input} onChange={(e) => setInput(e.target.value)} onBlur={() => setTicker(input.toUpperCase().trim() || "PETR4")}
            className="mono mt-1 w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-2.5 py-1.5 text-[13px] uppercase outline-none" />
        </label>
        <label className="text-[11px] text-[var(--text-tertiary)]">Capital de risco (R$)
          <input type="number" min={1000} step={1000} value={capital} onChange={(e) => setCapital(Math.max(1000, Number(e.target.value) || 1000))}
            className="mono mt-1 w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-2.5 py-1.5 text-[13px] outline-none" />
        </label>
        <label className="text-[11px] text-[var(--text-tertiary)]">Prazo (dias)
          <select value={prazo} onChange={(e) => setPrazo(Number(e.target.value))}
            className="mt-1 w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-2.5 py-1.5 text-[13px] outline-none">
            {[15, 30, 45, 60].map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </label>
        <div className="flex items-end"><div className="flex flex-wrap gap-1">
          {VIEWS.map((v) => (
            <button key={v.id} type="button" onClick={() => setVisao(v.id)} className="rounded-lg border px-2.5 py-1.5 text-[12px]"
              style={visao === v.id ? { background: "var(--accent)", color: "var(--bg-base)", borderColor: "var(--accent)" } : { borderColor: "var(--border-subtle)", color: "var(--text-secondary)" }}>
              {v.label}
            </button>
          ))}
        </div></div>
      </form>

      <div className="mb-3 flex items-center gap-2 text-[11px] text-[var(--text-tertiary)]">
        <span>perfil de risco:</span>
        {PERFIS.map((p) => (
          <button key={p} type="button" onClick={() => setPerfil(p)} className="rounded-md border px-2 py-0.5 text-[11px] capitalize"
            style={perfil === p ? { background: "color-mix(in oklch, var(--accent) 16%, transparent)", color: "var(--accent)", borderColor: "color-mix(in oklch, var(--accent) 40%, var(--border-subtle))" } : { borderColor: "var(--border-subtle)", color: "var(--text-secondary)" }}>
            {p}
          </button>
        ))}
      </div>

      {loading ? <p className="text-[12px] text-[var(--text-tertiary)]">sintetizando a decisão…</p> : null}
      {err ? <p className="text-[12px]" style={{ color: "var(--down)" }}>{err}</p> : null}

      {/* confiança + abstenção */}
      {d && conf && !loading ? (
        <div className="mb-4 rounded-xl border p-4" style={{ borderColor: `color-mix(in oklch, ${bandColor(conf.band)} 40%, var(--border-subtle))` }}>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <div className="flex items-baseline gap-2">
              <span className="mono text-[28px] font-semibold" style={{ color: bandColor(conf.band) }}>{conf.score}</span>
              <span className="text-[11px] text-[var(--text-tertiary)]">/100 confiança</span>
            </div>
            {mv ? (
              <div className="text-[11.5px] text-[var(--text-tertiary)]">
                <b className="mono" style={{ color: "var(--text-primary)" }}>{d.ticker}</b> R$ {d.spot} · mercado <b className="mono" style={{ color: "var(--accent)" }}>{pct(mv.iv)}</b> vs física <b className="mono">{pct(mv.physical)}</b>
                {mv.iv_rank != null ? <> · IVR {mv.iv_rank}</> : null} · regime <b>{mv.regime}</b>
                {d.signals ? <> · sinais <b style={{ color: d.signals.consensus > 0 ? "var(--down)" : d.signals.consensus < 0 ? "var(--up)" : undefined }}>{d.signals.consensus > 0 ? "vol cara" : d.signals.consensus < 0 ? "vol barata" : "neutros"}</b> ({Math.round(d.signals.agree_frac * 100)}% concordam)</> : null}
              </div>
            ) : null}
          </div>
          {/* fatores */}
          <div className="mt-3 flex flex-wrap gap-2">
            {Object.entries(conf.factors).map(([k, v]) => (
              <div key={k} className="flex items-center gap-1.5 rounded-md px-2 py-1 text-[10.5px]" style={{ background: "var(--bg-surface)" }}>
                <span className="text-[var(--text-tertiary)] capitalize">{k}</span>
                <span className="mono" style={{ color: v >= 0.7 ? "var(--up)" : v >= 0.4 ? "#d99a2b" : "var(--down)" }}>{Math.round(v * 100)}</span>
              </div>
            ))}
          </div>
          {d.abstain?.is_abstained ? (
            <div className="mt-3 rounded-lg px-3 py-2 text-[12px]" style={{ background: "color-mix(in oklch, var(--down) 12%, transparent)", color: "var(--down)" }}>
              <b>Fique de fora.</b> {d.abstain.reason}. Nenhuma estrutura é recomendada — a decisão honesta é não operar. <span style={{ opacity: 0.85 }}>↻ Reavalie quando a densidade recalibrar (o monitor de PIT precisa voltar acima de 0.05).</span>
            </div>
          ) : null}
        </div>
      ) : null}

      {/* cartões */}
      <div className="space-y-2.5">
        {(d?.cards ?? []).map((c, i) => <DecisionCard key={c.name} c={c} top={i === 0 && !d?.abstain?.is_abstained} />)}
      </div>

      {d && !loading && (d.cards?.length ?? 0) === 0 && !err ? (
        <p className="text-[12px] text-[var(--text-secondary)]">{d.note ?? "sem estruturas para esta visão."}</p>
      ) : null}

      {d?.liquidez_caveat ? <p className="mt-3 text-[10.5px] leading-relaxed text-[var(--text-tertiary)]">⚠ {d.liquidez_caveat}</p> : null}
    </div>
  );
}

function DecisionCard({ c, top }: { c: Card; top: boolean }) {
  const v = VERDICT[c.verdict] ?? VERDICT.OBSERVAR;
  const s = c.sizing;
  return (
    <div className="rounded-xl border p-3" style={{ borderColor: top ? `color-mix(in oklch, ${v.c} 45%, var(--border-subtle))` : "var(--border-subtle)" }}>
      <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-[13px] font-medium text-[var(--text-primary)]">{c.name}</span>
          <span className="rounded px-1.5 py-0.5 text-[10px] font-semibold" style={{ background: `color-mix(in oklch, ${v.c} 16%, transparent)`, color: v.c }}>{v.label}</span>
          {top ? <span className="rounded px-1.5 py-0.5 text-[9.5px]" style={{ background: "var(--accent)", color: "var(--bg-base)" }}>recomendada</span> : null}
          {!c.defined_risk ? <span className="text-[9.5px]" style={{ color: "var(--down)" }}>risco ilimitado</span> : null}
        </div>
        <div className="flex items-center gap-3 text-[12px]">
          <span className="text-[var(--text-tertiary)]">confiança <b className="mono" style={{ color: "var(--text-primary)" }}>{c.decision_score}</b></span>
          <span className="text-[var(--text-tertiary)]">POP <b className="mono">{Math.round(c.economics.pop * 100)}%</b></span>
        </div>
      </div>

      {/* sizing — a espinha */}
      <div className="mb-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-lg px-3 py-2 text-[11.5px]" style={{ background: "color-mix(in oklch, var(--accent) 6%, transparent)" }}>
        <span>tamanho: <b className="mono" style={{ color: s.lots > 0 ? "var(--text-primary)" : "var(--text-tertiary)" }}>{s.lots} lote{s.lots === 1 ? "" : "s"}</b></span>
        {s.lots > 0 ? <>
          <span className="text-[var(--text-tertiary)]">risco de cauda (CVaR): <b className="mono" style={{ color: "var(--down)" }}>{brl(-(s.cvar_at_risk ?? 0))}</b></span>
          {s.binding ? <span className="text-[10px] text-[var(--text-tertiary)]">limitado por {s.binding}</span> : null}
        </> : <span className="text-[10px] text-[var(--text-tertiary)]">{s.reason ?? "Kelly ≤ 0: sem edge de crescimento"}</span>}
      </div>

      {/* gatilho de retorno: o que faria este "não" virar "opere" */}
      {c.reactivate ? (
        <div className="mb-1.5 flex items-start gap-1.5 text-[11px]" style={{ color: "var(--accent)" }}>
          <span aria-hidden>↻</span><span>{c.reactivate}</span>
        </div>
      ) : null}

      {/* pernas */}
      <div className="mb-1.5 flex flex-wrap gap-1.5">
        {c.legs.map((l, j) => (
          <span key={j} className="mono rounded-md px-1.5 py-0.5 text-[10.5px]" style={{ background: "var(--bg-elevated)", color: l.action === "long" ? "var(--up)" : "var(--down)" }}>{legText(l)}</span>
        ))}
      </div>

      {/* por que — 3 atos */}
      <div className="mb-1.5 space-y-0.5 text-[11.5px] leading-relaxed">
        <p className="text-[var(--text-secondary)]">{c.why.tese}</p>
        <p className="text-[var(--text-tertiary)]"><b style={{ color: "var(--text-secondary)" }}>Sinais:</b> {c.why.sinais}.</p>
        <p className="text-[var(--text-tertiary)]">{c.why.ressalva}</p>
      </div>

      {/* invalidação */}
      <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-[10.5px] text-[var(--text-tertiary)]">
        <span>sai se:</span>
        {c.invalidation.price_stop != null ? <span>preço cruzar <b className="mono">R$ {c.invalidation.price_stop}</b></span> : null}
        {c.invalidation.vol_stop ? <span>{c.invalidation.vol_stop}</span> : null}
        <span>{c.invalidation.days_stop}d p/ o vencimento</span>
        <span>{c.invalidation.calib_stop}</span>
      </div>
    </div>
  );
}
