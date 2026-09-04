import { apiHeaders } from "@/lib/auth-session";

export async function GET(request: Request, context: { params: Promise<{ projectId: string; exportId: string }> }) {
  const { projectId, exportId } = await context.params;
  try {
    const headers = await apiHeaders();
    const range = request.headers.get("Range");
    if (range) headers.set("Range", range);
    const result = await fetch(new URL(`/projects/${encodeURIComponent(projectId)}/exports/${encodeURIComponent(exportId)}/video`, process.env.API_BASE_URL ?? "http://localhost:8000"), { headers, cache: "no-store" });
    const outgoing = new Headers({ "Cache-Control": "private, no-store" });
    for (const name of ["Content-Type", "Content-Length", "Content-Range", "Accept-Ranges"]) {
      const value = result.headers.get(name); if (value) outgoing.set(name, value);
    }
    return new Response(result.body, { status: result.status, headers: outgoing });
  } catch { return Response.json({ detail: "Video unavailable" }, { status: 503 }); }
}
