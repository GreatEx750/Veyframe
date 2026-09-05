import { z } from "zod";
import { viewportSchema } from "./schemas";
import { visualVariantIdSchema } from "./style";

const id = z.string().min(1);
export const longFormSectionIdSchema = z.enum([
  "hook", "problem", "promise", "product_walkthrough", "trust_technology",
  "editing_control", "finished_result", "closing",
]);
export const longFormDirectionRequestSchema = z.object({
  plan_id: id, run_id: id, project_id: id, job_id: id, parent_motion_run_id: id,
  visual_variant: visualVariantIdSchema, research_status: z.enum(["complete", "degraded"]),
  evidence_refs: z.array(id).min(1).max(160), parallel_source_refs: z.array(id).max(80).default([]),
  product_clip_refs: z.array(id).min(1).max(80), target_ids: z.array(id).max(160).default([]),
  created_at: z.string().datetime({ offset: true }),
}).strict();
const templateId = z.enum([
  "hook", "framed_product", "feature_callout", "split_explanation", "proof_safety", "closing",
]);
export const longFormNarrativeSectionSchema = z.object({
  id: longFormSectionIdSchema, order: z.number().int().min(0).max(7),
  start_ms: z.number().int().nonnegative(), end_ms: z.number().int().positive(),
  narration: z.string().min(1).max(1800), source_refs: z.array(id).min(1).max(40),
  product_clip_ref: id, product_visible: z.literal(true).default(true),
}).strict();
export const visualBeatSchema = z.object({
  id, section_id: longFormSectionIdSchema,
  start_ms: z.number().int().nonnegative(), end_ms: z.number().int().positive(),
  purpose: z.enum(["hook", "problem", "promise", "product_operation", "create_action", "finished_glimpse", "walkthrough", "evidence", "control", "result", "closing"]),
  template_id: templateId, product_clip_ref: id, target_id: id.nullable().default(null),
  source_refs: z.array(id).max(20).default([]),
}).strict();
export const captureChapterSchema = z.object({
  id, project_id: id, order: z.number().int().min(0).max(7),
  section_ids: z.array(longFormSectionIdSchema).min(1).max(4),
  start_ms: z.number().int().nonnegative(), end_ms: z.number().int().positive(),
  viewport: viewportSchema, account_ref: id, project_state_ref: id,
  style_version: z.literal("style-v1").default("style-v1"), cursor_continuity_key: id,
}).strict();
export const chapterCheckpointSchema = z.object({
  id, project_id: id, plan_id: id, chapter_id: id,
  status: z.enum(["pending", "captured", "failed", "approved"]),
  attempt: z.number().int().min(0).max(3), artifact_ref: id.nullable().default(null),
  artifact_sha256: z.string().regex(/^[a-f0-9]{64}$/).nullable().default(null),
  elapsed_ms: z.number().int().nonnegative().nullable().default(null),
  replaces_checkpoint_id: id.nullable().default(null), created_at: z.string().datetime({ offset: true }),
}).strict().superRefine((item, context) => {
  const hasArtifact = item.artifact_ref !== null && item.artifact_sha256 !== null;
  if (["captured", "approved"].includes(item.status) !== hasArtifact) {
    context.addIssue({ code: "custom", message: "Chapter artifact must match status" });
  }
});
export const chapterCheckpointsSchema = z.array(chapterCheckpointSchema);
export const condensedIntervalSchema = z.object({
  start_ms: z.number().int().nonnegative(), end_ms: z.number().int().positive(),
  actual_elapsed_ms: z.number().int().positive(), label: id.default("Time compressed"),
}).strict().refine((item) => item.end_ms > item.start_ms && item.actual_elapsed_ms > item.end_ms - item.start_ms);
export const audioMixPlanSchema = z.object({
  narration_lufs: z.number().min(-24).max(-12).default(-16),
  music_lufs: z.number().min(-40).max(-20).default(-28),
  ducking_db: z.number().min(-18).max(-3).default(-8),
  fade_ms: z.number().int().min(100).max(2000).default(500),
}).strict();
export const longFormVideoPlanSchema = z.object({
  id, project_id: id, job_id: id, adk_run_id: id, parent_motion_run_id: id,
  version: z.literal("longform-v1").default("longform-v1"),
  motion_version: z.literal("motion-v1").default("motion-v1"),
  style_version: z.literal("style-v1").default("style-v1"),
  visual_variant: visualVariantIdSchema, duration_ms: z.literal(180000).default(180000),
  research_status: z.enum(["complete", "degraded"]), evidence_refs: z.array(id).min(1).max(160),
  parallel_source_refs: z.array(id).max(80).default([]), product_clip_refs: z.array(id).min(1).max(80),
  target_ids: z.array(id).max(160).default([]), sections: z.array(longFormNarrativeSectionSchema).length(8),
  beats: z.array(visualBeatSchema).min(20).max(30), chapters: z.array(captureChapterSchema).min(2).max(8),
  condensed_intervals: z.array(condensedIntervalSchema).max(12).default([]), audio_mix: audioMixPlanSchema.default({ narration_lufs: -16, music_lufs: -28, ducking_db: -8, fade_ms: 500 }),
  first_product_operation_ms: z.number().int().min(0).max(20000), create_action_ms: z.number().int().min(0).max(30000),
  finished_glimpse_ms: z.number().int().min(0).max(45000), product_presence_percent: z.number().min(90).max(100),
  created_at: z.string().datetime({ offset: true }),
}).strict().superRefine((plan, context) => {
  const profile = [["hook", 4000], ["problem", 6000], ["promise", 10000], ["product_walkthrough", 75000], ["trust_technology", 35000], ["editing_control", 25000], ["finished_result", 20000], ["closing", 5000]] as const;
  let cursor = 0;
  profile.forEach(([name, duration], index) => {
    const section = plan.sections[index];
    if (!section || section.id !== name || section.order !== index || section.start_ms !== cursor || section.end_ms - section.start_ms !== duration) context.addIssue({ code: "custom", message: "Invalid long-form timing profile", path: ["sections", index] });
    cursor += duration;
  });
  const words = plan.sections.flatMap((section) => section.narration.trim().split(/\s+/)).length;
  if (words < 350 || words > 430) context.addIssue({ code: "custom", message: "Narration must contain 350 to 430 words" });
  const evidence = new Set(plan.evidence_refs), clips = new Set(plan.product_clip_refs), targets = new Set(plan.target_ids);
  if (plan.research_status === "complete" && plan.parallel_source_refs.length === 0) context.addIssue({ code: "custom", message: "Complete research requires direct Parallel evidence" });
  if (plan.parallel_source_refs.some((ref) => !evidence.has(ref))) context.addIssue({ code: "custom", message: "Parallel evidence is not approved" });
  plan.sections.forEach((section) => {
    const sectionWords = section.narration.trim().split(/\s+/).length;
    if (sectionWords > ((section.end_ms - section.start_ms) / 1000) * 3) context.addIssue({ code: "custom", message: "Narration exceeds the readable speech rate for its section" });
    if (!clips.has(section.product_clip_ref) || section.source_refs.some((ref) => !evidence.has(ref))) context.addIssue({ code: "custom", message: "Section references are not approved" });
  });
  plan.beats.forEach((beat) => {
    const section = plan.sections.find((item) => item.id === beat.section_id);
    if (!section || beat.start_ms < section.start_ms || beat.end_ms > section.end_ms || beat.end_ms <= beat.start_ms || !clips.has(beat.product_clip_ref) || (beat.target_id !== null && !targets.has(beat.target_id)) || beat.source_refs.some((ref) => !evidence.has(ref))) context.addIssue({ code: "custom", message: "Beat timing or references are not approved" });
  });
  if (new Set(plan.beats.map((beat) => beat.section_id)).size !== profile.length) context.addIssue({ code: "custom", message: "Every narrative section requires a visual beat" });
  const milestones = [["product_operation", plan.first_product_operation_ms], ["create_action", plan.create_action_ms], ["finished_glimpse", plan.finished_glimpse_ms]] as const;
  milestones.forEach(([purpose, start]) => {
    const matching = plan.beats.filter((beat) => beat.purpose === purpose);
    if (matching.length !== 1 || matching[0]?.start_ms !== start) context.addIssue({ code: "custom", message: "Proof-first milestone beat is invalid" });
  });
  const sectionIds = plan.chapters.flatMap((chapter) => chapter.section_ids);
  if (sectionIds.join("|") !== profile.map(([name]) => name).join("|")) context.addIssue({ code: "custom", message: "Capture chapters must cover each section once in order" });
  const continuity = plan.chapters[0] ? JSON.stringify([plan.chapters[0].viewport, plan.chapters[0].account_ref, plan.chapters[0].project_state_ref, plan.chapters[0].style_version, plan.chapters[0].cursor_continuity_key]) : "";
  plan.chapters.forEach((chapter, index) => {
    const chapterSections = chapter.section_ids.map((sectionId) => plan.sections.find((section) => section.id === sectionId));
    const currentContinuity = JSON.stringify([chapter.viewport, chapter.account_ref, chapter.project_state_ref, chapter.style_version, chapter.cursor_continuity_key]);
    if (chapter.project_id !== plan.project_id || chapter.order !== index || chapter.start_ms !== chapterSections[0]?.start_ms || chapter.end_ms !== chapterSections.at(-1)?.end_ms || chapter.end_ms <= chapter.start_ms || currentContinuity !== continuity) context.addIssue({ code: "custom", message: "Capture chapter lineage, timing, or continuity is invalid" });
  });
  let intervalEnd = 0;
  plan.condensed_intervals.forEach((interval) => {
    if (interval.start_ms < intervalEnd || interval.end_ms > plan.duration_ms) context.addIssue({ code: "custom", message: "Condensed intervals must be ordered within the video" });
    intervalEnd = interval.end_ms;
  });
});
export const longFormAdkStepSchema = z.object({
  id, run_id: id, project_id: id, kind: z.enum(["narrative", "template", "attention", "style"]),
  status: z.enum(["succeeded", "failed"]), tool_call_count: z.number().int().min(0).max(1),
  artifact_refs: z.array(id).max(160).default([]), output_sha256: z.string().regex(/^[a-f0-9]{64}$/).nullable().default(null),
  created_at: z.string().datetime({ offset: true }),
}).strict();
export const longFormAdkRunSchema = z.object({
  id, project_id: id, job_id: id, parent_motion_run_id: id, session_id: id,
  agent_name: z.literal("demodirector_longform_director"), model: id,
  status: z.enum(["running", "succeeded", "failed"]), runner_completed: z.boolean(),
  workflow_runs: z.number().int().min(0).max(1), step_ids: z.array(id).max(4),
  output_plan_id: id.nullable().default(null), started_at: z.string().datetime({ offset: true }),
  completed_at: z.string().datetime({ offset: true }).nullable().default(null),
  elapsed_ms: z.number().int().nonnegative().nullable().default(null), message: z.string().min(1).max(300),
}).strict();
export type LongFormVideoPlan = z.infer<typeof longFormVideoPlanSchema>;
export type ChapterCheckpoint = z.infer<typeof chapterCheckpointSchema>;
