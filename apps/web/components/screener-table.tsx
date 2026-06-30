"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowDown, ArrowUp } from "lucide-react";

import { InfoTip } from "@/components/info-tip";

type Row = {
  ticker: string;
  tipo: string;
  ultimo: number | null;
  var_pct: number | null;
  liquidez: number | null;
  iv: number | null;
  iv_vs_rv: string | null;
  iv_rank: number | null;
  vrp: number | null;
  pc_ratio: number | null;
  skew: number | null;
  provenance: string;
  asof: string;
};

type SortCol = "ultimo" | "var_pct" | "liquidez" | "iv" | "iv_rank" | "vrp";

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

function fmtLiq(n: number): string {
  if (n >= 1e9) return `R$ ${(n / 1e9).toFixed(1)} bi`;
  if (n >= 1e6) return `R$ ${(n / 1e6).toFixed(0)} mi`;
  return `R$ ${n.toLocaleString("pt-BR", { maximumFractionDigits: 0 })}`;
}

function tipoLabel(t: string): string {
  return t === "acao" ? "Ação" : t === "indice" ? "Índice" : t === "call" ? "Call" : t === "put" ? "Put" : t;
}

function SigBadge({ sig }: { sig: string | null }) {
  if (sig === "rico")
    return (
      <span className="rounded px-2 py-0.5 text-[11px]" style={{ background: "color-mix(in oklch, var(--accent) 18%, transparent)", color: "var(--accent)" }}>
        Rico
      </span>
    );
  if (sig === "barato")
    return (
      <span className="rounded px-2 py-0.5 text-[11px]" style={{ background: "color-mix(in oklch, var(--up) 18%, transparent)", color: "var(--up)" }}>
        Barato
      </span>
    );
  return <span className="text-[var(--text-tertiary)]">—</span>;
}

/** Sortable, right-aligned column header. The sort button and the InfoTip are
 *  siblings (never nested buttons). */
function SortTh({
  label, col, sort, onSort, tip, last,
}: {
  label: string;
  col: SortCol;
  sort: { col: SortCol | null; dir: 1 | -1 };
  onSort: (c: SortCol) => void;
  tip?: string;
  last?: boolean;
}) {
  const active = sort.col === col;
  return (
    <th className={`${last ? "px-4" : "px-3"} py-2.5 text-right font-normal`}>
      <span className="inline-flex items-center justify-end gap-1">
        <button
          type="button"
          onClick={() => onSort(col)}
          className={`inline-flex items-center gap-0.5 hover:text-[var(--accent)] ${active ? "text-[var(--accent)]" : ""}`}
          title={`Ordenar por ${label}`}
        >
          {label}
          {active ? (sort.dir === 1 ? <ArrowUp size={11} /> : <ArrowDown size={11} />) : null}
        </button>
        {tip ? <InfoTip text={tip} /> : null}
      </span>
    </th>
  );
}

export function ScreenerTable({ limit = 40 }: { limit?: number }) {
  const router = useRouter();
  const [rows, setRows] = useState<Row[]>([]);
  const [provenance, setProvenance] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [query, setQuery] = useState("");
  const [sig, setSig] = useState<"all" | "rico" | "barato">("all");
  const [sort, setSort] = useState<{ col: SortCol | null; dir: 1 | -1 }>({ col: null, dir: -1 });

  useEffect(() => {
    let alive = true;
    fetch(`${API}/screener`)
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status));
        return r.json();
      })
      .then((data: Row[]) => {
        if (!alive) return;
        setRows(Array.isArray(data) ? data : []);
        setProvenance(Array.isArray(data) && data.length ? data[0].provenance : "");
        setLoading(false);
      })
      .catch(() => {
        if (!alive) return;
        setError(true);
        setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  function toggleSort(col: SortCol) {
    setSort((s) => (s.col === col ? { col, dir: (s.dir === 1 ? -1 : 1) as 1 | -1 } : { col, dir: -1 }));
  }

  let view = rows.filter((r) => r.ticker.toUpperCase().includes(query.toUpperCase()));
  if (sig !== "all") view = view.filter((r) => r.iv_vs_rv === sig);
  if (sort.col) {
    const col = sort.col;
    view = [...view].sort((a, b) => {
      const av = a[col], bv = b[col];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      return (av < bv ? -1 : av > bv ? 1 : 0) * sort.dir;
    });
  }
  const filtered = view.slice(0, limit);

  const chip = (key: "all" | "rico" | "barato", text: string) => (
    <button
      type="button"
      onClick={() => setSig(key)}
      className={`rounded-lg px-3 py-1.5 text-[12px] ${
        sig === key ? "bg-[var(--bg-surface)] text-[var(--accent)]" : "text-[var(--text-secondary)] hover:bg-[var(--bg-surface)]"
      }`}
    >
      {text}
    </button>
  );

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="filtrar por ticker…"
          className="w-56 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-3 py-2 text-[13px] outline-none"
          style={{ color: "var(--text-primary)" }}
        />
        <div className="flex gap-1.5">
          {chip("all", "Todos")}
          {chip("rico", "Rico")}
          {chip("barato", "Barato")}
        </div>
      </div>
      {loading ? (
        <p className="text-[13px] text-[var(--text-tertiary)]">carregando o mercado…</p>
      ) : error ? (
        <p className="text-[13px] text-[var(--text-secondary)]">
          Sem dado de mercado — confira se o backend está no ar e se a ingestão foi rodada (cli update).
        </p>
      ) : rows.length === 0 ? (
        <p className="text-[13px] text-[var(--text-secondary)]">Nenhum ativo na base no momento.</p>
      ) : (
        <>
          <div className="overflow-x-auto rounded-xl border border-[var(--border-subtle)]">
            <table className="w-full min-w-[760px] text-[13px]">
              <thead>
                <tr className="bg-[var(--bg-surface)] text-left text-[var(--text-secondary)]">
                  <th className="px-4 py-2.5 font-normal">Ativo</th>
                  <th className="px-3 py-2.5 font-normal">Tipo</th>
                  <SortTh label="Último" col="ultimo" sort={sort} onSort={toggleSort} />
                  <SortTh label="Var %" col="var_pct" sort={sort} onSort={toggleSort} />
                  <SortTh label="Liquidez" col="liquidez" sort={sort} onSort={toggleSort} />
                  <SortTh label="IV" col="iv" sort={sort} onSort={toggleSort} tip="Volatilidade implícita: o 'nervosismo' que o mercado embute no preço da opção (% ao ano)." />
                  <SortTh label="IV Rank" col="iv_rank" sort={sort} onSort={toggleSort} tip="Onde a IV de hoje está na faixa mín–máx da janela (~1 ano). 0 = mínimo, 100 = máximo. Alto = volatilidade cara vs a própria história do ativo." />
                  <SortTh label="VRP" col="vrp" sort={sort} onSort={toggleSort} tip="Prêmio de variância = IV − RV, em pontos de vol. Positivo = implícita acima da realizada (você é pago por vender volatilidade)." />
                  <th className="px-4 py-2.5 text-right font-normal">
                    <span className="inline-flex items-center gap-1">IV vs RV
                      <InfoTip text="Heurística (não recomendação): IV implícita vs RV realizada. Rico = IV > RV; Barato = IV < RV." />
                    </span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r) => (
                  <tr
                    key={r.ticker}
                    onClick={() => router.push(`/opcoes?t=${r.ticker}`)}
                    className="atlas-row cursor-pointer border-t border-[var(--border-subtle)]"
                    title={`Abrir cadeia de ${r.ticker}`}
                  >
                    <td className="mono px-4 py-2.5 font-medium" style={{ color: "var(--accent)" }}>{r.ticker}</td>
                    <td className="px-3 py-2.5 text-[var(--text-secondary)]">{tipoLabel(r.tipo)}</td>
                    <td className="mono px-3 py-2.5 text-right">
                      {r.ultimo != null ? r.ultimo.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "—"}
                    </td>
                    <td className="mono px-3 py-2.5 text-right" style={{ color: r.var_pct == null ? undefined : r.var_pct >= 0 ? "var(--up)" : "var(--down)" }}>
                      {r.var_pct != null ? `${r.var_pct >= 0 ? "+" : ""}${r.var_pct.toFixed(1)}%` : "—"}
                    </td>
                    <td className="mono px-3 py-2.5 text-right">{r.liquidez != null ? fmtLiq(r.liquidez) : "—"}</td>
                    <td className="mono px-3 py-2.5 text-right">{r.iv != null ? `${(r.iv * 100).toFixed(0)}%` : "—"}</td>
                    <td className="mono px-3 py-2.5 text-right">{r.iv_rank != null ? r.iv_rank.toFixed(0) : "—"}</td>
                    <td className="mono px-3 py-2.5 text-right" style={{ color: r.vrp == null ? undefined : r.vrp >= 0 ? "var(--accent)" : "var(--up)" }}>
                      {r.vrp != null ? `${r.vrp >= 0 ? "+" : ""}${(r.vrp * 100).toFixed(1)}` : "—"}
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      <SigBadge sig={r.iv_vs_rv} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-4 text-[11.5px] text-[var(--text-tertiary)]">
            <span className="flex items-center gap-1.5">
              <i className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: "var(--accent)" }} /> Rico = IV &gt; RV
            </span>
            <span className="flex items-center gap-1.5">
              <i className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: "var(--up)" }} /> Barato = IV &lt; RV
            </span>
            <span>{filtered.length} de {view.length} ativos · clique num cabeçalho para ordenar</span>
            <span className="ml-auto">fonte: {provenance || "—"} · heurística, não recomendação</span>
          </div>
        </>
      )}
    </div>
  );
}
