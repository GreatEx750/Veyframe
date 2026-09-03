import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TimelineEditor, deleteSceneFromTimeline } from "./timeline-editor";

const timeline = {
  project_id: "project-1",
  duration_ms: 20_000,
  scene_clips: [
    { id: "scene-clip-1", scene_id: "Opening", start_ms: 0, end_ms: 8_000, source_uri: "opening.webm" },
    { id: "scene-clip-2", scene_id: "Workflow", start_ms: 8_000, end_ms: 20_000, source_uri: "workflow.webm" },
  ],
  caption_clips: [
    { id: "caption-1", scene_id: "Opening", start_ms: 0, end_ms: 8_000, text: "Opening caption" },
    { id: "caption-2", scene_id: "Workflow", start_ms: 8_000, end_ms: 20_000, text: "Workflow caption" },
  ],
  zoom_clips: [
    { id: "zoom-1", start_ms: 9_000, end_ms: 11_000, scale: 1.4, target_rect: { x: 200, y: 100, width: 300, height: 180 }, focus_x: null, focus_y: null, source_viewport: null, easing: "ease_in_out" as const, source: "auto" as const },
  ],
  cursor_events: [
    { timestamp_ms: 1_000, event_type: "click" as const, scene_id: "Opening", locator: null, x: 300, y: 200, bounding_box: null, viewport: { width: 1280, height: 720, scroll_x: 0, scroll_y: 0, device_scale_factor: 1 } },
    { timestamp_ms: 9_000, event_type: "click" as const, scene_id: "Workflow", locator: null, x: 700, y: 300, bounding_box: null, viewport: { width: 1280, height: 720, scroll_x: 0, scroll_y: 0, device_scale_factor: 1 } },
  ],
  audio_clips: [
    { id: "audio-1", scene_id: "Opening", start_ms: 0, end_ms: 8_000, source_uri: "opening.wav" },
    { id: "audio-2", scene_id: "Workflow", start_ms: 8_000, end_ms: 20_000, source_uri: "workflow.wav" },
  ],
  narration_overrides: {},
  voice_config: null,
  cta_text: null,
  presentation: { template: "edge_to_edge" as const },
};

const project = {
  id: "project-1",
  name: "FlowSync Feature Tour",
  website_url: "https://example.com/flow",
  product_summary: "Show the real automation workflow for product leaders.",
  audience: "Product leaders",
  tone: "Professional",
  requested_duration_seconds: 72,
  cta: "Try it",
  brand_kit_id: null,
  status: "editing" as const,
  job_status: "idle" as const,
  owner_user_id: "user-1",
  created_at: "2026-09-01T12:00:00Z",
  updated_at: "2026-09-01T13:00:00Z",
};

const videoExport = {
  id: "export-1",
  project_id: "project-1",
  status: "succeeded",
  quality: "1080p",
  filename: "demo.mp4",
  width: 1920,
  height: 1080,
  duration_ms: 20_000,
  size_bytes: 2048,
  thumbnail_path: "thumbnail.jpg",
  download_url: "/api/projects/project-1/exports/export-1/download?token=fixture-token",
  retryable: false,
  error: null,
  created_at: "2026-09-01T12:00:00Z",
};

beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("TimelineEditor", () => {
  it("keeps legacy Studio CSS below the current editor layout layer", () => {
    const legacyCss = readFileSync("src/app/studio.css", "utf8");
    const editorCss = readFileSync("src/app/styles.css", "utf8");

    expect(legacyCss).toContain("@layer legacy-editor");
    expect(editorCss).toContain("grid-template-columns: minmax(560px, 1fr) 390px");
    expect(editorCss).toContain(".editor-right-sidebar { grid-column: 2; grid-row: 2;");
    expect(editorCss).toContain(".clip-inspector { grid-column: auto; grid-row: auto;");
  });

  it("loads the selected project and its persisted timeline from the API", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/timeline")) {
        return { ok: true, json: async () => ({ current: { project_id: "project-1", version: 3, timeline, change_summary: "Saved timeline", affected_ids: [] }, can_undo: true, can_redo: false }) };
      }
      if (url.endsWith("/exports/latest")) {
        return { ok: true, json: async () => videoExport };
      }
      return { ok: true, json: async () => project };
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<TimelineEditor projectId="project-1" />);

    expect(await screen.findByRole("heading", { name: "FlowSync Feature Tour" })).toBeInTheDocument();
    expect(screen.getByText("Opening caption")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/projects/project-1", expect.objectContaining({ cache: "no-store" }));
    expect(fetchMock).toHaveBeenCalledWith("/api/projects/project-1/timeline", expect.objectContaining({ cache: "no-store" }));
    expect(fetchMock).toHaveBeenCalledWith("/api/projects/project-1/exports/latest", expect.objectContaining({ cache: "no-store" }));
    expect(screen.getByLabelText("Preview video")).toHaveAttribute(
      "src",
      "/api/projects/project-1/exports/latest/video",
    );
    expect(screen.getByLabelText("Preview video")).not.toHaveAttribute("controls");
    expect(screen.getByRole("button", { name: "Play preview" })).toBeEnabled();
    expect(screen.getByRole("link", { name: "Download MP4" })).toHaveAttribute(
      "href",
      videoExport.download_url,
    );
    expect(screen.queryByText("Build a polished product story.")).not.toBeInTheDocument();
  });

  it("uses one external playback bar instead of nested native video controls", async () => {
    window.sessionStorage.setItem(
      "demodirector:export:project-1",
      JSON.stringify(videoExport),
    );
    const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();

    render(<TimelineEditor initialTimeline={timeline} projectId="project-1" />);

    expect(screen.getByLabelText("Preview video")).not.toHaveAttribute("controls");
    fireEvent.click(screen.getByRole("button", { name: "Play preview" }));

    expect(play).toHaveBeenCalledOnce();
    expect(await screen.findByRole("button", { name: "Pause preview" })).toBeEnabled();
  });

  it("selecting a zoom updates the inspector and manual scale persists", () => {
    render(<TimelineEditor initialTimeline={timeline} projectId="project-1" />);

    fireEvent.click(screen.getByRole("button", { name: "Select zoom zoom-1" }));
    expect(screen.getByRole("heading", { name: "Zoom clip" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Zoom scale"), { target: { value: "1.8" } });

    expect(screen.getAllByRole("status").at(-1)).toHaveTextContent(
      "Camera change ready · save to timeline",
    );
    const saved = JSON.parse(String(window.localStorage.getItem("demodirector:timeline:project-1"))) as { zoom_clips: Array<{ scale: number; source: string }> };
    expect(saved.zoom_clips[0]).toMatchObject({ scale: 1.8, source: "manual" });
  });

  it("organizes editing modes in a right-side tool rail", () => {
    render(<TimelineEditor initialTimeline={timeline} projectId="project-1" />);

    expect(screen.getByRole("navigation", { name: "Editor tools" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Primary navigation" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Zoom" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "Overlay" }));
    expect(screen.getByRole("heading", { name: "Video frame" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Spotlight" })).toBeInTheDocument();
  });

  it("shows saved research and the real generation pipeline in Sources mode", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/research")) {
        return {
          ok: true,
          json: async () => ({
            project_id: "project-1",
            sources: [{
              id: "source-1",
              project_id: "project-1",
              title: "Official product documentation",
              url: "https://example.com/docs",
              snippet: "The official workflow automates product demos.",
              source_type: "partner_search",
              retrieved_at: "2026-09-02T12:00:00Z",
            }],
            warning: null,
          }),
        };
      }
      return {
        ok: true,
        json: async () => ({
          ai: {
            status: "ready",
            provider: "google",
            model: "gemini-test",
            tts_model: "gemini-tts-test",
            agent: "demodirector_director",
            detail: null,
          },
          research: { status: "ready", provider: "parallel", mode: "fast" },
        }),
      };
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<TimelineEditor initialProject={project} initialTimeline={timeline} projectId="project-1" />);

    const tools = screen.getByRole("navigation", { name: "Editor tools" });
    const toolButtons = Array.from(tools.querySelectorAll("button"));
    expect(toolButtons.slice(0, 3).map((button) => button.textContent)).toEqual([
      "Setup",
      "Sources",
      "Layout",
    ]);

    fireEvent.click(screen.getByRole("button", { name: "Sources" }));

    expect(await screen.findByRole("heading", { name: "Research sources" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Official product documentation" })).toHaveAttribute(
      "href",
      "https://example.com/docs",
    );
    expect(screen.getAllByText("Parallel Search")).toHaveLength(2);
    expect(screen.getByText("gemini-test")).toBeInTheDocument();
    expect(screen.getByText("Google ADK")).toBeInTheDocument();
    expect(screen.getByText(/gemini-tts-test/)).toBeInTheDocument();
    expect(screen.getByText("Browser capture")).toBeInTheDocument();
    expect(screen.getByText("FFmpeg render")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/project-1/research",
      expect.objectContaining({ cache: "no-store" }),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/runtime/provenance",
      expect.objectContaining({ cache: "no-store" }),
    );
  });

  it("drags the red target to update the zoom center point", () => {
    render(<TimelineEditor initialTimeline={timeline} projectId="project-1" />);
    const target = screen.getByLabelText("Zoom target");
    vi.spyOn(target, "getBoundingClientRect").mockReturnValue({
      width: 400,
      height: 200,
      left: 100,
      top: 50,
      right: 500,
      bottom: 250,
      x: 100,
      y: 50,
      toJSON: () => ({}),
    });

    fireEvent.pointerDown(target, { clientX: 400, clientY: 100, pointerId: 1 });

    const dot = screen.getByRole("slider", { name: "Zoom center point" });
    expect(dot).toHaveStyle({ left: "75%", top: "25%" });
    const saved = JSON.parse(String(window.localStorage.getItem(
      "demodirector:timeline:project-1",
    ))) as { zoom_clips: Array<{ focus_x: number; focus_y: number }> };
    expect(saved.zoom_clips[0]).toMatchObject({ focus_x: 960, focus_y: 180 });
  });

  it("persists a selected presentation template and requires a new export", async () => {
    const updatedTimeline = {
      ...timeline,
      presentation: { template: "spotlight" as const },
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        current: {
          project_id: "project-1",
          version: 2,
          timeline: updatedTimeline,
          change_summary: "Change video frame",
          affected_ids: ["project-1"],
        },
        can_undo: true,
        can_redo: false,
      }),
    });
    vi.stubGlobal("fetch", fetchMock);
    window.sessionStorage.setItem(
      "demodirector:export:project-1",
      JSON.stringify(videoExport),
    );
    const { container } = render(
      <TimelineEditor initialTimeline={timeline} projectId="project-1" />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Overlay" }));
    fireEvent.click(screen.getByRole("button", { name: "Spotlight" }));

    await waitFor(() => expect(screen.getAllByRole("status").at(-1)).toHaveTextContent(
      "Spotlight frame saved · export again to update the video",
    ));
    const request = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(request.body))).toMatchObject({
      operations: [{
        operation_type: "change_presentation",
        target_id: "project-1",
        arguments: { template: "spotlight" },
      }],
    });
    expect(screen.getByLabelText("Preview video")).toHaveAttribute(
      "src",
      "/api/projects/project-1/exports/latest/video",
    );
    expect(screen.getByRole("button", { name: "Play preview" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Export changes" })).toBeEnabled();
    expect(window.sessionStorage.getItem("demodirector:export:project-1")).not.toBeNull();
    expect(window.localStorage.getItem("demodirector:export-stale:project-1")).toBe("true");
    expect(container.querySelector(".editor-preview-player")).toContainElement(
      screen.getByLabelText("Preview video"),
    );
    expect(container.querySelector(".preview-stage")).toHaveClass("preview-template-rendered");
    expect(container.querySelector(".preview-stage")).not.toHaveClass("preview-template-spotlight");
  });

  it("saves zoom duration and focus location as an undoable timeline edit", async () => {
    const updatedZoom = {
      ...timeline.zoom_clips[0],
      end_ms: 13_500,
      focus_x: 960,
      focus_y: 180,
      source: "prompt_edit" as const,
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        current: {
          project_id: "project-1",
          version: 2,
          timeline: { ...timeline, zoom_clips: [updatedZoom] },
          change_summary: "Update zoom framing",
          affected_ids: ["zoom-1"],
        },
        can_undo: true,
        can_redo: false,
      }),
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<TimelineEditor initialTimeline={timeline} projectId="project-1" />);

    fireEvent.change(screen.getByLabelText("Zoom duration"), { target: { value: "4.5" } });
    fireEvent.change(screen.getByLabelText("Horizontal focus"), { target: { value: "75" } });
    fireEvent.change(screen.getByLabelText("Vertical focus"), { target: { value: "25" } });
    fireEvent.click(screen.getByRole("button", { name: "Save zoom" }));

    await waitFor(() => expect(screen.getAllByRole("status").at(-1)).toHaveTextContent(
      "Zoom saved · export again to update the video",
    ));
    const request = fetchMock.mock.calls[0][1] as RequestInit;
    const body = JSON.parse(String(request.body)) as {
      operations: Array<{ operation_type: string; target_id: string; arguments: Record<string, unknown> }>;
    };
    expect(body.operations[0]).toMatchObject({
      operation_type: "update_zoom",
      target_id: "zoom-1",
      arguments: { end_ms: 13_500, focus_x: 960, focus_y: 180 },
    });
    expect(screen.getByRole("button", { name: "Undo timeline edit" })).toBeEnabled();
  });

  it("removes a zoom from the saved timeline", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        current: {
          project_id: "project-1",
          version: 2,
          timeline: { ...timeline, zoom_clips: [] },
          change_summary: "Remove zoom",
          affected_ids: ["zoom-1"],
        },
        can_undo: true,
        can_redo: false,
      }),
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<TimelineEditor initialTimeline={timeline} projectId="project-1" />);

    fireEvent.click(screen.getByRole("button", { name: "Remove zoom" }));

    await waitFor(() => expect(screen.getAllByRole("status").at(-1)).toHaveTextContent(
      "Zoom removed · export again to update the video",
    ));
    expect(screen.queryByRole("button", { name: "Select zoom zoom-1" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Select a zoom" })).toBeInTheDocument();
    const request = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(request.body))).toMatchObject({
      operations: [{ operation_type: "delete_zoom", target_id: "zoom-1" }],
    });
  });

  it("dragging the playhead updates synchronized preview time", () => {
    render(<TimelineEditor initialTimeline={timeline} projectId="project-1" />);

    fireEvent.change(screen.getByLabelText("Timeline playhead"), { target: { value: "12500" } });

    expect(screen.getByLabelText("Preview time")).toHaveTextContent("0:13");
  });

  it("deleting a selected scene removes its caption and audio tracks", () => {
    render(<TimelineEditor initialTimeline={timeline} projectId="project-1" />);

    fireEvent.click(screen.getByRole("button", { name: "Cut" }));
    fireEvent.click(screen.getByRole("button", { name: /Delete/ }));

    expect(screen.queryByText("Opening caption")).not.toBeInTheDocument();
    expect(screen.getByText("Workflow caption")).toBeInTheDocument();
    expect(screen.getAllByRole("status").at(-1)).toHaveTextContent("Scene deleted · tracks updated");
  });

  it("the delete helper leaves unrelated clips unchanged apart from time shift", () => {
    const updated = deleteSceneFromTimeline(timeline, "Opening");

    expect(updated.duration_ms).toBe(12_000);
    expect(updated.scene_clips[0]).toMatchObject({ scene_id: "Workflow", start_ms: 0, end_ms: 12_000 });
    expect(updated.caption_clips[0]).toMatchObject({ id: "caption-2", text: "Workflow caption" });
    expect(updated.cursor_events).toHaveLength(1);
    expect(updated.cursor_events[0]).toMatchObject({ scene_id: "Workflow", timestamp_ms: 1_000 });
  });

  it("shows a typed edit summary for review before apply", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      json: async () => ({
        supported: true,
        summary: "Shorten the opening scene",
        explanation: "Trim one second without changing other clips.",
        operations: [{
          operation_type: "trim_scene",
          target_id: "scene-clip-1",
          arguments: { start_ms: 0, end_ms: 7_000 },
          rationale: "Reach the workflow sooner.",
        }],
      }),
    }))); 
    render(<TimelineEditor initialTimeline={timeline} projectId="project-1" />);

    fireEvent.click(screen.getByRole("button", { name: "Adjust" }));
    fireEvent.change(screen.getByLabelText("Edit instruction"), { target: { value: "Make the opening shorter" } });
    fireEvent.click(screen.getByRole("button", { name: "Propose edit" }));

    expect(await screen.findByRole("heading", { name: "Shorten the opening scene" })).toBeInTheDocument();
    expect(screen.getByText("trim scene")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Apply proposed edits" })).toBeEnabled();
  });

  it("applies a proposal transactionally and exposes undo", async () => {
    const changedTimeline = { ...timeline, zoom_clips: [{ ...timeline.zoom_clips[0], scale: 1.8, source: "prompt_edit" as const }] };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ supported: true, summary: "Increase focus", explanation: "Increase one zoom.", operations: [{ operation_type: "update_zoom", target_id: "zoom-1", arguments: { scale: 1.8 }, rationale: "Focus the action." }] }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ current: { project_id: "project-1", version: 2, timeline: changedTimeline, change_summary: "Increase focus", affected_ids: ["zoom-1"] }, can_undo: true, can_redo: false }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ current: { project_id: "project-1", version: 1, timeline, change_summary: "Initial timeline", affected_ids: [] }, can_undo: false, can_redo: true }) });
    vi.stubGlobal("fetch", fetchMock);
    render(<TimelineEditor initialTimeline={timeline} projectId="project-1" />);

    fireEvent.click(screen.getByRole("button", { name: "Adjust" }));
    fireEvent.change(screen.getByLabelText("Edit instruction"), { target: { value: "Increase focus" } });
    fireEvent.click(screen.getByRole("button", { name: "Propose edit" }));
    fireEvent.click(await screen.findByRole("button", { name: "Apply proposed edits" }));
    await waitFor(() => expect(screen.getAllByRole("status").at(-1)).toHaveTextContent("Applied version 2"));
    const undo = screen.getByRole("button", { name: "Undo timeline edit" });
    expect(undo).toBeEnabled();
    fireEvent.click(undo);
    await waitFor(() => expect(screen.getAllByRole("status").at(-1)).toHaveTextContent("Undid to version 1"));
  });

  it("creates a 1080p export and exposes its download", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ...videoExport,
      }),
    }));
    render(<TimelineEditor initialTimeline={timeline} projectId="project-1" />);

    fireEvent.click(screen.getByRole("button", { name: "Export 1080p" }));

    const download = await screen.findByRole("link", { name: "Download MP4" });
    expect(download).toHaveAttribute(
      "href",
      "/api/projects/project-1/exports/export-1/download?token=fixture-token",
    );
    expect(screen.getAllByRole("status").at(-1)).toHaveTextContent(
      "1080p export ready to download",
    );
  });

  it("shows an honest empty studio when the selected project has no timeline", async () => {
    const selectedProject = { ...project, id: "judge-demo-session-1" };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).endsWith("/timeline")) {
        return { ok: false, json: async () => ({ detail: "Timeline not found" }) };
      }
      return { ok: true, json: async () => selectedProject };
    }));

    render(<TimelineEditor projectId="judge-demo-session-1" />);

    expect(await screen.findByRole("heading", { name: "Timeline not ready" })).toBeInTheDocument();
    expect(screen.getAllByText("FlowSync Feature Tour")).toHaveLength(2);
    expect(screen.getByText(/doesn’t have a generated timeline yet/i)).toBeInTheDocument();
    expect(screen.queryByText("Meet your product story.")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Export unavailable" })).not.toBeInTheDocument();
  });
});
