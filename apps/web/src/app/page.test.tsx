import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import Home from "./page";

const replace = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
}));

const projectResponse = {
  id: "project-123",
  name: "Product team walkthrough",
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
  fireEvent.change(screen.getByLabelText(/Demo title/), { target: { value: `  ${projectResponse.name}  ` } });
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
  it.each(["Product Demo", "Presentation Demo"])("opens the exact newly queued %s job", async (format) => {
    const job = { id: "product-job", project_id: projectResponse.id, status: "queued",
      stage: "inspection", completed_stages: [], attempts: 0, version: 1,
      created_at: "2026-09-01T12:00:00Z", updated_at: "2026-09-01T12:00:00Z",
      message: "Queued", lease_until: null, export_id: null, timeline_version: null };
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => projectResponse })
      .mockResolvedValueOnce({ ok: true, json: async () => job }));
    render(<Home />); completeForm();
    fireEvent.click(screen.getByRole("radio", { name: format }));
    fireEvent.submit(document.getElementById("demo-form")!);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/jobs?job=product-job"));
  });
  it("starts the authored five-slide pipeline from the presentation option", async () => {
    const job = { id: "preview-job", project_id: projectResponse.id, status: "queued",
      stage: "inspection", completed_stages: [], attempts: 1, version: 1,
      created_at: "2026-09-01T12:00:00Z", updated_at: "2026-09-01T12:00:00Z",
      message: "Queued: first five slides", lease_until: null, export_id: null, timeline_version: null };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => projectResponse })
      .mockResolvedValueOnce({ ok: true, json: async () => job });
    vi.stubGlobal("fetch", fetchMock);
    render(<Home />);
    completeForm();
    fireEvent.click(screen.getByRole("radio", { name: "Presentation Demo" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Preview first five slides (61 seconds)" }));
    fireEvent.submit(document.getElementById("demo-form")!);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/jobs?job=preview-job"));
    expect(fetchMock).toHaveBeenCalledWith(`/api/projects/${projectResponse.id}/generation/presentation-preview`, expect.objectContaining({ method: "POST" }));
    expect(JSON.parse(fetchMock.mock.calls[0][1].body).name).toBe(projectResponse.name);
  });
  it("renders a setup form, example preview, and director settings", () => {
    render(<Home />);
    expect(screen.getByRole("heading", { level: 1, name: "Create product demo" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Demo setup" })).toBeInTheDocument();
    expect(screen.getByLabelText(/Website URL/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Demo title/)).toBeRequired();
    expect(screen.getByLabelText(/Describe your video/)).toBeInTheDocument();
    expect(screen.getByLabelText("Studio preview")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Director settings" })).toBeInTheDocument();
    const navigation = screen.getByRole("navigation", { name: "Primary navigation" });
    expect(within(navigation).getAllByRole("link").map((link) => link.textContent)).toEqual(["Projects", "Studio", "Jobs", "Voice", "Settings"]);
  });

  it("defaults to Product Demo with smooth zoom and configurable duration", () => {
    render(<Home />);
    expect(screen.getByRole("radio", { name: "Product Demo" })).toBeChecked();
    expect(screen.getByLabelText("Length")).toHaveValue("90");
    expect(screen.getByRole("switch", { name: "Smooth zoom" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByText("Both formats keep pointer movement and click feedback visible.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Length"), { target: { value: "30" } });
    expect(screen.getByLabelText("Length")).toHaveValue("30");
  });

  it("locks Presentation Demo to two minutes and restores the Product default", () => {
    render(<Home />);
    fireEvent.click(screen.getByRole("radio", { name: "Presentation Demo" }));
    expect(screen.getByRole("heading", { name: "Create presentation demo" })).toBeInTheDocument();
    expect(screen.getByLabelText("Length")).toBeDisabled();
    expect(screen.getByLabelText("Length")).toHaveValue("120");
    fireEvent.click(screen.getByRole("radio", { name: "Product Demo" }));
    expect(screen.getByLabelText("Length")).toBeEnabled();
    expect(screen.getByLabelText("Length")).toHaveValue("90");
  });

  it("switches between playable Northstar examples with a fresh player", () => {
    render(<Home />);
    const preview = within(screen.getByLabelText("Studio preview"));
    expect(preview.getByText("Example preview")).toBeInTheDocument();
    const product = preview.getByLabelText("Northstar Product Demo example");
    expect(product).toHaveAttribute("src", "/examples/northstar-product-20s.mp4");
    expect(product).toHaveAttribute("controls");
    expect(product).not.toHaveAttribute("autoplay");
    fireEvent.click(screen.getByRole("radio", { name: "Presentation Demo" }));
    const presentation = preview.getByLabelText("Northstar Presentation Demo example");
    expect(presentation).toHaveAttribute("src", "/examples/northstar-presentation-20s.mp4");
    expect(presentation).toHaveAttribute("controls");
    expect(product).not.toBeInTheDocument();
    expect(preview.queryByLabelText("Mock product application")).not.toBeInTheDocument();
    expect(preview.queryByRole("button", { name: "Play preview" })).not.toBeInTheDocument();
  });

  it("explains a failed example load and clears the error when switching format", () => {
    render(<Home />);
    fireEvent.error(screen.getByLabelText("Northstar Product Demo example"));
    expect(screen.getByRole("alert")).toHaveTextContent("Example video couldn’t load");
    expect(screen.getByRole("link", { name: "Open example video" })).toHaveAttribute("href", "/examples/northstar-product-20s.mp4");
    fireEvent.click(screen.getByRole("radio", { name: "Presentation Demo" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows field-level validation without submitting an invalid brief", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<Home />);
    fireEvent.click(screen.getByRole("button", { name: "Create demo" }));
    expect(await screen.findByText("Enter a valid website URL.")).toBeInTheDocument();
    expect(screen.getByText("Add a title for your demo.")).toBeInTheDocument();
    expect(screen.getByText("Describe the video in at least 20 characters.")).toBeInTheDocument();
    expect(screen.getByText("Choose a target audience.")).toBeInTheDocument();
    expect(screen.getByText("Add a call to action.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects a whitespace-only title and keeps the title when changing demo mode", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<Home />);
    completeForm();
    fireEvent.click(screen.getByRole("radio", { name: "Presentation Demo" }));
    expect(screen.getByLabelText(/Demo title/)).toHaveValue(`  ${projectResponse.name}  `);
    fireEvent.change(screen.getByLabelText(/Demo title/), { target: { value: "   " } });
    fireEvent.submit(document.getElementById("demo-form")!);
    expect(screen.getByLabelText(/Demo title/)).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText("Add a title for your demo.")).toBeInTheDocument();
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
    fireEvent.click(screen.getByRole("button", { name: "Create demo" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Generating demo…" })).toBeDisabled());
    resolveGeneration?.({ ok: true, json: async () => generationResult });
    await waitFor(() => expect(replace).toHaveBeenCalledWith(`/projects/${projectResponse.id}/editor`));
    expect(fetchMock).toHaveBeenCalledWith("/api/projects", expect.objectContaining({ method: "POST" }));
    expect(fetchMock).toHaveBeenCalledWith(`/api/projects/${projectResponse.id}/generate`, expect.objectContaining({ method: "POST" }));
    const request = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(request.body)).name).toBe(projectResponse.name);
    expect(JSON.parse(String(request.body))).toMatchObject({ website_url: "https://example.com", product_summary: projectResponse.product_summary, demo_mode: "presentation_demo", audience: "Product leaders", requested_duration_seconds: 120, cta: "Start a trial", zoom_enabled: false });
  });
});
