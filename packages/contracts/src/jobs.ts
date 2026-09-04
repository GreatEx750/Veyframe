import { z } from "zod";
const stage = z.enum(["inspection", "research", "understanding", "storyboard", "capture", "narration", "render", "done"]);
export const generationJobSchema = z.object({
  id: z.string().min(1), project_id: z.string().min(1),
  status: z.enum(["queued", "running", "awaiting_approval", "awaiting_retry", "failed", "succeeded"]), stage,
  completed_stages: z.array(stage), attempts: z.number().int().min(0).max(3), version: z.number().int().positive(),
  created_at: z.string().datetime({ offset: true }), updated_at: z.string().datetime({ offset: true }),
  lease_until: z.string().datetime({ offset: true }).nullable(), message: z.string().min(1),
  export_id: z.string().nullable(), timeline_version: z.number().int().positive().nullable(),
}).strict();
export type GenerationJob = z.infer<typeof generationJobSchema>;
