"use client";

import { useEffect, useRef, useState } from "react";
import { z } from "zod";
import styles from "./youtube-upload.module.css";

const connectionSchema = z.object({ enabled: z.boolean(), configured: z.boolean(), connected: z.boolean(), channel_title: z.string().nullable(), message: z.string() });
const uploadSchema = z.object({ id: z.string(), export_id: z.string(), status: z.enum(["queued", "uploading", "succeeded", "failed", "unknown"]), progress: z.number().int().min(0).max(100), message: z.string(), video_id: z.string().regex(/^[A-Za-z0-9_-]{11}$/).nullable() });
type Upload = z.infer<typeof uploadSchema>;

async function api(path: string, body?: object): Promise<unknown> {
  const response = await fetch(`/api/youtube/${path}`, {
    method: body ? "POST" : "GET", cache: "no-store",
    headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined,
  });
  const data: unknown = await response.json();
  if (!response.ok) {
    const error = z.object({ detail: z.string() }).safeParse(data);
    throw new Error(error.success ? error.data.detail : "YouTube request failed. Check your connection and try again.");
  }
  return data;
}

export function YouTubeUpload({ projectId, exportId, title: initialTitle }: { projectId: string; exportId: string; title: string }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [open, setOpen] = useState(false);
  const [connection, setConnection] = useState<z.infer<typeof connectionSchema> | null>(null);
  const [upload, setUpload] = useState<Upload | null>(null);
  const [title, setTitle] = useState(initialTitle);
  const [description, setDescription] = useState("");
  const [audience, setAudience] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const storageKey = `veyframe:youtube:${projectId}:${exportId}`;
  const running = upload?.status === "queued" || upload?.status === "uploading";

  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("youtube") !== "connected") return;
    const timer = window.setTimeout(() => setOpen(true), 0);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (!open) return;
    dialog.current?.showModal();
    let active = true;
    void api("status").then((data) => {
      if (active) setConnection(connectionSchema.parse(data));
    }).catch(() => { if (active) setError("Could not load the YouTube connection. Check the service and sign in again if needed."); });
    const savedId = sessionStorage.getItem(storageKey);
    if (savedId && /^[\w-]+$/.test(savedId)) {
      void api(`projects/${projectId}/uploads/${savedId}`).then((data) => {
        if (active) setUpload(uploadSchema.parse(data));
      }).catch(() => { if (active) setError("Previous upload status is unavailable. Check YouTube Studio before uploading again; the service may have restarted."); });
    }
    return () => { active = false; };
  }, [open, storageKey, projectId]);

  useEffect(() => {
    if (!running || !upload) return;
    let active = true;
    const timer = window.setInterval(() => {
      void api(`projects/${projectId}/uploads/${upload.id}`).then((data) => {
        if (active) { setUpload(uploadSchema.parse(data)); setError(""); }
      }).catch(() => { if (active) setError("Progress connection interrupted. Do not start another upload; check YouTube Studio if this persists."); });
    }, 1500);
    return () => { active = false; window.clearInterval(timer); };
  }, [running, upload, projectId]);

  async function connect() {
    setBusy(true); setError("");
    try {
      const { url } = z.object({ url: z.string().url() }).parse(await api("connect", { project_id: projectId }));
      const target = new URL(url);
      if (target.origin !== "https://accounts.google.com" || target.pathname !== "/o/oauth2/v2/auth") throw new Error("Invalid Google authorization destination.");
      window.location.assign(url);
    } catch (failure) { setError(failure instanceof Error ? failure.message : "Could not connect YouTube."); setBusy(false); }
  }

  async function disconnect() {
    setBusy(true); setError("");
    try { await api("disconnect", {}); setConnection(connectionSchema.parse(await api("status"))); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "Could not disconnect YouTube."); }
    finally { setBusy(false); }
  }

  async function start(event: React.FormEvent) {
    event.preventDefault();
    if (!connection?.connected || !confirmed || !audience || !title.trim() || busy || upload) return;
    setBusy(true); setError("");
    try {
      const result = uploadSchema.parse(await api(`projects/${projectId}/uploads`, {
        export_id: exportId, title: title.trim(), description: description.trim(), made_for_kids: audience === "yes", confirmed: true,
      }));
      setUpload(result);
      sessionStorage.setItem(storageKey, result.id);
    } catch (failure) { setError(failure instanceof Error ? failure.message : "Upload could not be started."); }
    finally { setBusy(false); }
  }

  return <>
    <button className="editor-preview-link" type="button" onClick={() => { setError(""); setOpen(true); }}>Upload to YouTube</button>
    <dialog ref={dialog} className={styles.dialog} aria-labelledby="youtube-title" onClose={() => setOpen(false)}>
      <div className={styles.heading}><h2 id="youtube-title">Upload to YouTube</h2><button type="button" aria-label="Close YouTube upload" onClick={() => dialog.current?.close()}>×</button></div>
      <p>This uploads the saved MP4 privately. It does not publish publicly or start a new generation.</p>
      {!connection && !error && <p role="status">Checking connection…</p>}
      {connection && <>
        <p>{connection.message}</p>
        {(!connection.enabled || !connection.configured) && <p>YouTube upload is not configured for this Veyframe service. Ask the service owner to enable the YouTube Data API and Google OAuth connection.</p>}
        {connection.enabled && connection.configured && !connection.connected && <button type="button" disabled={busy} onClick={() => void connect()}>Connect YouTube</button>}
        {connection.connected && <>
          <div className={styles.channel}><span>Channel: <strong>{connection.channel_title}</strong></span><button type="button" disabled={busy || running} onClick={() => void disconnect()}>Disconnect</button></div>
          {!upload && <form onSubmit={(event) => void start(event)}>
            <label htmlFor="youtube-video-title">Video title</label>
            <input id="youtube-video-title" required maxLength={100} value={title} onChange={(event) => setTitle(event.target.value)} />
            <label htmlFor="youtube-description">Description</label>
            <textarea id="youtube-description" maxLength={5000} rows={3} value={description} onChange={(event) => setDescription(event.target.value)} />
            <label htmlFor="youtube-audience">Is this video made for kids?</label>
            <select id="youtube-audience" required value={audience} onChange={(event) => setAudience(event.target.value)}><option value="">Choose an audience</option><option value="no">No, not made for kids</option><option value="yes">Yes, made for kids</option></select>
            <label className={styles.confirm}><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} required />I have permission to upload this video to the channel shown above.</label>
            <button type="submit" disabled={busy || !confirmed || !audience || !title.trim()}>{busy ? "Starting upload…" : "Confirm private upload"}</button>
          </form>}
        </>}
      </>}
      {upload && <div role="status" className={styles.result}>
        <p>{upload.message}</p>
        {running && <><progress aria-label="YouTube upload progress" max={100} value={upload.progress} /><span>{upload.progress}% transferred</span></>}
        {upload.video_id && <a href={`https://www.youtube.com/watch?v=${upload.video_id}`} target="_blank" rel="noreferrer">Open video on YouTube</a>}
        {(upload.status === "failed" || upload.status === "unknown") && <a href="https://studio.youtube.com/" target="_blank" rel="noreferrer">Check YouTube Studio</a>}
      </div>}
      {error && <p role="alert">{error}</p>}
      <p className={styles.note}>Reconnect after a service restart or deployment. Upload history is temporary. No automatic retries. Public uploads require YouTube approval for the API project.</p>
    </dialog>
  </>;
}
