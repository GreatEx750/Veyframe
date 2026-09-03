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
    if (pathname === "/login" || pathname === "/signup") return;
    let active = true;
    void fetch("/api/auth/session", { cache: "no-store" })
      .then(async (response) => {
        const body = await response.json() as { status?: string };
        if (active && (!response.ok || body.status !== "active")) {
          router.replace("/login?reason=session_expired");
          router.refresh();
        }
      })
      .catch(() => {
        if (active) {
          router.replace("/login?reason=session_expired");
          router.refresh();
        }
      });
    return () => {
      active = false;
    };
  }, [pathname, router]);

  return children;
}
