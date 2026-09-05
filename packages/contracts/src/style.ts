import { z } from "zod";

const nonEmptyString = z.string().min(1);
export const visualVariantIdSchema = z.enum([
  "editorial_story",
  "product_spotlight",
  "technical_proof",
]);
export const visualVariantVersionSchema = z.literal("style-v1");

export const variantSceneDefaultsSchema = z.object({
  variant_id: visualVariantIdSchema,
  product_scale: z.enum(["composed", "large", "evidence_focused"]),
  callout_density: z.enum(["low", "medium"]),
  motion_pace: z.enum(["calm", "deliberate", "precise"]),
}).strict();

export const variantOverrideSchema = z.object({
  scene_id: nonEmptyString,
  variant_id: visualVariantIdSchema,
}).strict();

export const styleDirectionDecisionSchema = z.object({
  recommended_variant: visualVariantIdSchema,
  selected_variant: visualVariantIdSchema,
  outcome: z.enum(["recommended", "accepted", "overridden"]),
  decided_at: z.string().datetime({ offset: true }),
}).strict();

export const styleDirectionPlanSchema = z.object({
  id: nonEmptyString,
  project_id: nonEmptyString,
  job_id: nonEmptyString,
  parent_run_id: nonEmptyString,
  version: visualVariantVersionSchema.default("style-v1"),
  audience: nonEmptyString,
  purpose: nonEmptyString,
  scene_ids: z.array(nonEmptyString).min(1).max(80),
  allowed_evidence_refs: z.array(nonEmptyString).min(1).max(120),
  recommendation_evidence_refs: z.array(nonEmptyString).min(1).max(40),
  rationale: z.string().min(1).max(240),
  decision: styleDirectionDecisionSchema,
  defaults: z.array(variantSceneDefaultsSchema).length(3),
  overrides: z.array(variantOverrideSchema).max(80).default([]),
  manual_override_of: nonEmptyString.nullable().default(null),
  created_at: z.string().datetime({ offset: true }),
}).strict().superRefine((plan, context) => {
  const expected = ["editorial_story", "product_spotlight", "technical_proof"];
  if (plan.defaults.map((item) => item.variant_id).join("|") !== expected.join("|")) {
    context.addIssue({ code: "custom", message: "Style defaults must contain the three fixed variants", path: ["defaults"] });
  }
  const scenes = new Set(plan.scene_ids);
  if (plan.overrides.some((item) => !scenes.has(item.scene_id)) || new Set(plan.overrides.map((item) => item.scene_id)).size !== plan.overrides.length) {
    context.addIssue({ code: "custom", message: "Style overrides must be unique and reference planned scenes", path: ["overrides"] });
  }
  const allowed = new Set(plan.allowed_evidence_refs);
  if (plan.recommendation_evidence_refs.some((item) => !allowed.has(item))) {
    context.addIssue({ code: "custom", message: "Style recommendation must cite approved project inputs", path: ["recommendation_evidence_refs"] });
  }
});

export type VisualVariantId = z.infer<typeof visualVariantIdSchema>;
export type StyleDirectionPlan = z.infer<typeof styleDirectionPlanSchema>;
