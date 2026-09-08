"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

const LOGOUT_EVENT = "demodirector:logout";

export function LogoutButton({ navigation = false }: { navigation?: boolean }) {
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
      router.replace("/");
      router.refresh();
      setLoading(false);
    }
  }

  return (
    <button
      aria-label="Log out"
      className={navigation ? "logout-button navigation-logout" : "logout-button"}
      disabled={loading}
      onClick={logout}
      type="button"
    >
      {navigation ? (
        <svg aria-hidden="true" className="icon" viewBox="0 0 24 24">
          <path d="M10 5H5v14h5M14 8l4 4-4 4m4-4H9" />
        </svg>
      ) : null}
      <span>{loading ? "Logging out…" : "Log out"}</span>
    </button>
  );
}
