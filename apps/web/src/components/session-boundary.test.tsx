import { render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SessionBoundary } from "./session-boundary";

const replace = vi.fn();
const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => "/projects",
  useRouter: () => ({ replace, refresh }),
}));

afterEach(() => {
  vi.unstubAllGlobals();
  replace.mockReset();
  refresh.mockReset();
});

describe("SessionBoundary", () => {
  it("returns stale protected sessions to login", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ status: "expired", session: null }),
      }),
    );

    render(<SessionBoundary><div>Protected project</div></SessionBoundary>);

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login?reason=session_expired"));
    expect(refresh).toHaveBeenCalled();
  });
});
