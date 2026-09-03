import { NextResponse } from "next/server";

import { apiBaseUrl, apiHeaders } from "@/lib/auth-session";

export async function GET() {
  try {
    const upstream = await fetch(new URL("/auth/session", apiBaseUrl()), {
      headers: await apiHeaders(),
      cache: "no-store",
    });
    return NextResponse.json(await upstream.json(), {
      status: upstream.status,
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return NextResponse.json(
      { detail: { code: "authentication_required", message: "Authentication is required." } },
      { status: 401, headers: { "Cache-Control": "no-store" } },
    );
  }
}
