"use client";
import { storyboardEvidenceSchema, type StoryboardEvidence } from "@demodirector/contracts";
import Link from "next/link";
import { useEffect, useState } from "react";

export function EvidenceApproval({ projectId, version, disabled = false }: { projectId: string; version: number; disabled?: boolean }) {
  const [evidence, setEvidence] = useState<StoryboardEvidence | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const base = `/api/projects/${encodeURIComponent(projectId)}/quality-api`;
  useEffect(() => {
    let active = true;
    void fetch(`${base}/evidence`, { cache: "no-store" }).then(async (response) => {
      const body: unknown = await response.json();
      if (!response.ok) throw new Error("Evidence could not be loaded. Reload after saving the storyboard.");
      const parsed = storyboardEvidenceSchema.parse(body);
      if (active) { setEvidence(parsed); setAcknowledged(false); setError(""); }
    }).catch((failure: unknown) => { if (active) setError(failure instanceof Error ? failure.message : "Evidence unavailable"); });
    return () => { active = false; };
  }, [base, version]);
  async function approve() {
    if (!evidence) return;
    setBusy(true); setError("");
    try {
      const response = await fetch(`${base}/storyboard-approval`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ expected_version: evidence.storyboard_version, fingerprint: evidence.fingerprint, acknowledge_unverified: acknowledged }) });
      const body: unknown = await response.json();
      if (!response.ok) throw new Error(typeof body === "object" && body && "detail" in body ? String(body.detail) : "Approval could not be saved");
      setEvidence(storyboardEvidenceSchema.parse(body));
    } catch (failure) { setError(failure instanceof Error ? failure.message : "Approval unavailable"); }
    finally { setBusy(false); }
  }
  return <section className="sources-section" aria-label="Narration evidence and approval">
    <h2>Narration evidence</h2><p>Check the script before recording. Source links are attribution, not a guarantee that a claim is true.</p>
    {error && <p role="alert">{error}</p>}
    {evidence && <>
      {evidence.claims.map((claim) => <article className="source-item" key={claim.id}>
        <p>{claim.text}</p><p>{claim.status.replaceAll("_", " ")} · {claim.explanation}</p>
        <ul>{claim.source_ids.map((id) => { const source = evidence.sources.find((s) => s.id === id)!; return <li key={id}><a href={source.url} target="_blank" rel="noreferrer">{source.title || source.url}</a> ({source.source_type.replaceAll("_", " ")})<blockquote>{source.snippet}</blockquote></li>; })}</ul>
      </article>)}
      <p>{evidence.unverified_count} statements require your judgment.</p>
      {disabled && <p>Save your changes before approving.</p>}
      {!evidence.approved && <>
        {evidence.unverified_count > 0 && <label><input type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} />I reviewed the unverified statements and accept responsibility for their accuracy.</label>}
        <button type="button" disabled={disabled || busy || evidence.storyboard_version !== version || (evidence.unverified_count > 0 && !acknowledged)} onClick={() => void approve()}>{busy ? "Saving approval…" : "Approve this storyboard and continue generation"}</button>
      </>}
      {evidence.approved && <p>Saved storyboard v{evidence.storyboard_version} approved. Changing its content or evidence invalidates approval.</p>}
      <Link href={`/projects/${projectId}/generation`}>Open generation progress</Link>
    </>}
  </section>;
}
