import { NextResponse } from "next/server";

import { apiBaseUrl, apiHeaders, clearSessionCookie } from "@/lib/auth-session";

function unavailable() {
  return NextResponse.json(
    { detail: { code: "session_check_unavailable", message: "Session check is temporarily unavailable." } },
    { status: 503, headers: { "Cache-Control": "no-store", "Retry-After": "3" } },
  );
}

export async function GET() {
  try {
    const upstream = await fetch(new URL("/auth/session", apiBaseUrl()), {
      headers: await apiHeaders(),
      cache: "no-store",
    });
    if (upstream.status >= 500 || upstream.status === 429) return unavailable();
    const body = await upstream.json() as { status?: string };
    const response = NextResponse.json(body, {
      status: upstream.status,
      headers: { "Cache-Control": "no-store" },
    });
    if (upstream.status === 401 || upstream.status === 403 ||
      ["absent", "expired", "revoked"].includes(body.status ?? "")) clearSessionCookie(response);
    return response;
  } catch {
    console.warn("Session check upstream connection or response failed; preserving session cookie.");
    return unavailable();
  }
}
