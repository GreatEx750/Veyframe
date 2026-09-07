"use client";

import { demoGenerationResultSchema, generationJobSchema, projectSchema } from "@demodirector/contracts";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { ProductNavigation } from "@/components/product-navigation";

type FormValues = {
  title: string;
  websiteUrl: string;
  productSummary: string;
  demoMode: "presentation_demo" | "product_demo" | "spotlight_demo" | "short_demo";
  orientation: "landscape" | "vertical";
  audience: string;
  tone: string;
  duration: string;
  cta: string;
  brandKit: string;
};

type FormErrors = Partial<Record<keyof FormValues, string>>;

const initialValues: FormValues = {
  title: "",
  websiteUrl: "",
  productSummary: "",
  demoMode: "product_demo",
  orientation: "landscape",
  audience: "",
  tone: "professional",
  duration: "90",
  cta: "",
  brandKit: "default-brand",
};

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

function Toggle({ checked, describedBy, label, onChange }: { checked: boolean; describedBy?: string; label: string; onChange: () => void }) {
  return <button aria-checked={checked} aria-describedby={describedBy} aria-label={label} className={`toggle ${checked ? "is-on" : ""}`} onClick={onChange} role="switch" type="button"><span /></button>;
}

function ExampleVideo({ presentation }: { presentation: boolean }) {
  const [failed, setFailed] = useState(false);
  const mode = presentation ? "Presentation" : "Product";
  const source = `/examples/northstar-${presentation ? "presentation" : "product"}-20s`;

  return <>
    <video
      aria-label={`Northstar ${mode} Demo example`}
      className="studio-example-video"
      controls
      onError={() => setFailed(true)}
      onLoadedData={() => setFailed(false)}
      playsInline
      poster={`${source}.jpg`}
      preload="metadata"
      src={`${source}.mp4`}
    />
    {failed && <p className="example-error" role="alert">Example video couldn’t load. <a href={`${source}.mp4`}>Open example video</a> or refresh to try again.</p>}
  </>;
}

function validate(values: FormValues): FormErrors {
  const errors: FormErrors = {};
  if (!values.title.trim()) errors.title = "Add a title for your demo.";
  else if (values.title.trim().length > 120) errors.title = "Keep the title to 120 characters or fewer.";
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

export default function Studio() {
  const router = useRouter();
  const [values, setValues] = useState(initialValues);
  const [errors, setErrors] = useState<FormErrors>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [captions, setCaptions] = useState(true);
  const [autoZoom, setAutoZoom] = useState(true);
  const [firstFive, setFirstFive] = useState(false);
  const demoModeLabel = ({presentation_demo: "Presentation Demo", product_demo: "Product Demo", spotlight_demo: "Spotlight", short_demo: "Short"})[values.demoMode];
  const isPromo = values.demoMode === "spotlight_demo" || values.demoMode === "short_demo";
  const isPresentation = values.demoMode === "presentation_demo";

  function update<K extends keyof FormValues>(field: K, value: FormValues[K]) {
    setValues((current) => ({ ...current, [field]: value }));
    setErrors((current) => ({ ...current, [field]: undefined }));
  }

  function selectDemoMode(demoMode: FormValues["demoMode"]) {
    setValues((current) => ({
      ...current,
      demoMode,
      duration: ({presentation_demo: "120", product_demo: "90", spotlight_demo: "30", short_demo: "45"})[demoMode],
      orientation: "landscape",
    }));
    setErrors((current) => ({ ...current, demoMode: undefined, duration: undefined }));
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
          name: values.title.trim(),
          website_url: values.websiteUrl,
          product_summary: values.productSummary,
          demo_mode: values.demoMode,
          ...(isPromo ? { output_orientation: values.orientation } : {}),
          audience: values.audience,
          tone: values.tone,
          requested_duration_seconds: Number(values.duration),
          cta: values.cta,
          brand_kit_id: values.brandKit,
          zoom_enabled: autoZoom,
        }),
      });
      const body: unknown = await response.json();
      const project = projectSchema.safeParse(body);
      if (!response.ok || !project.success) throw new Error("Project could not be saved");
      setMessage("Starting a saved generation job. You may close this tab once it is queued.");
      const preview = values.demoMode === "presentation_demo" && firstFive;
      const generationResponse = await fetch(`/api/projects/${project.data.id}/${preview ? "generation/presentation-preview" : "generate"}`, {
        method: "POST",
      });
      const generationBody: unknown = await generationResponse.json();
      if (generationResponse.status === 409) throw new Error("generation_conflict");
      const job = generationJobSchema.safeParse(generationBody);
      if (generationResponse.ok && job.success) {
        router.replace(`/jobs?job=${encodeURIComponent(job.data.id)}`);
        return;
      }
      const generation = demoGenerationResultSchema.safeParse(generationBody);
      if (!generationResponse.ok || !generation.success) {
        throw new Error("Demo generation did not complete");
      }
      window.sessionStorage.setItem(
        `demodirector:export:${project.data.id}`,
        JSON.stringify(generation.data.export),
      );
      router.replace(`/projects/${project.data.id}/editor`);
    } catch (error) {
      setMessage(error instanceof Error && error.message === "generation_conflict"
        ? "Generation cannot start while another job is active, or this project already has output. Open Jobs to review its status."
        : "We couldn’t finish this demo. Open Jobs to review its status, then try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="studio-shell">
      <ProductNavigation active="studio" />

      <header aria-label="Project controls" className="studio-topbar">
        <a aria-label="Back to project library" className="topbar-back" href="/projects"><Icon name="arrow" /></a>
        <div className="project-title"><h1>Create {isPresentation ? "presentation" : "product"} demo</h1><span>New project — create to save</span></div>
      </header>

      <section className="configuration" id="studio">
        <header className="panel-heading"><h2>Demo setup</h2><p>Describe what to record and who it is for.</p></header>
        <form id="demo-form" noValidate onSubmit={submit}>
          <div className="form-section">
            <div className="form-section-title"><span>01</span><b>Source &amp; brief</b></div>
            <label htmlFor="demo-title">Demo title <span>Required</span></label>
            <div className={`input-wrap ${errors.title ? "has-error" : ""}`}>
              <input aria-describedby={errors.title ? "demo-title-error" : undefined} aria-invalid={Boolean(errors.title)} id="demo-title" maxLength={120} name="title" placeholder="e.g. Wikipedia — explore the Solar System" required type="text" value={values.title} onChange={(event) => update("title", event.target.value)} />
            </div>
            {errors.title && <p className="field-error" id="demo-title-error">{errors.title}</p>}
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
            <fieldset aria-describedby="demo-format-note" className="demo-format">
              <legend>Demo format</legend>
              <div className="demo-format-options">
                <label className={values.demoMode === "product_demo" ? "selected" : ""}>
                  <input aria-describedby="product-demo-description" aria-label="Product Demo" checked={values.demoMode === "product_demo"} name="demo-format" onChange={() => selectDemoMode("product_demo")} type="radio" value="product_demo" />
                  <span><b>Product Demo</b><span id="product-demo-description">A continuous walkthrough with narration and optional smooth zoom.</span></span>
                </label>
                <label className={values.demoMode === "presentation_demo" ? "selected" : ""}>
                  <input aria-describedby="presentation-demo-description" aria-label="Presentation Demo" checked={values.demoMode === "presentation_demo"} name="demo-format" onChange={() => selectDemoMode("presentation_demo")} type="radio" value="presentation_demo" />
                  <span><b>Presentation Demo</b><span id="presentation-demo-description">A presentation with your footage, narration, and project-specific callouts. Targets two minutes; can extend to 2:20 for natural narration.</span></span>
                </label>
              {(["spotlight_demo", "short_demo"] as const).map(mode => <label key={mode} className={values.demoMode === mode ? "selected" : ""}>
                <input aria-label={mode === "spotlight_demo" ? "Spotlight" : "Short"} checked={values.demoMode === mode} name="demo-format" onChange={() => selectDemoMode(mode)} type="radio" value={mode} />
                <span><b>{mode === "spotlight_demo" ? "Spotlight" : "Short"}</b><span>{mode === "spotlight_demo" ? "One feature in 30 seconds: hook, demonstration, and next step." : "A 45-second introduction with connected product highlights."}</span></span>
              </label>)}
              </div>
              <p className="demo-format-note" id="demo-format-note">All formats keep pointer movement and click feedback visible.</p>
              {isPresentation && <label className="presentation-preview-option"><input type="checkbox" checked={firstFive} onChange={(event) => setFirstFive(event.target.checked)} />Preview first five slides (about 1 minute)</label>}
              {isPresentation && firstFive && <p className="field-guidance">Use the authored slide templates with real recordings and word-highlighted subtitles. Local preview; the full presentation remains two minutes. Word timing is estimated.</p>}
            </fieldset>
            <label htmlFor="audience">Target Audience</label>
            <select id="audience" value={values.audience} onChange={(event) => update("audience", event.target.value)}><option value="">Select an audience</option><option>Marketing teams</option><option>Video creators</option><option>Product leaders</option><option>Sales engineers</option><option>Customer success teams</option><option>Founders and operators</option></select>
            {errors.audience && <p className="field-error">{errors.audience}</p>}
            <div className="split-fields">
              <div><label htmlFor="tone">Voice &amp; Tone</label><select id="tone" value={values.tone} onChange={(event) => update("tone", event.target.value)}><option value="professional">Professional &amp; confident</option><option value="friendly">Friendly &amp; conversational</option><option value="energetic">Energetic &amp; bold</option></select>{errors.tone && <p className="field-error">{errors.tone}</p>}</div>
              <div><label htmlFor="duration">Length</label><select disabled={isPresentation || isPromo} id="duration" value={values.duration} onChange={(event) => update("duration", event.target.value)}>{values.demoMode === "presentation_demo" ? <option value="120">~2 minutes · up to 2:20</option> : isPromo ? <option value={values.duration}>{values.duration} seconds</option> : <><option value="20">20 seconds</option><option value="30">30 seconds</option><option value="60">~1 minute</option><option value="90">1–2 minutes</option><option value="150">2–3 minutes</option></>}</select>{errors.duration && <p className="field-error">{errors.duration}</p>}</div>
            </div>
            <label htmlFor="cta">Call to Action</label><input id="cta" placeholder="Book a demo" value={values.cta} onChange={(event) => update("cta", event.target.value)} />
            {errors.cta && <p className="field-error">{errors.cta}</p>}
            <label htmlFor="brand-kit">Brand kit</label><select id="brand-kit" value={values.brandKit} onChange={(event) => update("brandKit", event.target.value)}><option value="default-brand">Veyframe Brand</option><option value="clean-slate">Clean Slate</option></select>
            {errors.brandKit && <p className="field-error">{errors.brandKit}</p>}
          </div>

          <small className="form-note">Create your demo when the brief is ready. You can edit the result afterward.</small>
        </form>
      </section>

      <section aria-label="Preview and settings" className="studio-workspace">
      <section aria-label="Studio preview" className="preview-panel">
        <div className="preview-toolbar">
          <div className="canvas-meta"><b>Example preview</b><span>{demoModeLabel}</span></div>
          <span className="preview-dimensions">{isPromo ? `${values.duration} seconds` : "20 seconds"}</span>
        </div>
        {isPromo ? <Image width={values.orientation === "vertical" ? 432 : 1024} height={values.orientation === "vertical" ? 768 : 576} alt={`${demoModeLabel} template preview`} style={{width:"100%",maxHeight:420,objectFit:"contain"}} src={`/examples/${values.demoMode === "spotlight_demo" ? "spotlight" : "short"}-${values.orientation}.png`} /> : <ExampleVideo key={values.demoMode} presentation={isPresentation} />}
        <p className="preview-explanation">{isPromo ? "Template specimen. Gemini generates the final copy from your brief and website evidence." : "20-second Northstar example · Press play to watch with sound. Your settings apply to the demo you create, not this saved example."}</p>
      </section>

      <aside aria-labelledby="director-settings" className="automation">
        <header className="panel-heading"><div><Icon name="spark" /><h2 id="director-settings">Director settings</h2></div><p>Fine-tune narration, captions, and camera direction.</p></header>
        <section className="control-card narration-settings">
          <div className="control-title"><b>Narration</b></div>
          <div className="narration-fields">
            <div><label htmlFor="voice-select">Voice</label><select id="voice-select"><option>Emma — Professional</option><option>Alex — Warm</option></select></div>
            <div><label htmlFor="language">Language</label><select id="language"><option>English (US)</option><option>English (UK)</option></select></div>
            <div className="narration-pace"><label htmlFor="pace">Pace <span>1.0×</span></label><input id="pace" max="1.4" min="0.7" step="0.1" type="range" defaultValue="1" /></div>
          </div>
        </section>
        <section className="control-card compact"><div className="control-title"><b>Captions</b><Toggle checked={captions} label="Captions" onChange={() => setCaptions((value) => !value)} /></div><label htmlFor="caption-style">Style</label><select id="caption-style"><option>Auto highlight</option><option>Minimal</option></select></section>
        <section className="control-card compact"><div className="control-title"><b>Smooth zoom</b><Toggle checked={autoZoom} describedBy="smooth-zoom-help" label="Smooth zoom" onChange={() => setAutoZoom((value) => !value)} /></div><p className="control-help" id="smooth-zoom-help">Follows important recorded interactions. Pointer movement and click indicators stay visible when zoom is off.</p><label htmlFor="intensity">Intensity <span>70%</span></label><input aria-label="Zoom intensity" disabled={!autoZoom} id="intensity" max="100" min="0" type="range" defaultValue="70" /></section>
        <section className="control-card compact"><div className="control-title"><b>Export</b></div><label htmlFor="output-format">Output format</label><select id="output-format" disabled={!isPromo} value={values.orientation} onChange={event => update("orientation", event.target.value as FormValues["orientation"])}><option value="landscape">Landscape · 2560 × 1440</option>{isPromo && <option value="vertical">Vertical · 1080 × 1920</option>}</select></section>
      </aside>
      </section>

      <section aria-label="Generation actions" className="studio-generation-bar">
        <div className="generation-summary">
          <b>{demoModeLabel}</b>
          <a href="/jobs">View generation jobs</a>
          <span>{isPresentation ? (firstFive ? "First five slides · about 1 minute" : "~2 minutes · up to 2:20") : `${values.duration} seconds`} · {autoZoom ? "Smooth zoom on" : "Zoom off"}</span>
          {message && <p role="status">{message}</p>}
          {!message && Object.values(errors).some(Boolean) && <p role="status">Check the highlighted fields in Demo setup.</p>}
        </div>
        <button className="topbar-primary" disabled={isSubmitting} form="demo-form" type="submit"><Icon name="spark" />{isSubmitting ? "Generating demo…" : "Create demo"}</button>
      </section>
    </main>
  );
}
