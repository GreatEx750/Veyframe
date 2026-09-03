"use client";

import { demoGenerationResultSchema, projectSchema } from "@demodirector/contracts";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { ProductNavigation } from "@/components/product-navigation";

type FormValues = {
  websiteUrl: string;
  productSummary: string;
  audience: string;
  tone: string;
  duration: string;
  cta: string;
  brandKit: string;
};

type FormErrors = Partial<Record<keyof FormValues, string>>;

const initialValues: FormValues = {
  websiteUrl: "",
  productSummary: "",
  audience: "",
  tone: "professional",
  duration: "90",
  cta: "",
  brandKit: "default-brand",
};

const scenes = [
  { name: "Intro", duration: "0:08" },
  { name: "Dashboard", duration: "0:24" },
  { name: "Insights", duration: "0:28" },
  { name: "Goals", duration: "0:22" },
  { name: "Team", duration: "0:20" },
  { name: "Outro", duration: "0:12" },
];

const iconPaths: Record<string, string> = {
  studio: "M7 5h10l3 4v10H4V9l3-4Zm2 5v4l4-2-4-2Z",
  projects: "M4 6h6l2 2h8v11H4V6Z",
  brand: "m12 3 8 8-8 10-8-10 8-8Zm0 5-3 3 3 4 3-4-3-3Z",
  voice: "M9 6a3 3 0 0 1 6 0v6a3 3 0 0 1-6 0V6Zm-3 5a6 6 0 0 0 12 0M12 17v4",
  publish: "m4 12 16-8-6 16-3-7-1Z",
  settings: "M12 8a4 4 0 1 1 0 8 4 4 0 0 1 0-8Zm0-5v3m0 12v3M3 12h3m12 0h3M5.6 5.6l2.1 2.1m8.6 8.6 2.1 2.1m0-12.8-2.1 2.1m-8.6 8.6-2.1 2.1",
  arrow: "m15 18-6-6 6-6",
  spark: "M12 3l1.2 4.1L17 9l-3.8 1.9L12 15l-1.2-4.1L7 9l3.8-1.9L12 3Z",
};

function Icon({ name }: { name: string }) {
  return <svg aria-hidden="true" className="icon" viewBox="0 0 24 24"><path d={iconPaths[name] ?? iconPaths.studio} /></svg>;
}

function Toggle({ checked, label, onChange }: { checked: boolean; label: string; onChange: () => void }) {
  return <button aria-label={label} aria-pressed={checked} className={`toggle ${checked ? "is-on" : ""}`} onClick={onChange} type="button"><span /></button>;
}

function validate(values: FormValues): FormErrors {
  const errors: FormErrors = {};
  try {
    const url = new URL(values.websiteUrl);
    if (!["http:", "https:"].includes(url.protocol)) errors.websiteUrl = "Enter a public HTTP or HTTPS URL.";
  } catch {
    errors.websiteUrl = "Enter a valid website URL.";
  }
  if (values.productSummary.trim().length < 20) errors.productSummary = "Describe the video in at least 20 characters.";
  if (!values.audience) errors.audience = "Choose a target audience.";
  if (!values.tone) errors.tone = "Choose a voice and tone.";
  if (!Number.isInteger(Number(values.duration)) || Number(values.duration) <= 0) errors.duration = "Choose a valid video length.";
  if (!values.cta.trim()) errors.cta = "Add a call to action.";
  if (!values.brandKit) errors.brandKit = "Choose a brand kit.";
  return errors;
}

export default function Home() {
  const router = useRouter();
  const [values, setValues] = useState(initialValues);
  const [errors, setErrors] = useState<FormErrors>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [captions, setCaptions] = useState(true);
  const [autoZoom, setAutoZoom] = useState(true);
  const [device, setDevice] = useState("Desktop");
  const [selectedScene, setSelectedScene] = useState(1);
  const [isPlaying, setIsPlaying] = useState(false);

  function update<K extends keyof FormValues>(field: K, value: FormValues[K]) {
    setValues((current) => ({ ...current, [field]: value }));
    setErrors((current) => ({ ...current, [field]: undefined }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextErrors = validate(values);
    setErrors(nextErrors);
    setMessage(null);
    if (Object.keys(nextErrors).length > 0) return;
    setIsSubmitting(true);
    setMessage("Creating the project…");
    try {
      const response = await fetch("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          website_url: values.websiteUrl,
          product_summary: values.productSummary,
          audience: values.audience,
          tone: values.tone,
          requested_duration_seconds: Number(values.duration),
          cta: values.cta,
          brand_kit_id: values.brandKit,
        }),
      });
      const body: unknown = await response.json();
      const project = projectSchema.safeParse(body);
      if (!response.ok || !project.success) throw new Error("Project could not be saved");
      setMessage("Building your first cut — inspecting, recording, narrating, and rendering. Keep this tab open.");
      const generationResponse = await fetch(`/api/projects/${project.data.id}/generate`, {
        method: "POST",
      });
      const generationBody: unknown = await generationResponse.json();
      const generation = demoGenerationResultSchema.safeParse(generationBody);
      if (!generationResponse.ok || !generation.success) {
        throw new Error("Demo generation did not complete");
      }
      window.sessionStorage.setItem(
        `demodirector:export:${project.data.id}`,
        JSON.stringify(generation.data.export),
      );
      router.replace(`/projects/${project.data.id}/editor`);
    } catch {
      setMessage("We couldn’t finish this demo. Open Projects to review its status, then try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="studio-shell">
      <ProductNavigation active="studio" />

      <header aria-label="Project controls" className="studio-topbar">
        <a aria-label="Back to project library" className="topbar-back" href="/projects"><Icon name="arrow" /></a>
        <div className="project-title"><h1>Create product demo</h1><span><i /> Draft saved locally</span></div>
        <a className="topbar-action" href="#studio">Preview</a>
        <button className="topbar-primary" disabled={isSubmitting} form="demo-form" type="submit"><Icon name="spark" />{isSubmitting ? "Generating demo…" : "Create demo"}</button>
      </header>

      <section className="configuration" id="studio">
        <header className="panel-heading"><h2>Project tools</h2><p>Give the director enough context to build your first cut.</p></header>
        <form id="demo-form" noValidate onSubmit={submit}>
          <div className="form-section">
            <div className="form-section-title"><span>01</span><b>Source &amp; brief</b></div>
            <label htmlFor="website-url">Website URL <span>Required</span></label>
            <div className={`input-wrap ${errors.websiteUrl ? "has-error" : ""}`}><input id="website-url" placeholder="https://yourproduct.com" type="url" value={values.websiteUrl} onChange={(event) => update("websiteUrl", event.target.value)} /><i className="status-dot" /></div>
            {errors.websiteUrl && <p className="field-error">{errors.websiteUrl}</p>}
            <label htmlFor="video-brief">Describe your video <span>{values.productSummary.length}/500</span></label>
            <p className="field-guidance" id="video-brief-guidance">Mention the story, product moments, and ending you want. You can write naturally.</p>
            <textarea aria-describedby="video-brief-guidance" aria-invalid={Boolean(errors.productSummary)} className="video-brief-input" id="video-brief" maxLength={500} placeholder="Create a concise launch video that opens with the dashboard, shows how teams automate reporting, and ends with an invitation to start a trial." rows={7} value={values.productSummary} onChange={(event) => update("productSummary", event.target.value)} />
            {errors.productSummary && <p className="field-error">{errors.productSummary}</p>}
          </div>

          <div className="form-section">
            <div className="form-section-title"><span>02</span><b>Direction</b></div>
            <label htmlFor="audience">Target Audience</label>
            <select id="audience" value={values.audience} onChange={(event) => update("audience", event.target.value)}><option value="">Select an audience</option><option>Product leaders</option><option>Sales engineers</option><option>Customer success teams</option><option>Founders and operators</option></select>
            {errors.audience && <p className="field-error">{errors.audience}</p>}
            <div className="split-fields">
              <div><label htmlFor="tone">Voice &amp; Tone</label><select id="tone" value={values.tone} onChange={(event) => update("tone", event.target.value)}><option value="professional">Professional &amp; confident</option><option value="friendly">Friendly &amp; conversational</option><option value="energetic">Energetic &amp; bold</option></select>{errors.tone && <p className="field-error">{errors.tone}</p>}</div>
              <div><label htmlFor="duration">Length</label><select id="duration" value={values.duration} onChange={(event) => update("duration", event.target.value)}><option value="20">20 seconds</option><option value="60">~1 minute</option><option value="90">1–2 minutes</option><option value="150">2–3 minutes</option></select>{errors.duration && <p className="field-error">{errors.duration}</p>}</div>
            </div>
            <label htmlFor="cta">Call to Action</label><input id="cta" placeholder="Book a demo" value={values.cta} onChange={(event) => update("cta", event.target.value)} />
            {errors.cta && <p className="field-error">{errors.cta}</p>}
            <label htmlFor="brand-kit">Brand kit</label><select id="brand-kit" value={values.brandKit} onChange={(event) => update("brandKit", event.target.value)}><option value="default-brand">DemoDirector Brand</option><option value="clean-slate">Clean Slate</option></select>
            {errors.brandKit && <p className="field-error">{errors.brandKit}</p>}
          </div>

          <button className="gradient-button" disabled={isSubmitting} type="submit"><Icon name="spark" />{isSubmitting ? "Generating demo…" : "Create demo"}</button>
          <small className="form-note">One click creates the storyboard, recordings, voiceover, captions, camera moves, timeline, and MP4.</small>
          {message && <p className={`form-message ${isSubmitting ? "progress" : "error"}`} role="status">{message}</p>}
        </form>
      </section>

      <section aria-label="Studio preview" className="preview-panel">
        <div className="preview-toolbar">
          <div className="canvas-meta"><b>Canvas</b><span>{scenes[selectedScene].name}</span></div>
          <div className="device-tabs" role="group" aria-label="Preview device">
            {["Desktop", "Tablet", "Mobile"].map((item) => <button aria-pressed={device === item} className={device === item ? "selected" : ""} key={item} onClick={() => setDevice(item)} type="button">{item}</button>)}
          </div>
          <select aria-label="Preview resolution" className="resolution" defaultValue="1280 × 720"><option>1280 × 720</option><option>1920 × 1080</option></select>
        </div>
        <div className={`browser device-${device.toLowerCase()}`}>
          <div className="browser-bar"><span className="browser-dots"><i /><i /><i /></span><div className="address">app.ecotrack.com/dashboard</div><span className="secure-status">Secure</span></div>
          <div className="mock-app"><aside><div className="mock-logo"><i /> EcoTrack</div>{["Overview", "Dashboard", "Insights", "Goals", "Reports", "Team", "Settings"].map((item, index) => <span className={index === 0 ? "selected" : ""} key={item}>{item}</span>)}</aside><div className="mock-content"><header><div><h2>Overview</h2><p>Good morning, Alex</p></div><span>May 1 – May 31, 2026</span></header><div className="stat-grid"><article><small>Total carbon saved</small><b>128.6</b><em>↑ 18% this month</em></article><article><small>Impact score</small><b>78</b><em>↑ 12 points</em></article><article><small>Active goals</small><b>5<span>/8</span></b><em>● On track</em></article></div><div className="chart-grid"><article><small>Emissions breakdown</small><div className="donut"><b>128.6</b></div></article><article><small>Emissions over time</small><div className="line-chart"><i /><i /><i /><i /><i /><i /></div></article></div></div></div>
          <div className="caption-preview">This is your overview dashboard, with every signal in one place.</div>
          <div className="player-controls"><button aria-label={isPlaying ? "Pause preview" : "Play preview"} onClick={() => setIsPlaying((value) => !value)} type="button">{isPlaying ? "Ⅱ" : "▶"}</button><b>0:12 / 2:35</b><div className="progress"><i /></div><span>CC</span><span>1×</span><span>⛶</span></div>
        </div>
      </section>

      <aside aria-labelledby="director-settings" className="automation">
        <header className="panel-heading"><div><Icon name="spark" /><h2 id="director-settings">Director settings</h2></div><p>Fine-tune narration, captions, and camera direction.</p></header>
        <section className="control-card"><div className="control-title"><b>Narration</b><span>01</span></div><label htmlFor="voice-select">Voice</label><select id="voice-select"><option>Emma — Professional</option><option>Alex — Warm</option></select><label htmlFor="pace">Pace <span>1.0×</span></label><input id="pace" max="1.4" min="0.7" step="0.1" type="range" defaultValue="1" /><label htmlFor="language">Language</label><select id="language"><option>English (US)</option><option>English (UK)</option></select></section>
        <section className="control-card compact"><div className="control-title"><b>Captions</b><Toggle checked={captions} label="Toggle captions" onChange={() => setCaptions((value) => !value)} /></div><label htmlFor="caption-style">Style</label><select id="caption-style"><option>Auto highlight</option><option>Minimal</option></select></section>
        <section className="control-card compact"><div className="control-title"><b>Auto zoom</b><Toggle checked={autoZoom} label="Toggle auto zoom" onChange={() => setAutoZoom((value) => !value)} /></div><label htmlFor="intensity">Intensity <span>70%</span></label><input id="intensity" max="100" min="0" type="range" defaultValue="70" /></section>
        <section className="control-card compact"><div className="control-title"><b>Export</b><span>04</span></div><label htmlFor="output-format">Output format</label><select id="output-format"><option>Landscape · 1080p</option><option>Landscape · 720p</option></select></section>
        <section className="ready-card"><div><span>{scenes.length} scenes</span><span>{Math.ceil(Number(values.duration) / 60)} min</span></div><button className="gradient-button" disabled={isSubmitting} form="demo-form" type="submit"><Icon name="spark" />{isSubmitting ? "Generating demo…" : "Create Demo"}</button></section>
      </aside>

      <section aria-label="Project timeline" className="timeline">
        <div className="timeline-head"><div><b>Timeline</b><span>00:12:18</span></div><div className="timeline-tools"><button aria-label={isPlaying ? "Pause timeline" : "Play timeline"} onClick={() => setIsPlaying((value) => !value)} type="button">{isPlaying ? "Ⅱ" : "▶"}</button><span>100%</span></div></div>
        <div className="timeline-ruler"><span>0s</span><span>15s</span><span>30s</span><span>45s</span><span>1:00</span><span>1:15</span><span>1:30</span></div><div className="playhead"><i /></div>
        <div className="track scene-track"><b>Scenes</b><div className="timeline-scenes">{scenes.map((scene, index) => <button aria-pressed={selectedScene === index} className={`scene-thumb thumb-${index}`} key={scene.name} onClick={() => setSelectedScene(index)} type="button"><span>{index + 1} · {scene.name}</span><time>{scene.duration}</time></button>)}</div></div>
        <div className="track caption-track"><b>Captions</b><div className="caption-blocks"><span>Meet your product…</span><span>This is your overview dashboard.</span><span>See the insights that matter.</span><span>Turn signals into action.</span></div></div>
        <div className="track audio-track"><b>Voiceover</b><div className="waveform">{Array.from({ length: 68 }, (_, index) => <i key={index} style={{ height: `${8 + ((index * 13) % 22)}px` }} />)}</div></div>
      </section>
    </main>
  );
}
