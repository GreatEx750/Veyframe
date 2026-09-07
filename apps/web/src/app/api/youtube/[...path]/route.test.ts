import { afterEach, expect, it, vi } from "vitest";
import { GET, POST } from "./route";

vi.mock("@/lib/auth-session", () => ({ apiBaseUrl: () => "http://localhost:8000", apiHeaders: async (headers: HeadersInit) => new Headers(headers) }));
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });

it("rejects remote hosts, foreign origins and arbitrary proxy paths", async () => {
  const fetchMock = vi.fn(); vi.stubGlobal("fetch", fetchMock);
  expect((await GET(new Request("https://example.com/api/youtube/status"), { params: Promise.resolve({ path: ["status"] }) })).status).toBe(403);
  expect((await POST(new Request("http://localhost:3000/api/youtube/connect", { method: "POST", headers: { Origin: "https://evil.example" } }), { params: Promise.resolve({ path: ["connect"] }) })).status).toBe(403);
  expect((await GET(new Request("http://localhost:3000/api/youtube/secret"), { params: Promise.resolve({ path: ["secret"] }) })).status).toBe(404);
  expect(fetchMock).not.toHaveBeenCalled();
});

it("posts callback codes internally and redirects only to a validated project path", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ project_id: "project-1" }) });
  vi.stubGlobal("fetch", fetchMock);
  const result = await GET(new Request("http://localhost:3000/api/youtube/callback?state=test&code=private-code"), { params: Promise.resolve({ path: ["callback"] }) });
  expect(result.status).toBe(303);
  expect(result.headers.get("location")).toBe("http://localhost:3000/projects/project-1/editor?youtube=connected");
  expect(result.headers.get("referrer-policy")).toBe("no-referrer");
  expect(fetchMock.mock.calls[0][1].method).toBe("POST");
  expect(String(fetchMock.mock.calls[0][0])).not.toContain("private-code");
});

it("handles cancelled consent without redirecting to an untrusted destination", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, json: async () => ({ detail: "Cancelled" }) }));
  const result = await GET(new Request("http://localhost:3000/api/youtube/callback?state=test&error=access_denied"), { params: Promise.resolve({ path: ["callback"] }) });
  expect(result.headers.get("location")).toBe("http://localhost:3000/youtube/connection");
});

it("accepts the exact configured HTTPS origin for cloud", async () => {
  vi.stubEnv("YOUTUBE_PUBLIC_BASE_URL", "https://veyframe.example");
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ connected: false }) });
  vi.stubGlobal("fetch", fetchMock);
  const result = await GET(new Request("https://veyframe.example/api/youtube/status"), { params: Promise.resolve({ path: ["status"] }) });
  expect(result.status).toBe(200);
  expect(fetchMock).toHaveBeenCalledOnce();
});
