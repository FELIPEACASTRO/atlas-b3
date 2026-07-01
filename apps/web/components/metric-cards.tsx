"use client";

import { useEffect, useState } from "react";
import { LineChart, Flame, Snowflake, BarChart3 } from "lucide-react";

import { InfoTip } from "@/components/info-tip";

type Summary = {
  provenance: string;
  asof: string | null;
  underlyings: number;
  com_sinal: number;
  rico: number;
  barato: number;
  vol_total: number;
  bova11: number | null;
};

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

function fmtVol(n: number): string {
  if (n >= 1e9) return `R$ ${(n / 1e9).toFixed(1)} bi`;
  if (n >= 1e6) return `R$ ${(n / 1e6).toFixed(0)} mi`;
  return `R$ ${n.toLocaleString("pt-BR", { maximumFractionDigits: 0 })}`;
}

export function MetricCards() {
  const [s, setS] = useState<Summary | null>(null);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    let alive = true;
    fetch(`${API}/summary`)
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status));
        return r.json();
      })
      .then((d: Summary) => alive && setS(d))
      .catch(() => alive && setOffline(true));
    return () => {
      alive = false;
    };
  }, []);

  const cards = [
    {
      label: "BOVA11 (ETF Ibov)",
      value: s?.bova11 != null ? s.bova11.toFixed(2) : "—",
      icon: LineChart,
      tint: "var(--text-secondary)",
      tip: "BOVA11 é o ETF que segue o Ibovespa — o principal índice da Bolsa, um termômetro geral do mercado. O valor é o preço de fechamento do dia (EOD), em reais.",
    },
    {
      label: "Vol cara (heur.)",
      value: s ? String(s.rico) : "—",
      sub: s ? `/ ${s.com_sinal}` : undefined,
      accent: true,
      icon: Flame,
      tint: "var(--accent)",
      tip: "Quantos ativos estão hoje com a volatilidade CARA (IV implícita acima da RV realizada) — o prêmio das opções está 'gordo', terreno de quem vende. O número após a barra ('/') é o total de ativos com sinal de vol no dia. Heurística, não recomendação.",
    },
    {
      label: "Vol barata (heur.)",
      value: s ? String(s.barato) : "—",
      icon: Snowflake,
      tint: "var(--up)",
      tip: "Quantos ativos estão hoje com a volatilidade BARATA (IV implícita abaixo da RV realizada) — as opções estão baratas frente ao que o ativo oscilou, terreno de quem compra. Heurística, não recomendação.",
    },
    {
      label: "Vol. do dia",
      value: s ? fmtVol(s.vol_total) : "—",
      icon: BarChart3,
      tint: "var(--text-secondary)",
      tip: "Volume financeiro total negociado no dia, somando todos os ativos (a liquidez do mercado). Quanto maior, mais fácil entrar e sair de posições sem mexer muito no preço.",
    },
  ];

  return (
    <>
      <div className="mb-3 grid grid-cols-2 gap-3 md:grid-cols-4">
        {cards.map((c, i) => {
          const Icon = c.icon;
          return (
            <div
              key={c.label}
              className="atlas-card atlas-rise rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-4"
              style={{ animationDelay: `${i * 60}ms` }}
            >
              <div className="mb-1.5 flex items-center justify-between">
                <span className="inline-flex items-center gap-1 text-[12px] text-[var(--text-secondary)]">
                  {c.label}
                  <InfoTip text={c.tip} />
                </span>
                <span className="grid h-6 w-6 place-items-center rounded-md" style={{ background: "color-mix(in oklch, " + c.tint + " 14%, transparent)", color: c.tint }}>
                  <Icon size={13} />
                </span>
              </div>
              <div className="flex items-baseline gap-1.5">
                <span className={`mono text-xl font-medium ${c.accent ? "text-[var(--accent)]" : ""}`}>{c.value}</span>
                {c.sub ? <span className="text-[12px] text-[var(--text-tertiary)]">{c.sub}</span> : null}
              </div>
            </div>
          );
        })}
      </div>
      <div className="mb-4 text-[11px] text-[var(--text-tertiary)]">
        fonte: {offline ? "API fora do ar" : s?.provenance ?? "carregando…"}
      </div>
    </>
  );
}
