"use client";

import { Info } from "lucide-react";

/** A tiny ⓘ that reveals an explanation on hover/focus — for jargon like IV Rank,
 *  VRP, the greeks. Keeps the tables readable while staying self-explanatory. */
export function InfoTip({ text }: { text: string }) {
  return (
    <span className="group relative inline-flex align-middle" tabIndex={0}>
      <Info size={11} className="cursor-help text-[var(--text-tertiary)] transition-colors group-hover:text-[var(--accent)]" />
      <span
        className="pointer-events-none absolute bottom-full left-1/2 z-30 mb-1.5 hidden w-56 -translate-x-1/2 rounded-lg border px-2.5 py-2 text-left text-[11px] font-normal leading-snug shadow-xl group-hover:block group-focus:block"
        style={{ background: "var(--bg-elevated)", borderColor: "var(--border-subtle)", color: "var(--text-secondary)" }}
      >
        {text}
      </span>
    </span>
  );
}
