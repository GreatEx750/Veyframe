import { z } from "zod";
import { researchSourceSchema } from "./schemas";
export const storyboardEvidenceSchema = z.object({
  project_id: z.string().min(1), storyboard_version: z.number().int().positive(),
  fingerprint: z.string().regex(/^[a-f0-9]{64}$/),
  claims: z.array(z.object({
    id: z.string().min(1), scene_id: z.string().min(1), text: z.string().min(1),
    status: z.enum(["source_quote", "source_linked", "user_assertion", "unverified"]),
    source_ids: z.array(z.string().min(1)), explanation: z.string().min(1),
  }).strict()),
  sources: z.array(researchSourceSchema), unverified_count: z.number().int().nonnegative(),
  approved: z.boolean(), approval_required: z.boolean(),
}).strict().superRefine((value, ctx) => {
  const known = new Set(value.sources.map((s) => s.id));
  if (value.sources.some((s) => s.project_id !== value.project_id) || value.claims.some((c) => c.source_ids.some((id) => !known.has(id))) || value.unverified_count !== value.claims.filter((c) => c.status === "unverified" || c.status === "source_linked").length) {
    ctx.addIssue({ code: "custom", message: "Evidence references or unverified count are invalid" });
  }
});
export type StoryboardEvidence = z.infer<typeof storyboardEvidenceSchema>;
