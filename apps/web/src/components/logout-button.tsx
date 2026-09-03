"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

const LOGOUT_EVENT = "demodirector:logout";

export function LogoutButton({ compact = false }: { compact?: boolean }) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);

  async function logout() {
    setLoading(true);
    try {
      await fetch("/api/auth/logout", { method: "POST", cache: "no-store" });
    } catch {
      // The local cookie is still expired by the web route when reachable; clear browser state.
    } finally {
      sessionStorage.clear();
      localStorage.setItem(LOGOUT_EVENT, String(Date.now()));
      if (typeof BroadcastChannel !== "undefined") {
        const channel = new BroadcastChannel(LOGOUT_EVENT);
        channel.postMessage("logout");
        channel.close();
      }
      router.replace("/login?loggedOut=1");
      router.refresh();
      setLoading(false);
    }
  }

  return (
    <button
      className={compact ? "logout-button compact" : "logout-button"}
      disabled={loading}
      onClick={logout}
      type="button"
    >
      {loading ? "Logging out…" : "Log out"}
    </button>
  );
}
