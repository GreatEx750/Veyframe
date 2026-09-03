import { NextResponse } from "next/server";

import { apiHeaders } from "@/lib/auth-session";

export async function GET(
  _request: Request,
  context: { params: Promise<{ projectId: string }> },
) {
  const { projectId } = await context.params;
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";
  try {
    const response = await fetch(
      new URL(`/projects/${encodeURIComponent(projectId)}/exports/latest`, apiBaseUrl),
      { headers: await apiHeaders(), cache: "no-store" },
    );
    const body = (await response.json()) as Record<string, unknown>;
    if (typeof body.download_url === "string") {
      body.download_url = `/api${body.download_url}`;
    }
    return NextResponse.json(body, { status: response.status });
  } catch {
    return NextResponse.json(
      { detail: "The export service is temporarily unavailable" },
      { status: 503 },
    );
  }
}
