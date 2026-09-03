import { NextResponse } from "next/server";

import { apiHeaders } from "@/lib/auth-session";

type Context = { params: Promise<{ projectId: string; action: string }> };

export async function POST(_request: Request, context: Context) {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";
  const { projectId, action } = await context.params;
  if (action !== "undo" && action !== "redo") {
    return NextResponse.json({ detail: "Unknown timeline history action" }, { status: 404 });
  }
  try {
    const response = await fetch(new URL(`/projects/${projectId}/timeline/${action}`, apiBaseUrl), {
      method: "POST",
      headers: await apiHeaders(),
      cache: "no-store",
    });
    return NextResponse.json(await response.json(), { status: response.status });
  } catch {
    return NextResponse.json({ detail: "Timeline history is temporarily unavailable" }, { status: 503 });
  }
}
