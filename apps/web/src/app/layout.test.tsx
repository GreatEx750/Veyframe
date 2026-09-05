import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import RootLayout from "./layout";

vi.mock("next/font/google", () => ({
  Inter: () => ({ className: "inter", variable: "--font-inter" }),
}));

afterEach(() => vi.unstubAllGlobals());

it("shows the project content without a floating demo banner for judge sessions", async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      status: "active",
      session: { expires_at: "2099-01-01T00:00:00Z", user: { role: "judge_demo" } },
    }),
  });
  vi.stubGlobal("fetch", fetchMock);
  const layout = RootLayout({ children: <main>Project library</main> });
  render(layout.props.children.props.children);
  await waitFor(() => expect(fetchMock).toHaveBeenCalled());
  expect(screen.getByText("Project library")).toBeInTheDocument();
  expect(screen.queryByText("Judge demo")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Reset sandbox" })).not.toBeInTheDocument();
});
