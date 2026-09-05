import { describe, expect, it } from "vitest";

import { attentionPlanSchema, normalizedRectSchema } from "./attention";

const target = {
  id: "target-1", scene_id: "scene-1", locator_fingerprint: "a".repeat(64),
  timestamp_ms: 1_000, rect: { x: 0.2, y: 0.3, width: 0.1, height: 0.1 },
  viewport: { width: 1280, height: 720, scroll_x: 0, scroll_y: 0, device_scale_factor: 1 },
};
const plan = {
  id: "attention-plan-1", project_id: "project-1", job_id: "job-1",
  parent_run_id: "motion-run-1", duration_ms: 10_000, targets: [target],
  narration_statement_ids: ["statement-1"], summary: "Guide attention.",
  callouts: [{
    id: "callout-1", target_id: "target-1", callout_type: "label_connector",
    placement: "top_left", start_ms: 1_000, end_ms: 2_000, text: "Create project",
  }],
  caption_emphasis: [], created_at: "2026-09-04T12:00:00.000Z",
};

describe("attention contracts", () => {
  it("accepts an observed target and bounded callout", () => {
    expect(attentionPlanSchema.parse(plan).callouts).toHaveLength(1);
  });

  it("rejects hallucinated targets and off-frame geometry", () => {
    expect(attentionPlanSchema.safeParse({
      ...plan, callouts: [{ ...plan.callouts[0], target_id: "foreign" }],
    }).success).toBe(false);
    expect(normalizedRectSchema.safeParse({ x: 0.95, y: 0, width: 0.1, height: 0.1 }).success)
      .toBe(false);
  });
});
