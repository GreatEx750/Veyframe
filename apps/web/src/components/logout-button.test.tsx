import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LogoutButton } from "./logout-button";

const replace = vi.fn();
const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, refresh }),
}));

describe("LogoutButton", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    replace.mockReset();
    refresh.mockReset();
    sessionStorage.clear();
    localStorage.clear();
  });

  it("clears browser session state and returns to the landing page", async () => {
    sessionStorage.setItem("editor", "private");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ status: "logged_out" }), { status: 200 }),
    );
    render(<LogoutButton />);

    fireEvent.click(screen.getByRole("button", { name: "Log out" }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
    expect(sessionStorage.getItem("editor")).toBeNull();
    expect(localStorage.getItem("demodirector:logout")).toBeTruthy();
    expect(refresh).toHaveBeenCalled();
  });

  it("still clears the local session when the backend is unavailable", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("offline"));
    render(<LogoutButton />);

    fireEvent.click(screen.getByRole("button", { name: "Log out" }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
  });
});
