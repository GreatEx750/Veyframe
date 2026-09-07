import { apiBaseUrl, apiHeaders } from "@/lib/auth-session";

type Context = { params: Promise<{ path: string[] }> };

function appOrigin() {
  try {
    const url = new URL(process.env.YOUTUBE_PUBLIC_BASE_URL ?? "http://localhost:3000");
    const local = url.protocol === "http:" && url.hostname === "localhost" && url.port === "3000";
    const hosted = url.protocol === "https:" && Boolean(url.hostname);
    if ((!local && !hosted) || url.username || url.password || url.pathname !== "/" || url.search || url.hash) return null;
    return url.origin;
  } catch {
    return null;
  }
}

export async function GET(request: Request, context: Context) {
  return proxy(request, context);
}
export const POST = GET;

async function proxy(request: Request, { params }: Context) {
  const { path } = await params;
  const key = path.join("/");
  const callback = key === "callback" && request.method === "GET";
  const allowed = (request.method === "GET" && (key === "status" || /^projects\/[\w-]+\/uploads\/[\w-]+$/.test(key)))
    || (request.method === "POST" && (["connect", "disconnect"].includes(key) || /^projects\/[\w-]+\/uploads$/.test(key))) || callback;
  if (!allowed) return Response.json({ detail: "Not found" }, { status: 404 });
  const origin = appOrigin();
  if (!origin || new URL(request.url).origin !== origin) {
    return Response.json({ detail: "YouTube upload is unavailable for this application origin." }, { status: 403 });
  }
  if (request.method === "POST" && request.headers.get("origin") !== origin) {
    return Response.json({ detail: "Invalid request origin." }, { status: 403 });
  }
  try {
    const query = new URL(request.url).searchParams;
    const result = await fetch(new URL(`/youtube/${key}`, apiBaseUrl()), {
      method: callback ? "POST" : request.method,
      headers: await apiHeaders({ "Content-Type": "application/json", "Origin": origin }),
      cache: "no-store",
      body: callback ? JSON.stringify({ state: query.get("state") ?? "", code: query.get("error") ? null : query.get("code") })
        : request.method === "POST" ? await request.text() : undefined,
    });
    const data: unknown = await result.json();
    if (callback) {
      const projectId = result.ok && data && typeof data === "object" && "project_id" in data ? data.project_id : null;
      const destination = typeof projectId === "string" && /^[\w-]+$/.test(projectId)
        ? `/projects/${projectId}/editor?youtube=connected` : "/youtube/connection";
      return new Response(null, { status: 303, headers: { Location: origin + destination, "Cache-Control": "no-store", "Referrer-Policy": "no-referrer" } });
    }
    return Response.json(data, { status: result.status, headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ detail: "YouTube connection unavailable. Check that the Veyframe API is running." }, { status: 503 });
  }
}
