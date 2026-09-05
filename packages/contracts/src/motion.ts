import { z } from "zod";
import { editorialTemplateDraftSchema, editorialTemplatePlanSchema } from "./editorial";

export const motionPrimitiveSchema = z.enum(["fade_slide", "scale_settle", "stagger_text", "highlight_reveal", "browser_frame_move", "background_dim"]);
export const motionLayerSchema = z.enum(["background", "product", "mask", "cursor", "callout", "captions", "transition"]);
export const motionEasingSchema = z.enum(["linear", "standard", "emphasized"]);
export const motionDesignVersionSchema = z.literal("motion-v1");
const layerOrder = ["background", "product", "mask", "cursor", "callout", "captions", "transition"] as const;
const unsafeText = /<\s*script|javascript\s*:|data\s*:\s*text\/html|\$\(|`[^`]*`|(?:^|\s)(?:rm|del)\s+-[rf]/i;

export const motionTokenSetSchema = z.object({
  version: z.literal("motion-v1").default("motion-v1"), font_family: z.literal("Inter").default("Inter"),
  title_size: z.number().int().min(32).max(96).default(64), body_size: z.number().int().min(18).max(48).default(32),
  fast_ms: z.number().int().min(100).max(400).default(200), normal_ms: z.number().int().min(300).max(900).default(600), deliberate_ms: z.number().int().min(700).max(1800).default(1200),
  standard_easing: z.literal("cubic-bezier(0.22, 1, 0.36, 1)").default("cubic-bezier(0.22, 1, 0.36, 1)"),
  emphasized_easing: z.literal("cubic-bezier(0.16, 1, 0.3, 1)").default("cubic-bezier(0.16, 1, 0.3, 1)"),
  background: z.literal("#111214").default("#111214"), surface: z.literal("#1B1D20").default("#1B1D20"),
  text: z.literal("#F5F6F7").default("#F5F6F7"), accent: z.literal("#86E1A8").default("#86E1A8"),
  layer_order: z.array(motionLayerSchema).default([...layerOrder]),
}).strict().superRefine((tokens, ctx) => {
  if (!(tokens.fast_ms < tokens.normal_ms && tokens.normal_ms < tokens.deliberate_ms)) ctx.addIssue({ code: "custom", message: "Motion durations must be ordered" });
  if (tokens.layer_order.join("|") !== layerOrder.join("|")) ctx.addIssue({ code: "custom", message: "Motion layer order is fixed" });
});

const motionCueDraftFields = {
  scene_id: z.string().min(1), primitive: motionPrimitiveSchema, layer: motionLayerSchema,
  start_ms: z.number().int().nonnegative(), end_ms: z.number().int().positive(), easing: motionEasingSchema,
  text: z.string().max(120).nullable(), product_clip_ref: z.string().regex(/^scene:[A-Za-z0-9._:-]+$/),
};
const motionPrimitiveBase = z.object(motionCueDraftFields).strict();
const refineCue = (cue: z.infer<typeof motionPrimitiveBase>, ctx: z.RefinementCtx) => {
  if (cue.end_ms <= cue.start_ms) ctx.addIssue({ code: "custom", message: "Motion cue end must follow start" });
  if (["stagger_text", "highlight_reveal"].includes(cue.primitive) && !cue.text) ctx.addIssue({ code: "custom", message: "Text primitive requires text" });
  if (cue.text && unsafeText.test(cue.text)) ctx.addIssue({ code: "custom", message: "Motion text cannot contain executable content" });
};
export const motionCueDraftSchema = motionPrimitiveBase.superRefine(refineCue);
export const motionCueSchema = z.object({ id: z.string().min(1), ...motionCueDraftFields }).strict().superRefine(refineCue);
export const motionDirectionDraftSchema = z.object({
  summary: z.string().min(1).max(240),
  cues: z.array(motionCueDraftSchema).min(1).max(80),
  editorial: editorialTemplateDraftSchema.nullable().default(null),
}).strict();
export const motionDirectionRequestSchema = z.object({
  project_id: z.string().min(1), job_id: z.string().min(1), storyboard_id: z.string().min(1), storyboard_version: z.number().int().positive(),
  duration_ms: z.number().int().positive().max(600000), evidence_fingerprint: z.string().regex(/^[a-f0-9]{64}$/),
  source_ids: z.array(z.string().min(1)).max(100), scene_ids: z.array(z.string().min(1)).min(1).max(80),
  product_clip_refs: z.array(z.string().regex(/^scene:[A-Za-z0-9._:-]+$/)).min(1).max(80), created_at: z.string().datetime({ offset: true }),
}).strict().superRefine((request, ctx) => {
  const unique = (values: string[]) => new Set(values).size === values.length;
  if (!unique(request.source_ids) || !unique(request.scene_ids) || !unique(request.product_clip_refs)) ctx.addIssue({ code: "custom", message: "Motion request references must be unique" });
  const expected = new Set(request.scene_ids.map((id) => `scene:${id}`));
  if (request.product_clip_refs.some((ref) => !expected.has(ref))) ctx.addIssue({ code: "custom", message: "Product clip must identify a requested scene" });
});
export const motionDirectionPlanSchema = z.object({
  id: z.string().min(1), project_id: z.string().min(1), job_id: z.string().min(1), run_id: z.string().min(1),
  request_fingerprint: z.string().regex(/^[a-f0-9]{64}$/), design_tokens: motionTokenSetSchema,
  duration_ms: z.number().int().positive().max(600000), scene_ids: z.array(z.string().min(1)).min(1).max(80),
  product_clip_refs: z.array(z.string()).min(1).max(80), summary: z.string().min(1).max(240),
  cues: z.array(motionCueSchema).min(1).max(80), created_at: z.string().datetime({ offset: true }),
  editorial_plan: editorialTemplatePlanSchema.nullable().default(null),
}).strict().superRefine((plan, ctx) => {
  const fail = (message: string) => ctx.addIssue({ code: "custom", message });
  if (new Set(plan.scene_ids).size !== plan.scene_ids.length || new Set(plan.product_clip_refs).size !== plan.product_clip_refs.length || new Set(plan.cues.map((cue) => cue.id)).size !== plan.cues.length) fail("Motion references must be unique");
  const scenes = new Set(plan.scene_ids); const clips = new Set(plan.product_clip_refs);
  if (plan.cues.some((cue) => !scenes.has(cue.scene_id) || !clips.has(cue.product_clip_ref) || cue.end_ms > plan.duration_ms)) fail("Motion cues must reference owned inputs and fit duration");
  for (const layer of layerOrder) {
    const cues = plan.cues.filter((cue) => cue.layer === layer).sort((a, b) => a.start_ms - b.start_ms);
    if (cues.some((cue, index) => index > 0 && cue.start_ms < cues[index - 1].end_ms)) fail("Motion cues on one layer cannot overlap");
  }
});
export const adkMotionRunSchema = z.object({
  id: z.string().min(1), project_id: z.string().min(1), job_id: z.string().min(1), session_id: z.string().min(1),
  agent_name: z.literal("demodirector_motion_director"), model: z.string().min(1), status: z.enum(["running", "succeeded", "failed"]),
  started_at: z.string().datetime({ offset: true }), completed_at: z.string().datetime({ offset: true }).nullable(), elapsed_ms: z.number().int().nonnegative().nullable(),
  retry_count: z.number().int().min(0).max(2), workflow_runs: z.number().int().min(0).max(1), input_artifact_ids: z.array(z.string().min(1)).min(1).max(120),
  output_plan_id: z.string().min(1).nullable(), validation_status: z.enum(["pending", "passed", "failed"]), message: z.string().min(1).max(300),
}).strict().superRefine((run, ctx) => {
  const fail = (message: string) => ctx.addIssue({ code: "custom", message });
  if (run.status === "running" && (run.completed_at !== null || run.elapsed_ms !== null || run.validation_status !== "pending" || run.output_plan_id !== null)) fail("Running ADK motion state is invalid");
  if (run.status !== "running") {
    if (!run.completed_at || run.elapsed_ms === null) fail("Completed ADK motion run requires timing");
    else if (Math.abs(new Date(run.completed_at).getTime() - new Date(run.started_at).getTime() - run.elapsed_ms) > 5) fail("ADK timing must match");
  }
  if (run.status === "succeeded" && (run.workflow_runs !== 1 || run.validation_status !== "passed" || !run.output_plan_id)) fail("Successful ADK motion run requires validated output");
  if (run.status === "failed" && (run.validation_status !== "failed" || run.output_plan_id !== null)) fail("Failed ADK motion run cannot expose output");
  if (/api_key=|bearer |password=|secret=/i.test(run.message)) fail("ADK motion message contains credentials");
});
export const compiledMotionCueSchema = z.object({
  cue_id: z.string().min(1), primitive: motionPrimitiveSchema, layer: motionLayerSchema, layer_index: z.number().int().min(0).max(6),
  start_frame: z.number().int().nonnegative(), end_frame: z.number().int().positive(), easing: motionEasingSchema,
}).strict();
export const compiledMotionCompositionSchema = z.object({
  project_id: z.string().min(1), plan_id: z.string().min(1), design_version: z.literal("motion-v1"),
  width: z.number().int().min(320).max(3840), height: z.number().int().min(180).max(2160), fps: z.number().int().min(12).max(60), duration_ms: z.number().int().positive(),
  cues: z.array(compiledMotionCueSchema), deterministic_hash: z.string().regex(/^[a-f0-9]{64}$/),
}).strict();

export type ADKMotionRun = z.infer<typeof adkMotionRunSchema>;
export type MotionDesignVersion = z.infer<typeof motionDesignVersionSchema>;
export type MotionDirectionPlan = z.infer<typeof motionDirectionPlanSchema>;
export type MotionDirectionRequest = z.infer<typeof motionDirectionRequestSchema>;
