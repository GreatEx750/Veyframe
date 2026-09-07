"use client";

import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect } from "react";

const LOGOUT_EVENT = "demodirector:logout";

export function SessionBoundary({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    const redirect = () => {
      router.replace("/login?loggedOut=1");
      router.refresh();
    };
    const onStorage = (event: StorageEvent) => {
      if (event.key === LOGOUT_EVENT) redirect();
    };
    window.addEventListener("storage", onStorage);
    const channel = typeof BroadcastChannel === "undefined" ? null : new BroadcastChannel(LOGOUT_EVENT);
    if (channel) channel.onmessage = redirect;
    return () => {
      window.removeEventListener("storage", onStorage);
      channel?.close();
    };
  }, [router]);

  useEffect(() => {
    if (pathname === "/" || pathname === "/login" || pathname === "/signup") return;
    let active = true;
    let retry: ReturnType<typeof setTimeout> | undefined;
    const retryLater = () => { if (active) retry = setTimeout(check, 3000); };
    const check = () => { void fetch("/api/auth/session", { cache: "no-store" })
      .then(async (response) => {
        if (response.status >= 500 || response.status === 429) { retryLater(); return; }
        const body = await response.json() as { status?: string };
        if (active && (response.status === 401 || response.status === 403 ||
          ["absent", "expired", "revoked"].includes(body.status ?? ""))) {
          router.replace("/login?reason=session_expired");
          router.refresh();
        } else if (body.status !== "active") retryLater();
      })
      .catch(retryLater);
    };
    check();
    return () => {
      active = false;
      clearTimeout(retry);
    };
  }, [pathname, router]);

  return children;
}
