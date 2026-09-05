import { NextResponse } from "next/server";
import { apiHeaders } from "@/lib/auth-session";

type Context = { params: Promise<{ projectId: string; path: string[] }> };
async function proxy(request: Request, context: Context) {
  const { projectId, path } = await context.params;
  const suffix = path.join("/");
  const allowed = /^(exports\/[^/]+\/reviews(\/latest)?|optimizations(\/[^/]+(\/(apply|cancel))?)?|evidence|source-contributions|storyboard-approval)$/.test(suffix);
  if (!allowed || path.some((p) => p === "." || p === ".." || /[?#\\]/.test(p))) return NextResponse.json({ detail: "Not found" }, { status: 404 });
  try {
    const response = await fetch(new URL(`/projects/${encodeURIComponent(projectId)}/${path.map(encodeURIComponent).join("/")}`, process.env.API_BASE_URL ?? "http://localhost:8000"), {
      method: request.method,
      headers: await apiHeaders({ "Content-Type": "application/json" }),
      body: request.method === "GET" ? undefined : await request.text(), cache: "no-store",
    });
    return NextResponse.json(await response.json(), { status: response.status, headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ detail: "The service is temporarily unavailable. Reload saved status before retrying." }, { status: 503 });
  }
}
export const GET = proxy;
export const POST = proxy;
