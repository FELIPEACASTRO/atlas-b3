"use client";

import { useEffect } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";

export default function Error({ error, reset }: { error: Error; reset: () => void }) {
  useEffect(() => {
    // surface to the console for local debugging; never to the user
    console.error(error);
  }, [error]);

  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 p-8 text-center">
      <div className="grid h-12 w-12 place-items-center rounded-2xl" style={{ background: "color-mix(in oklch, var(--down) 14%, transparent)", color: "var(--down)" }}>
        <AlertTriangle size={22} />
      </div>
      <div>
        <p className="text-[14px] font-medium text-[var(--text-primary)]">Algo quebrou ao montar esta tela.</p>
        <p className="mt-1 text-[12.5px] text-[var(--text-tertiary)]">
          Pode ter sido uma resposta inesperada do servidor. Seus dados estão a salvo.
        </p>
      </div>
      <button
        onClick={reset}
        className="atlas-row flex items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-3.5 py-2 text-[13px] text-[var(--text-secondary)] hover:border-[color-mix(in_oklch,var(--accent)_40%,var(--border-subtle))]"
      >
        <RotateCcw size={14} /> Tentar de novo
      </button>
    </div>
  );
}
