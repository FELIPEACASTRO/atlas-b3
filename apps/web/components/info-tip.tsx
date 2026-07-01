"use client";

import { Info } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

/** A tiny ⓘ that reveals an explanation on hover/tap — for jargon like IV Rank,
 *  VRP, the greeks. The bubble is rendered in a PORTAL with position:fixed so it
 *  floats above everything and is never clipped by a table's `overflow-x-auto`
 *  (which used to hide it behind the table). Closes on Esc / scroll / outside tap. */
export function InfoTip({ text }: { text: string }) {
  const ref = useRef<HTMLButtonElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number; above: boolean } | null>(null);

  function show() {
    const r = ref.current?.getBoundingClientRect();
    if (!r) return;
    const above = r.top > 140; // enough room above? else drop below the icon
    setPos({ top: above ? r.top - 6 : r.bottom + 6, left: r.left + r.width / 2, above });
  }
  const hide = () => setPos(null);

  useEffect(() => {
    if (!pos) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && hide();
    const onScroll = () => hide();
    const onDown = (e: Event) => {
      if (ref.current && !ref.current.contains(e.target as Node)) hide();
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("scroll", onScroll, true); // capture: any scroll container
    document.addEventListener("mousedown", onDown);
    document.addEventListener("touchstart", onDown);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", onScroll, true);
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("touchstart", onDown);
    };
  }, [pos]);

  return (
    <>
      <button
        ref={ref}
        type="button"
        aria-label="ajuda"
        className="inline-flex cursor-help align-middle"
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          if (pos) hide();
          else show();
        }}
      >
        <Info size={11} className="text-[var(--text-tertiary)] transition-colors hover:text-[var(--accent)]" />
      </button>
      {pos && typeof document !== "undefined"
        ? createPortal(
            <span
              role="tooltip"
              className="pointer-events-none fixed z-[1000] w-56 rounded-lg border px-2.5 py-2 text-left text-[11px] font-normal leading-snug shadow-xl"
              style={{
                top: pos.top,
                left: pos.left,
                transform: `translateX(-50%) ${pos.above ? "translateY(-100%)" : ""}`.trim(),
                background: "var(--bg-elevated)",
                borderColor: "var(--border-subtle)",
                color: "var(--text-secondary)",
              }}
            >
              {text}
            </span>,
            document.body,
          )
        : null}
    </>
  );
}
