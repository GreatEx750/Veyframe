import { NextResponse } from "next/server";

import { apiBaseUrl, apiHeaders } from "@/lib/auth-session";

export async function GET(
  _request: Request,
  context: { params: Promise<{ projectId: string }> },
) {
  const { projectId } = await context.params;
  try {
    const response = await fetch(
      new URL(`/projects/${encodeURIComponent(projectId)}/research`, apiBaseUrl()),
      { headers: await apiHeaders(), cache: "no-store" },
    );
    return NextResponse.json(await response.json(), { status: response.status });
  } catch {
    return NextResponse.json({ detail: "Saved research is temporarily unavailable" }, { status: 503 });
  }
}
