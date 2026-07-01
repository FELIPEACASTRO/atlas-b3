"use client";

import { useEffect, useState } from "react";

import { VolHistory } from "@/components/vol-history";
import { CalibrationPanel } from "@/components/calibration-panel";
import { EdgeMap } from "@/components/edge-map";
import { KernelMap } from "@/components/kernel-map";
import { FairIv } from "@/components/fair-iv";
import { IvSurface } from "@/components/iv-surface";
import { OptionPanel } from "@/components/option-panel";
import { InfoTip } from "@/components/info-tip";

type Row = {
  ticker: string;
  kind: string;
  strike: number;
  last: number;
  iv: number | null;
  delta: number | null;
  gamma: number | null;
  vega: number | null;
  theta: number | null;
  provenance: string;
  asof: string;
};

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

function fmt(n: number | null, d = 2): string {
  return n == null ? "—" : n.toFixed(d);
}

export function OptionsChain() {
  const [ticker, setTicker] = useState("PETR4");
  const [input, setInput] = useState("PETR4");
  const [rows, setRows] = useState<Row[]>([]);
  const [prov, setProv] = useState("");
  const [loading, setLoading] = useState(true);
  const [kind, setKind] = useState<"all" | "call" | "put">("all");
  const [openOpt, setOpenOpt] = useState<string | null>(null);

  // deep-link from the command palette: /opcoes?t=PETR4
  useEffect(() => {
    const t = new URLSearchParams(window.location.search).get("t");
    if (t) {
      const u = t.toUpperCase();
      // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time deep-link sync from the URL
      setTicker(u);
      setInput(u);
    }
  }, []);

  useEffect(() => {
    let alive = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset loading when the ticker changes
    setLoading(true);
    fetch(`${API}/chain/${ticker}`)
      .then((r) => r.json())
      .then((d: Row[]) => {
        if (!alive) return;
        setRows(Array.isArray(d) ? d : []);
        setProv(d?.[0]?.provenance ?? "");
        setLoading(false);
      })
      .catch(() => {
        if (alive) {
          setRows([]);
          setLoading(false);
        }
      });
    return () => {
      alive = false;
    };
  }, [ticker]);

  const filtered = rows.filter((r) => kind === "all" || r.kind === kind).slice(0, 200);

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setTicker(input.toUpperCase().trim() || "PETR4");
          }}
          className="flex min-w-0 flex-1 gap-2 sm:flex-none"
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            aria-label="subjacente"
            placeholder="subjacente (ex: PETR4)"
            className="min-w-0 flex-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-3 py-2 text-[13px] outline-none sm:flex-none"
            style={{ color: "var(--text-primary)" }}
          />
          <button className="rounded-lg border border-[var(--border-subtle)] px-3 py-2 text-[13px] text-[var(--text-secondary)]">
            Buscar
          </button>
        </form>
        <div className="ml-auto flex gap-1.5">
          {(["all", "call", "put"] as const).map((k) => (
            <button
              key={k}
              onClick={() => setKind(k)}
              className={`rounded-lg px-3 py-1.5 text-[12px] ${
                kind === k ? "bg-[var(--bg-surface)] text-[var(--accent)]" : "text-[var(--text-secondary)]"
              }`}
            >
              {k === "all" ? "Tudo" : k === "call" ? "Calls" : "Puts"}
            </button>
          ))}
        </div>
      </div>

      <VolHistory ticker={ticker} />
      <CalibrationPanel ticker={ticker} />
      <EdgeMap ticker={ticker} />
      <KernelMap ticker={ticker} />
      <FairIv ticker={ticker} />
      <IvSurface ticker={ticker} />

      {loading ? (
        <p className="text-[13px] text-[var(--text-tertiary)]">carregando cadeia…</p>
      ) : rows.length === 0 ? (
        <p className="text-[13px] text-[var(--text-secondary)]">
          Sem cadeia para {ticker}. Rode a ingestão e tente um subjacente líquido (PETR4, VALE3, BOVA11).
        </p>
      ) : (
        <>
          <div className="overflow-x-auto rounded-xl border border-[var(--border-subtle)]">
            <table className="w-full min-w-[640px] text-[13px]">
              <thead>
                <tr className="bg-[var(--bg-surface)] text-left text-[var(--text-secondary)]">
                  <th className="px-4 py-2.5 font-normal">Série</th>
                  <th className="px-3 py-2.5 font-normal">Tipo</th>
                  <ColHead label="Strike" tip="Preço combinado: o valor pelo qual a opção dá direito de comprar (call) ou vender (put) o ativo." />
                  <ColHead label="Último" tip="Prêmio: o preço pago (comprador) ou recebido (vendedor) por 1 opção hoje." />
                  <ColHead label="IV" tip="Volatilidade implícita: o 'nervosismo' que o mercado embute no preço da opção (% ao ano)." />
                  <ColHead label="Δ" tip="Delta: quanto o preço da opção sobe (aprox.) se o ativo subir R$1. Também ≈ a chance de virar exercício." />
                  <ColHead label="Γ" tip="Gama: o quão rápido o Delta muda quando o ativo se mexe." />
                  <ColHead label="Vega" tip="Vega: quanto a opção ganha/perde se a volatilidade subir 1 ponto." />
                  <ColHead label="θ/dia" tip="Theta: o desgaste do tempo — quanto a opção perde por dia, só pelo calendário." last />
                </tr>
              </thead>
              <tbody>
                {filtered.map((r, i) => (
                  <tr
                    key={`${r.ticker}-${i}`}
                    onClick={() => setOpenOpt(r.ticker)}
                    title={`Analisar ${r.ticker}`}
                    className="atlas-row cursor-pointer border-t border-[var(--border-subtle)]"
                  >
                    <td className="mono px-4 py-2.5 font-medium" style={{ color: "var(--accent)" }}>{r.ticker}</td>
                    <td className="px-3 py-2.5">
                      <span className="text-[11px]" style={{ color: r.kind === "call" ? "#7FB6F0" : "#C3A0F5" }}>
                        {r.kind === "call" ? "Call" : "Put"}
                      </span>
                    </td>
                    <td className="mono px-3 py-2.5 text-right">{fmt(r.strike)}</td>
                    <td className="mono px-3 py-2.5 text-right">{fmt(r.last)}</td>
                    <td className="mono px-3 py-2.5 text-right">{r.iv != null ? `${(r.iv * 100).toFixed(0)}%` : "—"}</td>
                    <td className="mono px-3 py-2.5 text-right">{fmt(r.delta)}</td>
                    <td className="mono px-3 py-2.5 text-right">{fmt(r.gamma, 4)}</td>
                    <td className="mono px-3 py-2.5 text-right">{fmt(r.vega)}</td>
                    <td className="mono px-4 py-2.5 text-right" style={{ color: r.theta != null && r.theta < 0 ? "var(--down)" : undefined }}>{fmt(r.theta, 3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-3 text-[11px] text-[var(--text-tertiary)]">
            fonte: {prov} · IV/gregas (Bjerksund-Stensland, americana) · {filtered.length} séries · clique numa série para analisar
          </div>
        </>
      )}

      {openOpt ? <OptionPanel ticker={openOpt} onClose={() => setOpenOpt(null)} /> : null}
    </div>
  );
}

function ColHead({ label, tip, last }: { label: string; tip: string; last?: boolean }) {
  return (
    <th className={`${last ? "px-4" : "px-3"} py-2.5 text-right font-normal`}>
      <span className="inline-flex items-center justify-end gap-1">
        {label} <InfoTip text={tip} />
      </span>
    </th>
  );
}
