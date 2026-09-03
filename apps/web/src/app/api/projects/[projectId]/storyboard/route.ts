import { NextResponse } from "next/server";

import { apiHeaders } from "@/lib/auth-session";

type Context = { params: Promise<{ projectId: string }> };

async function proxy(request: Request, context: Context, method: "GET" | "PUT") {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";
  const { projectId } = await context.params;
  try {
    const response = await fetch(new URL(`/projects/${projectId}/storyboard`, apiBaseUrl), {
      method,
      headers: await apiHeaders(method === "PUT" ? { "Content-Type": "application/json" } : {}),
      body: method === "PUT" ? await request.text() : undefined,
      cache: "no-store",
    });
    return NextResponse.json(await response.json(), { status: response.status });
  } catch {
    return NextResponse.json({ detail: "The storyboard service is temporarily unavailable" }, { status: 503 });
  }
}

export function GET(request: Request, context: Context) {
  return proxy(request, context, "GET");
}

export function PUT(request: Request, context: Context) {
  return proxy(request, context, "PUT");
}
