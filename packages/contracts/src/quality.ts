import { z } from "zod";
import { editOperationSchema } from "./schemas";

const text = z.string().min(1);
export const qualityDimensions = ["visual_clarity", "narration_sync", "caption_readability", "pacing", "camera_quality", "cta_effectiveness"] as const;
const dimension = z.enum(qualityDimensions);
export const videoReviewSchema = z.object({
  id: text, project_id: text, export_id: text, timeline_version: z.number().int().positive(),
  status: z.enum(["running", "succeeded", "failed"]), model_name: text, prompt_version: text,
  created_at: z.string().datetime({ offset: true }), duration_ms: z.number().int().positive().max(180000),
  evidence: z.array(z.object({ id: text, start_ms: z.number().int().nonnegative(), end_ms: z.number().int().positive(), media_sha256: z.string().regex(/^[a-f0-9]{64}$/) }).strict()).min(1).max(180),
  result: z.object({
    scores: z.array(z.object({ dimension, score: z.number().int().min(0).max(100), explanation: text.max(800), finding_ids: z.array(text).max(12) }).strict()).length(6),
    findings: z.array(z.object({
      id: text, dimension, severity: z.enum(["low", "medium", "high"]),
      start_ms: z.number().int().nonnegative(), end_ms: z.number().int().positive(),
      observation: text.max(800), evidence_summary: text.max(800), evidence_ids: z.array(text).min(1).max(4),
      repair_category: z.enum(["camera", "caption", "pacing", "narration", "cta", "recapture", "manual"]),
    }).strict()).max(12),
  }).strict().nullable(),
  overall_score: z.number().min(0).max(100).nullable(), error: z.string().nullable(),
  model_calls: z.number().int().min(0).max(1), retryable: z.boolean(),
}).strict().superRefine((review, ctx) => {
  const fail = () => ctx.addIssue({ code: "custom", message: "Invalid review evidence or scores" });
  const evidence = new Map(review.evidence.map((e) => [e.id, e]));
  if (evidence.size !== review.evidence.length || review.evidence.some((e) => e.end_ms <= e.start_ms || e.end_ms > review.duration_ms)) fail();
  if (review.status !== "succeeded") {
    if (review.result || review.overall_score !== null) fail();
    if (review.status === "failed" && (!review.error || !review.retryable)) fail();
    return;
  }
  const result = review.result;
  if (!result || review.error || review.retryable) { fail(); return; }
  if (new Set(result.scores.map((s) => s.dimension)).size !== 6) fail();
  if (Math.abs(result.scores.reduce((sum, s) => sum + s.score, 0) / 6 - (review.overall_score ?? -1)) > .0051) fail();
  if (new Set(result.findings.map((f) => f.id)).size !== result.findings.length) fail();
  for (const s of result.scores) {
    const ids = result.findings.filter((f) => f.dimension === s.dimension).map((f) => f.id).sort();
    if (JSON.stringify([...new Set(s.finding_ids)].sort()) !== JSON.stringify(ids)) fail();
  }
  for (const f of result.findings) {
    if (f.end_ms <= f.start_ms || f.end_ms > review.duration_ms || f.evidence_ids.some((id) => {
      const e = evidence.get(id); return !e || e.start_ms >= f.end_ms || e.end_ms <= f.start_ms;
    })) fail();
  }
});
export type VideoReview = z.infer<typeof videoReviewSchema>;

export const optimizationRunSchema = z.object({
  id: text, project_id: text, review_id: text, before_export_id: text,
  before_version: z.number().int().positive(), before_score: z.number().min(0).max(100),
  proposal: z.object({ operations: z.array(editOperationSchema).max(3), finding_ids: z.array(text).max(3), explanation: text, unsupported_findings: z.array(text) }).strict(),
  status: z.enum(["proposed", "running", "succeeded", "failed", "cancelled"]),
  stop_reason: z.enum(["awaiting_approval", "target_reached", "improved", "no_improvement", "unsupported", "render_failed", "review_failed", "version_conflict", "cancelled", "apply_failed", "budget_limit"]),
  after_version: z.number().int().positive().nullable(), after_export_id: text.nullable(), after_review_id: text.nullable(),
  after_score: z.number().min(0).max(100).nullable(), score_delta: z.number().nullable(),
  cycles: z.number().int().min(0).max(1), model_calls: z.number().int().min(0).max(1),
  created_at: z.string().datetime({ offset: true }), message: text,
}).strict();
export type OptimizationRun = z.infer<typeof optimizationRunSchema>;
