import { render, screen, waitFor } from "@testing-library/react";
import { usePathname } from "next/navigation";
import { describe, expect, it, vi } from "vitest";

import { JudgeBanner } from "./judge-banner";

describe("JudgeBanner", () => {
  it("clears the judge banner after the session becomes absent", async () => {
    const pathname = vi.mocked(usePathname);
    pathname.mockReturnValue("/projects");
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          status: "active",
          session: {
            expires_at: "2026-09-02T01:00:00Z",
            user: { role: "judge_demo" },
          },
        }),
      })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ status: "absent" }) });
    vi.stubGlobal("fetch", fetchMock);
    const view = render(<JudgeBanner />);

    expect(await screen.findByText(/Pre-generated 20-second workflow/)).toBeInTheDocument();

    pathname.mockReturnValue("/login");
    view.rerender(<JudgeBanner />);
    await waitFor(() => {
      expect(screen.queryByText(/Pre-generated 20-second workflow/)).not.toBeInTheDocument();
    });
  });
});
