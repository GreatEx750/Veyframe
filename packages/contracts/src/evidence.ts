import { z } from "zod";
import { researchSourceSchema } from "./schemas";
const text = z.string().min(1);
export const narrationEvidenceSchema = z.object({
  id: text, scene_id: text, text,
  status: z.enum(["source_quote", "source_linked", "user_assertion", "unverified"]),
  source_ids: z.array(text), explanation: text,
}).strict();
export const storyboardEvidenceSchema = z.object({
  project_id: z.string().min(1), storyboard_version: z.number().int().positive(),
  fingerprint: z.string().regex(/^[a-f0-9]{64}$/),
  claims: z.array(narrationEvidenceSchema),
  sources: z.array(researchSourceSchema), unverified_count: z.number().int().nonnegative(),
  approved: z.boolean(), approval_required: z.boolean(),
}).strict().superRefine((value, ctx) => {
  const known = new Set(value.sources.map((s) => s.id));
  if (value.sources.some((s) => s.project_id !== value.project_id) || value.claims.some((c) => c.source_ids.some((id) => !known.has(id))) || value.unverified_count !== value.claims.filter((c) => c.status === "unverified" || c.status === "source_linked").length) {
    ctx.addIssue({ code: "custom", message: "Evidence references or unverified count are invalid" });
  }
});
export type StoryboardEvidence = z.infer<typeof storyboardEvidenceSchema>;

export const contributionSourceSchema = z.object({
  id: text,
  project_id: text,
  title: text,
  url: z.string().url().nullable(),
  domain: text,
  origin: z.enum(["project_brief", "website_inspection", "parallel_search"]),
  retrieval_state: z.enum(["saved", "partial"]),
  retrieved_at: z.string().datetime().nullable(),
  excerpt: text.max(500),
}).strict();

export const contributionSceneSchema = z.object({
  id: text,
  title: text,
  order: z.number().int().nonnegative(),
}).strict();

export const sourceContributionSchema = z.object({
  id: text,
  project_id: text,
  source_id: text,
  kind: z.enum(["brief_context", "website_structure", "research_context", "factual_narration"]),
  scene_ids: z.array(text),
  narration_statement_ids: z.array(text),
  usage_state: z.enum(["used", "unused"]),
  label: text,
}).strict();

export const sourceContributionMapSchema = z.object({
  project_id: text,
  storyboard_version: z.number().int().positive(),
  fingerprint: z.string().regex(/^[a-f0-9]{64}$/),
  status: z.enum(["ready", "stale", "approval_required"]),
  partial_evidence: z.boolean(),
  sources: z.array(contributionSourceSchema),
  scenes: z.array(contributionSceneSchema),
  narration_statements: z.array(narrationEvidenceSchema),
  contributions: z.array(sourceContributionSchema),
}).strict().superRefine((value, ctx) => {
  const fail = (message: string) => ctx.addIssue({ code: "custom", message });
  const sourceIds = new Set(value.sources.map((source) => source.id));
  const sceneIds = new Set(value.scenes.map((scene) => scene.id));
  const statements = new Map(value.narration_statements.map((statement) => [statement.id, statement]));
  if (sourceIds.size !== value.sources.length || sceneIds.size !== value.scenes.length || statements.size !== value.narration_statements.length) fail("Contribution IDs must be unique");
  if (value.sources.some((source) => source.project_id !== value.project_id)) fail("Contribution sources must belong to the project");
  if (value.status !== "ready" && (value.contributions.length > 0 || value.narration_statements.length > 0)) fail("Stale maps must discard usage references");
  if (value.narration_statements.some((statement) => !sceneIds.has(statement.scene_id) || statement.source_ids.some((id) => !sourceIds.has(id)))) fail("Narration statements must use known evidence");
  const contributionIds = new Set<string>();
  for (const contribution of value.contributions) {
    if (contributionIds.has(contribution.id)) fail("Contribution IDs must be unique");
    contributionIds.add(contribution.id);
    if (contribution.project_id !== value.project_id || !sourceIds.has(contribution.source_id)) fail("Contribution must use project evidence");
    if (contribution.scene_ids.some((id) => !sceneIds.has(id)) || contribution.narration_statement_ids.some((id) => !statements.has(id))) fail("Contribution references are unknown");
    const used = contribution.scene_ids.length > 0 || contribution.narration_statement_ids.length > 0;
    if ((contribution.usage_state === "used") !== used) fail("Contribution usage state is inconsistent");
    if (contribution.kind === "website_structure" && contribution.narration_statement_ids.length > 0) fail("Website structure cannot support narration claims");
    if (contribution.kind === "factual_narration") {
      if (contribution.narration_statement_ids.length === 0) fail("Factual narration requires supported statements");
      for (const id of contribution.narration_statement_ids) {
        const statement = statements.get(id);
        if (!statement || !["source_quote", "source_linked"].includes(statement.status) || !statement.source_ids.includes(contribution.source_id) || !contribution.scene_ids.includes(statement.scene_id)) fail("Factual narration is not supported by saved evidence");
      }
    }
  }
});
export type SourceContributionMap = z.infer<typeof sourceContributionMapSchema>;
