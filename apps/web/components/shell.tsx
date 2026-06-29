import Link from "next/link";
import {
  Radar,
  Filter,
  CandlestickChart,
  Briefcase,
  UserSearch,
  Search,
} from "lucide-react";

const modules = [
  { icon: Radar, label: "Radar", href: "/" },
  { icon: Filter, label: "Screener", href: "/" },
  { icon: CandlestickChart, label: "Opções", href: "/" },
  { icon: Briefcase, label: "Carteira", href: "/" },
  { icon: UserSearch, label: "Analista", href: "/analista" },
];

export function Shell({
  active,
  children,
}: {
  active: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen">
      <aside className="flex w-52 shrink-0 flex-col gap-1 border-r border-[var(--border-subtle)] p-3">
        <div className="mb-2 flex items-center gap-2 px-2 py-3">
          <div className="grid h-8 w-8 place-items-center rounded-lg bg-[var(--accent)] text-[var(--bg-base)]">
            <Radar size={18} />
          </div>
          <div>
            <div className="text-sm font-medium">ATLAS</div>
            <div className="text-[11px] text-[var(--text-tertiary)]">terminal B3</div>
          </div>
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

      <main className="min-w-0 flex-1">
        <header className="flex h-14 items-center justify-between gap-3 border-b border-[var(--border-subtle)] px-5">
          <div className="flex w-72 items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-3 py-1.5 text-[13px] text-[var(--text-tertiary)]">
            <Search size={15} /> Buscar ou comando
            <span className="mono ml-auto rounded border border-[var(--border-subtle)] px-1.5 text-[11px]">⌘K</span>
          </div>
          <div className="flex items-center gap-2 text-[13px] text-[var(--text-secondary)]">
            <span className="h-2 w-2 rounded-full" style={{ background: "var(--up)" }} /> ao vivo · EOD
          </div>
        </header>
        <div className="p-5">{children}</div>
      </main>
    </div>
  );
}
