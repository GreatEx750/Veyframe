import { NextResponse } from "next/server";

import { apiHeaders } from "@/lib/auth-session";

export async function GET(
  request: Request,
  context: { params: Promise<{ projectId: string }> },
) {
  const { projectId } = await context.params;
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";
  const range = request.headers.get("range");
  try {
    const response = await fetch(
      new URL(`/projects/${encodeURIComponent(projectId)}/exports/latest/video`, apiBaseUrl),
      {
        headers: await apiHeaders(range ? { Range: range } : {}),
        cache: "no-store",
      },
    );
    if (!response.ok) {
      return NextResponse.json(
        { detail: "Project video is unavailable" },
        { status: response.status },
      );
    }
    const headers = new Headers({
      "Content-Type": response.headers.get("content-type") ?? "video/mp4",
      "Content-Disposition": response.headers.get("content-disposition") ?? "inline",
      "Cache-Control": "private, no-store",
    });
    for (const name of ["accept-ranges", "content-length", "content-range"]) {
      const value = response.headers.get(name);
      if (value) headers.set(name, value);
    }
    return new Response(response.body, { status: response.status, headers });
  } catch {
    return NextResponse.json(
      { detail: "The video service is temporarily unavailable" },
      { status: 503 },
    );
  }
}
