import { NextResponse } from "next/server";

import { apiHeaders } from "@/lib/auth-session";

type Context = { params: Promise<{ projectId: string }> };

export async function POST(request: Request, context: Context) {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";
  const { projectId } = await context.params;
  try {
    const response = await fetch(new URL(`/projects/${projectId}/timeline/apply`, apiBaseUrl), {
      method: "POST",
      headers: await apiHeaders({ "Content-Type": "application/json" }),
      body: await request.text(),
      cache: "no-store",
    });
    return NextResponse.json(await response.json(), { status: response.status });
  } catch {
    return NextResponse.json({ detail: "Timeline edits are temporarily unavailable" }, { status: 503 });
  }
}
