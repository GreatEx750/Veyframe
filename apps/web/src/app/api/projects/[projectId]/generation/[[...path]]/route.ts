import { apiHeaders } from "@/lib/auth-session";
export async function GET(request: Request, context: { params: Promise<{ projectId: string; path?: string[] }> }) {
  return proxy(request, context);
}
export const POST = GET;
async function proxy(request: Request, context: { params: Promise<{ projectId: string; path?: string[] }> }) {
  const { projectId, path = [] } = await context.params;
  if (path.length && (path.length !== 2 || !/^[a-f0-9-]{36}$/.test(path[0]) || path[1] !== "retry")) return Response.json({ detail: "Not found" }, { status: 404 });
  try {
    const result = await fetch(new URL(`/projects/${encodeURIComponent(projectId)}/generation${path.length ? `/${path.join("/")}` : ""}`, process.env.API_BASE_URL ?? "http://localhost:8000"), {
      method: request.method, headers: await apiHeaders({ "Content-Type": "application/json" }), cache: "no-store",
      body: request.method === "POST" ? await request.text() : undefined,
    });
    return Response.json(await result.json(), { status: result.status, headers: { "Cache-Control": "no-store" } });
  } catch { return Response.json({ detail: "Progress unavailable; your job remains saved." }, { status: 503 }); }
}
