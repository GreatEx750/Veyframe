import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DemoLibrary } from "./demo-library";

const replace = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
}));

const projects = [
  {
    id: "project-rendering",
    name: "FlowSync Feature Tour",
    website_url: "https://example.com/flow",
    product_summary: "Show the automation workflow.",
    audience: "Product leaders",
    tone: "Professional",
    requested_duration_seconds: 72,
    cta: "Try it",
    brand_kit_id: null,
    status: "rendering",
    job_status: "running",
    created_at: "2026-09-01T12:00:00Z",
    updated_at: "2026-09-01T13:00:00Z",
  },
  {
    id: "project-failed",
    name: "PulseCRM Onboarding",
    website_url: "https://example.com/crm",
    product_summary: "Onboard a new teammate.",
    audience: "Customer success teams",
    tone: "Friendly",
    requested_duration_seconds: 95,
    cta: "Book a demo",
    brand_kit_id: "crm-brand",
    status: "failed",
    job_status: "failed",
    created_at: "2026-08-31T12:00:00Z",
    updated_at: "2026-09-01T12:00:00Z",
  },
  {
    id: "project-published",
    name: "Northstar Launch Demo",
    website_url: "https://example.com/northstar",
    product_summary: "Show the complete Northstar workflow.",
    audience: "Product leaders",
    tone: "Professional",
    requested_duration_seconds: 120,
    cta: "Start a trial",
    brand_kit_id: null,
    demo_mode: "presentation_demo",
    zoom_enabled: true,
    status: "published",
    job_status: "succeeded",
    created_at: "2026-09-01T14:00:00Z",
    updated_at: "2026-09-01T15:00:00Z",
  },
];

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  replace.mockReset();
});

function renderLibrary() {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok: true, json: async () => projects }),
  );
  return render(<DemoLibrary />);
}

describe("DemoLibrary", () => {
  it("uses the same ordered product navigation as the Studio", () => {
    renderLibrary();
    const navigation = screen.getByRole("navigation", { name: "Primary navigation" });

    expect(within(navigation).getAllByRole("link").map((link) => link.textContent)).toEqual(["Projects", "Studio", "Jobs", "Settings"]);
    expect(within(navigation).queryByText("Brand")).not.toBeInTheDocument();
    expect(within(navigation).queryByText("Output")).not.toBeInTheDocument();
  });

  it("loads project cards with visible workflow statuses", async () => {
    renderLibrary();

    expect(await screen.findByText("FlowSync Feature Tour")).toBeInTheDocument();
    expect(screen.getAllByText("Rendering").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Failed").length).toBeGreaterThan(0);
    const presentationProject = screen.getByRole("link", { name: /Northstar Launch Demo/ });
    expect(within(presentationProject).getByText("Presentation")).toBeInTheDocument();
  });

  it("searches and filters project cards", async () => {
    renderLibrary();
    await screen.findByText("FlowSync Feature Tour");

    fireEvent.change(screen.getByLabelText("Search demos"), { target: { value: "Pulse" } });

    expect(screen.getByText("PulseCRM Onboarding")).toBeInTheDocument();
    expect(screen.queryByText("FlowSync Feature Tour")).not.toBeInTheDocument();
  });

  it("opens a selected project in the editor", async () => {
    renderLibrary();
    const card = await screen.findByRole("link", { name: /FlowSync Feature Tour/ });

    await waitFor(() =>
      expect(card).toHaveAttribute("href", "/projects/project-rendering/editor"),
    );
  });

  it("shows a playable generated-video preview on published projects", async () => {
    renderLibrary();

    const preview = await screen.findByLabelText("Preview Northstar Launch Demo");

    expect(preview).toHaveAttribute(
      "src",
      "/api/projects/project-published/exports/latest/video",
    );
    expect(screen.getByText(/Video ready/)).toBeInTheDocument();
  });

  it("uses the packaged video for a Northstar judge project", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [{ ...projects[2], id: "judge-demo-session-1", name: "Northstar AI — Judge Demo" }],
      }),
    );
    render(<DemoLibrary />);

    const preview = await screen.findByLabelText("Preview Northstar AI — Judge Demo");

    expect(preview).toHaveAttribute("src", "/judge-demo.mp4");
  });

  it("returns an expired session to login instead of leaving the library loading", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 401, json: async () => ({ detail: "expired" }) }),
    );
    render(<DemoLibrary />);

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login?reason=session_expired"));
    expect(screen.queryByText("Loading your demos…")).not.toBeInTheDocument();
  });

  it("deletes only the confirmed project and updates the library", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => projects })
      .mockResolvedValueOnce({ ok: true, status: 204 });
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<DemoLibrary />);
    await screen.findByText("FlowSync Feature Tour");

    fireEvent.click(screen.getByRole("button", { name: "Delete FlowSync Feature Tour" }));

    await waitFor(() => expect(screen.queryByText("FlowSync Feature Tour")).not.toBeInTheDocument());
    expect(screen.getByText("PulseCRM Onboarding")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("FlowSync Feature Tour deleted");
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/projects/project-rendering",
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("keeps the project when deletion is cancelled", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => projects });
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<DemoLibrary />);
    await screen.findByText("FlowSync Feature Tour");

    fireEvent.click(screen.getByRole("button", { name: "Delete FlowSync Feature Tour" }));

    expect(screen.getByText("FlowSync Feature Tour")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
