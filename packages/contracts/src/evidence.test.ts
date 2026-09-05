import { describe, expect, it } from "vitest";

import { sourceContributionMapSchema } from "./evidence";

const fixture = {
  project_id: "project-1",
  storyboard_version: 2,
  fingerprint: "a".repeat(64),
  status: "ready",
  partial_evidence: false,
  sources: [
    {
      id: "source-1",
      project_id: "project-1",
      title: "Official guide",
      url: "https://example.com/guide",
      domain: "example.com",
      origin: "parallel_search",
      retrieval_state: "saved",
      retrieved_at: "2026-09-04T12:00:00Z",
      excerpt: "A safe saved excerpt.",
    },
  ],
  scenes: [{ id: "scene-1", title: "Opening", order: 0 }],
  narration_statements: [
    {
      id: "statement-1",
      scene_id: "scene-1",
      text: "A factual statement.",
      status: "source_quote",
      source_ids: ["source-1"],
      explanation: "Saved excerpt match.",
    },
  ],
  contributions: [
    {
      id: "source-1:factual_narration",
      project_id: "project-1",
      source_id: "source-1",
      kind: "factual_narration",
      scene_ids: ["scene-1"],
      narration_statement_ids: ["statement-1"],
      usage_state: "used",
      label: "Supports approved narration",
    },
  ],
};

describe("source contribution map", () => {
  it("accepts project-owned references to supported narration", () => {
    expect(sourceContributionMapSchema.safeParse(fixture).success).toBe(true);
  });

  it("rejects foreign sources, missing scenes, and unsupported statements", () => {
    expect(sourceContributionMapSchema.safeParse({
      ...fixture,
      sources: [{ ...fixture.sources[0], project_id: "foreign-project" }],
    }).success).toBe(false);
    expect(sourceContributionMapSchema.safeParse({
      ...fixture,
      contributions: [{ ...fixture.contributions[0], scene_ids: ["missing-scene"] }],
    }).success).toBe(false);
    expect(sourceContributionMapSchema.safeParse({
      ...fixture,
      narration_statements: [{ ...fixture.narration_statements[0], source_ids: [] }],
    }).success).toBe(false);
  });

  it("requires stale maps to discard old usage references", () => {
    expect(sourceContributionMapSchema.safeParse({
      ...fixture,
      status: "stale",
      contributions: [],
      narration_statements: [],
    }).success).toBe(true);
    expect(sourceContributionMapSchema.safeParse({ ...fixture, status: "stale" }).success)
      .toBe(false);
  });
});
