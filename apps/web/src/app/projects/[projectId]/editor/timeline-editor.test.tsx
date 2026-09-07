import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  TimelineEditor,
  deleteSceneFromTimeline,
  duplicateSceneInTimeline,
  splitSceneInTimeline,
} from "./timeline-editor";

const timeline = {
  project_id: "project-1",
  duration_ms: 20_000,
  demo_mode: "product_demo" as const,
  presentation_pack_id: null,
  motion_plan_id: null,
  motion_design_version: null,
  attention_plan_id: null,
  attention_design_version: null,
  style_plan_id: null,
  style_design_version: null,
  visual_variant: null,
  long_form_plan_id: null,
  long_form_version: null,
  scene_clips: [
    { id: "scene-clip-1", scene_id: "Opening", start_ms: 0, end_ms: 8_000, source_uri: "opening.webm", source_start_ms: 0 },
    { id: "scene-clip-2", scene_id: "Workflow", start_ms: 8_000, end_ms: 20_000, source_uri: "workflow.webm", source_start_ms: 0 },
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
  presentation: { template: "edge_to_edge" as const, zoom_enabled: true },
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
  demo_mode: "product_demo" as const,
  output_orientation: "landscape" as const,
  zoom_enabled: true,
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

function completedTraceStage(
  kind: string,
  label: string,
  service: string,
  sequence: number,
  contribution: { key: string; label: string; value: number; unit: string },
  outputHref: string | null = null,
) {
  return {
    id: `${kind}:1`, project_id: "project-1", kind, sequence, attempt: 1, retry_count: 0,
    status: "succeeded", label, service,
    started_at: "2026-09-04T12:00:00.000Z", completed_at: "2026-09-04T12:00:01.000Z", elapsed_ms: 1000,
    message: `${label} completed.`, contributions: [contribution], output_href: outputHref,
  };
}

const generationTrace = {
  id: "trace-job-1", project_id: "project-1", job_id: "job-1", status: "succeeded",
  created_at: "2026-09-04T12:00:00.000Z", updated_at: "2026-09-04T12:00:10.000Z",
  stages: [
    completedTraceStage("inspection", "Inspect website", "Playwright", 11, { key: "pages_inspected", label: "Pages inspected", value: 1, unit: "pages" }, "/projects/project-1/editor#source-group-website_inspection"),
    completedTraceStage("research", "Research public context", "Parallel Search · fast", 21, { key: "sources_saved", label: "Sources saved", value: 1, unit: "sources" }, "/projects/project-1/editor#source-group-parallel_search"),
    { id: "adk_coordination:0", project_id: "project-1", kind: "adk_coordination", sequence: 30, attempt: 0, retry_count: 0, status: "not_used", label: "Coordinate planning workflow", service: "Google ADK", started_at: null, completed_at: null, elapsed_ms: null, message: "Available for agent-led workflows; this durable run used typed stage orchestration.", contributions: [{ key: "workflow_runs", label: "Agent workflow runs", value: 0, unit: "runs" }], output_href: null },
    completedTraceStage("understanding", "Understand product", "Google Gemini · gemini-test", 41, { key: "features_understood", label: "Features understood", value: 3, unit: "features" }),
    completedTraceStage("storyboard", "Plan storyboard", "Google Gemini · gemini-test", 51, { key: "scenes_planned", label: "Scenes planned", value: 2, unit: "scenes" }, "/projects/project-1/storyboard"),
    completedTraceStage("capture", "Record browser flow", "Playwright", 61, { key: "interactions_recorded", label: "Interactions recorded", value: 2, unit: "interactions" }),
    completedTraceStage("narration", "Create narration", "Gemini TTS · gemini-tts-test", 71, { key: "narration_segments", label: "Narration segments", value: 2, unit: "segments" }),
    completedTraceStage("auto_camera", "Frame interactions", "Auto Camera", 81, { key: "zooms_created", label: "Camera moves", value: 1, unit: "zooms" }),
    completedTraceStage("captions", "Build captions", "Caption engine", 91, { key: "captions_created", label: "Caption clips", value: 2, unit: "captions" }),
    completedTraceStage("render", "Render video", "FFmpeg", 101, { key: "exports_created", label: "Exports created", value: 1, unit: "exports" }, "/projects/project-1/editor#editor-preview"),
  ],
};

const motionPlan = {
  id: "motion-plan-1",
  project_id: "project-1",
  job_id: "job-1",
  run_id: "motion-run-1",
  request_fingerprint: "f".repeat(64),
  design_tokens: {},
  duration_ms: 20_000,
  scene_ids: ["Opening", "Workflow"],
  product_clip_refs: ["scene:Opening", "scene:Workflow"],
  summary: "Keep the working product visible while each proof point lands.",
  cues: [{
    id: "cue-1", scene_id: "Opening", primitive: "fade_slide", layer: "transition",
    start_ms: 0, end_ms: 600, easing: "standard", text: null,
    product_clip_ref: "scene:Opening",
  }],
  editorial_plan: {
    id: "editorial-plan-1", project_id: "project-1", job_id: "job-1",
    run_id: "motion-run-1", motion_plan_id: "motion-plan-1",
    catalog_version: "editorial-v1", design_version: "motion-v1", duration_ms: 20_000,
    scene_ids: ["Opening", "Workflow"], product_clip_refs: ["scene:Opening", "scene:Workflow"],
    summary: "Keep the product visible.",
    scenes: [
      { id: "editorial-scene-1", scene_id: "Opening", section: "hook", template_id: "hook", product_clip_ref: "scene:Opening", product_treatment: "moving_background", start_ms: 0, end_ms: 8_000, eyebrow: null, title: "See it work", body: null, crop: { x: 0, y: 0, width: 1, height: 1 } },
      { id: "editorial-scene-2", scene_id: "Workflow", section: "product_walkthrough", template_id: "feature_callout", product_clip_ref: "scene:Workflow", product_treatment: "full_focus", start_ms: 8_000, end_ms: 20_000, eyebrow: null, title: "Follow the workflow", body: null, crop: { x: 0, y: 0, width: 1, height: 1 } },
    ],
    created_at: "2026-09-04T12:00:00.000Z",
  },
  created_at: "2026-09-04T12:00:00.000Z",
};

const attentionPlan = {
  id: "attention-plan-1", project_id: "project-1", job_id: "job-1",
  parent_run_id: "motion-run-1", manual_override_of: null, duration_ms: 20_000,
  targets: [{
    id: "target-1", scene_id: "Opening", locator_fingerprint: "a".repeat(64),
    timestamp_ms: 1_000, rect: { x: 0.2, y: 0.3, width: 0.1, height: 0.1 },
    viewport: { width: 1280, height: 720, scroll_x: 0, scroll_y: 0, device_scale_factor: 1 },
  }],
  narration_statement_ids: ["Opening-statement-1"], summary: "Guide attention to the recorded Create control.",
  callouts: [{ id: "callout-1", target_id: "target-1", callout_type: "label_connector", placement: "top_left", start_ms: 1_000, end_ms: 2_000, text: "Create project" }],
  caption_emphasis: [], created_at: "2026-09-04T12:00:00.000Z",
};

const stylePlan = {
  id: "style-plan-1", project_id: "project-1", job_id: "job-1",
  parent_run_id: "motion-run-1", version: "style-v1",
  audience: "Product leaders", purpose: "Show the working product",
  scene_ids: ["Opening", "Workflow"],
  allowed_evidence_refs: ["storyboard:1", "attention:1"],
  recommendation_evidence_refs: ["storyboard:1"],
  rationale: "Keep the working product large and the motion restrained.",
  decision: { recommended_variant: "product_spotlight", selected_variant: "product_spotlight", outcome: "recommended", decided_at: "2026-09-04T12:00:00.000Z" },
  defaults: [
    { variant_id: "editorial_story", product_scale: "composed", callout_density: "medium", motion_pace: "deliberate" },
    { variant_id: "product_spotlight", product_scale: "large", callout_density: "low", motion_pace: "calm" },
    { variant_id: "technical_proof", product_scale: "evidence_focused", callout_density: "medium", motion_pace: "precise" },
  ],
  overrides: [], manual_override_of: null, created_at: "2026-09-04T12:00:00.000Z",
};

const longFormSections = [
  ["hook", 4_000], ["problem", 6_000], ["promise", 10_000],
  ["product_walkthrough", 75_000], ["trust_technology", 35_000],
  ["editing_control", 25_000], ["finished_result", 20_000], ["closing", 5_000],
] as const;
let longFormCursor = 0;
const narrationCounts = [10, 14, 22, 170, 78, 56, 42, 8];
const longFormPlan = {
  id: "longform-plan-1", project_id: "project-1", job_id: "job-1",
  adk_run_id: "longform-run-1", parent_motion_run_id: "motion-run-1",
  version: "longform-v1", motion_version: "motion-v1", style_version: "style-v1",
  visual_variant: "product_spotlight", duration_ms: 180_000, research_status: "complete",
  evidence_refs: ["source:source-1"], parallel_source_refs: ["source:source-1"],
  product_clip_refs: ["scene:Opening"], target_ids: ["target-1"],
  sections: longFormSections.map(([id, duration], order) => {
    const start = longFormCursor; longFormCursor += duration;
    return { id, order, start_ms: start, end_ms: longFormCursor, narration: Array(narrationCounts[order]).fill("product").join(" "), source_refs: ["source:source-1"], product_clip_ref: "scene:Opening", product_visible: true };
  }),
  beats: Array.from({ length: 24 }, (_, index) => {
    const section = Math.min(7, Math.floor(index / 3));
    const [sectionId] = longFormSections[section];
    const sectionStart = [0, 4_000, 10_000, 20_000, 95_000, 130_000, 155_000, 175_000][section];
    let start = sectionStart + (index % 3) * 1_000;
    let purpose = sectionId === "hook" ? "hook" : sectionId === "problem" ? "problem" : sectionId === "promise" ? "promise" : sectionId === "closing" ? "closing" : "walkthrough";
    if (index === 9) { start = 20_000; purpose = "product_operation"; }
    if (index === 10) { start = 25_000; purpose = "create_action"; }
    if (index === 11) { start = 40_000; purpose = "finished_glimpse"; }
    return { id: `beat-${index + 1}`, section_id: sectionId, start_ms: start, end_ms: start + 500, purpose, template_id: "framed_product", product_clip_ref: "scene:Opening", target_id: null, source_refs: ["source:source-1"] };
  }),
  chapters: [
    { id: "chapter-1", order: 0, section_ids: ["hook", "problem"], start_ms: 0, end_ms: 10_000 },
    { id: "chapter-2", order: 1, section_ids: ["promise", "product_walkthrough"], start_ms: 10_000, end_ms: 95_000 },
    { id: "chapter-3", order: 2, section_ids: ["trust_technology", "editing_control"], start_ms: 95_000, end_ms: 155_000 },
    { id: "chapter-4", order: 3, section_ids: ["finished_result", "closing"], start_ms: 155_000, end_ms: 180_000 },
  ].map((chapter) => ({ ...chapter, project_id: "project-1", viewport: { width: 2560, height: 1440, scroll_x: 0, scroll_y: 0, device_scale_factor: 1 }, account_ref: "account:owner", project_state_ref: "storyboard:1", style_version: "style-v1", cursor_continuity_key: "cursor:1" })),
  condensed_intervals: [], audio_mix: { narration_lufs: -16, music_lufs: -28, ducking_db: -8, fade_ms: 500 },
  first_product_operation_ms: 20_000, create_action_ms: 25_000, finished_glimpse_ms: 40_000,
  product_presence_percent: 100, created_at: "2026-09-04T12:00:00.000Z",
};
const chapterCheckpoints = longFormPlan.chapters.map((chapter, index) => ({
  id: `checkpoint-${index + 1}`, project_id: "project-1", plan_id: longFormPlan.id,
  chapter_id: chapter.id, status: index === 1 ? "failed" : "pending", attempt: index === 1 ? 1 : 0,
  artifact_ref: null, artifact_sha256: null, elapsed_ms: null, replaces_checkpoint_id: null,
  created_at: "2026-09-04T12:00:00.000Z",
}));

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

  it.each([false, true])("observes playback without seeking when paused=%s", (paused) => {
    render(<TimelineEditor initialTimeline={timeline} projectId="project-1" />);
    const video = screen.getByLabelText("Preview video") as HTMLVideoElement;
    let clock = 0;
    const seek = vi.fn();
    Object.defineProperty(video, "currentTime", { configurable: true, get: () => clock, set: seek });
    Object.defineProperty(video, "paused", { configurable: true, value: paused });

    for (const second of [0.2514, 0.5028, 1.0041, 3.7549, 20]) {
      clock = second;
      fireEvent.timeUpdate(video);
      expect(screen.getByLabelText("Timeline playhead")).toHaveValue(String(Math.round(second * 1000)));
    }

    expect(screen.getByLabelText("Preview time")).toHaveTextContent("0:20");
    expect(seek).not.toHaveBeenCalled();
  });

  it.each([false, true])("seeks once for deliberate scrubbing when paused=%s", (paused) => {
    render(<TimelineEditor initialTimeline={timeline} projectId="project-1" />);
    const video = screen.getByLabelText("Preview video") as HTMLVideoElement;
    let clock = 0;
    const seek = vi.fn((seconds: number) => { clock = seconds; });
    Object.defineProperty(video, "currentTime", { configurable: true, get: () => clock, set: seek });
    Object.defineProperty(video, "paused", { configurable: true, value: paused });

    fireEvent.change(screen.getByLabelText("Timeline playhead"), { target: { value: "12500" } });
    fireEvent.timeUpdate(video);
    expect(seek).toHaveBeenCalledExactlyOnceWith(12.5);
    expect(screen.getByLabelText("Preview time")).toHaveTextContent("0:13");
  });

  it("keeps captions and playhead seeking available without the Captions sidebar mode", () => {
    render(<TimelineEditor initialTimeline={timeline} projectId="project-1" />);
    expect(screen.getByText("Workflow caption")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Timeline playhead"), { target: { value: "8000" } });
    expect((screen.getByLabelText("Preview video") as HTMLVideoElement).currentTime).toBe(8);
    expect(screen.getByLabelText("Timeline playhead")).toHaveValue("8000");
  });

  it("selecting a timeline scene seeks its recorded segment exactly once", () => {
    render(<TimelineEditor initialTimeline={timeline} projectId="project-1" />);
    const video = screen.getByLabelText("Preview video") as HTMLVideoElement;
    const seek = vi.fn();
    Object.defineProperty(video, "currentTime", { configurable: true, get: () => 0, set: seek });
    fireEvent.click(screen.getByRole("button", { name: /2Workflow/ }));
    expect(seek).toHaveBeenCalledExactlyOnceWith(8);
    expect(screen.getByLabelText("Timeline playhead")).toHaveValue("8000");
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
    expect(screen.getByText("Recording frame")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Spotlight" })).toBeInTheDocument();
  });

  it("uses the authored template sequence instead of a second frame for Presentation Demo", () => {
    const presentationTimeline = {
      ...timeline,
      duration_ms: 120_000,
      demo_mode: "presentation_demo" as const,
      presentation_pack_id: "presentation-story@1" as const,
    };

    render(<TimelineEditor initialTimeline={presentationTimeline} projectId="project-1" />);

    fireEvent.click(screen.getByRole("button", { name: "Setup" }));
    expect(screen.getByText("Template sequence")).toBeInTheDocument();
    expect(screen.getByText("Presentation Story v1")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Overlay" }));
    expect(screen.getByRole("heading", { name: "Video frame" })).toBeInTheDocument();
    expect(screen.getByText("Recording frame")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Presentation Story v1 controls framing and places the real product recording inside its authored layouts. No additional recording frame is applied.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edge-to-edge" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Soft frame" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Spotlight" })).not.toBeInTheDocument();
  });

  it("shows the saved format and reversibly bypasses smooth zoom", async () => {
    const updatedTimeline = {
      ...timeline,
      presentation: { ...timeline.presentation, zoom_enabled: false },
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        current: {
          project_id: "project-1",
          version: 2,
          timeline: updatedTimeline,
          change_summary: "Disable smooth zoom",
          affected_ids: ["project-1"],
        },
        can_undo: true,
        can_redo: false,
      }),
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<TimelineEditor initialProject={project} initialTimeline={timeline} projectId="project-1" />);

    fireEvent.click(screen.getByRole("button", { name: "Setup" }));
    expect(screen.getByText("Format")).toBeInTheDocument();
    expect(screen.getByText("Product Demo")).toBeInTheDocument();
    expect(screen.getByText("Smooth zoom")).toBeInTheDocument();
    expect(screen.getByText("On")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Zoom" }));
    const switchControl = screen.getByRole("switch", { name: "Smooth zoom" });
    expect(switchControl).toHaveAttribute("aria-checked", "true");
    fireEvent.click(switchControl);

    expect(await screen.findByText("Zooms are bypassed on export. Saved zoom clips are retained and remain editable.")).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Smooth zoom" })).toHaveAttribute("aria-checked", "false");
    expect(screen.getByRole("button", { name: "Select zoom zoom-1" })).toBeInTheDocument();
    const request = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(request.body))).toMatchObject({
      summary: "Disable smooth zoom",
      operations: [{
        operation_type: "change_presentation",
        target_id: "project-1",
        arguments: { template: "edge_to_edge", zoom_enabled: false },
      }],
    });
  });

  it("shows saved research and the real generation pipeline in Sources mode", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/source-contributions")) {
        return {
          ok: true,
          json: async () => ({
            project_id: "project-1",
            storyboard_version: 2,
            fingerprint: "a".repeat(64),
            status: "ready",
            partial_evidence: false,
            sources: [
              { id: "brief:project-1", project_id: "project-1", title: "Project brief", url: null, domain: "Creator input", origin: "project_brief", retrieval_state: "saved", retrieved_at: "2026-09-02T12:00:00Z", excerpt: "Show the workflow." },
              { id: "website-1", project_id: "project-1", title: "Product dashboard", url: "https://example.com", domain: "example.com", origin: "website_inspection", retrieval_state: "saved", retrieved_at: "2026-09-02T12:00:00Z", excerpt: "Dashboard Continue" },
              { id: "source-1", project_id: "project-1", title: "Official product documentation", url: "https://example.com/docs", domain: "example.com", origin: "parallel_search", retrieval_state: "saved", retrieved_at: "2026-09-02T12:00:00Z", excerpt: "The official workflow automates product demos." },
              { id: "source-unused", project_id: "project-1", title: "Archived release notes", url: "https://example.com/releases", domain: "example.com", origin: "parallel_search", retrieval_state: "saved", retrieved_at: "2026-09-02T12:00:00Z", excerpt: "Previous release context." },
            ],
            scenes: [
              { id: "Opening", title: "Opening", order: 0 },
              { id: "Workflow", title: "Workflow", order: 1 },
            ],
            narration_statements: [{ id: "Workflow-statement-1", scene_id: "Workflow", text: "The workflow automates product demos.", status: "source_quote", source_ids: ["source-1"], explanation: "Text appears in a saved excerpt." }],
            contributions: [
              { id: "brief:project-1:brief_context", project_id: "project-1", source_id: "brief:project-1", kind: "brief_context", scene_ids: ["Opening", "Workflow"], narration_statement_ids: [], usage_state: "used", label: "Used to frame the approved storyboard" },
              { id: "website-1:website_structure", project_id: "project-1", source_id: "website-1", kind: "website_structure", scene_ids: ["Opening"], narration_statement_ids: [], usage_state: "used", label: "Used to plan page structure and capture steps" },
              { id: "source-1:research_context", project_id: "project-1", source_id: "source-1", kind: "research_context", scene_ids: ["Workflow"], narration_statement_ids: [], usage_state: "used", label: "Research context used in approved scenes" },
              { id: "source-1:factual_narration", project_id: "project-1", source_id: "source-1", kind: "factual_narration", scene_ids: ["Workflow"], narration_statement_ids: ["Workflow-statement-1"], usage_state: "used", label: "Attributed in approved narration" },
              { id: "source-unused:research_context", project_id: "project-1", source_id: "source-unused", kind: "research_context", scene_ids: [], narration_statement_ids: [], usage_state: "unused", label: "Research context — not used in the final script" },
            ],
          }),
        };
      }
      if (url.endsWith("/generation/trace")) return {
        ok: true,
        status: 200,
        json: async () => generationTrace,
      };
      if (url.endsWith("/generation/motion-plan")) return {
        ok: true,
        status: 200,
        json: async () => motionPlan,
      };
      if (url.endsWith("/generation/attention-plan")) return {
        ok: true,
        status: 200,
        json: async () => attentionPlan,
      };
      if (url.endsWith("/generation/style-plan")) return {
        ok: true,
        status: 200,
        json: async () => stylePlan,
      };
      if (url.endsWith("/generation/long-form-plan")) return { ok: true, status: 200, json: async () => longFormPlan };
      if (url.endsWith("/generation/long-form-checkpoints")) return { ok: true, status: 200, json: async () => chapterCheckpoints };
      throw new Error(`Unexpected URL: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<TimelineEditor initialProject={project} initialTimeline={timeline} projectId="project-1" />);

    const tools = screen.getByRole("navigation", { name: "Editor tools" });
    const toolButtons = Array.from(tools.querySelectorAll("button"));
    expect(toolButtons.map((button) => button.textContent)).toEqual([
      "Setup",
      "Sources",
      "Layout",
      "Cut",
      "Zoom",
      "Overlay",
      "Adjust",
    ]);

    fireEvent.click(screen.getByRole("button", { name: "Sources" }));

    expect(await screen.findByRole("heading", { name: "Source map" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Official product documentation" })).toHaveAttribute(
      "href",
      "https://example.com/docs",
    );
    expect(screen.getAllByText(/Parallel Search/).length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText("Project brief").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Website inspection")).toBeInTheDocument();
    expect(screen.getByText("Research context — not used in the final script")).toBeInTheDocument();
    expect(screen.queryByText(/verified claim/i)).not.toBeInTheDocument();
    expect(screen.getAllByText("Google Gemini · gemini-test")).toHaveLength(2);
    expect(screen.getByText("Google ADK")).toBeInTheDocument();
    expect(await screen.findByText(/Google ADK planned 1 validated cue/)).toBeInTheDocument();
    expect(screen.getByText(/2 product-present templates/)).toBeInTheDocument();
    expect(await screen.findByText(/accepted 1 target-aware callout/)).toBeInTheDocument();
    expect(await screen.findByText("Product Spotlight")).toBeInTheDocument();
    expect(await screen.findByText(`${longFormPlan.sections.length} sections · ${longFormPlan.beats.length} visual beats`)).toBeInTheDocument();
    expect(screen.getByText(/1 linked project inputs/)).toBeInTheDocument();
    expect(screen.getByText(/Gemini TTS · gemini-tts-test/)).toBeInTheDocument();
    expect(screen.getByText("Record browser flow")).toBeInTheDocument();
    expect(screen.getByText("FFmpeg")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/project-1/quality-api/source-contributions",
      expect.objectContaining({ cache: "no-store" }),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/project-1/generation/trace",
      expect.objectContaining({ cache: "no-store" }),
    );
    const renderStage = screen.getByText("Render video").closest("details")!;
    fireEvent.click(within(renderStage).getByText("Render video"));
    expect(within(renderStage).getByRole("link", { name: "Open saved output" })).toHaveAttribute("href", "/projects/project-1/editor#editor-preview");

    const usageButtons = screen.getAllByRole("button", { name: "Review usage" });
    fireEvent.click(usageButtons.at(-1)!);
    expect(screen.getByRole("heading", { name: "Official product documentation" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Approved narration/ }));
    expect(screen.getByLabelText("Preview time")).toHaveTextContent("0:08");
    fireEvent.click(screen.getByRole("button", { name: "← All sources" }));
    expect(screen.getByRole("heading", { name: "Where each source was used" })).toBeInTheDocument();
  });

  it.each(["Quality", "Style", "Story", "Callouts", "Captions", "Audio"])("does not expose the removed %s sidebar mode", (label) => {
    render(<TimelineEditor initialProject={project} initialTimeline={timeline} projectId="project-1" />);
    const tools = screen.getByRole("navigation", { name: "Editor tools" });
    expect(within(tools).queryByRole("button", { name: label })).not.toBeInTheDocument();
    expect(within(tools).getByRole("button", { name: "Zoom" })).toHaveAttribute("aria-pressed", "true");
  });

  it("removes stale usage links and provides an approval route", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).endsWith("/source-contributions")) return {
        ok: true, status: 200,
        json: async () => ({
          project_id: "project-1", storyboard_version: 3, fingerprint: "b".repeat(64),
          status: "stale", partial_evidence: true,
          sources: [{ id: "brief:project-1", project_id: "project-1", title: "Project brief", url: null, domain: "Creator input", origin: "project_brief", retrieval_state: "saved", retrieved_at: null, excerpt: "Changed brief." }],
          scenes: [{ id: "Opening", title: "Opening", order: 0 }], narration_statements: [], contributions: [],
        }),
      };
      return { ok: false, status: 404, json: async () => ({ detail: "Generation trace not found" }) };
    }));
    render(<TimelineEditor initialProject={project} initialTimeline={timeline} projectId="project-1" />);

    fireEvent.click(screen.getByRole("button", { name: "Sources" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Old scene and narration links were removed");
    expect(screen.getByRole("link", { name: "Review storyboard evidence" })).toHaveAttribute("href", "/projects/project-1/storyboard");
    expect(screen.queryByRole("button", { name: "Review usage" })).not.toBeInTheDocument();
  });

  it("renders partial and empty approved evidence states", async () => {
    const emptyMap = {
      project_id: "project-1", storyboard_version: 2, fingerprint: "c".repeat(64),
      status: "ready", partial_evidence: true, sources: [], scenes: [],
      narration_statements: [], contributions: [],
    };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).endsWith("/source-contributions")) {
        return { ok: true, status: 200, json: async () => emptyMap };
      }
      return { ok: false, status: 404, json: async () => ({ detail: "Generation trace not found" }) };
    }));
    render(<TimelineEditor initialProject={project} initialTimeline={timeline} projectId="project-1" />);

    fireEvent.click(screen.getByRole("button", { name: "Sources" }));

    expect(await screen.findByText(/Some evidence groups are empty/)).toHaveAttribute("role", "status");
    expect(screen.getByText("No saved evidence is available for this approved storyboard.")).toBeInTheDocument();
    expect(screen.getByText("No durable generation activity is available for this project.")).toBeInTheDocument();
  });

  it("keeps failed and retried stage attempts understandable", async () => {
    const emptyMap = {
      project_id: "project-1", storyboard_version: 2, fingerprint: "d".repeat(64),
      status: "ready", partial_evidence: false, sources: [], scenes: [],
      narration_statements: [], contributions: [],
    };
    const failedInspection = {
      ...generationTrace.stages[0], id: "inspection:1", sequence: 11, status: "failed",
      message: "Inspect website failed. Saved checkpoints are unchanged.", contributions: [],
      output_href: null,
    };
    const recoveredInspection = {
      ...generationTrace.stages[0], id: "inspection:2", sequence: 12, attempt: 2,
      retry_count: 1, message: "Inspect website completed and saved 1 pages.",
    };
    const retriedTrace = {
      ...generationTrace,
      stages: [failedInspection, recoveredInspection, ...generationTrace.stages.slice(1)],
    };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).endsWith("/source-contributions")) {
        return { ok: true, status: 200, json: async () => emptyMap };
      }
      return { ok: true, status: 200, json: async () => retriedTrace };
    }));
    render(<TimelineEditor initialProject={project} initialTimeline={timeline} projectId="project-1" />);

    fireEvent.click(screen.getByRole("button", { name: "Sources" }));

    const attempts = await screen.findAllByText("Inspect website");
    expect(attempts).toHaveLength(2);
    const failedAttempt = attempts[0].closest("details")!;
    const recoveredAttempt = attempts[1].closest("details")!;
    fireEvent.click(attempts[0]);
    expect(within(failedAttempt).getByText("Inspect website failed. Saved checkpoints are unchanged.")).toBeInTheDocument();
    expect(within(failedAttempt).getByText("Attempt 1")).toBeInTheDocument();
    fireEvent.click(attempts[1]);
    expect(within(recoveredAttempt).getByText("Attempt 2 · 1 retry")).toBeInTheDocument();
  });

  it("shows a trace-specific error while keeping the source map usable", async () => {
    const emptyMap = {
      project_id: "project-1", storyboard_version: 2, fingerprint: "e".repeat(64),
      status: "ready", partial_evidence: false, sources: [], scenes: [],
      narration_statements: [], contributions: [],
    };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => String(input).endsWith("/source-contributions")
      ? { ok: true, status: 200, json: async () => emptyMap }
      : { ok: true, status: 200, json: async () => ({ invalid: true }) }));
    render(<TimelineEditor initialProject={project} initialTimeline={timeline} projectId="project-1" />);

    fireEvent.click(screen.getByRole("button", { name: "Sources" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Generation activity is temporarily unavailable");
    expect(screen.getByRole("heading", { name: "Where each source was used" })).toBeInTheDocument();
  });

  it("shows an accessible Sources error without replacing saved editor state", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    render(<TimelineEditor initialProject={project} initialTimeline={timeline} projectId="project-1" />);

    fireEvent.click(screen.getByRole("button", { name: "Sources" }));

    expect(screen.getByText(/Loading saved evidence/)).toBeInTheDocument();
    expect(await screen.findByRole("alert")).toHaveTextContent("Source details are temporarily unavailable");
    expect(screen.getByText("Opening caption")).toBeInTheDocument();
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
      presentation: { template: "spotlight" as const, zoom_enabled: true },
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
        arguments: { template: "spotlight", zoom_enabled: true },
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

  it("keeps the fixed Presentation Demo sequence read-only in Cut mode", () => {
    const presentationTimeline = {
      ...timeline,
      duration_ms: 120_000,
      demo_mode: "presentation_demo" as const,
      presentation_pack_id: "presentation-story@1" as const,
    };
    render(<TimelineEditor initialTimeline={presentationTimeline} projectId="project-1" />);

    fireEvent.click(screen.getByRole("button", { name: "Cut" }));

    expect(screen.getByRole("note")).toHaveTextContent(
      "The authored Presentation Demo sequence is fixed at 2:00, so scene timing is read-only.",
    );
    expect(screen.queryByRole("button", { name: "Split at playhead" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete scene" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Duplicate scene" })).not.toBeInTheDocument();
    expect(deleteSceneFromTimeline(presentationTimeline, "Opening")).toBe(presentationTimeline);
    expect(duplicateSceneInTimeline(presentationTimeline, "Opening")).toBe(presentationTimeline);
    expect(splitSceneInTimeline(presentationTimeline, "Opening", 4_000)).toBe(presentationTimeline);
  });

  it("keeps source playback continuous when a Product Demo scene is split", () => {
    const sourceOffsetTimeline = {
      ...timeline,
      scene_clips: timeline.scene_clips.map((scene, index) =>
        index === 0 ? { ...scene, source_start_ms: 2_500 } : scene,
      ),
    };

    const updated = splitSceneInTimeline(sourceOffsetTimeline, "Opening", 3_000);

    expect(updated.duration_ms).toBe(sourceOffsetTimeline.duration_ms);
    expect(updated.scene_clips[0]).toMatchObject({
      scene_id: "Opening",
      start_ms: 0,
      end_ms: 3_000,
      source_start_ms: 2_500,
    });
    expect(updated.scene_clips[1]).toMatchObject({
      scene_id: "Opening-split",
      start_ms: 3_000,
      end_ms: 8_000,
      source_start_ms: 5_500,
    });
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

  it("creates a 1440p export and exposes its download", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ...videoExport,
        quality: "1440p",
        width: 2560,
        height: 1440,
      }),
    }));
    render(<TimelineEditor initialTimeline={timeline} projectId="project-1" />);

    fireEvent.click(screen.getByRole("button", { name: "Export 1440p" }));

    const download = await screen.findByRole("link", { name: "Download MP4" });
    expect(download).toHaveAttribute(
      "href",
      "/api/projects/project-1/exports/export-1/download?token=fixture-token",
    );
    expect(screen.getAllByRole("status").at(-1)).toHaveTextContent(
      "1440p export ready to download",
    );
  });

  it("opens the packaged Northstar timeline and video when the judge project has no API timeline", async () => {
    const selectedProject = { ...project, id: "judge-demo-session-1" };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).endsWith("/timeline")) {
        return { ok: false, json: async () => ({ detail: "Timeline not found" }) };
      }
      return { ok: true, json: async () => selectedProject };
    }));

    render(<TimelineEditor projectId="judge-demo-session-1" />);

    const preview = await screen.findByLabelText("Preview video");
    expect(preview).toHaveAttribute("src", "/judge-demo.mp4");
    expect(screen.queryByRole("heading", { name: "Timeline not ready" })).not.toBeInTheDocument();
    expect(screen.getAllByText("Northstar product tour").length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "Download MP4" })).toHaveAttribute("href", "/judge-demo.mp4");
  });
});
