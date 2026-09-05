import { describe, expect, it } from "vitest";

import { adkMotionRunSchema, motionDirectionPlanSchema, motionDirectionRequestSchema } from "./motion";

const request = {
  project_id: "project-1", job_id: "job-1", storyboard_id: "storyboard-1", storyboard_version: 2,
  duration_ms: 20000, evidence_fingerprint: "a".repeat(64), source_ids: ["source-1"],
  scene_ids: ["scene-1"], product_clip_refs: ["scene:scene-1"], created_at: "2026-09-04T12:00:00.000Z",
};
const cue = {
  id: "cue-1", scene_id: "scene-1", primitive: "fade_slide", layer: "transition",
  start_ms: 0, end_ms: 600, easing: "standard", text: "Open with the product",
  product_clip_ref: "scene:scene-1",
};
const plan = {
  id: "motion-plan-1", project_id: "project-1", job_id: "job-1", run_id: "motion-run-1",
  request_fingerprint: "b".repeat(64), design_tokens: {
    version: "motion-v1", font_family: "Inter", title_size: 64, body_size: 32,
    fast_ms: 200, normal_ms: 600, deliberate_ms: 1200,
    standard_easing: "cubic-bezier(0.22, 1, 0.36, 1)", emphasized_easing: "cubic-bezier(0.16, 1, 0.3, 1)",
    background: "#111214", surface: "#1B1D20", text: "#F5F6F7", accent: "#86E1A8",
    layer_order: ["background", "product", "mask", "cursor", "callout", "captions", "transition"],
  },
  duration_ms: 20000, scene_ids: ["scene-1"], product_clip_refs: ["scene:scene-1"],
  summary: "Keep the product visible.", cues: [cue], created_at: "2026-09-04T12:00:00.000Z",
};

describe("motion direction contracts", () => {
  it("accepts bounded request and plan data", () => {
    expect(motionDirectionRequestSchema.safeParse(request).success).toBe(true);
    expect(motionDirectionPlanSchema.safeParse(plan).success).toBe(true);
  });

  it("rejects foreign references, overlaps, executable text, and unknown properties", () => {
    expect(motionDirectionPlanSchema.safeParse({ ...plan, cues: [{ ...cue, scene_id: "foreign" }] }).success).toBe(false);
    expect(motionDirectionPlanSchema.safeParse({ ...plan, cues: [cue, { ...cue, id: "cue-2", start_ms: 300, end_ms: 900 }] }).success).toBe(false);
    expect(motionDirectionPlanSchema.safeParse({ ...plan, cues: [{ ...cue, text: "javascript:alert(1)" }] }).success).toBe(false);
    expect(motionDirectionPlanSchema.safeParse({ ...plan, arbitrary_code: "run()" }).success).toBe(false);
  });

  it("requires a successful ADK run to have a validated output", () => {
    const run = {
      id: "motion-run-1", project_id: "project-1", job_id: "job-1", session_id: "session-1",
      agent_name: "demodirector_motion_director", model: "gemini-2.5-flash", status: "succeeded",
      started_at: "2026-09-04T12:00:00.000Z", completed_at: "2026-09-04T12:00:00.750Z",
      elapsed_ms: 750, retry_count: 0, workflow_runs: 1,
      input_artifact_ids: ["storyboard:storyboard-1:2", `evidence:${"a".repeat(64)}`],
      output_plan_id: "motion-plan-1", validation_status: "passed", message: "Validated motion direction saved.",
    };
    expect(adkMotionRunSchema.safeParse(run).success).toBe(true);
    expect(adkMotionRunSchema.safeParse({ ...run, workflow_runs: 0 }).success).toBe(false);
    expect(adkMotionRunSchema.safeParse({ ...run, message: "api_key=private" }).success).toBe(false);
  });
});
