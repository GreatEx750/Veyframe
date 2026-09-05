import { describe, expect, it } from "vitest";

import {
  editorialTemplateCatalogSchema,
  editorialTemplatePlanSchema,
  productPresenceReportSchema,
} from "./editorial";

const scene = {
  id: "editorial-scene-1",
  scene_id: "scene-1",
  section: "hook",
  template_id: "hook",
  product_clip_ref: "scene:scene-1",
  product_treatment: "moving_background",
  start_ms: 0,
  end_ms: 10_000,
  eyebrow: null,
  title: "Show the product",
  body: null,
  crop: { x: 0, y: 0, width: 1, height: 1 },
};

const plan = {
  id: "editorial-plan-1",
  project_id: "project-1",
  job_id: "job-1",
  run_id: "run-1",
  motion_plan_id: "motion-plan-1",
  catalog_version: "editorial-v1",
  design_version: "motion-v1",
  duration_ms: 10_000,
  scene_ids: ["scene-1"],
  product_clip_refs: ["scene:scene-1"],
  summary: "Product-present hook.",
  scenes: [scene],
  created_at: "2026-09-04T12:00:00.000Z",
};

describe("editorial contracts", () => {
  it("keeps the six-template catalog fixed", () => {
    expect(editorialTemplateCatalogSchema.parse({}).template_ids).toHaveLength(6);
    expect(editorialTemplateCatalogSchema.safeParse({ template_ids: ["hook"] }).success).toBe(false);
  });

  it("requires complete owned product coverage", () => {
    expect(editorialTemplatePlanSchema.parse(plan).scenes[0].template_id).toBe("hook");
    expect(editorialTemplatePlanSchema.safeParse({
      ...plan,
      scenes: [{ ...scene, product_clip_ref: "scene:foreign" }],
    }).success).toBe(false);
  });

  it("rejects product presence below ninety percent", () => {
    expect(productPresenceReportSchema.safeParse({
      duration_ms: 10_000,
      visible_product_ms: 8_900,
      percentage: 89,
      violating_intervals: [{ start_ms: 8_900, end_ms: 10_000 }],
    }).success).toBe(false);
  });
});
