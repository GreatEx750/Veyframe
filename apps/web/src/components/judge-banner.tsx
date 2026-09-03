"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";

export function JudgeBanner() {
  const pathname = usePathname();
  const [expiresAt, setExpiresAt] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    fetch("/api/auth/session", { cache: "no-store" })
      .then((response) => (response.ok ? response.json() : null))
      .then((body: { status?: string; session?: { expires_at?: string; user?: { role?: string } } } | null) => {
        if (!active) return;
        setExpiresAt(
          body?.status === "active" && body.session?.user?.role === "judge_demo"
            ? body.session.expires_at ?? null
            : null,
        );
      })
      .catch(() => { if (active) setExpiresAt(null); });
    return () => { active = false; };
  }, [pathname]);

  if (!expiresAt) return null;

  async function reset() {
    setMessage("Resetting…");
    const response = await fetch("/api/judge/reset", { method: "POST", cache: "no-store" });
    setMessage(response.ok ? "Sandbox reset." : "Reset unavailable.");
  }

  return (
    <aside className="judge-banner" role="status">
      <span><b>Judge demo</b> · Pre-generated 20-second workflow · No paid AI calls</span>
      <small>Expires {new Date(expiresAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</small>
      <button onClick={reset} type="button">Reset sandbox</button>
      {message && <em>{message}</em>}
    </aside>
  );
}
