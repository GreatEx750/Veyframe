import { NextResponse } from "next/server";

import { apiHeaders } from "@/lib/auth-session";

export async function POST(
  _request: Request,
  context: { params: Promise<{ projectId: string }> },
) {
  const { projectId } = await context.params;
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";
  try {
    const response = await fetch(
      new URL(`/projects/${encodeURIComponent(projectId)}/generate`, apiBaseUrl),
      {
        method: "POST",
        headers: await apiHeaders(),
        cache: "no-store",
      },
    );
    const body = (await response.json()) as Record<string, unknown>;
    const videoExport = body.export;
    if (videoExport && typeof videoExport === "object") {
      const exportBody = videoExport as Record<string, unknown>;
      if (typeof exportBody.download_url === "string") {
        exportBody.download_url = `/api${exportBody.download_url}`;
      }
    }
    return NextResponse.json(body, { status: response.status });
  } catch {
    return NextResponse.json(
      { detail: "The generation service is temporarily unavailable" },
      { status: 503 },
    );
  }
}
