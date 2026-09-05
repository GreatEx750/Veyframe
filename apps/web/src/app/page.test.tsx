import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import Home from "./page";

const replace = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
}));

const projectResponse = {
  id: "project-123",
  name: "Untitled demo",
  website_url: "https://example.com/",
  product_summary: "A focused workspace for modern product teams.",
  audience: "Product leaders",
  tone: "professional",
  requested_duration_seconds: 90,
  cta: "Start a trial",
  brand_kit_id: "default-brand",
  status: "draft",
  job_status: "idle",
  created_at: "2026-09-01T12:00:00Z",
  updated_at: "2026-09-01T12:00:00Z",
};

function completeForm() {
  fireEvent.change(screen.getByLabelText(/Website URL/), { target: { value: "https://example.com" } });
  fireEvent.change(screen.getByLabelText(/Describe your video/), { target: { value: projectResponse.product_summary } });
  fireEvent.change(screen.getByLabelText("Target Audience"), { target: { value: "Product leaders" } });
  fireEvent.change(screen.getByLabelText("Call to Action"), { target: { value: "Start a trial" } });
}

afterEach(() => {
  vi.unstubAllGlobals();
  replace.mockReset();
});

describe("Create Demo Studio", () => {
  it("renders a complete editing workspace with tools, canvas, inspector, and timeline", () => {
    render(<Home />);
    const projectControls = screen.getByRole("banner", { name: "Project controls" });
    expect(projectControls).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Create product demo" })).toBeInTheDocument();
    expect(within(projectControls).getByText("New project — create to save")).toBeInTheDocument();
    expect(within(projectControls).queryByText("Draft saved locally")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Project tools" })).toBeInTheDocument();
    expect(screen.getByLabelText(/Website URL/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Describe your video/)).toBeInTheDocument();
    expect(screen.getByText(/Mention the story, product moments, and ending/i)).toBeInTheDocument();
    expect(within(screen.getByLabelText("Length")).getByRole("option", { name: "30 seconds" })).toHaveValue("30");
    expect(screen.getByLabelText("Studio preview")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Director settings" })).toBeInTheDocument();
    expect(screen.getByLabelText("Project timeline")).toBeInTheDocument();
    const navigation = screen.getByRole("navigation", { name: "Primary navigation" });
    expect(within(navigation).getAllByRole("link").map((link) => link.textContent)).toEqual(["Projects", "Studio", "Voice", "Settings"]);
    expect(within(navigation).queryByText("Brand")).not.toBeInTheDocument();
    expect(within(navigation).queryByText("Output")).not.toBeInTheDocument();
  });

  it("defaults to Product Demo with smooth zoom and always-visible click feedback", () => {
    render(<Home />);

    expect(screen.getByRole("radio", { name: "Product Demo" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Presentation Demo" })).not.toBeChecked();
    expect(screen.getByLabelText("Length")).toBeEnabled();
    expect(screen.getByLabelText("Length")).toHaveValue("90");
    expect(screen.getByRole("switch", { name: "Smooth zoom" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByLabelText("Zoom intensity")).toBeEnabled();
    expect(screen.getByText("Both formats keep pointer movement and click feedback visible.")).toBeInTheDocument();
    expect(within(screen.getByLabelText("Studio preview")).getByText(/Product Demo/)).toBeInTheDocument();

    const timeline = within(screen.getByLabelText("Project timeline"));
    expect(timeline.getByText("00:12 / 01:30")).toBeInTheDocument();
    expect(timeline.getByText("1:30")).toBeInTheDocument();
    expect(timeline.getByRole("button", { name: "1. Intro, 0:00 to 0:06" })).toBeInTheDocument();
    expect(timeline.getByRole("button", { name: "6. Outro, 1:21 to 1:30" })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Length"), { target: { value: "30" } });
    expect(timeline.getByText("00:12 / 00:30")).toBeInTheDocument();
    expect(timeline.getByRole("button", { name: "6. Outro, 0:27 to 0:30" })).toBeInTheDocument();
  });

  it("locks Presentation Demo to the fixed two-minute format and restores the Product default", () => {
    render(<Home />);

    fireEvent.click(screen.getByRole("radio", { name: "Presentation Demo" }));
    expect(
      screen.getByRole("heading", { level: 1, name: "Create presentation demo" }),
    ).toBeInTheDocument();
    expect(
      within(screen.getByRole("banner", { name: "Project controls" })).getByText(
        "New project — create to save",
      ),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Length")).toBeDisabled();
    expect(screen.getByLabelText("Length")).toHaveValue("120");
    expect(within(screen.getByLabelText("Length")).getByRole("option", { name: "2 minutes · fixed presentation format" })).toHaveValue("120");

    const preview = within(screen.getByLabelText("Studio preview"));
    const timeline = within(screen.getByLabelText("Project timeline"));
    expect(preview.getByText("0:12 / 2:00")).toBeInTheDocument();
    expect(timeline.getByText("00:12 / 02:00")).toBeInTheDocument();
    expect(timeline.getByText("2:00")).toBeInTheDocument();
    expect(timeline.getByRole("button", { name: "1. Intro, 0:00 to 0:05" })).toBeInTheDocument();
    expect(timeline.getByRole("button", { name: "2. Problem + promise, 0:05 to 0:20" })).toBeInTheDocument();
    expect(timeline.getByRole("button", { name: "3. Product walkthrough, 0:20 to 1:20" })).toBeInTheDocument();
    expect(timeline.getByRole("button", { name: "5. Editing + result, 1:40 to 1:55" })).toBeInTheDocument();
    expect(timeline.getByRole("button", { name: "6. Outro, 1:55 to 2:00" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: "Product Demo" }));
    expect(
      screen.getByRole("heading", { level: 1, name: "Create product demo" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Length")).toBeEnabled();
    expect(screen.getByLabelText("Length")).toHaveValue("90");
    expect(timeline.getByText("00:12 / 01:30")).toBeInTheDocument();
  });

  it("previews authored Presentation bookends and framed product scenes", () => {
    render(<Home />);

    const preview = within(screen.getByLabelText("Studio preview"));
    const timeline = within(screen.getByLabelText("Project timeline"));
    expect(preview.getByLabelText("Full-screen product recording")).toBeInTheDocument();
    expect(preview.getByLabelText("Mock product application")).toBeInTheDocument();
    expect(preview.queryByLabelText("Authored presentation layout")).not.toBeInTheDocument();
    expect(preview.getByText("EcoTrack")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: "Presentation Demo" }));
    expect(preview.queryByLabelText("Full-screen product recording")).not.toBeInTheDocument();
    expect(preview.getByLabelText("Authored presentation layout")).toBeInTheDocument();
    expect(preview.getByLabelText("Product recording aperture")).toBeInTheDocument();
    expect(preview.getByLabelText("Mock product application")).toBeInTheDocument();
    expect(preview.getByText("Problem + promise")).toBeInTheDocument();
    expect(preview.getByText("EcoTrack")).toBeInTheDocument();

    fireEvent.click(timeline.getByRole("button", { name: "1. Intro, 0:00 to 0:05" }));
    expect(preview.getByLabelText("Authored intro title card")).toBeInTheDocument();
    expect(preview.queryByLabelText("Product recording aperture")).not.toBeInTheDocument();
    expect(preview.queryByLabelText("Mock product application")).not.toBeInTheDocument();
    expect(preview.queryByText("EcoTrack")).not.toBeInTheDocument();

    fireEvent.click(timeline.getByRole("button", { name: "6. Outro, 1:55 to 2:00" }));
    expect(preview.getByLabelText("Authored outro title card")).toBeInTheDocument();
    expect(preview.queryByLabelText("Product recording aperture")).not.toBeInTheDocument();
    expect(preview.queryByLabelText("Mock product application")).not.toBeInTheDocument();
    expect(preview.queryByText("EcoTrack")).not.toBeInTheDocument();
  });

  it("shows field-level validation without submitting an invalid brief", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<Home />);
    fireEvent.click(screen.getAllByRole("button", { name: "Create demo" })[1]);
    expect(await screen.findByText("Enter a valid website URL.")).toBeInTheDocument();
    expect(screen.getByText("Describe the video in at least 20 characters.")).toBeInTheDocument();
    expect(screen.getByText("Choose a target audience.")).toBeInTheDocument();
    expect(screen.getByText("Add a call to action.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("creates, generates, and opens a completed demo from one click", async () => {
    let resolveGeneration: ((value: unknown) => void) | undefined;
    const generationResult = {
      project: { ...projectResponse, status: "published", job_status: "succeeded" },
      export: {
        id: "export-1",
        project_id: projectResponse.id,
        status: "succeeded",
        quality: "1080p",
        filename: "demo.mp4",
        width: 1920,
        height: 1080,
        duration_ms: 90_000,
        size_bytes: 2048,
        thumbnail_path: null,
        download_url: `/api/projects/${projectResponse.id}/exports/export-1/download?token=12345678901234567890`,
        retryable: false,
        error: null,
        created_at: "2026-09-01T12:02:00Z",
      },
      timeline_version: 1,
      warnings: [],
    };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => projectResponse })
      .mockReturnValueOnce(new Promise((resolve) => { resolveGeneration = resolve; }));
    vi.stubGlobal("fetch", fetchMock);
    render(<Home />);
    completeForm();
    fireEvent.click(screen.getByRole("radio", { name: "Presentation Demo" }));
    fireEvent.click(screen.getByRole("switch", { name: "Smooth zoom" }));
    expect(screen.getByLabelText("Zoom intensity")).toBeDisabled();
    fireEvent.click(screen.getAllByRole("button", { name: "Create demo" })[1]);
    await waitFor(() => expect(screen.getAllByRole("button", { name: "Generating demo…" })[0]).toBeDisabled());
    resolveGeneration?.({ ok: true, json: async () => generationResult });
    await waitFor(() => expect(replace).toHaveBeenCalledWith(`/projects/${projectResponse.id}/editor`));
    expect(fetchMock).toHaveBeenCalledWith("/api/projects", expect.objectContaining({ method: "POST" }));
    expect(fetchMock).toHaveBeenCalledWith(`/api/projects/${projectResponse.id}/generate`, expect.objectContaining({ method: "POST" }));
    const request = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(request.body))).toMatchObject({ website_url: "https://example.com", product_summary: projectResponse.product_summary, demo_mode: "presentation_demo", audience: "Product leaders", requested_duration_seconds: 120, cta: "Start a trial", zoom_enabled: false });
  });
});
