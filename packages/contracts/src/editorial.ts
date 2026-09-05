import { z } from "zod";

export const editorialTemplateIdSchema = z.enum([
  "hook", "framed_product", "feature_callout", "split_explanation", "proof_safety", "closing",
]);
export const productTreatmentSchema = z.enum([
  "full_focus", "framed_product", "split_explanation", "moving_background",
]);
export const narrativeSectionSchema = z.enum([
  "hook", "problem", "promise", "product_walkthrough", "trust_technology",
  "editing_control", "finished_result", "closing",
]);
const catalog = [
  "hook", "framed_product", "feature_callout", "split_explanation", "proof_safety", "closing",
] as const;

export const editorialTemplateCatalogSchema = z.object({
  version: z.literal("editorial-v1").default("editorial-v1"),
  template_ids: z.array(editorialTemplateIdSchema).default([...catalog]),
}).strict().superRefine((value, context) => {
  if (value.template_ids.join("|") !== catalog.join("|")) {
    context.addIssue({ code: "custom", message: "Editorial template catalog is fixed" });
  }
});

export const renderSafeCropSchema = z.object({
  x: z.number().min(0).max(1), y: z.number().min(0).max(1),
  width: z.number().positive().max(1), height: z.number().positive().max(1),
}).strict().superRefine((value, context) => {
  if (value.x + value.width > 1 || value.y + value.height > 1) {
    context.addIssue({ code: "custom", message: "Editorial crop must fit the product frame" });
  }
});

const editorialSceneFields = {
  scene_id: z.string().min(1), section: narrativeSectionSchema,
  template_id: editorialTemplateIdSchema,
  product_clip_ref: z.string().regex(/^scene:[A-Za-z0-9._:-]+$/),
  product_treatment: productTreatmentSchema,
  start_ms: z.number().int().nonnegative(), end_ms: z.number().int().positive(),
  eyebrow: z.string().max(32).nullable().default(null), title: z.string().min(1).max(80),
  body: z.string().max(180).nullable().default(null), crop: renderSafeCropSchema,
};
const sceneBase = z.object(editorialSceneFields).strict();
const refineScene = (value: z.infer<typeof sceneBase>, context: z.RefinementCtx) => {
  if (value.end_ms - value.start_ms < 1_000) {
    context.addIssue({ code: "custom", message: "Editorial scenes require a one-second hold" });
  }
};
export const editorialSceneDraftSchema = sceneBase.superRefine(refineScene);
export const editorialSceneSchema = z.object({ id: z.string().min(1), ...editorialSceneFields })
  .strict().superRefine(refineScene);
export const editorialTemplateDraftSchema = z.object({
  summary: z.string().min(1).max(240), scenes: z.array(editorialSceneDraftSchema).min(1).max(80),
}).strict();

export const presenceViolationSchema = z.object({
  start_ms: z.number().int().nonnegative(), end_ms: z.number().int().positive(),
}).strict().refine((value) => value.end_ms > value.start_ms);
export const productPresenceReportSchema = z.object({
  duration_ms: z.number().int().positive(), visible_product_ms: z.number().int().nonnegative(),
  percentage: z.number().min(90).max(100),
  violating_intervals: z.array(presenceViolationSchema).default([]),
}).strict().superRefine((value, context) => {
  const expected = Math.round((value.visible_product_ms / value.duration_ms) * 100_000) / 1_000;
  if (Math.abs(expected - value.percentage) > 0.01) {
    context.addIssue({ code: "custom", message: "Product presence percentage must match duration" });
  }
});

export const editorialTemplatePlanSchema = z.object({
  id: z.string().min(1), project_id: z.string().min(1), job_id: z.string().min(1),
  run_id: z.string().min(1), motion_plan_id: z.string().min(1),
  catalog_version: z.literal("editorial-v1"), design_version: z.literal("motion-v1"),
  duration_ms: z.number().int().positive().max(600_000),
  scene_ids: z.array(z.string().min(1)).min(1).max(80),
  product_clip_refs: z.array(z.string().regex(/^scene:[A-Za-z0-9._:-]+$/)).min(1).max(80),
  summary: z.string().min(1).max(240), scenes: z.array(editorialSceneSchema).min(1).max(80),
  created_at: z.string().datetime({ offset: true }),
}).strict().superRefine((value, context) => {
  const fail = (message: string) => context.addIssue({ code: "custom", message });
  if (value.scenes.map((scene) => scene.scene_id).join("|") !== value.scene_ids.join("|")) {
    fail("Editorial scenes must cover requested scenes in order");
  }
  const clips = new Set(value.product_clip_refs);
  if (value.scenes.some((scene) => !clips.has(scene.product_clip_ref))) fail("Foreign product clip");
  let expectedStart = 0;
  for (const scene of value.scenes) {
    if (scene.start_ms !== expectedStart) fail("Editorial scenes must be contiguous");
    expectedStart = scene.end_ms;
  }
  if (expectedStart !== value.duration_ms) fail("Editorial scenes must cover the video");
});

export type EditorialTemplateId = z.infer<typeof editorialTemplateIdSchema>;
export type EditorialTemplatePlan = z.infer<typeof editorialTemplatePlanSchema>;
export type ProductPresenceReport = z.infer<typeof productPresenceReportSchema>;
