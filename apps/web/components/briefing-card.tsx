"use client";

import { useEffect, useState } from "react";
import { ThumbsUp, ThumbsDown, Flag, Scale } from "lucide-react";

type Sizing = { pct_capital: number; lotes: number; max_loss_brl: number };
type Briefing = {
  ticker: string;
  setup_facts: string;
  case_for: string[];
  case_against: string[];
  risk_reward: { max_gain_per_lot: number; max_loss_per_lot: number; breakeven: number; ratio: number };
  sizing: Record<string, Sizing>;
  invalidation: string;
  confidence: string;
  verdict: string;
  provenance: string;
};

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const PROFILES = ["conservador", "moderado", "agressivo"] as const;

function brl(n: number): string {
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
}

export function BriefingCard() {
  const [b, setB] = useState<Briefing | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let alive = true;
    fetch(`${API}/briefing/sample`)
      .then((r) => r.json())
      .then((data: Briefing) => {
        if (alive) setB(data);
      })
      .catch(() => alive && setError(true));
    return () => {
      alive = false;
    };
  }, []);

  if (error) return <p className="text-[13px] text-[var(--text-secondary)]">API offline — suba o backend para ver o briefing ao vivo.</p>;
  if (!b) return <p className="text-[13px] text-[var(--text-tertiary)]">carregando briefing…</p>;

  const rr = b.risk_reward;

  return (
    <div className="max-w-3xl">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <div className="grid h-8 w-8 place-items-center rounded-lg bg-[var(--accent)] text-[var(--bg-base)]">
            <UserSearchIcon />
          </div>
          <div>
            <div className="text-sm font-medium">Briefing do analista — {b.ticker}</div>
            <div className="text-[11px] text-[var(--text-tertiary)]">análise transparente, não recomendação</div>
          </div>
        </div>
        <span className="rounded-md px-2.5 py-1 text-[11px]" style={{ background: "color-mix(in oklch, var(--accent) 18%, transparent)", color: "var(--accent)" }}>
          confiança: {b.confidence}
        </span>
      </div>

      <div className="mb-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-3.5">
        <div className="mb-1 text-[11.5px] text-[var(--text-secondary)]">O setup (fato)</div>
        <div className="text-[13px]">{b.setup_facts}</div>
      </div>

      <div className="mb-3 grid gap-3 md:grid-cols-2">
        <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-3.5">
          <div className="mb-1 flex items-center gap-1.5 text-[11.5px]" style={{ color: "var(--up)" }}>
            <ThumbsUp size={14} /> A favor
          </div>
          <ul className="list-disc pl-4 text-[12.5px] text-[var(--text-secondary)]">
            {b.case_for.map((c, i) => <li key={i} className="my-1">{c}</li>)}
          </ul>
        </div>
        <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-3.5">
          <div className="mb-1 flex items-center gap-1.5 text-[11.5px]" style={{ color: "var(--down)" }}>
            <ThumbsDown size={14} /> Contra (o risco)
          </div>
          <ul className="list-disc pl-4 text-[12.5px] text-[var(--text-secondary)]">
            {b.case_against.map((c, i) => <li key={i} className="my-1">{c}</li>)}
          </ul>
        </div>
      </div>

      <div className="mb-3 grid grid-cols-2 gap-2.5 md:grid-cols-4">
        <Tile label="Ganho máx/lote" value={rr.max_gain_per_lot.toFixed(2)} color="var(--up)" />
        <Tile label="Perda máx/lote" value={rr.max_loss_per_lot.toFixed(2)} color="var(--down)" />
        <Tile label="Breakeven" value={rr.breakeven.toFixed(2)} />
        <Tile label="Risco/retorno" value={`1 : ${rr.ratio.toFixed(2)}`} />
      </div>

      <div className="mb-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-3.5">
        <div className="mb-2.5 text-[12.5px] font-medium">Tamanho sugerido — ousada ou não, você escolhe</div>
        <div className="grid grid-cols-3 gap-2.5">
          {PROFILES.map((p) => {
            const s = b.sizing[p];
            return (
              <div key={p} className="rounded-lg border border-[var(--border-subtle)] p-3">
                <div className="mb-1 text-[11px] capitalize text-[var(--text-tertiary)]">{p}</div>
                <div className="mono text-[15px] font-medium">{s.lotes} lotes</div>
                <div className="text-[11.5px] text-[var(--text-secondary)]">{(s.pct_capital * 100).toFixed(1)}% · perda máx {brl(s.max_loss_brl)}</div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="mb-2 flex items-start gap-2 text-[12px] text-[var(--text-secondary)]">
        <Flag size={14} style={{ color: "var(--accent)", marginTop: 2 }} />
        <span><b className="font-medium text-[var(--text-primary)]">Invalida se:</b> {b.invalidation}</span>
      </div>
      <div className="flex items-start gap-2 text-[12px] text-[var(--text-secondary)]">
        <Scale size={14} style={{ marginTop: 2 }} />
        <span><b className="font-medium text-[var(--text-primary)]">Veredito:</b> {b.verdict}</span>
      </div>

      <div className="mt-3 text-[11px] text-[var(--text-tertiary)]">fonte: {b.provenance}</div>
    </div>
  );
}

function Tile({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-3">
      <div className="text-[11px] text-[var(--text-secondary)]">{label}</div>
      <div className="mono text-[15px] font-medium" style={color ? { color } : undefined}>{value}</div>
    </div>
  );
}

function UserSearchIcon() {
  return <span className="text-[15px] leading-none">◎</span>;
}
