import { afterEach, describe, expect, it, vi } from "vitest";

import { GET, POST } from "./route";

afterEach(() => vi.unstubAllGlobals());

describe("project API proxy", () => {
  it("forwards project library reads to the application API", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ status: 200, json: async () => [] });
    vi.stubGlobal("fetch", fetchMock);

    const response = await GET();

    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledWith(
      new URL("http://localhost:8000/projects"),
      expect.objectContaining({ cache: "no-store" }),
    );
  });

  it("forwards project creation to the application API", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ status: 201, json: async () => ({ id: "project-1" }) });
    vi.stubGlobal("fetch", fetchMock);
    const request = new Request("http://localhost/api/projects", { method: "POST", body: JSON.stringify({ website_url: "https://example.com" }) });
    const response = await POST(request);
    expect(response.status).toBe(201);
    expect(await response.json()).toEqual({ id: "project-1" });
    expect(fetchMock).toHaveBeenCalledWith(new URL("http://localhost:8000/projects"), expect.objectContaining({ method: "POST", cache: "no-store" }));
  });

  it("returns a service error when the API cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    const response = await POST(new Request("http://localhost/api/projects", { method: "POST" }));
    expect(response.status).toBe(503);
    expect(await response.json()).toEqual({ detail: "The project service is temporarily unavailable" });
  });
});
