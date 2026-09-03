import {
  timelineSchema,
  videoExportSchema,
  type Timeline,
  type VideoExport,
} from "@demodirector/contracts";

export const JUDGE_DEMO_VIDEO_URL = "/judge-demo.mp4";

export function isJudgeDemoProject(projectId: string) {
  return projectId.startsWith("judge-demo-");
}

export function judgeDemoTimeline(projectId: string): Timeline {
  return timelineSchema.parse({
    project_id: projectId,
    duration_ms: 20_000,
    scene_clips: [
      {
        id: "northstar-continuous-recording",
        scene_id: "Northstar product tour",
        start_ms: 0,
        end_ms: 20_000,
        source_uri: JUDGE_DEMO_VIDEO_URL,
      },
    ],
    caption_clips: [],
    zoom_clips: [],
    cursor_events: [],
    audio_clips: [],
    cta_text: "Explore the complete DemoDirector workflow",
    presentation: { template: "edge_to_edge" },
  });
}

export function judgeDemoExport(projectId: string): VideoExport {
  return videoExportSchema.parse({
    id: `northstar-fixture-${projectId}`,
    project_id: projectId,
    status: "succeeded",
    quality: "720p",
    filename: "judge-demo.mp4",
    width: 1280,
    height: 720,
    duration_ms: 20_000,
    size_bytes: 250_526,
    download_url: JUDGE_DEMO_VIDEO_URL,
    retryable: false,
    created_at: "2026-09-01T00:00:00Z",
  });
}
