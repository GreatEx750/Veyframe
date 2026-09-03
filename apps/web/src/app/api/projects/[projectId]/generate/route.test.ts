import { afterEach, describe, expect, it, vi } from "vitest";

import { POST } from "./route";

afterEach(() => vi.unstubAllGlobals());

describe("one-click generation proxy", () => {
  it("forwards the long-running request and localizes the download URL", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      status: 200,
      json: async () => ({
        project: { id: "project-1" },
        export: {
          download_url: "/projects/project-1/exports/export-1/download?token=12345678901234567890",
        },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const response = await POST(
      new Request("http://localhost/api/projects/project-1/generate", { method: "POST" }),
      { params: Promise.resolve({ projectId: "project-1" }) },
    );

    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledWith(
      new URL("http://localhost:8000/projects/project-1/generate"),
      expect.objectContaining({ method: "POST", cache: "no-store" }),
    );
    expect(await response.json()).toMatchObject({
      export: {
        download_url: "/api/projects/project-1/exports/export-1/download?token=12345678901234567890",
      },
    });
  });

  it("returns a service error when generation cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));

    const response = await POST(
      new Request("http://localhost/api/projects/project-1/generate", { method: "POST" }),
      { params: Promise.resolve({ projectId: "project-1" }) },
    );

    expect(response.status).toBe(503);
  });
});
