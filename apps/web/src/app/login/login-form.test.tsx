import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LoginForm } from "./login-form";

const replace = vi.fn();
const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, refresh }),
}));

describe("LoginForm", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    replace.mockReset();
    refresh.mockReset();
  });

  it("logs in and always opens the project library", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ landing_path: "/projects/project-1/editor" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    render(<LoginForm />);

    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "user@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "secure-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Log in" }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/projects"));
    expect(JSON.parse(String(fetchSpy.mock.calls[0][1]?.body)).return_to).toBe("/projects");
  });

  it("shows the generic backend authentication error", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({ detail: { message: "Email or password is incorrect." } }),
        { status: 401, headers: { "Content-Type": "application/json" } },
      ),
    );
    render(<LoginForm />);

    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "user@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "wrong" } });
    fireEvent.click(screen.getByRole("button", { name: "Log in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Email or password is incorrect.");
    expect(replace).not.toHaveBeenCalled();
  });

  it("opens the project library after creating a short-lived judge sandbox", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ landing_path: "/projects/judge-demo/editor" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    render(<LoginForm />);

    fireEvent.click(screen.getByRole("button", { name: "Enter Judge Demo" }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/projects"));
  });
});
