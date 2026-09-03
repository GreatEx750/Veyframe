import { cookies } from "next/headers";
import { NextResponse } from "next/server";

export const SESSION_COOKIE = "demodirector_session";

export function apiBaseUrl() {
  return process.env.API_BASE_URL ?? "http://localhost:8000";
}

export async function apiHeaders(extra: HeadersInit = {}): Promise<Headers> {
  const headers = new Headers(extra);
  try {
    const token = (await cookies()).get(SESSION_COOKIE)?.value;
    if (token) headers.set("Authorization", `Bearer ${token}`);
  } catch {
    // Route unit tests may run without a Next request store.
  }
  return headers;
}

export function setSessionCookie(
  response: NextResponse,
  token: string,
  expiresAt: string,
) {
  response.cookies.set({
    name: SESSION_COOKIE,
    value: token,
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    expires: new Date(expiresAt),
  });
}

export function clearSessionCookie(response: NextResponse) {
  response.cookies.set({
    name: SESSION_COOKIE,
    value: "",
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    expires: new Date(0),
  });
}
