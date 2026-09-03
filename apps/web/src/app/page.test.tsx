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
    expect(screen.getByRole("banner", { name: "Project controls" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Create product demo" })).toBeInTheDocument();
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
    fireEvent.click(screen.getAllByRole("button", { name: "Create demo" })[1]);
    await waitFor(() => expect(screen.getAllByRole("button", { name: "Generating demo…" })[0]).toBeDisabled());
    resolveGeneration?.({ ok: true, json: async () => generationResult });
    await waitFor(() => expect(replace).toHaveBeenCalledWith(`/projects/${projectResponse.id}/editor`));
    expect(fetchMock).toHaveBeenCalledWith("/api/projects", expect.objectContaining({ method: "POST" }));
    expect(fetchMock).toHaveBeenCalledWith(`/api/projects/${projectResponse.id}/generate`, expect.objectContaining({ method: "POST" }));
    const request = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(request.body))).toMatchObject({ website_url: "https://example.com", product_summary: projectResponse.product_summary, audience: "Product leaders", requested_duration_seconds: 90, cta: "Start a trial" });
  });
});
