"use client";
import { generationJobSchema, type GenerationJob } from "@demodirector/contracts";
import Link from "next/link";
import { useEffect, useState } from "react";

export function GenerationProgress({ projectId }: { projectId: string }) {
  const [job, setJob] = useState<GenerationJob | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const response = await fetch(`/api/projects/${projectId}/generation`, { cache: "no-store" });
        if (!response.ok) throw new Error("Saved generation status is temporarily unavailable.");
        const parsed = generationJobSchema.parse(await response.json());
        if (active) { setJob(parsed); setError(""); }
        if (parsed.status === "succeeded" || parsed.status === "failed") return;
      } catch (failure) { if (active) setError(failure instanceof Error ? failure.message : "Unable to load progress"); }
      if (active) timer = setTimeout(() => void poll(), 5000);
    }
    void poll();
    return () => { active = false; clearTimeout(timer); };
  }, [projectId]);
  async function retry() {
    if (!job) return;
    setBusy(true);
    try {
      const response = await fetch(`/api/projects/${projectId}/generation/${job.id}/retry`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ approved: true }) });
      if (!response.ok) throw new Error("Retry unavailable. Reload to check the latest status.");
      setJob(generationJobSchema.parse(await response.json())); setError("");
    } catch (failure) { setError(failure instanceof Error ? failure.message : "Retry failed"); }
    finally { setBusy(false); }
  }
  return <main className="storyboard-page">
    <Link href="/projects">Back to projects</Link><h1>Demo generation</h1>
    <p>You may close this browser. Reopen this page to see saved progress.</p>
    {error && <p role="alert">{error}</p>}
    <p role="status">{job?.message ?? "Loading saved job…"}</p>
    {job && <><p>Stage: {job.stage} · {job.completed_stages.length}/7 completed</p><ul>{job.completed_stages.map((stage) => <li key={stage}>{stage} saved</li>)}</ul>
      {job.status === "awaiting_retry" && <><p>Only the failed stage will run again. If its earlier provider call completed without saving, retrying may incur another charge.</p><button disabled={busy || job.attempts >= 3} onClick={() => void retry()} type="button">Approve retry of this stage</button></>}
      {job.status === "queued" && <><p>Local development requires the separate generation worker. Cloud runs use the configured task queue.</p><button type="button" disabled={busy} onClick={() => void retry()}>Ensure job is dispatched</button></>}
      {job.status === "awaiting_approval" && <Link href={`/projects/${projectId}/storyboard`}>Review evidence and approve storyboard</Link>}
      {job.status === "succeeded" && <Link href={`/projects/${projectId}/editor`}>Open finished demo</Link>}
    </>}
  </main>;
}
