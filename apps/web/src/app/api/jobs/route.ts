import { NextResponse } from "next/server";
import { apiBaseUrl, apiHeaders, clearSessionCookie } from "@/lib/auth-session";

export async function GET() {
  try {
    const response = await fetch(new URL("/jobs", apiBaseUrl()), { headers: await apiHeaders(), cache: "no-store" });
    const result = NextResponse.json(await response.json(), { status: response.status, headers: { "Cache-Control": "no-store" } });
    if (response.status === 401) clearSessionCookie(result);
    return result;
  } catch {
    return NextResponse.json({ detail: "Job status is temporarily unavailable" }, { status: 503 });
  }
}
