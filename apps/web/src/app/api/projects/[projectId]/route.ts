import { NextResponse } from "next/server";

import { apiBaseUrl, apiHeaders } from "@/lib/auth-session";

type Context = { params: Promise<{ projectId: string }> };

export async function GET(_request: Request, context: Context) {
  const { projectId } = await context.params;
  try {
    const response = await fetch(new URL(`/projects/${projectId}`, apiBaseUrl()), {
      headers: await apiHeaders(),
      cache: "no-store",
    });
    return NextResponse.json(await response.json(), { status: response.status });
  } catch {
    return NextResponse.json({ detail: "The project could not be loaded" }, { status: 503 });
  }
}

export async function DELETE(_request: Request, context: Context) {
  const { projectId } = await context.params;
  try {
    const response = await fetch(new URL(`/projects/${projectId}`, apiBaseUrl()), {
      method: "DELETE",
      headers: await apiHeaders(),
      cache: "no-store",
    });
    if (response.status === 204) return new NextResponse(null, { status: 204 });
    return NextResponse.json(await response.json(), { status: response.status });
  } catch {
    return NextResponse.json({ detail: "The project could not be deleted" }, { status: 503 });
  }
}
