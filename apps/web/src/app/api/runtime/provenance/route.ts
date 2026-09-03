import { NextResponse } from "next/server";

import { apiBaseUrl, apiHeaders } from "@/lib/auth-session";

export async function GET() {
  try {
    const headers = await apiHeaders();
    const [aiResponse, researchResponse] = await Promise.all([
      fetch(new URL("/ai/health", apiBaseUrl()), { headers, cache: "no-store" }),
      fetch(new URL("/research/health", apiBaseUrl()), { headers, cache: "no-store" }),
    ]);
    if (!aiResponse.ok || !researchResponse.ok) {
      return NextResponse.json({ detail: "Runtime provenance is temporarily unavailable" }, { status: 502 });
    }
    return NextResponse.json({
      ai: await aiResponse.json(),
      research: await researchResponse.json(),
    });
  } catch {
    return NextResponse.json({ detail: "Runtime provenance is temporarily unavailable" }, { status: 503 });
  }
}
