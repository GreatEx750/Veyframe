import { NextResponse } from "next/server";

import { apiBaseUrl, apiHeaders, clearSessionCookie } from "@/lib/auth-session";

export async function POST() {
  let body: unknown = {
    status: "already_absent",
    reason: "absent",
    message: "You are logged out.",
  };
  let status = 200;
  try {
    const upstream = await fetch(new URL("/auth/logout", apiBaseUrl()), {
      method: "POST",
      headers: await apiHeaders(),
      cache: "no-store",
    });
    body = await upstream.json();
    status = upstream.ok ? 200 : upstream.status;
  } catch {
    // The browser session is still cleared when the identity service is unavailable.
  }
  const response = NextResponse.json(body, {
    status,
    headers: { "Cache-Control": "no-store" },
  });
  clearSessionCookie(response);
  return response;
}
