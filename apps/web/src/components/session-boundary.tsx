"use client";

import { useRouter } from "next/navigation";
import { ReactNode, useEffect } from "react";

const LOGOUT_EVENT = "demodirector:logout";

export function SessionBoundary({ children }: { children: ReactNode }) {
  const router = useRouter();

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

  return children;
}
