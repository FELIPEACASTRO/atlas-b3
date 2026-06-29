"use client";

import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function LiveBadge() {
  const [label, setLabel] = useState("EOD");
  const [ok, setOk] = useState(false);

  useEffect(() => {
    let alive = true;
    fetch(`${API}/summary`)
      .then((r) => r.json())
      .then((d: { asof: string | null }) => {
        if (!alive) return;
        if (d.asof) {
          setLabel(`EOD ${d.asof}`);
          setOk(true);
        } else {
          setLabel("fixture (sem dado real)");
        }
      })
      .catch(() => alive && setLabel("API offline"));
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className="flex items-center gap-2 text-[13px] text-[var(--text-secondary)]">
      <span className="h-2 w-2 rounded-full" style={{ background: ok ? "var(--up)" : "var(--text-tertiary)" }} />
      {label}
    </div>
  );
}
