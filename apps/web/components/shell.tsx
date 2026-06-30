"use client";

import Link from "next/link";
import { useState } from "react";
import {
  Radar,
  Filter,
  CandlestickChart,
  Briefcase,
  UserSearch,
  MessageSquare,
  Search,
  Menu,
  X,
} from "lucide-react";

import { LiveBadge } from "@/components/live-badge";
import { CommandPalette } from "@/components/command-palette";

const modules = [
  { icon: Radar, label: "Radar", href: "/" },
  { icon: Filter, label: "Screener", href: "/screener" },
  { icon: CandlestickChart, label: "Opções", href: "/opcoes" },
  { icon: Briefcase, label: "Carteira", href: "/carteira" },
  { icon: UserSearch, label: "Analista", href: "/analista" },
  { icon: MessageSquare, label: "Chat", href: "/chat" },
];

function Brand() {
  return (
    <div className="mb-2 flex items-center gap-2 px-2 py-3">
      <div className="grid h-8 w-8 place-items-center rounded-lg bg-[var(--accent)] text-[var(--bg-base)]">
        <Radar size={18} />
      </div>
      <div>
        <div className="text-sm font-medium">ATLAS</div>
        <div className="text-[11px] text-[var(--text-tertiary)]">terminal B3</div>
      </div>
    </div>
  );
}

function NavLinks({ active, onNavigate }: { active: string; onNavigate?: () => void }) {
  return (
    <>
      {modules.map((m) => {
        const Icon = m.icon;
        const on = m.label === active;
        return (
          <Link
            key={m.label}
            href={m.href}
            onClick={onNavigate}
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
    </>
  );
}

export function Shell({
  active,
  children,
}: {
  active: string;
  children: React.ReactNode;
}) {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div className="flex min-h-screen">
      {/* Sidebar — fixed on laptop/desktop, hidden on mobile */}
      <aside className="hidden w-52 shrink-0 flex-col gap-1 border-r border-[var(--border-subtle)] p-3 md:flex">
        <Brand />
        <NavLinks active={active} />
      </aside>

      {/* Mobile drawer */}
      {menuOpen ? (
        <div className="fixed inset-0 z-50 md:hidden" role="dialog" aria-modal="true">
          <div className="absolute inset-0 bg-black/55" onClick={() => setMenuOpen(false)} />
          <aside className="absolute left-0 top-0 flex h-full w-64 flex-col gap-1 border-r border-[var(--border-subtle)] bg-[var(--bg-base)] p-3 shadow-2xl">
            <button
              onClick={() => setMenuOpen(false)}
              aria-label="fechar menu"
              className="mb-1 grid h-8 w-8 place-items-center self-end rounded-lg text-[var(--text-secondary)] hover:bg-[var(--bg-surface)]"
            >
              <X size={18} />
            </button>
            <Brand />
            <NavLinks active={active} onNavigate={() => setMenuOpen(false)} />
          </aside>
        </div>
      ) : null}

      <main className="min-w-0 flex-1">
        <header className="flex h-14 items-center gap-2 border-b border-[var(--border-subtle)] px-3 md:px-5">
          <button
            onClick={() => setMenuOpen(true)}
            aria-label="abrir menu"
            className="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-[var(--text-secondary)] hover:bg-[var(--bg-surface)] md:hidden"
          >
            <Menu size={20} />
          </button>
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
      <CommandPalette />
    </div>
  );
}
