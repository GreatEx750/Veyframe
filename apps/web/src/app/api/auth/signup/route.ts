import { signupResultSchema } from "@demodirector/contracts";
import { NextResponse } from "next/server";

import { apiBaseUrl, setSessionCookie } from "@/lib/auth-session";

export async function POST(request: Request) {
  try {
    const upstream = await fetch(new URL("/auth/signup", apiBaseUrl()), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: await request.text(),
      cache: "no-store",
    });
    const raw: unknown = await upstream.json();
    if (!upstream.ok) {
      return NextResponse.json(raw, {
        status: upstream.status,
        headers: { "Cache-Control": "no-store" },
      });
    }
    const result = signupResultSchema.parse(raw);
    const response = NextResponse.json(
      { status: result.status, session: result.session, message: result.message },
      { status: upstream.status, headers: { "Cache-Control": "no-store" } },
    );
    if (result.session && result.session_token) {
      setSessionCookie(response, result.session_token, result.session.expires_at);
    }
    return response;
  } catch {
    return NextResponse.json(
      { detail: { code: "account_unavailable", message: "Account service is temporarily unavailable." } },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}
