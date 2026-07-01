import { Shell } from "@/components/shell";
import { ScreenerTable } from "@/components/screener-table";

export default function ScreenerPage() {
  return (
    <Shell active="Screener">
      <div className="mb-4">
        <h1 className="text-[15px] font-medium">Screener — rastreador de ativos</h1>
        <p className="text-[12px] text-[var(--text-tertiary)]">
          Filtre e ordene por volatilidade: procure vol cara para vender prêmio, ou vol barata para comprar. Clique num cabeçalho para ordenar e num ativo para abrir a cadeia de opções.
        </p>
      </div>
      <ScreenerTable limit={200} />
    </Shell>
  );
}
