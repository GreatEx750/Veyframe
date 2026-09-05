import { describe, expect, it } from "vitest";
import { styleDirectionPlanSchema } from "./style";

const plan = {
  id: "style-1", project_id: "project-1", job_id: "job-1", parent_run_id: "motion-1",
  version: "style-v1", audience: "Product leaders", purpose: "Show the product",
  scene_ids: ["scene-1"], allowed_evidence_refs: ["storyboard:1"],
  recommendation_evidence_refs: ["storyboard:1"], rationale: "Use a composed editorial pace.",
  decision: { recommended_variant: "editorial_story", selected_variant: "editorial_story", outcome: "recommended", decided_at: "2026-09-04T12:00:00Z" },
  defaults: [
    { variant_id: "editorial_story", product_scale: "composed", callout_density: "medium", motion_pace: "deliberate" },
    { variant_id: "product_spotlight", product_scale: "large", callout_density: "low", motion_pace: "calm" },
    { variant_id: "technical_proof", product_scale: "evidence_focused", callout_density: "medium", motion_pace: "precise" },
  ], overrides: [], manual_override_of: null, created_at: "2026-09-04T12:00:00Z",
};

describe("style direction contracts", () => {
  it("accepts the fixed versioned catalog", () => expect(styleDirectionPlanSchema.parse(plan).defaults).toHaveLength(3));
  it("rejects unknown evidence", () => expect(() => styleDirectionPlanSchema.parse({ ...plan, recommendation_evidence_refs: ["unknown"] })).toThrow());
  it("rejects foreign scene overrides", () => expect(() => styleDirectionPlanSchema.parse({ ...plan, overrides: [{ scene_id: "foreign", variant_id: "technical_proof" }] })).toThrow());
});
