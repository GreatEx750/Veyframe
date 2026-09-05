import { describe, expect, it } from "vitest";

import { generationTraceSchema } from "./jobs";

const stage = {
  id: "inspection:1", project_id: "project-1", kind: "inspection", sequence: 11,
  attempt: 1, retry_count: 0, status: "succeeded", label: "Inspect website", service: "Playwright",
  started_at: "2026-09-04T12:00:00.000Z", completed_at: "2026-09-04T12:00:01.250Z", elapsed_ms: 1250,
  message: "Saved website inspection.", contributions: [{ key: "pages_inspected", label: "Pages inspected", value: 2, unit: "pages" }],
  output_href: "/projects/project-1/editor#source-group-website_inspection",
} as const;
const trace = {
  id: "trace-job-1", project_id: "project-1", job_id: "job-1", status: "succeeded",
  created_at: "2026-09-04T12:00:00.000Z", updated_at: "2026-09-04T12:00:01.250Z",
  stages: [stage],
} as const;

describe("generation trace contract", () => {
  it("validates owned chronological stages and matching elapsed time", () => {
    expect(generationTraceSchema.safeParse(trace).success).toBe(true);
  });

  it("rejects foreign, out-of-order, and inconsistent stage data", () => {
    expect(generationTraceSchema.safeParse({ ...trace, stages: [{ ...stage, project_id: "foreign" }] }).success).toBe(false);
    expect(generationTraceSchema.safeParse({ ...trace, stages: [{ ...stage, sequence: 20 }, { ...stage, id: "research:1", kind: "research", sequence: 10 }] }).success).toBe(false);
    expect(generationTraceSchema.safeParse({ ...trace, stages: [{ ...stage, elapsed_ms: 5 }] }).success).toBe(false);
    expect(generationTraceSchema.safeParse({ ...trace, stages: [{ ...stage, attempt: 2, retry_count: 0 }] }).success).toBe(true);
  });

  it("rejects credential-bearing messages", () => {
    expect(generationTraceSchema.safeParse({ ...trace, stages: [{ ...stage, message: "api_key=private" }] }).success).toBe(false);
    expect(generationTraceSchema.safeParse({ ...trace, stages: [{ ...stage, output_href: "https://private.example/output" }] }).success).toBe(false);
  });
});
