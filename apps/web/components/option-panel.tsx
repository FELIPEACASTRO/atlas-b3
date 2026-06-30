"use client";

import { useEffect, useState } from "react";
import { X, ThumbsUp, ThumbsDown, TrendingUp, HandCoins, Sigma, Scale, Lightbulb, Microscope, Globe } from "lucide-react";

type Greek = { nome: string; valor: string; explicacao: string };
type Analysis = {
  ticker: string; underlying: string; kind: string; tipo_label: string;
  strike: number; venc: string; dte: number; last: number; spot: number;
  moneyness: string; moneyness_txt: string; intrinsic: number; extrinsic: number;
  iv: number | null; iv_rank: number | null; vrp: number | null;
  breakeven: number; max_perda_titular: number; custo_theta_dia: number;
  resumo: string; analogia: string; micro: string; macro: string;
  pros: string[]; contras: string[]; comprar: string; vender_sair: string;
  gregas: Greek[]; veredito: string; provenance: string;
};

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const pct = (v: number | null) => (v == null ? "—" : `${(v * 100).toFixed(0)}%`);
const brl = (v: number | null) => (v == null ? "—" : v.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 }));
const mnyColor = (m: string) => (m === "ITM" ? "var(--up)" : m === "OTM" ? "var(--text-tertiary)" : "var(--accent)");

function Stat({ label, value, tint }: { label: string; value: string; tint?: string }) {
  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-2.5 py-1.5">
      <div className="text-[10px] text-[var(--text-tertiary)]">{label}</div>
      <div className="mono text-[13px]" style={{ color: tint }}>{value}</div>
    </div>
  );
}

export function OptionPanel({ ticker, onClose }: { ticker: string; onClose: () => void }) {
  const [a, setA] = useState<Analysis | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    let alive = true;
    setA(null); setErr("");
    fetch(`${API}/option/${ticker}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(r)))
      .then((d) => alive && setA(d))
      .catch(() => alive && setErr("não foi possível analisar esta opção (sem dado/subjacente)"));
    return () => { alive = false; };
  }, [ticker]);

  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-40 flex justify-end"
      style={{ background: "color-mix(in oklch, var(--bg-base) 55%, transparent)", backdropFilter: "blur(4px)" }}
      onClick={onClose}
    >
      <div
        className="atlas-pop h-full w-[min(94vw,480px)] overflow-y-auto border-l border-[var(--border-subtle)] bg-[var(--bg-elevated)]"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-5 py-3.5">
          <div>
            <div className="mono text-[15px] font-medium">{ticker}</div>
            <div className="text-[11px] text-[var(--text-tertiary)]">análise transparente, não recomendação</div>
          </div>
          <button onClick={onClose} aria-label="fechar" className="grid h-8 w-8 place-items-center rounded-lg text-[var(--text-secondary)] hover:bg-[var(--bg-surface)]">
            <X size={16} />
          </button>
        </div>

        {err ? (
          <p className="px-5 py-6 text-[13px]" style={{ color: "var(--down)" }}>{err}</p>
        ) : !a ? (
          <p className="px-5 py-6 text-[13px] text-[var(--text-tertiary)]">analisando…</p>
        ) : (
          <div className="space-y-4 px-5 py-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-md px-2 py-0.5 text-[11px]" style={{ background: "color-mix(in oklch, var(--accent) 16%, transparent)", color: "var(--accent)" }}>
                {a.tipo_label}
              </span>
              <span className="rounded-md px-2 py-0.5 text-[11px]" style={{ background: "color-mix(in oklch, " + mnyColor(a.moneyness) + " 16%, transparent)", color: mnyColor(a.moneyness) }}>
                {a.moneyness} · {a.moneyness_txt}
              </span>
              <span className="text-[12px] text-[var(--text-tertiary)]">{a.dte} dias até {a.venc}</span>
            </div>

            <p className="text-[13px] leading-relaxed text-[var(--text-secondary)]">{a.resumo}</p>

            <div className="rounded-xl p-3" style={{ background: "color-mix(in oklch, var(--accent) 9%, transparent)" }}>
              <div className="mb-1 flex items-center gap-1.5 text-[12px]" style={{ color: "var(--accent)" }}>
                <Lightbulb size={13} /> Em palavras simples
              </div>
              <p className="text-[12.5px] leading-relaxed" style={{ color: "var(--text-primary)" }}>{a.analogia}</p>
            </div>

            <div className="grid grid-cols-3 gap-2">
              <Stat label="Strike" value={`R$ ${a.strike.toFixed(2)}`} />
              <Stat label={`Spot ${a.underlying}`} value={`R$ ${a.spot.toFixed(2)}`} />
              <Stat label="Último (prêmio)" value={`R$ ${a.last.toFixed(2)}`} />
              <Stat label="IV / IV Rank" value={`${pct(a.iv)} · ${a.iv_rank != null ? a.iv_rank.toFixed(0) : "—"}`} tint="var(--accent)" />
              <Stat label="Breakeven" value={`R$ ${a.breakeven.toFixed(2)}`} />
              <Stat label="θ/dia (contrato)" value={`R$ ${a.custo_theta_dia.toFixed(0)}`} tint="var(--down)" />
              <Stat label="Intrínseco" value={`R$ ${a.intrinsic.toFixed(2)}`} />
              <Stat label="Valor de tempo" value={`R$ ${a.extrinsic.toFixed(2)}`} />
              <Stat label="Perda máx (titular)" value={brl(a.max_perda_titular)} tint="var(--down)" />
            </div>

            <div className="rounded-xl border border-[var(--border-subtle)] p-3">
              <div className="mb-1 flex items-center gap-1.5 text-[12px] text-[var(--text-secondary)]">
                <Microscope size={13} /> No detalhe (esta opção)
              </div>
              <p className="text-[12.5px] leading-relaxed text-[var(--text-secondary)]">{a.micro}</p>
            </div>
            <div className="rounded-xl border border-[var(--border-subtle)] p-3">
              <div className="mb-1 flex items-center gap-1.5 text-[12px] text-[var(--text-secondary)]">
                <Globe size={13} /> No mercado (visão geral)
              </div>
              <p className="text-[12.5px] leading-relaxed text-[var(--text-secondary)]">{a.macro}</p>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl border border-[var(--border-subtle)] p-3">
                <div className="mb-1.5 flex items-center gap-1.5 text-[12px]" style={{ color: "var(--up)" }}>
                  <ThumbsUp size={13} /> A favor
                </div>
                <ul className="space-y-1.5">
                  {a.pros.map((p, i) => <li key={i} className="text-[12px] leading-snug text-[var(--text-secondary)]">• {p}</li>)}
                </ul>
              </div>
              <div className="rounded-xl border border-[var(--border-subtle)] p-3">
                <div className="mb-1.5 flex items-center gap-1.5 text-[12px]" style={{ color: "var(--down)" }}>
                  <ThumbsDown size={13} /> Contra / risco
                </div>
                <ul className="space-y-1.5">
                  {a.contras.map((p, i) => <li key={i} className="text-[12px] leading-snug text-[var(--text-secondary)]">• {p}</li>)}
                </ul>
              </div>
            </div>

            <div className="rounded-xl border p-3" style={{ borderColor: "color-mix(in oklch, var(--up) 30%, var(--border-subtle))" }}>
              <div className="mb-1.5 flex items-center gap-1.5 text-[12px]" style={{ color: "var(--up)" }}>
                <TrendingUp size={13} /> Se você COMPRAR (titular)
              </div>
              <p className="text-[12.5px] leading-relaxed text-[var(--text-secondary)]">{a.comprar}</p>
            </div>
            <div className="rounded-xl border p-3" style={{ borderColor: "color-mix(in oklch, var(--accent) 30%, var(--border-subtle))" }}>
              <div className="mb-1.5 flex items-center gap-1.5 text-[12px]" style={{ color: "var(--accent)" }}>
                <HandCoins size={13} /> Se você VENDER ou SAIR (lançador)
              </div>
              <p className="text-[12.5px] leading-relaxed text-[var(--text-secondary)]">{a.vender_sair}</p>
            </div>

            {a.gregas.length ? (
              <div className="rounded-xl border border-[var(--border-subtle)] p-3">
                <div className="mb-2 flex items-center gap-1.5 text-[12px] text-[var(--text-secondary)]">
                  <Sigma size={13} /> As gregas, traduzidas
                </div>
                <div className="space-y-2">
                  {a.gregas.map((g) => (
                    <div key={g.nome} className="flex gap-2.5">
                      <span className="mono shrink-0 rounded bg-[var(--bg-surface)] px-1.5 py-0.5 text-[11px]" style={{ minWidth: 78, textAlign: "center" }}>{g.valor}</span>
                      <span className="text-[12px] leading-snug text-[var(--text-secondary)]"><b className="text-[var(--text-primary)]">{g.nome}:</b> {g.explicacao}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="rounded-xl p-3" style={{ background: "color-mix(in oklch, var(--accent) 10%, transparent)" }}>
              <div className="mb-1 flex items-center gap-1.5 text-[12px]" style={{ color: "var(--accent)" }}>
                <Scale size={13} /> Veredito honesto
              </div>
              <p className="text-[12.5px] leading-relaxed" style={{ color: "var(--text-primary)" }}>{a.veredito}</p>
            </div>

            <div className="text-[11px] text-[var(--text-tertiary)]">fonte: {a.provenance} · modelo: IV/gregas americanas (Bjerksund-Stensland)</div>
          </div>
        )}
      </div>
    </div>
  );
}
