import { judgeSessionSchema } from "@demodirector/contracts";
import { NextResponse } from "next/server";

import { apiBaseUrl, setSessionCookie } from "@/lib/auth-session";

export async function POST() {
  try {
    const upstream = await fetch(new URL("/auth/judge-session", apiBaseUrl()), {
      method: "POST",
      cache: "no-store",
    });
    const raw: unknown = await upstream.json();
    if (!upstream.ok) {
      return NextResponse.json(raw, {
        status: upstream.status,
        headers: { "Cache-Control": "no-store" },
      });
    }
    const result = judgeSessionSchema.parse(raw);
    const response = NextResponse.json(
      {
        session: result.session,
        sandbox: result.sandbox,
        capabilities: result.capabilities,
        landing_path: result.landing_path,
      },
      { headers: { "Cache-Control": "no-store" } },
    );
    setSessionCookie(response, result.session_token, result.session.expires_at);
    return response;
  } catch {
    return NextResponse.json(
      { detail: { message: "Judge demo is temporarily unavailable." } },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}
