import { NextResponse } from "next/server";

import { apiBaseUrl, apiHeaders, clearSessionCookie } from "@/lib/auth-session";

export async function GET() {
  try {
    const upstream = await fetch(new URL("/auth/session", apiBaseUrl()), {
      headers: await apiHeaders(),
      cache: "no-store",
    });
    const body = await upstream.json() as { status?: string };
    const response = NextResponse.json(body, {
      status: upstream.status,
      headers: { "Cache-Control": "no-store" },
    });
    if (!upstream.ok || body.status !== "active") clearSessionCookie(response);
    return response;
  } catch {
    const response = NextResponse.json(
      { detail: { code: "authentication_required", message: "Authentication is required." } },
      { status: 401, headers: { "Cache-Control": "no-store" } },
    );
    clearSessionCookie(response);
    return response;
  }
}
