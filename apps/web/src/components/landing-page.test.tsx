import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LandingPage } from "./landing-page";

const router = vi.hoisted(() => ({ replace: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));

describe("Veyframe public landing page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
    vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
    vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({
      matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn(),
    }));
  });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

  it("offers real account destinations and all four formats", () => {
    render(<LandingPage />);
    expect(screen.getByRole("link", { name: "Get started" })).toHaveAttribute("href", "/signup");
    expect(screen.getByRole("link", { name: "Log in" })).toHaveAttribute("href", "/login");
    expect(screen.getAllByRole("tab")).toHaveLength(4);
    expect(screen.getAllByRole("tab")[0]).toHaveTextContent("Presentations");
    expect(screen.getByRole("tab", { name: "Presentations" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("button", { name: "Judge Demo Mode" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Video production benchmark" })).toBeInTheDocument();
  });

  it("changes the footage with mouse and keyboard tab selection", () => {
    render(<LandingPage />);
    fireEvent.click(screen.getByRole("tab", { name: "Presentations" }));
    expect(screen.getByLabelText("Presentations preview")).toHaveAttribute("src", "/landing/presentation-preview.mp4");
    fireEvent.keyDown(screen.getByRole("tab", { name: "Presentations" }), { key: "ArrowRight" });
    expect(screen.getByRole("tab", { name: "Product demos" })).toHaveAttribute("aria-selected", "true");
  });

  it("keeps the preview paused across tab changes after the user pauses", () => {
    render(<LandingPage />);
    fireEvent.click(screen.getByRole("button", { name: "Pause preview" }));
    fireEvent.click(screen.getByRole("tab", { name: "Shorts" }));
    expect(screen.getByLabelText("Shorts preview")).toHaveAttribute("poster", "/landing/short-google-rounded-poster.jpg");
    expect(screen.getByLabelText("Shorts preview")).toHaveAttribute("src", "/landing/short-preview.mp4?v=rounded-3");
    expect(screen.getByRole("button", { name: "Play preview" })).toBeInTheDocument();
    expect(screen.getByLabelText("Shorts preview")).not.toHaveAttribute("autoplay");
  });

  it("offers a usable sample link when preview media fails", () => {
    render(<LandingPage />);
    fireEvent.error(screen.getByLabelText("Presentations preview"));
    expect(screen.getByRole("alert")).toHaveTextContent("Preview couldn’t load");
    expect(screen.getByRole("link", { name: "Open the example video" })).toHaveAttribute("href", "/examples/northstar-presentation-20s.mp4");
  });

  it("creates a judge session before opening the project library", async () => {
    const fetch = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal("fetch", fetch);
    render(<LandingPage />);
    fireEvent.click(screen.getByRole("button", { name: "Judge Demo Mode" }));
    expect(screen.getByRole("button", { name: "Opening demo…" })).toBeDisabled();
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/projects"));
    expect(fetch).toHaveBeenCalledWith("/api/auth/judge-session", { method: "POST" });
    expect(router.refresh).toHaveBeenCalled();
  });

  it("allows retry when the judge session cannot be opened", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false }));
    render(<LandingPage />);
    fireEvent.click(screen.getByRole("button", { name: "Judge Demo Mode" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Judge demo is temporarily unavailable");
    expect(screen.getByRole("button", { name: "Judge Demo Mode" })).toBeEnabled();
    expect(router.replace).not.toHaveBeenCalled();
  });
});
