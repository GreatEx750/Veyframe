import { z } from "zod";

import { viewportSchema } from "./schemas";

export const calloutTypeSchema = z.enum([
  "label_connector", "spotlight", "numbered_step", "feature_card", "status_badge",
  "metric_card", "before_after",
]);
export const calloutPlacementSchema = z.enum([
  "top_left", "top_right", "bottom_left", "bottom_right",
]);
export const normalizedRectSchema = z.object({
  x: z.number().min(0).max(1), y: z.number().min(0).max(1),
  width: z.number().positive().max(1), height: z.number().positive().max(1),
}).strict().refine((value) => value.x + value.width <= 1 && value.y + value.height <= 1);
export const targetObservationSchema = z.object({
  id: z.string().min(1), scene_id: z.string().min(1),
  locator_fingerprint: z.string().regex(/^[a-f0-9]{64}$/), timestamp_ms: z.number().int().nonnegative(),
  rect: normalizedRectSchema, viewport: viewportSchema,
}).strict();
const calloutFields = {
  target_id: z.string().min(1), callout_type: calloutTypeSchema, placement: calloutPlacementSchema,
  start_ms: z.number().int().nonnegative(), end_ms: z.number().int().positive(),
  text: z.string().min(1).max(72),
};
const calloutBase = z.object(calloutFields).strict();
const refineCallout = (value: z.infer<typeof calloutBase>, context: z.RefinementCtx) => {
  const duration = value.end_ms - value.start_ms;
  if (duration < 600 || duration > 8_000) context.addIssue({ code: "custom", message: "Invalid callout duration" });
};
export const animatedCalloutDraftSchema = calloutBase.superRefine(refineCallout);
export const animatedCalloutSchema = z.object({ id: z.string().min(1), ...calloutFields })
  .strict().superRefine(refineCallout);
export const captionEmphasisSchema = z.object({
  statement_id: z.string().min(1), word: z.string().min(1).max(32),
  start_ms: z.number().int().nonnegative(), end_ms: z.number().int().positive(),
  style: z.enum(["weight", "underline", "accent"]),
}).strict().refine((value) => value.end_ms > value.start_ms && value.end_ms - value.start_ms <= 2_000);
export const attentionDraftSchema = z.object({
  summary: z.string().min(1).max(240), callouts: z.array(animatedCalloutDraftSchema).max(40),
  caption_emphasis: z.array(captionEmphasisSchema).max(80),
}).strict();
export const attentionPlanSchema = z.object({
  id: z.string().min(1), project_id: z.string().min(1), job_id: z.string().min(1),
  parent_run_id: z.string().min(1), duration_ms: z.number().int().positive().max(600_000),
  manual_override_of: z.string().min(1).nullable().default(null),
  targets: z.array(targetObservationSchema).max(120),
  narration_statement_ids: z.array(z.string().min(1)).max(120),
  summary: z.string().min(1).max(240), callouts: z.array(animatedCalloutSchema).max(40),
  caption_emphasis: z.array(captionEmphasisSchema).max(80),
  created_at: z.string().datetime({ offset: true }),
}).strict().superRefine((value, context) => {
  const targets = new Set(value.targets.map((target) => target.id));
  const statements = new Set(value.narration_statement_ids);
  if (value.callouts.some((callout) => !targets.has(callout.target_id) || callout.end_ms > value.duration_ms)) {
    context.addIssue({ code: "custom", message: "Callout target or timing is invalid" });
  }
  if (value.caption_emphasis.some((item) => !statements.has(item.statement_id))) {
    context.addIssue({ code: "custom", message: "Caption emphasis is not approved" });
  }
  const ordered = [...value.callouts].sort((a, b) => a.start_ms - b.start_ms);
  if (ordered.some((item, index) => index > 0 && item.start_ms < ordered[index - 1].end_ms)) {
    context.addIssue({ code: "custom", message: "Primary callouts cannot overlap" });
  }
});

export type AttentionPlan = z.infer<typeof attentionPlanSchema>;
