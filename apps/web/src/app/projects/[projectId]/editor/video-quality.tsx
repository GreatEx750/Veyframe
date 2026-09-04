"use client";

import { videoReviewSchema, optimizationRunSchema, type OptimizationRun, type VideoReview } from "@demodirector/contracts";
import { useEffect, useState } from "react";

export function VideoQuality({ projectId, exportId, onSeek, onTimelineChanged }: { projectId: string; exportId?: string; onSeek: (ms: number) => void; onTimelineChanged?: () => void }) {
  const [review, setReview] = useState<VideoReview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [optimization, setOptimization] = useState<OptimizationRun | null>(null);
  const base = `/api/projects/${encodeURIComponent(projectId)}/quality-api`;
  useEffect(() => {
    if (!exportId) return;
    let active = true;
    void fetch(`${base}/exports/${encodeURIComponent(exportId)}/reviews/latest`, { cache: "no-store" }).then(async (response) => {
      if (response.status === 404) return;
      const parsed = videoReviewSchema.safeParse(await response.json());
      if (active && response.ok && parsed.success) setReview(parsed.data);
    }).catch(() => { if (active) setError("Saved review unavailable. Reload to check its status."); });
    return () => { active = false; };
  }, [base, exportId]);

  async function requestReview() {
    setBusy(true); setError("");
    try {
      const response = await fetch(`${base}/exports/${encodeURIComponent(exportId!)}/reviews`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ retry: review?.status === "failed" || review?.status === "running" }) });
      const body: unknown = await response.json();
      if (!response.ok) throw new Error(typeof body === "object" && body && "detail" in body ? String(body.detail) : "Review unavailable");
      setReview(videoReviewSchema.parse(body));
    } catch (failure) { setError(failure instanceof Error ? failure.message : "Review unavailable"); }
    finally { setBusy(false); }
  }

  async function optimize(action: "propose" | "apply" | "cancel") {
    setBusy(true); setError("");
    try {
      const suffix = action === "propose" ? "optimizations" : `optimizations/${optimization!.id}/${action}`;
      const body = action === "propose" ? { review_id: review!.id } : action === "apply" ? { approved: true, expected_version: optimization!.before_version } : {};
      const response = await fetch(`${base}/${suffix}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const result: unknown = await response.json();
      if (!response.ok) throw new Error(typeof result === "object" && result && "detail" in result ? String(result.detail) : "Optimization unavailable");
      const saved = optimizationRunSchema.parse(result);
      setOptimization(saved);
      if (saved.after_version !== null) onTimelineChanged?.();
    } catch (failure) { setError(failure instanceof Error ? failure.message : "Optimization unavailable"); }
    finally { setBusy(false); }
  }

  return <section aria-label="Rendered video quality">
    <h2>Video quality</h2>
    <p>Review the rendered picture and audio. Scores are AI assessments, not verified business outcomes.</p>
    <button type="button" disabled={!exportId || busy} onClick={() => void requestReview()}>{busy ? "Working…" : review?.status === "running" ? "Recover interrupted review" : review?.status === "failed" ? "Retry review" : review?.status === "succeeded" ? "Load saved review" : "Review video · one AI call"}</button>
    {!exportId && <p>Export the saved timeline first.</p>}
    {error && <p role="alert">{error}</p>}
    {review?.status === "running" && <p role="status">Review in progress. Reopen this panel to load its saved result.</p>}
    {review?.error && <p role="alert">{review.error}</p>}
    {review?.result && <>
      <p>Overall: {review.overall_score}/100 · timeline v{review.timeline_version}</p>
      <dl>{review.result.scores.map((score) => <div key={score.dimension}><dt>{score.dimension.replaceAll("_", " ")}: {score.score}/100</dt><dd>{score.explanation}</dd></div>)}</dl>
      {review.result.findings.map((finding) => <article className="source-item" key={finding.id}>
        <button type="button" onClick={() => onSeek(finding.start_ms)}>Seek {(finding.start_ms / 1000).toFixed(1)}s</button>
        <p>{finding.severity}: {finding.observation}</p><p>{finding.evidence_summary}</p>
      </article>)}
      <p>{review.model_name} · {review.prompt_version} · {new Date(review.created_at).toLocaleString()}</p>
      <button type="button" disabled={busy} onClick={() => void optimize("propose")}>Propose safe repairs · no AI call</button>
    </>}
    {optimization && <section aria-label="Optimization proposal">
      <h3>Repair proposal</h3><p>{optimization.proposal.explanation}</p>
      <ol>{optimization.proposal.operations.map((operation, index) => <li key={index}>{operation.operation_type.replaceAll("_", " ")} — {operation.rationale}</li>)}</ol>
      {optimization.proposal.unsupported_findings.length > 0 && <p>{optimization.proposal.unsupported_findings.length} findings need manual editing or a later repair capability.</p>}
      {optimization.status === "proposed" && <>
        <button type="button" disabled={busy || optimization.proposal.operations.length === 0} onClick={() => void optimize("apply")}>Approve edits, render, and one AI review</button>
        <button type="button" disabled={busy} onClick={() => void optimize("cancel")}>Cancel proposal</button>
      </>}
      <p role="status">{optimization.message}</p>
      {optimization.after_score !== null && <p>Before {optimization.before_score} → after {optimization.after_score}; change {optimization.score_delta}. {optimization.stop_reason.replaceAll("_", " ")}</p>}
      <a href={`/api/projects/${projectId}/exports/${optimization.before_export_id}/video`} target="_blank" rel="noreferrer">Open original video</a>
      {optimization.after_export_id && <> · <a href={`/api/projects/${projectId}/exports/${optimization.after_export_id}/video`} target="_blank" rel="noreferrer">Open candidate video</a><p>The original stays preferred. Reload the editor to inspect the saved candidate timeline; use Export changes to choose it.</p></>}
    </section>}
  </section>;
}
