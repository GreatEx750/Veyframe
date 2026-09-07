import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
  afterEach(() => { vi.useRealTimers(); cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

  it("offers real account destinations and all four formats", () => {
    render(<LandingPage />);
    expect(screen.getByRole("link", { name: "Get started" })).toHaveAttribute("href", "/signup");
    expect(screen.getByRole("link", { name: "Log in" })).toHaveAttribute("href", "/login");
    expect(screen.getAllByRole("tab")).toHaveLength(4);
    expect(screen.getAllByRole("tab")[0]).toHaveTextContent("Presentations");
    expect(screen.getByRole("tab", { name: "Presentations" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("button", { name: "Judge Demo Mode" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Video production benchmark" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Built for stories like yours" })).toBeInTheDocument();
    expect(screen.getByText(/synthetic testimonial tweets/i)).toBeInTheDocument();
    expect(screen.getByText("Epiq")).toBeInTheDocument();
    expect(screen.getByText("Roamstead")).toBeInTheDocument();
    expect(screen.getByText("HabiWatch")).toBeInTheDocument();
    expect(screen.getAllByText("BoneTwein")).toHaveLength(2);
    expect(screen.getAllByRole("img", { name: /project logo/i })).toHaveLength(4);
    const sectionHeadings = screen.getAllByRole("heading", { level: 2 });
    expect(sectionHeadings.indexOf(screen.getByRole("heading", { name: "Video production benchmark" })))
      .toBeLessThan(sectionHeadings.indexOf(screen.getByRole("heading", { name: "Built for stories like yours" })));
    const proofBand = screen.getByTestId("landing-proof-band");
    expect(proofBand).toContainElement(screen.getByRole("heading", { name: "Video production benchmark" }));
    expect(proofBand).toContainElement(screen.getByRole("heading", { name: "Built for stories like yours" }));
  });

  it("auto-advances the project testimonial carousel and keeps source links visible", () => {
    vi.useFakeTimers();
    render(<LandingPage />);
    expect(screen.getByText("AI outbreak intelligence")).toBeInTheDocument();
    expect(screen.getByText("1 / 4")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "View Epiq" })[0]).toHaveAttribute(
      "href", "https://devpost.com/software/epiq-1ubx5q",
    );

    act(() => vi.advanceTimersByTime(7000));

    expect(screen.getByText("2 / 4")).toBeInTheDocument();
    expect(screen.getByRole("article", { name: "HabiWatch synthetic testimonial" }))
      .toHaveAttribute("aria-current", "true");
    expect(screen.getAllByRole("link", { name: "View HabiWatch" })[0]).toHaveAttribute(
      "href", "https://devpost.com/software/habiwatchai",
    );
    vi.useRealTimers();
  });

  it("supports previous, next, and pause controls for project stories", () => {
    render(<LandingPage />);
    fireEvent.click(screen.getByRole("button", { name: "Next testimonial" }));
    expect(screen.getByText("2 / 4")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Previous testimonial" }));
    expect(screen.getByText("1 / 4")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Pause testimonials" }));
    expect(screen.getByRole("button", { name: "Play testimonials" })).toBeInTheDocument();
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
    expect(screen.getByLabelText("Shorts preview")).toHaveAttribute("poster", "/landing/short-google-editorial-poster.jpg");
    expect(screen.getByLabelText("Shorts preview")).toHaveAttribute("src", "/landing/short-preview.mp4?v=editorial-5");
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
