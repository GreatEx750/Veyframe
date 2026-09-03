import { NextResponse } from "next/server";

import { apiBaseUrl, apiHeaders } from "@/lib/auth-session";

export async function GET() {
  try {
    const response = await fetch(new URL("/projects", apiBaseUrl()), {
      headers: await apiHeaders(),
      cache: "no-store",
    });
    const body: unknown = await response.json();
    return NextResponse.json(body, { status: response.status });
  } catch {
    return NextResponse.json(
      { detail: "The project service is temporarily unavailable" },
      { status: 503 },
    );
  }
}

export async function POST(request: Request) {
  try {
    const response = await fetch(new URL("/projects", apiBaseUrl()), {
      method: "POST",
      headers: await apiHeaders({ "Content-Type": "application/json" }),
      body: await request.text(),
      cache: "no-store",
    });
    const body: unknown = await response.json();
    return NextResponse.json(body, { status: response.status });
  } catch {
    return NextResponse.json({ detail: "The project service is temporarily unavailable" }, { status: 503 });
  }
}
