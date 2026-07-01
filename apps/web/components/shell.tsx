"use client";

import Link from "next/link";
import {
  Radar,
  Filter,
  CandlestickChart,
  Briefcase,
  UserSearch,
  Target,
  Gauge,
  MessageSquare,
  Search,
} from "lucide-react";

import { LiveBadge } from "@/components/live-badge";
import { CommandPalette } from "@/components/command-palette";

const modules = [
  { icon: Radar, label: "Radar", href: "/" },
  { icon: Filter, label: "Screener", href: "/screener" },
  { icon: CandlestickChart, label: "Opções", href: "/opcoes" },
  { icon: Briefcase, label: "Carteira", href: "/carteira" },
  { icon: UserSearch, label: "Analista", href: "/analista" },
  { icon: Target, label: "Estratégias", href: "/estrategias" },
  { icon: Gauge, label: "Decisão", href: "/decisao" },
  { icon: MessageSquare, label: "Chat", href: "/chat" },
];

function Logo({ withText = true }: { withText?: boolean }) {
  return (
    <div className="flex items-center gap-2">
      <div className="grid h-8 w-8 place-items-center rounded-lg bg-[var(--accent)] text-[var(--bg-base)]">
        <Radar size={18} />
      </div>
      {withText ? (
        <div>
          <div className="text-sm font-medium">ATLAS</div>
          <div className="text-[11px] text-[var(--text-tertiary)]">terminal B3</div>
        </div>
      ) : null}
    </div>
  );
}

export function Shell({
  active,
  children,
}: {
  active: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen">
      {/* Laptop/desktop: fixed sidebar (hidden on mobile) */}
      <aside className="hidden w-52 shrink-0 flex-col gap-1 border-r border-[var(--border-subtle)] p-3 md:flex">
        <div className="mb-2 px-2 py-3">
          <Logo />
        </div>
        {modules.map((m) => {
          const Icon = m.icon;
          const on = m.label === active;
          return (
            <Link
              key={m.label}
              href={m.href}
              className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm ${
                on
                  ? "bg-[var(--bg-surface)] text-[var(--accent)]"
                  : "text-[var(--text-secondary)] hover:bg-[var(--bg-surface)]"
              }`}
            >
              <Icon size={17} /> {m.label}
            </Link>
          );
        })}
      </aside>

      <main className="min-w-0 flex-1 pb-[68px] md:pb-0">
        <header className="flex h-14 items-center gap-2 border-b border-[var(--border-subtle)] px-3 md:px-5">
          {/* compact logo on mobile (the sidebar carries it on desktop) */}
          <Link href="/" className="md:hidden" aria-label="ATLAS — início">
            <Logo withText={false} />
          </Link>
          <button
            onClick={() => window.dispatchEvent(new Event("atlas:open-command"))}
            className="atlas-card flex min-w-0 flex-1 items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-3 py-1.5 text-[13px] text-[var(--text-tertiary)] md:w-72 md:flex-none"
          >
            <Search size={15} className="shrink-0" />
            <span className="truncate">Buscar ou comando</span>
            <span className="mono ml-auto hidden rounded border border-[var(--border-subtle)] px-1.5 text-[11px] sm:inline">⌘K</span>
          </button>
          <div className="shrink-0">
            <LiveBadge />
          </div>
        </header>
        <div className="p-3 md:p-5">{children}</div>
      </main>

      {/* Mobile: app-like bottom tab bar (hidden on desktop) */}
      <nav className="fixed bottom-0 left-0 right-0 z-40 flex border-t border-[var(--border-subtle)] bg-[var(--bg-base)] md:hidden">
        {modules.map((m) => {
          const Icon = m.icon;
          const on = m.label === active;
          return (
            <Link
              key={m.label}
              href={m.href}
              aria-current={on ? "page" : undefined}
              className={`flex flex-1 flex-col items-center gap-0.5 py-2 text-[9.5px] ${
                on ? "text-[var(--accent)]" : "text-[var(--text-tertiary)]"
              }`}
            >
              <Icon size={19} />
              {m.label}
            </Link>
          );
        })}
      </nav>

      <CommandPalette />
    </div>
  );
}
