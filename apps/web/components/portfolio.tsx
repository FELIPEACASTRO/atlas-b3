"use client";

import { useEffect, useState } from "react";

type Pos = {
  ticker: string;
  tipo: string | null;
  qty: number;
  last: number | null;
  value: number | null;
  delta: number | null;
  gamma: number | null;
  vega: number | null;
  theta: number | null;
};
type PF = {
  n_positions: number;
  total_value: number;
  net_delta: number;
  net_gamma: number;
  net_vega: number;
  net_theta: number;
  provenance: string;
  asof: string | null;
};
type Stress = {
  scenarios: { shock_pct: number; pnl: number }[];
  pnl_vol_up: number;
  theta_per_day: number;
};

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const fmt = (n: number | null, d = 2): string => (n == null ? "—" : n.toFixed(d));
const brl = (n: number | null): string =>
  n == null ? "—" : n.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });

export function Portfolio() {
  const [rows, setRows] = useState<Pos[]>([]);
  const [pf, setPf] = useState<PF | null>(null);
  const [stress, setStress] = useState<Stress | null>(null);
  const [ticker, setTicker] = useState("");
  const [qty, setQty] = useState("");
  const [err, setErr] = useState("");

  function load() {
    fetch(`${API}/positions`)
      .then((r) => (r.ok ? r.json() : []))
      .then(setRows)
      .catch(() => setErr("API offline — suba o backend"));
    fetch(`${API}/portfolio`)
      .then((r) => (r.ok ? r.json() : null))
      .then(setPf)
      .catch(() => {});
    fetch(`${API}/portfolio/stress`)
      .then((r) => (r.ok ? r.json() : null))
      .then(setStress)
      .catch(() => {});
  }
  useEffect(load, []);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!ticker || !qty) return;
    const r = await fetch(`${API}/positions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ticker, qty: parseFloat(qty) }),
    });
    if (!r.ok) {
      setErr("não foi possível adicionar — defina ATLAS_DB e rode a ingestão");
      return;
    }
    setTicker("");
    setQty("");
    setErr("");
    load();
  }

  async function remove(t: string) {
    await fetch(`${API}/positions/${t}`, { method: "DELETE" });
    load();
  }

  return (
    <div className="max-w-4xl">
      <form onSubmit={add} className="mb-4 flex flex-wrap items-center gap-2">
        <input
          value={ticker}
          onChange={(e) => setTicker(e.target.value)}
          aria-label="ticker"
          placeholder="ticker (PETR4, PETRA38…)"
          className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-3 py-2 text-[13px] outline-none"
          style={{ color: "var(--text-primary)" }}
        />
        <input
          value={qty}
          onChange={(e) => setQty(e.target.value)}
          aria-label="quantidade"
          type="number"
          placeholder="qtd (+ comprado / − vendido)"
          className="w-52 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-3 py-2 text-[13px] outline-none"
          style={{ color: "var(--text-primary)" }}
        />
        <button className="rounded-lg px-3 py-2 text-[13px] font-medium" style={{ background: "var(--accent)", color: "var(--bg-base)" }}>
          Adicionar
        </button>
        {err ? <span className="text-[12px]" style={{ color: "var(--down)" }}>{err}</span> : null}
      </form>

      {pf ? (
        <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-5">
          {([
            ["Valor total", brl(pf.total_value)],
            ["Δ líquido", fmt(pf.net_delta)],
            ["Γ líquido", fmt(pf.net_gamma, 4)],
            ["Vega líquido", fmt(pf.net_vega)],
            ["θ/dia líquido", fmt(pf.net_theta)],
          ] as const).map(([l, v]) => (
            <div key={l} className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4">
              <div className="text-[12px] text-[var(--text-secondary)]">{l}</div>
              <div className="mono text-xl font-medium">{v}</div>
            </div>
          ))}
        </div>
      ) : null}

      {stress && stress.scenarios.length ? (
        <div className="mb-4 rounded-xl border border-[var(--border-subtle)] p-4">
          <div className="mb-2 text-[12px] text-[var(--text-secondary)]">
            Stress de mercado (Δ-Γ, vol constante) — P&amp;L aprox. se todos os ativos moverem:
          </div>
          <div className="flex flex-wrap gap-2">
            {stress.scenarios.map((s) => (
              <div key={s.shock_pct} className="min-w-[72px] rounded-lg bg-[var(--bg-surface)] px-2.5 py-1.5 text-center">
                <div className="text-[11px] text-[var(--text-tertiary)]">{s.shock_pct > 0 ? "+" : ""}{s.shock_pct}%</div>
                <div className="mono text-[13px]" style={{ color: s.pnl > 0 ? "var(--up)" : s.pnl < 0 ? "var(--down)" : "var(--text-secondary)" }}>
                  {brl(s.pnl)}
                </div>
              </div>
            ))}
          </div>
          <div className="mt-2 text-[11px] text-[var(--text-tertiary)]">
            IV +5 pts: <span className="mono">{brl(stress.pnl_vol_up)}</span> · θ/dia:{" "}
            <span className="mono">{brl(stress.theta_per_day)}</span> · aproximação Taylor, não revalorização completa
          </div>
        </div>
      ) : null}

      {rows.length === 0 ? (
        <p className="text-[13px] text-[var(--text-tertiary)]">Sem posições. Adicione um ticker acima (ações ou opções).</p>
      ) : (
        <div className="overflow-hidden rounded-xl border border-[var(--border-subtle)]">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="bg-[var(--bg-surface)] text-left text-[var(--text-secondary)]">
                <th className="px-4 py-2.5 font-normal">Ativo</th>
                <th className="px-3 py-2.5 font-normal">Tipo</th>
                <th className="px-3 py-2.5 text-right font-normal">Qtd</th>
                <th className="px-3 py-2.5 text-right font-normal">Último</th>
                <th className="px-3 py-2.5 text-right font-normal">Valor</th>
                <th className="px-3 py-2.5 text-right font-normal">Δ</th>
                <th className="px-3 py-2.5 text-right font-normal">Γ</th>
                <th className="px-3 py-2.5 text-right font-normal">Vega</th>
                <th className="px-3 py-2.5 text-right font-normal">θ/dia</th>
                <th className="px-4 py-2.5" />
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.ticker} className="border-t border-[var(--border-subtle)]">
                  <td className="mono px-4 py-2.5 font-medium">{r.ticker}</td>
                  <td className="px-3 py-2.5 text-[var(--text-secondary)]">{r.tipo ?? "—"}</td>
                  <td className="mono px-3 py-2.5 text-right">{r.qty}</td>
                  <td className="mono px-3 py-2.5 text-right">{fmt(r.last)}</td>
                  <td className="mono px-3 py-2.5 text-right">{brl(r.value)}</td>
                  <td className="mono px-3 py-2.5 text-right">{fmt(r.delta)}</td>
                  <td className="mono px-3 py-2.5 text-right">{fmt(r.gamma, 4)}</td>
                  <td className="mono px-3 py-2.5 text-right">{fmt(r.vega)}</td>
                  <td className="mono px-3 py-2.5 text-right">{fmt(r.theta)}</td>
                  <td className="px-4 py-2.5 text-right">
                    <button onClick={() => remove(r.ticker)} className="text-[12px] text-[var(--text-tertiary)] hover:text-[var(--down)]">
                      remover
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {pf ? (
        <div className="mt-3 text-[11px] text-[var(--text-tertiary)]">fonte: {pf.provenance} · risco consolidado das gregas reais</div>
      ) : null}
    </div>
  );
}
