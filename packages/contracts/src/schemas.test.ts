import { describe, expect, it } from "vitest";

import {
  captureActionSchema,
  demoGenerationResultSchema,
  editOperationSchema,
  interactionEventSchema,
  projectSchema,
  sceneSchema,
  timelineSchema,
  videoPresentationSchema,
  zoomClipSchema,
} from "./schemas";

const validAction = {
  type: "click",
  locator_strategy: "role",
  locator: "Create a demo",
  value: null,
  description: "Open the demo creator",
} as const;

describe("shared client contracts", () => {
  it("keeps captured interaction coordinates inside their viewport", () => {
    const edgeEvent = {
      timestamp_ms: 0,
      event_type: "click",
      x: 1280,
      y: 720,
      viewport: { width: 1280, height: 720 },
    } as const;

    expect(interactionEventSchema.safeParse(edgeEvent).success).toBe(true);
    expect(interactionEventSchema.safeParse({ ...edgeEvent, x: 1281 }).success).toBe(false);
    expect(interactionEventSchema.safeParse({ ...edgeEvent, y: 721 }).success).toBe(false);
  });

  it("accepts only completed one-click generation results", () => {
    const project = {
      id: "project-1",
      name: "Launch demo",
      website_url: "https://example.com",
      product_summary: "A concise product summary",
      audience: "Product teams",
      tone: "Professional",
      requested_duration_seconds: 20,
      cta: "Start a trial",
      brand_kit_id: null,
      status: "published",
      job_status: "succeeded",
      owner_user_id: "system",
      created_at: "2026-09-01T12:00:00Z",
      updated_at: "2026-09-01T12:00:00Z",
    } as const;
    const videoExport = {
      id: "export-1",
      project_id: "project-1",
      status: "succeeded",
      quality: "1440p",
      filename: "demo.mp4",
      width: 2560,
      height: 1440,
      duration_ms: 20_000,
      size_bytes: 1024,
      thumbnail_path: null,
      download_url: "/projects/project-1/exports/export-1/download?token=12345678901234567890",
      retryable: false,
      error: null,
      created_at: "2026-09-01T12:00:00Z",
    } as const;

    expect(demoGenerationResultSchema.safeParse({
      project,
      export: videoExport,
      timeline_version: 1,
      warnings: [],
    }).success).toBe(true);
    expect(demoGenerationResultSchema.safeParse({
      project: { ...project, status: "rendering" },
      export: videoExport,
      timeline_version: 1,
      warnings: [],
    }).success).toBe(false);
  });

  it("accepts a complete scene fixture", () => {
    const result = sceneSchema.safeParse({
      id: "scene-1",
      storyboard_id: "storyboard-1",
      order: 0,
      title: "Open the studio",
      objective: "Introduce the primary workflow",
      narration: "Start by opening the demo studio.",
      source_ids: ["source-1"],
      capture_plan: {
        start_url: "https://example.com",
        actions: [validAction],
        success_assertions: [
          {
            ...validAction,
            type: "assert_visible",
            description: "Confirm the studio is visible",
          },
        ],
        timeout_seconds: 30,
      },
      expected_evidence: ["Studio heading"],
      duration_seconds: 8,
    });

    expect(result.success).toBe(true);
  });

  it("rejects unknown capture and edit operation types", () => {
    expect(captureActionSchema.safeParse({ ...validAction, type: "evaluate" }).success).toBe(false);
    expect(
      editOperationSchema.safeParse({
        operation_type: "run_script",
        target_id: "scene-1",
        arguments: {},
        rationale: "Not allowed",
      }).success,
    ).toBe(false);
  });

  it("rejects non-positive scene duration and invalid zoom ranges", () => {
    const zoom = {
      id: "zoom-1",
      start_ms: 1000,
      end_ms: 2000,
      scale: 1.5,
      target_rect: { x: 10, y: 20, width: 200, height: 100 },
      easing: "ease_in_out",
      source: "auto",
    } as const;

    expect(zoomClipSchema.safeParse({ ...zoom, scale: 0.5 }).success).toBe(false);
    expect(zoomClipSchema.safeParse({ ...zoom, end_ms: 1000 }).success).toBe(false);
    expect(zoomClipSchema.safeParse({ ...zoom, focus_x: 110, focus_y: 70, source_viewport: { width: 1280, height: 720 } }).success).toBe(true);
    expect(zoomClipSchema.safeParse({ ...zoom, focus_x: 110 }).success).toBe(false);
    expect(
      timelineSchema.safeParse({
        project_id: "project-1",
        duration_ms: 1500,
        scene_clips: [],
        caption_clips: [],
        zoom_clips: [zoom],
        audio_clips: [],
      }).success,
    ).toBe(false);
    expect(timelineSchema.safeParse({
      project_id: "project-1",
      duration_ms: 1_500,
      cursor_events: [{
        timestamp_ms: 1_500,
        event_type: "click",
        x: 640,
        y: 360,
        viewport: { width: 1280, height: 720 },
      }],
    }).success).toBe(false);
  });

  it("validates presentation templates and gives timelines an edge-to-edge default", () => {
    expect(videoPresentationSchema.parse({})).toEqual({ template: "edge_to_edge", zoom_enabled: true });
    expect(videoPresentationSchema.safeParse({ template: "spotlight" }).success).toBe(true);
    expect(videoPresentationSchema.safeParse({ template: "generated_filter" }).success).toBe(false);
    expect(timelineSchema.parse({ project_id: "project-1", duration_ms: 1_000 }).presentation)
      .toEqual({ template: "edge_to_edge", zoom_enabled: true });
  });

  it("defaults legacy projects and timelines to Product Demo with smooth zoom", () => {
    const parsed = projectSchema.parse({
      id: "project-legacy",
      name: "Legacy demo",
      website_url: "https://example.com",
      product_summary: "A complete product workflow for a focused team.",
      audience: "Product leaders",
      tone: "Professional",
      requested_duration_seconds: 30,
      cta: "Try it",
      created_at: "2026-09-04T12:00:00Z",
      updated_at: "2026-09-04T12:00:00Z",
    });

    expect(parsed.demo_mode).toBe("product_demo");
    expect(parsed.zoom_enabled).toBe(true);
    expect(timelineSchema.parse({ project_id: parsed.id, duration_ms: 30_000 })).toMatchObject({
      demo_mode: "product_demo",
      presentation_pack_id: null,
      presentation: { template: "edge_to_edge", zoom_enabled: true },
    });
  });

  it("requires the shipped pack for Presentation Demo timelines", () => {
    const presentationMedia = {
      scene_clips: [{
        id: "presentation-clip",
        scene_id: "presentation-capture",
        source_uri: "captures/presentation.webm",
        start_ms: 0,
        end_ms: 120_000,
      }],
      cursor_events: [{
        timestamp_ms: 8_000,
        event_type: "click",
        x: 640,
        y: 360,
        viewport: { width: 1280, height: 720 },
      }],
    } as const;
    expect(timelineSchema.safeParse({
      project_id: "project-presentation",
      duration_ms: 120_000,
      demo_mode: "presentation_demo",
    }).success).toBe(false);
    expect(timelineSchema.parse({
      project_id: "project-presentation",
      duration_ms: 120_000,
      demo_mode: "presentation_demo",
      presentation_pack_id: "presentation-story@1",
      presentation: { template: "edge_to_edge", zoom_enabled: false },
      ...presentationMedia,
    }).presentation.zoom_enabled).toBe(false);
    expect(timelineSchema.safeParse({
      project_id: "project-presentation",
      duration_ms: 30_000,
      demo_mode: "presentation_demo",
      presentation_pack_id: "presentation-story@1",
    }).success).toBe(false);
    expect(timelineSchema.safeParse({
      project_id: "project-presentation",
      duration_ms: 120_000,
      demo_mode: "presentation_demo",
      presentation_pack_id: "presentation-story@1",
      cursor_events: presentationMedia.cursor_events,
    }).success).toBe(false);
    expect(timelineSchema.safeParse({
      project_id: "project-presentation",
      duration_ms: 120_000,
      demo_mode: "presentation_demo",
      presentation_pack_id: "presentation-story@1",
      scene_clips: presentationMedia.scene_clips,
    }).success).toBe(false);
    expect(projectSchema.safeParse({
      id: "project-invalid",
      name: "Invalid",
      website_url: "https://example.com",
      product_summary: "A complete product workflow for a focused team.",
      audience: "Product leaders",
      tone: "Professional",
      requested_duration_seconds: 30,
      cta: "Try it",
      demo_mode: "runtime_slides",
      created_at: "2026-09-04T12:00:00Z",
      updated_at: "2026-09-04T12:00:00Z",
    }).success).toBe(false);
  });
});
