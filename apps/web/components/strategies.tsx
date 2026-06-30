"use client";

import { useEffect, useState } from "react";

type Leg = { kind: string; action: string; strike: number; premium: number };
type Strategy = {
  name: string;
  thesis: string;
  defined_risk: boolean;
  vol_stance: string;
  lots: number;
  cost: number;
  max_loss: number;
  max_gain: number;
  ev: number;
  pop: number;
  breakevens: number[];
  legs: Leg[];
};
type Resp = {
  ticker: string;
  spot: number | null;
  visao: string;
  capital: number;
  prazo: number;
  regime?: { regime: string; bias: string };
  market_vs_physical?: { iv: number | null; physical: number; vrp: number };
  strategies: Strategy[];
  provenance: string;
  note?: string;
};

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";
const VIEWS = [
  { id: "alta", label: "Alta" },
  { id: "baixa", label: "Baixa" },
  { id: "neutro", label: "Neutro" },
  { id: "renda", label: "Renda" },
];
const brl = (v: number) => `R$ ${Math.round(v).toLocaleString("pt-BR")}`;
const legText = (l: Leg) =>
  `${l.action === "long" ? "compra" : "venda"} ${l.kind === "call" ? "call" : "put"} ${l.strike} @ ${l.premium.toFixed(2)}`;

export function Strategies() {
  const [ticker, setTicker] = useState("PETR4");
  const [input, setInput] = useState("PETR4");
  const [capital, setCapital] = useState(20000);
  const [prazo, setPrazo] = useState(30);
  const [visao, setVisao] = useState("alta");
  const [d, setD] = useState<Resp | null>(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset loading when inputs change
    setLoading(true);
    setErr("");
    const url = `${API}/strategies/${ticker}?capital=${capital}&prazo=${prazo}&visao=${visao}`;
    fetch(url)
      .then(async (r) => {
        if (!r.ok)
          throw new Error(
            r.status === 503
              ? "Ainda não há dados de mercado carregados no terminal."
              : `Não consegui montar as estratégias agora (erro ${r.status}).`,
          );
        return (await r.json()) as Resp;
      })
      .then((j) => alive && (setD(j), setLoading(false)))
      .catch((e) => alive && (setErr(e instanceof Error ? e.message : "falha"), setLoading(false)));
    return () => {
      alive = false;
    };
  }, [ticker, capital, prazo, visao]);

  const mvp = d?.market_vs_physical;

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-1 flex items-center gap-2.5">
        <h1 className="text-[16px] font-medium">Consultor de estratégias</h1>
        <span className="rounded px-1.5 py-0.5 text-[10px]" style={{ background: "color-mix(in oklch, var(--accent) 14%, transparent)", color: "var(--accent)" }}>
          POP + valor esperado, não recomendação
        </span>
      </div>
      <p className="mb-3 text-[12px] text-[var(--text-tertiary)]">
        diga ativo, capital de risco, prazo e sua visão — o ATLAS monta estruturas da cadeia real e mede cada uma na densidade calibrada.
      </p>

      {/* inputs */}
      <form
        onSubmit={(e) => { e.preventDefault(); setTicker(input.toUpperCase().trim() || "PETR4"); }}
        className="mb-4 grid gap-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-3 sm:grid-cols-[1fr_1fr_1fr_auto]"
      >
        <label className="text-[11px] text-[var(--text-tertiary)]">
          Ativo
          <input value={input} onChange={(e) => setInput(e.target.value)} onBlur={() => setTicker(input.toUpperCase().trim() || "PETR4")}
            className="mono mt-1 w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-2.5 py-1.5 text-[13px] uppercase outline-none" />
        </label>
        <label className="text-[11px] text-[var(--text-tertiary)]">
          Capital de risco (R$)
          <input type="number" min={1000} step={1000} value={capital} onChange={(e) => setCapital(Math.max(1000, Number(e.target.value) || 1000))}
            className="mono mt-1 w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-2.5 py-1.5 text-[13px] outline-none" />
        </label>
        <label className="text-[11px] text-[var(--text-tertiary)]">
          Prazo (dias)
          <select value={prazo} onChange={(e) => setPrazo(Number(e.target.value))}
            className="mt-1 w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-2.5 py-1.5 text-[13px] outline-none">
            {[15, 30, 45, 60].map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </label>
        <div className="flex items-end">
          <div className="flex flex-wrap gap-1">
            {VIEWS.map((v) => (
              <button key={v.id} type="button" onClick={() => setVisao(v.id)}
                className="rounded-lg border px-2.5 py-1.5 text-[12px]"
                style={visao === v.id
                  ? { background: "var(--accent)", color: "var(--bg-base)", borderColor: "var(--accent)" }
                  : { borderColor: "var(--border-subtle)", color: "var(--text-secondary)" }}>
                {v.label}
              </button>
            ))}
          </div>
        </div>
      </form>

      {/* context */}
      {d && d.spot != null ? (
        <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11.5px] text-[var(--text-tertiary)]">
          <span><b className="mono" style={{ color: "var(--text-primary)" }}>{d.ticker}</b> R$ {d.spot}</span>
          {d.regime ? <span>regime: <b style={{ color: "var(--text-secondary)" }}>{d.regime.regime}</b></span> : null}
          {mvp ? <span>mercado <b className="mono" style={{ color: "var(--accent)" }}>{(mvp.iv != null ? mvp.iv * 100 : 0).toFixed(0)}%</b> vs física <b className="mono">{(mvp.physical * 100).toFixed(0)}%</b></span> : null}
        </div>
      ) : null}

      {loading ? <p className="text-[12px] text-[var(--text-tertiary)]">montando estratégias…</p> : null}
      {err ? <p className="text-[12px]" style={{ color: "var(--down)" }}>{err}</p> : null}
      {d && !loading && !err && d.strategies.length === 0 ? (
        <p className="text-[12px] text-[var(--text-secondary)]">{d.note ?? "sem estratégias para esta cadeia."}</p>
      ) : null}

      <div className="space-y-2.5">
        {(d?.strategies ?? []).map((s, i) => (
          <StrategyCard key={s.name} s={s} top={i === 0} />
        ))}
      </div>

      {d && d.strategies.length ? (
        <p className="mt-3 text-[10.5px] text-[var(--text-tertiary)]">
          POP = probabilidade de lucro; EV = valor esperado, ambos medidos na densidade física calibrada · fonte: {d.provenance} · {d.note}
        </p>
      ) : null}
    </div>
  );
}

function StrategyCard({ s, top }: { s: Strategy; top: boolean }) {
  const evUp = s.ev >= 0;
  return (
    <div className="rounded-xl border p-3" style={{ borderColor: top ? "color-mix(in oklch, var(--accent) 45%, var(--border-subtle))" : "var(--border-subtle)" }}>
      <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-[13px] font-medium text-[var(--text-primary)]">{s.name}</span>
          {top ? <span className="rounded px-1.5 py-0.5 text-[9.5px]" style={{ background: "var(--accent)", color: "var(--bg-base)" }}>melhor p/ sua tese</span> : null}
          <span className="rounded-md px-1.5 py-0.5 text-[9.5px]" style={{ background: "var(--bg-surface)", color: "var(--text-tertiary)" }}>{s.thesis}</span>
          {!s.defined_risk ? <span className="text-[9.5px]" style={{ color: "var(--down)" }}>risco ilimitado</span> : null}
        </div>
        <div className="flex items-center gap-3 text-[12px]">
          <span className="text-[var(--text-tertiary)]">POP <b className="mono" style={{ color: "var(--text-primary)" }}>{Math.round(s.pop * 100)}%</b></span>
          <span className="text-[var(--text-tertiary)]">EV <b className="mono" style={{ color: evUp ? "var(--up)" : "var(--down)" }}>{evUp ? "+" : ""}{brl(s.ev)}</b></span>
        </div>
      </div>
      <div className="mb-1.5 flex flex-wrap gap-1.5">
        {s.legs.map((l, j) => (
          <span key={j} className="mono rounded-md px-1.5 py-0.5 text-[10.5px]"
            style={{ background: "var(--bg-elevated)", color: l.action === "long" ? "var(--up)" : "var(--down)" }}>
            {legText(l)}
          </span>
        ))}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-[11px] text-[var(--text-tertiary)]">
        <span>lotes: <b className="mono" style={{ color: "var(--text-secondary)" }}>{s.lots}</b></span>
        <span>risco máx: <b className="mono" style={{ color: "var(--down)" }}>{brl(s.max_loss)}</b></span>
        <span>ganho máx: <b className="mono" style={{ color: "var(--up)" }}>{s.defined_risk ? brl(s.max_gain) : "alto"}</b></span>
        {s.breakevens.length ? <span>breakeven: <b className="mono" style={{ color: "var(--text-secondary)" }}>{s.breakevens.join(" / ")}</b></span> : null}
      </div>
    </div>
  );
}
