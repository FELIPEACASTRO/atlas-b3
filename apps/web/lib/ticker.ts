// Contexto leve de ativo: o ticker escolhido viaja entre as telas (Opções → Estratégias → Decisão)
// via localStorage, client-only. Lido só em useEffect (nunca no render → sem mismatch de hidratação SSR).
const KEY = "atlas.ticker";

export function readTicker(fallback = "PETR4"): string {
  if (typeof window === "undefined") return fallback;
  try {
    const t = window.localStorage.getItem(KEY);
    return t ? t.toUpperCase() : fallback;
  } catch {
    return fallback;
  }
}

export function writeTicker(t: string): void {
  if (typeof window === "undefined" || !t) return;
  try {
    window.localStorage.setItem(KEY, t.toUpperCase());
  } catch {
    /* localStorage indisponível (modo privado) — ignora silenciosamente */
  }
}
