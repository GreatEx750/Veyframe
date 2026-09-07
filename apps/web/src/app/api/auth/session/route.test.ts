import { afterEach, expect, it, vi } from "vitest";
import { GET } from "./route";

const clear = vi.hoisted(() => vi.fn());
vi.mock("@/lib/auth-session", () => ({
  apiBaseUrl: () => "https://api.example.com",
  apiHeaders: async () => new Headers(),
  clearSessionCookie: clear,
}));
afterEach(() => { vi.unstubAllGlobals(); clear.mockReset(); });

it("returns temporary unavailability without erasing a session on connection failure", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fetch failed")));
  expect((await GET()).status).toBe(503);
  expect(clear).not.toHaveBeenCalled();
});

it("keeps cookies on an upstream service failure", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("unavailable", { status: 503 })));
  expect((await GET()).status).toBe(503);
  expect(clear).not.toHaveBeenCalled();
});

it("still clears an explicitly expired session", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ status: "expired" })));
  expect((await GET()).status).toBe(200);
  expect(clear).toHaveBeenCalledOnce();
});
