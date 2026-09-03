import { NextRequest, NextResponse } from "next/server";

import { SESSION_COOKIE } from "@/lib/auth-session";

export function proxy(request: NextRequest) {
  if (process.env.DEMO_AUTH_REQUIRED !== "true") return NextResponse.next();
  if (request.cookies.has(SESSION_COOKIE)) return NextResponse.next();
  const login = new URL("/login", request.url);
  return NextResponse.redirect(login);
}

export const config = {
  matcher: ["/", "/projects/:path*"],
};
