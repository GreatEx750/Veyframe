import { NextResponse } from "next/server";

import { apiHeaders } from "@/lib/auth-session";

export async function POST(
  _request: Request,
  { params }: { params: Promise<{ projectId: string; sceneId: string }> },
) {
  const apiBaseUrl = process.env.API_BASE_URL ?? "http://localhost:8000";
  const { projectId, sceneId } = await params;
  try {
    const response = await fetch(
      new URL(`/projects/${projectId}/storyboard/scenes/${sceneId}/regenerate`, apiBaseUrl),
      { method: "POST", headers: await apiHeaders(), cache: "no-store" },
    );
    return NextResponse.json(await response.json(), { status: response.status });
  } catch {
    return NextResponse.json({ detail: "The storyboard service is temporarily unavailable" }, { status: 503 });
  }
}
