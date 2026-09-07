"use client";

import { jobsOverviewSchema, type JobDetails, type JobsOverview } from "@demodirector/contracts";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ProductNavigation } from "@/components/product-navigation";
import "./jobs.css";

function duration(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  return minutes >= 60 ? `${Math.floor(minutes / 60)}h ${minutes % 60}m` : `${minutes}m ${seconds % 60}s`;
}
function date(value: string) { return new Date(value).toLocaleString(); }

export function JobsDashboard({ projectId, jobId }: { projectId?: string; jobId?: string }) {
  const [overview, setOverview] = useState<JobsOverview | null>(null);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const response = await fetch("/api/jobs", { cache: "no-store", signal: controller.signal });
        if (!response.ok) throw new Error(response.status === 401 ? "Sign in again to see your jobs." : "Live updates are disconnected. Showing the last saved status; retrying automatically.");
        const data = jobsOverviewSchema.parse(await response.json());
        if (active) { setOverview(data); setError(""); }
      } catch (failure) {
        if (active) setError(failure instanceof Error && !failure.message.includes("[") ? failure.message : "The server returned an invalid job update. Retrying automatically.");
      } finally {
        if (active) timer = setTimeout(() => void poll(), 3000);
      }
    }
    void poll();
    return () => { active = false; controller.abort(); clearTimeout(timer); };
  }, [revision]);
  const requestedJob = selected || jobId;
  const hasTarget = Boolean(requestedJob || projectId);
  const details = requestedJob
    ? overview?.jobs.find((item) => item.job.id === requestedJob)
    : projectId
      ? overview?.jobs.find((item) => item.job.project_id === projectId)
      : overview?.jobs[0];

  async function retry(entry: JobDetails, approved = true, rebuild = false) {
    setBusy(true); setActionError("");
    const suffix = entry.kind === "presentation_preview" ? "presentation-preview" : entry.kind === "presentation" ? "presentation" : `${entry.job.id}/retry`;
    try {
      const response = await fetch(`/api/projects/${entry.job.project_id}/generation/${suffix}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(rebuild ? { approved, rebuild } : { approved }),
      });
      if (!response.ok) throw new Error(response.status === 409 ? "Another job is active, or this retry is no longer available. Check the job list." : "Retry could not be queued. Saved work is unchanged.");
      setRevision((value) => value + 1);
    } catch (failure) { setActionError(failure instanceof Error ? failure.message : "Retry failed."); }
    finally { setBusy(false); }
  }

  return <main className="library-shell jobs-shell">
    <ProductNavigation active="jobs" />
    <div className="jobs-content">
      <header className="jobs-heading"><div><h1>Generation jobs</h1><p>{overview ? `${overview.active_count} active · Maximum 1 generation per account` : "Loading your saved jobs…"}</p></div><Link href="/studio">Back to Studio</Link></header>
      {error && <p className="jobs-warning" role="alert">{error}</p>}
      <p className="jobs-sync">{overview ? `Last synced ${date(overview.server_time)} · Updates every 3 seconds` : "Connecting to the generation service…"}</p>
      {overview && hasTarget && !details && <p role="status" className="jobs-note">Waiting for the selected job to appear in your saved jobs. This page checks automatically. If the job was removed or belongs to another account, it will not appear. <Link href="/jobs">Show all jobs</Link></p>}
      {overview && !hasTarget && overview.jobs.length === 0 && <section className="jobs-empty"><h2>No generation jobs yet</h2><p>Create a demo in Studio. Its progress and activity will appear here.</p><Link href="/studio">Create a demo</Link></section>}
      {overview && overview.jobs.length > 0 && <div className="jobs-layout">
        <nav aria-label="Generation jobs" className="jobs-list">{overview.jobs.map((entry) => <button key={entry.job.id} aria-current={entry.job.id === details?.job.id ? "true" : undefined} onClick={() => setSelected(entry.job.id)} type="button">
          <b>{entry.project_name}</b><span>{entry.format_label ?? (entry.kind === "presentation_preview" ? "First five slides" : entry.kind === "presentation" ? "Presentation · 2 minutes" : "Demo generation")} · {entry.job.status.replaceAll("_", " ")}</span><span>{date(entry.job.created_at)}</span><code>{entry.job.id.slice(0, 8)}</code>
        </button>)}</nav>
        {details && <section className="job-detail" aria-label="Selected job details">
          <header><h2>{details.project_name}</h2><Link href="/projects">Project library</Link></header>
          <p className={`job-health job-health-${details.health}`} role="status">{details.health_message}</p>
          <h3>Current step</h3><p className="job-current-step">{details.job.message}</p>
          <dl className="job-facts">
            <div><dt>Status</dt><dd>{details.job.status.replaceAll("_", " ")}</dd></div>
            <div><dt>Stage</dt><dd>{details.job.stage}</dd></div>
            <div><dt>Elapsed since queued</dt><dd>{duration(details.elapsed_seconds)}</dd></div>
            <div><dt>Since last progress</dt><dd>{duration(details.step_elapsed_seconds)}</dd></div>
            <div><dt>Estimated remaining</dt><dd>{details.eta_min_seconds === null || details.eta_max_seconds === null ? "Not currently estimable" : `${duration(details.eta_min_seconds)} – ${duration(details.eta_max_seconds)}`}</dd></div>
            <div><dt>{details.kind !== "generation" ? "Generation attempt" : "Current stage attempt"}</dt><dd>{details.job.attempts} / 3</dd></div>
            <div><dt>Worker heartbeat</dt><dd>{details.heartbeat_at ? date(details.heartbeat_at) : "Not yet reported"}</dd></div>
            <div><dt>Last progress</dt><dd>{date(details.last_progress_at)}</dd></div>
            <div><dt>Worker lease expires</dt><dd>{details.job.lease_until ? date(details.job.lease_until) : "No active stage lease"}</dd></div>
          </dl>
          <p className="jobs-note">{details.estimate_basis}</p>
          <details className="job-identifiers"><summary>Job identifiers</summary><p>Job: <code>{details.job.id}</code></p><p>Project: <code>{details.job.project_id}</code></p><p>Snapshot version: {details.job.version}</p></details>
          <h3>Saved stages</h3><p>{details.job.completed_stages.length ? details.job.completed_stages.join(" → ") : "No completed stages yet."}</p>
          <div className="job-actions">
            {details.job.status === "queued" && details.kind === "generation" && <><p>Re-send this saved job to the worker without creating another generation.</p><button type="button" disabled={busy} onClick={() => void retry(details, false)}>Re-send to worker</button></>}
            {details.job.status === "succeeded" && <Link href={`/projects/${details.job.project_id}/editor`}>Play finished demo</Link>}
            {details.job.status === "succeeded" && details.kind === "presentation" && details.job.attempts < 3 && <><p>Rebuild from saved slides after a correction. Changed copy may require new narration; existing exports are kept.</p><button type="button" disabled={busy || (overview?.active_count ?? 0) > 0} onClick={() => void retry(details, true, true)}>Rebuild from saved slides</button></>}
            {details.job.status === "awaiting_approval" && <Link href={`/projects/${details.job.project_id}/storyboard`}>Review and approve storyboard</Link>}
            {(details.job.status === "awaiting_retry" || (details.kind !== "generation" && details.job.status === "failed")) && <><p>Retry reuses saved work. Unsaved provider calls may be charged again.</p><button type="button" disabled={busy || details.job.attempts >= 3 || (overview?.active_count ?? 0) > 0} onClick={() => void retry(details)}>Approve retry</button></>}
          </div>
          {actionError && <p role="alert" className="jobs-warning">{actionError}</p>}
          <h3>Activity log <span>({details.events.length} saved updates)</span></h3>
          {!details.events.length && <p className="jobs-note">Earlier activity was not recorded for this job. The current step above is its last saved status; new worker activity will appear here.</p>}
          <div className="job-log" tabIndex={0} role="region" aria-label="Timestamped activity log"><table><thead><tr><th>Time</th><th>Stage</th><th>Update</th></tr></thead><tbody>{[...details.events].reverse().map((event) => <tr key={event.sequence} className={`log-${event.level}`}><td><time dateTime={event.at}>{date(event.at)}</time></td><td>{event.stage}</td><td>{event.level === "error" && "Error: "}{event.message}</td></tr>)}</tbody></table></div>
        </section>}
      </div>}
    </div>
  </main>;
}
