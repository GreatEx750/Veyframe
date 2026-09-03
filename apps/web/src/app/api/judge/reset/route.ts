import { NextResponse } from "next/server";

import { apiBaseUrl, apiHeaders } from "@/lib/auth-session";

export async function POST() {
  try {
    const upstream = await fetch(new URL("/judge/reset", apiBaseUrl()), {
      method: "POST",
      headers: await apiHeaders(),
      cache: "no-store",
    });
    return NextResponse.json(await upstream.json(), {
      status: upstream.status,
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return NextResponse.json({ detail: "Judge sandbox could not be reset" }, { status: 503 });
  }
}
