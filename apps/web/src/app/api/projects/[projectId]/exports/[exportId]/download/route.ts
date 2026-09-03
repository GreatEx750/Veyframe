import { NextResponse } from "next/server";

import { apiHeaders } from "@/lib/auth-session";

export async function GET(
  request: Request,
  context: { params: Promise<{ projectId: string; exportId: string }> },
) {
  const { projectId, exportId } = await context.params;
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";
  const token = new URL(request.url).searchParams.get("token") ?? "";
  try {
    const upstream = new URL(
      `/projects/${encodeURIComponent(projectId)}/exports/${encodeURIComponent(exportId)}/download`,
      apiBaseUrl,
    );
    upstream.searchParams.set("token", token);
    const response = await fetch(upstream, { headers: await apiHeaders(), cache: "no-store" });
    if (!response.ok) {
      return NextResponse.json({ detail: "Export download is unavailable" }, { status: response.status });
    }
    return new Response(response.body, {
      status: 200,
      headers: {
        "Content-Type": "video/mp4",
        "Content-Disposition": response.headers.get("content-disposition") ?? "attachment",
      },
    });
  } catch {
    return NextResponse.json({ detail: "The export service is temporarily unavailable" }, { status: 503 });
  }
}
