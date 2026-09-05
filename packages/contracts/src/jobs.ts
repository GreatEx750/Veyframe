import { z } from "zod";
const stage = z.enum(["inspection", "research", "understanding", "storyboard", "motion", "capture", "attention", "style", "narration", "render", "done"]);
export const generationJobSchema = z.object({
  id: z.string().min(1), project_id: z.string().min(1),
  status: z.enum(["queued", "running", "awaiting_approval", "awaiting_retry", "failed", "succeeded"]), stage,
  completed_stages: z.array(stage), attempts: z.number().int().min(0).max(3), version: z.number().int().positive(),
  created_at: z.string().datetime({ offset: true }), updated_at: z.string().datetime({ offset: true }),
  lease_until: z.string().datetime({ offset: true }).nullable(), message: z.string().min(1),
  export_id: z.string().nullable(), timeline_version: z.number().int().positive().nullable(),
}).strict();
export type GenerationJob = z.infer<typeof generationJobSchema>;

export const traceStageKindSchema = z.enum(["inspection", "research", "adk_coordination", "understanding", "storyboard", "capture", "narration", "auto_camera", "captions", "render"]);
export const stageContributionSchema = z.object({
  key: z.enum(["pages_inspected", "controls_observed", "sources_saved", "workflow_runs", "validated_motion_plans", "motion_cues", "templates_assigned", "product_presence", "attention_targets", "callouts_proposed", "callouts_accepted", "style_recommendations", "style_overrides", "longform_plans", "director_steps", "parallel_sources_linked", "chapters_planned", "features_understood", "claims_attributed", "scenes_planned", "actions_planned", "actions_executed", "interactions_recorded", "recordings_created", "narration_segments", "zooms_created", "captions_created", "exports_created", "output_width", "output_height", "output_duration", "adk_plan_consumed"]),
  label: z.string().min(1), value: z.number().int().nonnegative(), unit: z.string().min(1),
}).strict();
export const generationTraceStageSchema = z.object({
  id: z.string().min(1), project_id: z.string().min(1), kind: traceStageKindSchema,
  sequence: z.number().int().nonnegative(), attempt: z.number().int().min(0).max(3), retry_count: z.number().int().min(0).max(2),
  status: z.enum(["pending", "running", "succeeded", "failed", "not_used"]),
  label: z.string().min(1), service: z.string().min(1),
  started_at: z.string().datetime({ offset: true }).nullable(), completed_at: z.string().datetime({ offset: true }).nullable(),
  elapsed_ms: z.number().int().nonnegative().nullable(), message: z.string().min(1).max(300),
  contributions: z.array(stageContributionSchema), output_href: z.string().regex(/^(?:\/|#)[^\s]*$/).nullable(),
}).strict().superRefine((stage, ctx) => {
  const fail = (message: string) => ctx.addIssue({ code: "custom", message });
  if (["running", "succeeded", "failed"].includes(stage.status) && stage.attempt < 1) fail("Executed stages require an attempt");
  if (["pending", "not_used"].includes(stage.status) && stage.attempt !== 0) fail("Unexecuted stages cannot have an attempt");
  if (stage.status === "running" && (!stage.started_at || stage.completed_at || stage.elapsed_ms !== null)) fail("Running timing is invalid");
  if (["succeeded", "failed"].includes(stage.status)) {
    if (!stage.started_at || !stage.completed_at || stage.elapsed_ms === null) fail("Completed timing is required");
    else if (Math.abs(new Date(stage.completed_at).getTime() - new Date(stage.started_at).getTime() - stage.elapsed_ms) > 5) fail("Elapsed time must match timestamps");
  }
  if (/api_key=|bearer |password=|secret=/i.test(stage.message)) fail("Trace message contains credentials");
});
export const generationTraceSchema = z.object({
  id: z.string().min(1), project_id: z.string().min(1), job_id: z.string().min(1),
  status: z.enum(["running", "awaiting_approval", "awaiting_retry", "failed", "succeeded"]),
  created_at: z.string().datetime({ offset: true }), updated_at: z.string().datetime({ offset: true }),
  stages: z.array(generationTraceStageSchema),
}).strict().superRefine((trace, ctx) => {
  const sequences = trace.stages.map((stage) => stage.sequence);
  if (trace.stages.some((stage) => stage.project_id !== trace.project_id) || sequences.some((value, index) => index > 0 && value < sequences[index - 1]) || new Set(trace.stages.map((stage) => stage.id)).size !== trace.stages.length) {
    ctx.addIssue({ code: "custom", message: "Trace stages must be project-owned, unique, and chronological" });
  }
});
export type GenerationTrace = z.infer<typeof generationTraceSchema>;
