import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SignupForm } from "./signup-form";

const replace = vi.fn();
const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, refresh }),
}));

describe("SignupForm", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    replace.mockReset();
    refresh.mockReset();
  });

  it("validates password length before submitting", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<SignupForm />);

    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "user@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "short" } });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByText("Use at least 12 characters for your password.")).toBeVisible();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("creates a session and navigates to the private library", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ status: "signed_in", message: "Account created." }), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );
    render(<SignupForm />);

    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "user@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "a-long-secure-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/projects"));
    expect(refresh).toHaveBeenCalled();
  });

  it("shows the verification-required result without navigating", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          status: "verification_required",
          message: "Check your email to verify the account before signing in.",
        }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      ),
    );
    render(<SignupForm />);

    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "user@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "a-long-secure-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(
      await screen.findByText("Check your email to verify the account before signing in."),
    ).toBeVisible();
    expect(replace).not.toHaveBeenCalled();
  });
});
