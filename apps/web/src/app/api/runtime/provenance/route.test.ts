import { afterEach, describe, expect, it, vi } from "vitest";

import { GET } from "./route";

afterEach(() => vi.unstubAllGlobals());

describe("runtime provenance proxy", () => {
  it("combines Google AI and direct Parallel runtime health", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => ({
      ok: true,
      status: 200,
      json: async () => String(input).endsWith("/ai/health")
        ? { status: "ready", provider: "google", model: "gemini-test", tts_model: "gemini-tts-test", agent: "demodirector_director", detail: null }
        : { status: "ready", provider: "parallel", mode: "fast" },
    }));
    vi.stubGlobal("fetch", fetchMock);

    const response = await GET();

    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      ai: { provider: "google", model: "gemini-test" },
      research: { provider: "parallel", mode: "fast" },
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
