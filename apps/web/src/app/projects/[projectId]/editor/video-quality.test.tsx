import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { qualityDimensions, videoReviewSchema } from "@demodirector/contracts";
import { VideoQuality } from "./video-quality";

const fixture = {
  id: "review-1", project_id: "project-1", export_id: "export-1", timeline_version: 1,
  status: "succeeded", model_name: "fixture", prompt_version: "v1", created_at: "2026-09-03T00:00:00Z",
  duration_ms: 20000, evidence: [{ id: "media-0", start_ms: 0, end_ms: 1000, media_sha256: "a".repeat(64) }],
  result: { scores: qualityDimensions.map((dimension) => ({ dimension, score: 70, explanation: "Observed", finding_ids: dimension === "camera_quality" ? ["f1"] : [] })),
    findings: [{ id: "f1", dimension: "camera_quality", severity: "high", start_ms: 100, end_ms: 900, observation: "Zoom crops navigation", evidence_summary: "Clipped top edge", evidence_ids: ["media-0"], repair_category: "camera" }] },
  overall_score: 70, error: null, model_calls: 1, retryable: false,
};
afterEach(() => vi.unstubAllGlobals());
it("loads saved results without a paid request and seeks the preview", async () => {
  const fetcher = vi.fn().mockResolvedValue(Response.json(fixture));
  vi.stubGlobal("fetch", fetcher);
  const seek = vi.fn();
  render(<VideoQuality projectId="project-1" exportId="export-1" onSeek={seek} />);
  await screen.findByText("Overall: 70/100 · timeline v1");
  fireEvent.click(screen.getByRole("button", { name: "Seek 0.1s" }));
  expect(seek).toHaveBeenCalledWith(100);
  expect(fetcher).toHaveBeenCalledTimes(1);
});
it("requests review only after an explicit click", async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(Response.json({}, { status: 404 })).mockResolvedValueOnce(Response.json(fixture));
  vi.stubGlobal("fetch", fetcher);
  render(<VideoQuality projectId="project-1" exportId="export-1" onSeek={() => {}} />);
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByRole("button", { name: "Review video · one AI call" }));
  await screen.findByText("Overall: 70/100 · timeline v1");
  expect(fetcher.mock.calls[1][1].method).toBe("POST");
});
it("rejects fabricated evidence and incorrect aggregate scores", () => {
  expect(videoReviewSchema.safeParse(fixture).success).toBe(true);
  expect(videoReviewSchema.safeParse({ ...fixture, overall_score: 100 }).success).toBe(false);
  expect(videoReviewSchema.safeParse({ ...fixture, evidence: [] }).success).toBe(false);
});
