"use client";

import {
  editPlanSchema,
  attentionPlanSchema,
  generationTraceSchema,
  motionDirectionPlanSchema,
  styleDirectionPlanSchema,
  longFormVideoPlanSchema,
  chapterCheckpointsSchema,
  chapterCheckpointSchema,
  projectSchema,
  sourceContributionMapSchema,
  timelineHistoryStateSchema,
  timelineSchema,
  videoExportSchema,
  type EditPlan,
  type AttentionPlan,
  type EditOperation,
  type Project,
  type GenerationTrace,
  type MotionDirectionPlan,
  type StyleDirectionPlan,
  type VisualVariantId,
  type LongFormVideoPlan,
  type ChapterCheckpoint,
  type SceneClip,
  type SourceContributionMap,
  type Timeline,
  type VideoExport,
  type ZoomClip,
} from "@demodirector/contracts";
import Link from "next/link";
import { VideoQuality } from "./video-quality";
import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";

import {
  isJudgeDemoProject,
  JUDGE_DEMO_VIDEO_URL,
  judgeDemoExport,
  judgeDemoTimeline,
} from "@/lib/judge-demo";

type TimelineEditorProps = {
  projectId: string;
  initialProject?: Project;
  initialTimeline?: Timeline;
};

type EditorMode = "setup" | "sources" | "quality" | "layout" | "style" | "story" | "cut" | "zoom" | "callouts" | "overlay" | "captions" | "audio" | "adjust";
type PresentationTemplate = Timeline["presentation"]["template"];

const editorModes: Array<{ id: EditorMode; label: string }> = [
  { id: "setup", label: "Setup" },
  { id: "sources", label: "Sources" },
  { id: "quality", label: "Quality" },
  { id: "layout", label: "Layout" },
  { id: "style", label: "Style" },
  { id: "story", label: "Story" },
  { id: "cut", label: "Cut" },
  { id: "zoom", label: "Zoom" },
  { id: "callouts", label: "Callouts" },
  { id: "overlay", label: "Overlay" },
  { id: "captions", label: "Captions" },
  { id: "audio", label: "Audio" },
  { id: "adjust", label: "Adjust" },
];

const storageKey = (projectId: string) => `demodirector:timeline:${projectId}`;
const exportStorageKey = (projectId: string) => `demodirector:export:${projectId}`;
const exportStaleKey = (projectId: string) => `demodirector:export-stale:${projectId}`;

function loadGeneratedExport(projectId: string): VideoExport | null {
  if (typeof window === "undefined") return null;
  try {
    const saved = window.sessionStorage.getItem(exportStorageKey(projectId));
    if (!saved) return null;
    const parsed = videoExportSchema.safeParse(JSON.parse(saved) as unknown);
    return parsed.success ? parsed.data : null;
  } catch {
    return null;
  }
}

function loadExportStale(projectId: string) {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(exportStaleKey(projectId)) === "true";
  } catch {
    return false;
  }
}

function loadTimeline(projectId: string, initialTimeline?: Timeline): Timeline | null {
  if (typeof window !== "undefined") {
    try {
      const saved = window.localStorage.getItem(storageKey(projectId));
      if (saved) {
        const parsed = timelineSchema.safeParse(JSON.parse(saved) as unknown);
        if (parsed.success) return parsed.data;
      }
    } catch { /* Ignore corrupt or unavailable browser storage. */ }
  }
  return initialTimeline ?? null;
}

function shiftTime(startMs: number, endMs: number, boundary: number, delta: number) {
  return startMs >= boundary
    ? { start_ms: startMs + delta, end_ms: endMs + delta }
    : { start_ms: startMs, end_ms: endMs };
}

export function deleteSceneFromTimeline(timeline: Timeline, sceneId: string): Timeline {
  if (timeline.demo_mode === "presentation_demo") return timeline;
  const scene = timeline.scene_clips.find((clip) => clip.scene_id === sceneId);
  if (!scene || timeline.scene_clips.length <= 1) return timeline;
  const removedDuration = scene.end_ms - scene.start_ms;
  const shift = <T extends { start_ms: number; end_ms: number }>(clip: T): T => ({
    ...clip,
    ...shiftTime(clip.start_ms, clip.end_ms, scene.end_ms, -removedDuration),
  });
  return timelineSchema.parse({
    ...timeline,
    duration_ms: timeline.duration_ms - removedDuration,
    scene_clips: timeline.scene_clips
      .filter((clip) => clip.scene_id !== sceneId)
      .map(shift),
    caption_clips: timeline.caption_clips
      .filter((clip) => clip.scene_id !== sceneId)
      .map(shift),
    audio_clips: timeline.audio_clips
      .filter((clip) => clip.scene_id !== sceneId)
      .map(shift),
    zoom_clips: timeline.zoom_clips
      .filter((clip) => clip.end_ms <= scene.start_ms || clip.start_ms >= scene.end_ms)
      .map(shift),
    cursor_events: timeline.cursor_events
      .filter((event) => event.scene_id !== sceneId && (event.timestamp_ms < scene.start_ms || event.timestamp_ms >= scene.end_ms))
      .map((event) => event.timestamp_ms >= scene.end_ms
        ? { ...event, timestamp_ms: event.timestamp_ms - removedDuration }
        : event),
  });
}

export function duplicateSceneInTimeline(timeline: Timeline, sceneId: string): Timeline {
  if (timeline.demo_mode === "presentation_demo") return timeline;
  const scene = timeline.scene_clips.find((clip) => clip.scene_id === sceneId);
  if (!scene) return timeline;
  const duration = scene.end_ms - scene.start_ms;
  const duplicateId = `${scene.scene_id}-copy`;
  const shiftedScenes = timeline.scene_clips.map((clip) =>
    clip.start_ms >= scene.end_ms
      ? { ...clip, start_ms: clip.start_ms + duration, end_ms: clip.end_ms + duration }
      : clip,
  );
  const duplicate: SceneClip = {
    ...scene,
    id: `${scene.id}-copy`,
    scene_id: duplicateId,
    start_ms: scene.end_ms,
    end_ms: scene.end_ms + duration,
  };
  const shiftedCursorEvents = timeline.cursor_events.map((event) =>
    event.timestamp_ms >= scene.end_ms
      ? { ...event, timestamp_ms: event.timestamp_ms + duration }
      : event,
  );
  const duplicateCursorEvents = timeline.cursor_events
    .filter((event) => event.scene_id === sceneId)
    .map((event) => ({
      ...event,
      scene_id: duplicateId,
      timestamp_ms: event.timestamp_ms + duration,
    }));
  return timelineSchema.parse({
    ...timeline,
    duration_ms: timeline.duration_ms + duration,
    scene_clips: [...shiftedScenes, duplicate].sort((a, b) => a.start_ms - b.start_ms),
    caption_clips: timeline.caption_clips.map((clip) =>
      clip.start_ms >= scene.end_ms
        ? { ...clip, start_ms: clip.start_ms + duration, end_ms: clip.end_ms + duration }
        : clip,
    ),
    zoom_clips: timeline.zoom_clips.map((clip) =>
      clip.start_ms >= scene.end_ms
        ? { ...clip, start_ms: clip.start_ms + duration, end_ms: clip.end_ms + duration }
        : clip,
    ),
    cursor_events: [...shiftedCursorEvents, ...duplicateCursorEvents]
      .sort((a, b) => a.timestamp_ms - b.timestamp_ms),
    audio_clips: timeline.audio_clips.map((clip) =>
      clip.start_ms >= scene.end_ms
        ? { ...clip, start_ms: clip.start_ms + duration, end_ms: clip.end_ms + duration }
        : clip,
    ),
  });
}

export function splitSceneInTimeline(
  timeline: Timeline,
  sceneId: string,
  splitAtMs: number,
): Timeline {
  if (timeline.demo_mode === "presentation_demo") return timeline;
  const scene = timeline.scene_clips.find((clip) => clip.scene_id === sceneId);
  if (!scene || splitAtMs <= scene.start_ms || splitAtMs >= scene.end_ms) return timeline;
  const first = { ...scene, end_ms: splitAtMs };
  const second: SceneClip = {
    ...scene,
    id: `${scene.id}-split`,
    scene_id: `${scene.scene_id}-split`,
    start_ms: splitAtMs,
    source_start_ms: scene.source_start_ms + (splitAtMs - scene.start_ms),
  };
  return timelineSchema.parse({
    ...timeline,
    scene_clips: timeline.scene_clips.flatMap((clip) =>
      clip.id === scene.id ? [first, second] : [clip],
    ),
  });
}

export function TimelineEditor({ projectId, initialProject, initialTimeline }: TimelineEditorProps) {
  const [generatedExport] = useState(() => loadGeneratedExport(projectId));
  const [exportStale, setExportStale] = useState(() => loadExportStale(projectId));
  const [project, setProject] = useState<Project | null>(initialProject ?? null);
  const [timeline, setTimeline] = useState(() => loadTimeline(projectId, initialTimeline));
  const [selectedSceneId, setSelectedSceneId] = useState(timeline?.scene_clips[0]?.scene_id ?? null);
  const [selectedZoomId, setSelectedZoomId] = useState(timeline?.zoom_clips[0]?.id ?? null);
  const [activeMode, setActiveMode] = useState<EditorMode>("zoom");
  const [playheadMs, setPlayheadMs] = useState(0);
  const [status, setStatus] = useState(
    generatedExport ? `${generatedExport.quality} export ready to download` : initialTimeline ? "Timeline ready" : "Loading project timeline",
  );
  const [instruction, setInstruction] = useState("");
  const [proposal, setProposal] = useState<EditPlan | null>(null);
  const [planning, setPlanning] = useState(false);
  const [timelineVersion, setTimelineVersion] = useState(0);
  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [savingZoom, setSavingZoom] = useState(false);
  const [videoExport, setVideoExport] = useState<VideoExport | null>(generatedExport);
  const [sourceMap, setSourceMap] = useState<SourceContributionMap | null>(null);
  const [generationTrace, setGenerationTrace] = useState<GenerationTrace | null>(null);
  const [motionPlan, setMotionPlan] = useState<MotionDirectionPlan | null>(null);
  const [attentionPlan, setAttentionPlan] = useState<AttentionPlan | null>(null);
  const [stylePlan, setStylePlan] = useState<StyleDirectionPlan | null>(null);
  const [selectedStyleSceneId, setSelectedStyleSceneId] = useState<string | null>(null);
  const [savingStyle, setSavingStyle] = useState(false);
  const [longFormPlan, setLongFormPlan] = useState<LongFormVideoPlan | null>(null);
  const [chapterCheckpoints, setChapterCheckpoints] = useState<ChapterCheckpoint[]>([]);
  const [retryingChapterId, setRetryingChapterId] = useState<string | null>(null);
  const [selectedCalloutId, setSelectedCalloutId] = useState<string | null>(null);
  const [savingCallout, setSavingCallout] = useState(false);
  const [traceError, setTraceError] = useState<string | null>(null);
  const [selectedContributionId, setSelectedContributionId] = useState<string | null>(null);
  const [sourcesLoading, setSourcesLoading] = useState(false);
  const [sourcesError, setSourcesError] = useState<string | null>(null);
  const [previewPlaying, setPreviewPlaying] = useState(false);
  const [loadingProject, setLoadingProject] = useState(!initialTimeline);
  const [loadError, setLoadError] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const focusDragRef = useRef(false);

  useEffect(() => {
    if (initialTimeline) return;
    let active = true;

    void Promise.all([
      fetch(`/api/projects/${projectId}`, { cache: "no-store" }),
      fetch(`/api/projects/${projectId}/timeline`, { cache: "no-store" }),
      fetch(`/api/projects/${projectId}/exports/latest`, { cache: "no-store" }),
    ]).then(async ([projectResponse, timelineResponse, exportResponse]) => {
      const parsedProject = projectSchema.safeParse(await projectResponse.json());
      if (!projectResponse.ok || !parsedProject.success) throw new Error("Project not found");
      if (!active) return;
      setProject(parsedProject.data);

      const exportIsStale = loadExportStale(projectId);
      setExportStale(exportIsStale);
      let savedExport = generatedExport;
      if (isJudgeDemoProject(projectId)) {
        savedExport = judgeDemoExport(projectId);
        setVideoExport(savedExport);
      } else if (exportResponse.ok) {
        const parsedExport = videoExportSchema.safeParse(await exportResponse.json());
        if (parsedExport.success) {
          savedExport = parsedExport.data;
          setVideoExport(parsedExport.data);
        }
      }

      if (timelineResponse.ok) {
        const parsedTimeline = timelineHistoryStateSchema.safeParse(await timelineResponse.json());
        if (!parsedTimeline.success) throw new Error("Invalid project timeline");
        const loadedTimeline = parsedTimeline.data.current.timeline;
        setTimeline(loadedTimeline);
        setSelectedSceneId(loadedTimeline.scene_clips[0]?.scene_id ?? null);
        setSelectedZoomId(loadedTimeline.zoom_clips[0]?.id ?? null);
        setTimelineVersion(parsedTimeline.data.current.version);
        setCanUndo(parsedTimeline.data.can_undo);
        setCanRedo(parsedTimeline.data.can_redo);
        setStatus(
          savedExport
            ? exportIsStale
              ? "Timeline changed · previewing previous export"
              : `${savedExport.quality} export ready to play`
            : "Project timeline loaded",
        );
      } else if (isJudgeDemoProject(projectId)) {
        const loadedTimeline = judgeDemoTimeline(projectId);
        setTimeline(loadedTimeline);
        setSelectedSceneId(loadedTimeline.scene_clips[0]?.scene_id ?? null);
        setSelectedZoomId(null);
        setTimelineVersion(1);
        setCanUndo(false);
        setCanRedo(false);
        setStatus("Northstar fixture ready to play");
      } else {
        setTimeline(null);
        setStatus("Project loaded · timeline not ready");
      }
    }).catch(() => {
      if (active) setLoadError("This project could not be loaded. Return to Projects and try again.");
    }).finally(() => {
      if (active) setLoadingProject(false);
    });

    return () => {
      active = false;
    };
  }, [generatedExport, initialTimeline, projectId]);

  useEffect(() => {
    if (videoRef.current) videoRef.current.currentTime = playheadMs / 1_000;
  }, [playheadMs]);

  useEffect(() => {
    if (activeMode !== "sources") return;
    let active = true;

    void Promise.all([
      fetch(`/api/projects/${projectId}/quality-api/source-contributions`, { cache: "no-store" }),
      fetch(`/api/projects/${projectId}/generation/trace`, { cache: "no-store" }),
    ]).then(async ([contributionResponse, traceResponse]) => {
      const parsedContributions = sourceContributionMapSchema.safeParse(await contributionResponse.json());
      if (!contributionResponse.ok || !parsedContributions.success) {
        throw new Error("Invalid source provenance");
      }
      if (!active) return;
      setSourceMap(parsedContributions.data);
      if (traceResponse.status === 404) {
        setGenerationTrace(null);
      } else {
        const parsedTrace = generationTraceSchema.safeParse(await traceResponse.json());
        if (!traceResponse.ok || !parsedTrace.success) {
          setTraceError("Generation activity is temporarily unavailable.");
        } else {
          setGenerationTrace(parsedTrace.data);
        }
      }
    }).catch(() => {
      if (active) setSourcesError("Source details are temporarily unavailable. The saved project is unchanged.");
    }).finally(() => {
      if (active) setSourcesLoading(false);
    });
    void fetch(`/api/projects/${projectId}/generation/motion-plan`, { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok || !active) return;
        const parsed = motionDirectionPlanSchema.safeParse(await response.json());
        if (parsed.success && active) setMotionPlan(parsed.data);
      })
      .catch(() => undefined);

    return () => {
      active = false;
    };
  }, [activeMode, projectId]);

  useEffect(() => {
    if (activeMode !== "sources" && activeMode !== "story") return;
    let active = true;
    void Promise.all([
      fetch(`/api/projects/${projectId}/generation/long-form-plan`, { cache: "no-store" }),
      fetch(`/api/projects/${projectId}/generation/long-form-checkpoints`, { cache: "no-store" }),
    ]).then(async ([planResponse, checkpointsResponse]) => {
      if (!active || planResponse.status === 404) return;
      const parsedPlan = longFormVideoPlanSchema.safeParse(await planResponse.json());
      const parsedCheckpoints = chapterCheckpointsSchema.safeParse(await checkpointsResponse.json());
      if (planResponse.ok && checkpointsResponse.ok && parsedPlan.success && parsedCheckpoints.success) {
        setLongFormPlan(parsedPlan.data);
        setChapterCheckpoints(parsedCheckpoints.data);
      }
    }).catch(() => undefined);
    return () => { active = false; };
  }, [activeMode, projectId]);

  useEffect(() => {
    if (activeMode !== "sources" && activeMode !== "style") return;
    let active = true;
    void fetch(`/api/projects/${projectId}/generation/style-plan`, { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok || !active) return;
        const parsed = styleDirectionPlanSchema.safeParse(await response.json());
        if (!parsed.success || !active) return;
        setStylePlan(parsed.data);
        setSelectedStyleSceneId((current) => current ?? parsed.data.scene_ids[0] ?? null);
      })
      .catch(() => undefined);
    return () => { active = false; };
  }, [activeMode, projectId]);

  useEffect(() => {
    if (activeMode !== "sources" && activeMode !== "callouts") return;
    let active = true;
    void fetch(`/api/projects/${projectId}/generation/attention-plan`, { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok || !active) return;
        const parsed = attentionPlanSchema.safeParse(await response.json());
        if (!parsed.success || !active) return;
        setAttentionPlan(parsed.data);
        setSelectedCalloutId((current) => current ?? parsed.data.callouts[0]?.id ?? null);
      })
      .catch(() => undefined);
    return () => { active = false; };
  }, [activeMode, projectId]);

  function navigateToMappedScene(sceneId: string) {
    const startMs = [
      ...activeTimeline.audio_clips,
      ...activeTimeline.caption_clips,
      ...activeTimeline.scene_clips,
    ].filter((clip) => clip.scene_id === sceneId).map((clip) => clip.start_ms).sort((a, b) => a - b)[0] ?? 0;
    setSelectedSceneId(sceneId);
    setPlayheadMs(startMs);
  }

  async function togglePreview() {
    const video = videoRef.current;
    if (!video || !videoExport) return;
    if (previewPlaying) {
      video.pause();
      setPreviewPlaying(false);
      return;
    }
    try {
      await video.play();
      setPreviewPlaying(true);
    } catch {
      setStatus("The video could not start. Reload the project and try again.");
    }
  }

  if (loadingProject) {
    return <main className="editor-shell editor-state-shell"><section className="editor-load-state" role="status"><b>Loading project</b><p>Preparing the saved timeline and editor controls…</p></section></main>;
  }

  if (loadError) {
    return <main className="editor-shell editor-state-shell"><section className="editor-load-state error" role="alert"><b>Project unavailable</b><p>{loadError}</p><Link href="/projects">Return to Projects</Link></section></main>;
  }

  if (!timeline) {
    return (
      <main className="editor-shell editor-state-shell editor-empty-shell">
        <header className="editor-topbar editor-empty-topbar">
          <Link href="/projects" aria-label="Back to projects">‹</Link>
          <div><h1>{project?.name ?? "Project studio"}</h1><small>{status}</small></div>
          <Link className="editor-preview-link" href="/projects">Projects</Link>
        </header>
        <section className="editor-empty-state">
          <span>Studio</span>
          <h1>Timeline not ready</h1>
          <p><b>{project?.name ?? "This project"}</b> doesn’t have a generated timeline yet. Once its recording workflow creates one, the saved scenes, captions, audio, and camera moves will appear here.</p>
          <Link href="/projects">Return to Projects</Link>
          <Link href={`/projects/${projectId}/generation`}>Open saved generation progress</Link>
        </section>
      </main>
    );
  }

  const activeTimeline: Timeline = timeline;
  const previewVideoUrl = isJudgeDemoProject(projectId)
    ? JUDGE_DEMO_VIDEO_URL
    : `/api/projects/${projectId}/exports/latest/video`;
  const selectedZoom = activeTimeline.zoom_clips.find((clip) => clip.id === selectedZoomId) ?? null;
  const selectedCallout = attentionPlan?.callouts.find((item) => item.id === selectedCalloutId) ?? null;
  const selectedCalloutTarget = attentionPlan?.targets.find((item) => item.id === selectedCallout?.target_id) ?? null;

  function persist(next: Timeline, message: string) {
    setTimeline(next);
    window.localStorage.setItem(storageKey(projectId), JSON.stringify(next));
    setStatus(message);
  }

  function updateSelectedCallout(changes: Partial<AttentionPlan["callouts"][number]>) {
    if (!attentionPlan || !selectedCallout) return;
    setAttentionPlan({
      ...attentionPlan,
      callouts: attentionPlan.callouts.map((item) => item.id === selectedCallout.id
        ? { ...item, ...changes }
        : item),
    });
  }

  function updateSelectedTarget(axis: "x" | "y", value: number) {
    if (!attentionPlan || !selectedCalloutTarget) return;
    setAttentionPlan({
      ...attentionPlan,
      targets: attentionPlan.targets.map((item) => item.id === selectedCalloutTarget.id
        ? { ...item, rect: { ...item.rect, [axis]: value } }
        : item),
    });
  }

  async function saveCallout(remove = false) {
    if (!attentionPlan || !selectedCallout || !selectedCalloutTarget) return;
    setSavingCallout(true);
    try {
      const response = await fetch(`/api/projects/${projectId}/generation/attention-plan`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          callout_id: selectedCallout.id,
          expected_timeline_version: timelineVersion,
          text: selectedCallout.text,
          placement: selectedCallout.placement,
          start_ms: selectedCallout.start_ms,
          end_ms: selectedCallout.end_ms,
          target_x: selectedCalloutTarget.rect.x,
          target_y: selectedCalloutTarget.rect.y,
          remove,
        }),
      });
      const parsed = attentionPlanSchema.safeParse(await response.json());
      if (!response.ok || !parsed.success) throw new Error("Attention update failed");
      setAttentionPlan(parsed.data);
      setSelectedCalloutId(parsed.data.callouts[0]?.id ?? null);
      const nextTimeline = { ...activeTimeline, attention_plan_id: parsed.data.id };
      persist(nextTimeline, remove ? "Callout removed · export to update the video" : "Callout saved · export to update the video");
      setTimelineVersion((version) => version + 1);
    } catch {
      setStatus("Callout could not be saved · reload and try again");
    } finally {
      setSavingCallout(false);
    }
  }

  async function selectVisualStyle(
    variantId: VisualVariantId,
    sceneId?: string,
    resetScene = false,
  ) {
    if (!stylePlan) return;
    setSavingStyle(true);
    try {
      const response = await fetch(`/api/projects/${projectId}/generation/style-plan`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          expected_timeline_version: timelineVersion,
          variant_id: variantId,
          scene_id: sceneId,
          reset_scene: resetScene,
        }),
      });
      const parsed = styleDirectionPlanSchema.safeParse(await response.json());
      if (!response.ok || !parsed.success) throw new Error("Style update failed");
      setStylePlan(parsed.data);
      const nextTimeline = timelineSchema.parse({
        ...activeTimeline,
        style_plan_id: parsed.data.id,
        style_design_version: parsed.data.version,
        visual_variant: parsed.data.decision.selected_variant,
      });
      persist(nextTimeline, resetScene ? "Scene style reset · export to update the video" : "Style saved · export to update the video");
      setTimelineVersion((version) => version + 1);
      setCanUndo(true);
      setExportStale(true);
      window.localStorage.setItem(exportStaleKey(projectId), "true");
    } catch {
      setStatus("Style could not be saved · reload and try again");
    } finally {
      setSavingStyle(false);
    }
  }

  async function retryLongFormChapter(chapterId: string) {
    setRetryingChapterId(chapterId);
    try {
      const response = await fetch(`/api/projects/${projectId}/generation/long-form-chapters/${chapterId}/retry`, { method: "POST" });
      const parsed = chapterCheckpointSchema.safeParse(await response.json());
      if (!response.ok || !parsed.success) throw new Error("Chapter retry failed");
      setChapterCheckpoints((current) => current.map((item) => item.chapter_id === chapterId ? parsed.data : item));
      if (parsed.data.status === "captured") {
        const timelineResponse = await fetch(`/api/projects/${projectId}/timeline`, { cache: "no-store" });
        const parsedTimeline = timelineHistoryStateSchema.safeParse(await timelineResponse.json());
        if (!timelineResponse.ok || !parsedTimeline.success) throw new Error("Updated timeline failed");
        setTimeline(parsedTimeline.data.current.timeline);
        setTimelineVersion(parsedTimeline.data.current.version);
        setCanUndo(parsedTimeline.data.can_undo);
        setCanRedo(parsedTimeline.data.can_redo);
        setExportStale(true);
        window.localStorage.setItem(exportStaleKey(projectId), "true");
        setStatus("Chapter regenerated — approved chapters were kept");
      } else {
        setStatus("Chapter capture failed — earlier chapters are still saved");
      }
    } catch {
      setStatus("Chapter could not be regenerated — reload and try again");
    } finally {
      setRetryingChapterId(null);
    }
  }

  function deleteSelectedScene() {
    if (!selectedSceneId || activeTimeline.demo_mode === "presentation_demo") return;
    const next = deleteSceneFromTimeline(activeTimeline, selectedSceneId);
    persist(next, "Scene deleted · tracks updated");
    setSelectedSceneId(next.scene_clips[0]?.scene_id ?? null);
  }

  function duplicateSelectedScene() {
    if (!selectedSceneId || activeTimeline.demo_mode === "presentation_demo") return;
    persist(duplicateSceneInTimeline(activeTimeline, selectedSceneId), "Scene duplicated");
  }

  function splitSelectedScene() {
    if (activeTimeline.demo_mode === "presentation_demo") return;
    const scene = activeTimeline.scene_clips.find((clip) => clip.scene_id === selectedSceneId);
    if (!scene || playheadMs <= scene.start_ms || playheadMs >= scene.end_ms) {
      setStatus("Place the playhead inside the selected scene to split it.");
      return;
    }
    persist(splitSceneInTimeline(activeTimeline, scene.scene_id, playheadMs), "Scene split at playhead");
  }

  function updateZoom(
    values: Partial<Pick<ZoomClip, "scale" | "end_ms" | "focus_x" | "focus_y">>,
  ) {
    if (!selectedZoom) return;
    const next = timelineSchema.parse({
      ...activeTimeline,
      zoom_clips: activeTimeline.zoom_clips.map((clip) =>
        clip.id === selectedZoom.id ? { ...clip, ...values, source: "manual" } : clip,
      ),
    });
    persist(next, "Camera change ready · save to timeline");
  }

  function updateZoomDuration(seconds: number) {
    if (!selectedZoom || !Number.isFinite(seconds)) return;
    const maximum = activeTimeline.duration_ms - selectedZoom.start_ms;
    const durationMs = Math.min(maximum, Math.max(300, Math.round(seconds * 1_000)));
    updateZoom({ end_ms: selectedZoom.start_ms + durationMs });
  }

  function updateZoomFocus(axis: "x" | "y", percent: number) {
    if (!selectedZoom || !Number.isFinite(percent)) return;
    const width = selectedZoom.source_viewport?.width ?? 1_280;
    const height = selectedZoom.source_viewport?.height ?? 720;
    const currentX = selectedZoom.focus_x
      ?? selectedZoom.target_rect.x + selectedZoom.target_rect.width / 2;
    const currentY = selectedZoom.focus_y
      ?? selectedZoom.target_rect.y + selectedZoom.target_rect.height / 2;
    const bounded = Math.min(100, Math.max(0, percent)) / 100;
    updateZoom({
      focus_x: axis === "x" ? Math.round(width * bounded) : currentX,
      focus_y: axis === "y" ? Math.round(height * bounded) : currentY,
    });
  }

  function updateZoomFocusPoint(horizontalPercent: number, verticalPercent: number) {
    if (!selectedZoom) return;
    const width = selectedZoom.source_viewport?.width ?? 1_280;
    const height = selectedZoom.source_viewport?.height ?? 720;
    updateZoom({
      focus_x: Math.round(width * Math.min(100, Math.max(0, horizontalPercent)) / 100),
      focus_y: Math.round(height * Math.min(100, Math.max(0, verticalPercent)) / 100),
    });
  }

  function updateFocusFromPointer(event: ReactPointerEvent<HTMLDivElement>) {
    const bounds = event.currentTarget.getBoundingClientRect();
    if (bounds.width <= 0 || bounds.height <= 0) return;
    updateZoomFocusPoint(
      ((event.clientX - bounds.left) / bounds.width) * 100,
      ((event.clientY - bounds.top) / bounds.height) * 100,
    );
  }

  async function applyEditorOperation(
    operation: EditOperation,
    successMessage: string,
    options?: { pendingMessage: string; summary: string },
  ) {
    setSavingZoom(true);
    setStatus(options?.pendingMessage ?? (
      operation.operation_type === "delete_zoom"
        ? "Removing zoom…"
        : operation.operation_type === "change_presentation"
          ? "Applying recording frame…"
          : "Saving zoom…"
    ));
    try {
      const response = await fetch(`/api/projects/${projectId}/timeline/apply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          expected_version: timelineVersion,
          base_timeline: activeTimeline,
          summary: options?.summary ?? (operation.operation_type === "delete_zoom"
            ? "Remove zoom"
            : operation.operation_type === "change_presentation"
              ? "Change recording frame"
              : "Update zoom framing"),
          operations: [operation],
        }),
      });
      const parsed = timelineHistoryStateSchema.safeParse(await response.json());
      if (!response.ok || !parsed.success) throw new Error("Camera edit failed");
      persist(parsed.data.current.timeline, successMessage);
      setTimelineVersion(parsed.data.current.version);
      setCanUndo(parsed.data.can_undo);
      setCanRedo(parsed.data.can_redo);
      setSelectedZoomId(
        parsed.data.current.timeline.zoom_clips.find(
          (clip) => clip.id === operation.target_id,
        )?.id
        ?? parsed.data.current.timeline.zoom_clips[0]?.id
        ?? null,
      );
      window.localStorage.setItem(exportStaleKey(projectId), "true");
      setExportStale(true);
    } catch {
      setStatus("The edit was not saved. Reload the timeline and try again.");
    } finally {
      setSavingZoom(false);
    }
  }

  async function saveSelectedZoom() {
    if (!selectedZoom) return;
    await applyEditorOperation(
      {
        operation_type: "update_zoom",
        target_id: selectedZoom.id,
        arguments: {
          scale: selectedZoom.scale,
          end_ms: selectedZoom.end_ms,
          focus_x: selectedZoom.focus_x,
          focus_y: selectedZoom.focus_y,
        },
        rationale: "Save the user-selected zoom duration and focus point.",
      },
      "Zoom saved · export again to update the video",
    );
  }

  async function removeSelectedZoom() {
    if (!selectedZoom) return;
    await applyEditorOperation(
      {
        operation_type: "delete_zoom",
        target_id: selectedZoom.id,
        arguments: {},
        rationale: "Remove the user-selected camera move.",
      },
      "Zoom removed · export again to update the video",
    );
  }

  async function applyPresentation(template: PresentationTemplate) {
    await applyEditorOperation(
      {
        operation_type: "change_presentation",
        target_id: projectId,
        arguments: { ...activeTimeline.presentation, template },
        rationale: "Apply the user-selected recording frame without changing zoom settings.",
      },
      `${template === "edge_to_edge" ? "Edge-to-edge" : template === "soft_frame" ? "Soft frame" : "Spotlight frame"} saved · export again to update the video`,
      { pendingMessage: "Applying recording frame…", summary: "Change recording frame" },
    );
  }

  async function toggleSmoothZoom() {
    const zoomEnabled = !activeTimeline.presentation.zoom_enabled;
    await applyEditorOperation(
      {
        operation_type: "change_presentation",
        target_id: projectId,
        arguments: { ...activeTimeline.presentation, zoom_enabled: zoomEnabled },
        rationale: `${zoomEnabled ? "Include" : "Bypass"} saved smooth zoom clips without deleting camera edits.`,
      },
      `Smooth zoom ${zoomEnabled ? "enabled" : "disabled"} · export again to update the video`,
      {
        pendingMessage: `${zoomEnabled ? "Enabling" : "Disabling"} smooth zoom…`,
        summary: `${zoomEnabled ? "Enable" : "Disable"} smooth zoom`,
      },
    );
  }

  async function proposeEdit() {
    if (!instruction.trim()) return;
    setPlanning(true);
    setProposal(null);
    try {
      const response = await fetch(`/api/projects/${projectId}/edit-plan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ instruction, timeline }),
      });
      const parsed = editPlanSchema.safeParse(await response.json());
      if (!response.ok || !parsed.success) throw new Error("Invalid edit proposal");
      setProposal(parsed.data);
      setStatus("Edit proposal ready for review");
    } catch {
      setStatus("The edit planner could not prepare a safe proposal.");
    } finally {
      setPlanning(false);
    }
  }

  async function createExport() {
    setExporting(true);
    setStatus("Rendering 1440p export…");
    try {
      const response = await fetch(`/api/projects/${projectId}/exports`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ timeline, quality: "1440p" }),
      });
      const parsed = videoExportSchema.safeParse(await response.json());
      if (!response.ok || !parsed.success) throw new Error("Invalid export response");
      if (parsed.data.status === "succeeded") {
        setVideoExport(parsed.data);
        setExportStale(false);
        window.localStorage.removeItem(exportStaleKey(projectId));
        window.sessionStorage.setItem(exportStorageKey(projectId), JSON.stringify(parsed.data));
      }
      setStatus(
        parsed.data.status === "succeeded"
          ? `${parsed.data.quality} export ready to download`
          : "Export failed · retry when ready",
      );
    } catch {
      setStatus("Export service unavailable · try again");
    } finally {
      setExporting(false);
    }
  }

  async function applyProposal() {
    if (!proposal?.supported) return;
    setStatus("Applying all proposed edits…");
    try {
      const response = await fetch(`/api/projects/${projectId}/timeline/apply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          expected_version: timelineVersion,
          base_timeline: timeline,
          summary: proposal.summary,
          operations: proposal.operations,
        }),
      });
      const parsed = timelineHistoryStateSchema.safeParse(await response.json());
      if (!response.ok || !parsed.success) throw new Error("Timeline apply failed");
      persist(parsed.data.current.timeline, `Applied version ${parsed.data.current.version}`);
      setTimelineVersion(parsed.data.current.version);
      setCanUndo(parsed.data.can_undo);
      setCanRedo(parsed.data.can_redo);
      setProposal(null);
    } catch {
      setStatus("No edits were applied. Reload the timeline and try again.");
    }
  }

  async function moveHistory(action: "undo" | "redo") {
    try {
      const response = await fetch(`/api/projects/${projectId}/timeline/${action}`, {
        method: "POST",
      });
      const parsed = timelineHistoryStateSchema.safeParse(await response.json());
      if (!response.ok || !parsed.success) throw new Error("History action failed");
      persist(parsed.data.current.timeline, `${action === "undo" ? "Undid" : "Redid"} to version ${parsed.data.current.version}`);
      setTimelineVersion(parsed.data.current.version);
      setCanUndo(parsed.data.can_undo);
      setCanRedo(parsed.data.can_redo);
    } catch {
      setStatus(`Couldn’t ${action} the timeline.`);
    }
  }

  const playheadPercent = (playheadMs / timeline.duration_ms) * 100;
  const selectedScene = timeline.scene_clips.find((clip) => clip.scene_id === selectedSceneId) ?? null;
  const focusWidth = selectedZoom?.source_viewport?.width ?? 1_280;
  const focusHeight = selectedZoom?.source_viewport?.height ?? 720;
  const focusX = selectedZoom
    ? selectedZoom.focus_x ?? selectedZoom.target_rect.x + selectedZoom.target_rect.width / 2
    : 0;
  const focusY = selectedZoom
    ? selectedZoom.focus_y ?? selectedZoom.target_rect.y + selectedZoom.target_rect.height / 2
    : 0;
  const focusXPercent = Math.round((focusX / focusWidth) * 100);
  const focusYPercent = Math.round((focusY / focusHeight) * 100);
  return (
    <main className="editor-shell">
      <header className="editor-topbar">
        <Link href="/projects" aria-label="Back to projects">‹</Link>
        <div><h1>{project?.name ?? "Demo editor"}</h1><small>{status}</small></div>
        <span>{Math.round(timeline.duration_ms / 1_000)} seconds</span>
        <button aria-label="Undo timeline edit" disabled={!canUndo} onClick={() => void moveHistory("undo")} type="button">↶</button>
        <button aria-label="Redo timeline edit" disabled={!canRedo} onClick={() => void moveHistory("redo")} type="button">↷</button>
        <a className="editor-preview-link" href="#editor-preview">Preview</a>
        {videoExport?.status === "succeeded" && videoExport.download_url && !exportStale ? (
          <a className="publish-button export-download" href={videoExport.download_url}>Download MP4</a>
        ) : (
          <button className="publish-button" disabled={exporting} onClick={() => void createExport()} type="button">
            {exporting ? "Exporting…" : videoExport ? "Export changes" : "Export 1440p"}
          </button>
        )}
      </header>

      <section className="editor-preview" id="editor-preview" aria-label="Synchronized preview">
        <div className="editor-preview-player">
        <div className={`preview-stage preview-template-${videoExport ? "rendered" : timeline.presentation.template} preview-style-${stylePlan?.decision.selected_variant ?? timeline.visual_variant ?? "none"}`}>
          <div className="preview-video-frame">
            <video
            aria-label="Preview video"
            key={videoExport?.id ?? "no-export"}
            onEnded={() => setPreviewPlaying(false)}
            onPause={() => setPreviewPlaying(false)}
            onPlay={() => setPreviewPlaying(true)}
            onTimeUpdate={(event) => setPlayheadMs(Math.min(timeline.duration_ms, Math.round(event.currentTarget.currentTime * 1_000)))}
            playsInline
            preload="metadata"
            ref={videoRef}
              src={videoExport ? previewVideoUrl : undefined}
            />
            {!videoExport && <div className="preview-product">
              <span>{project ? domainLabel(project.website_url) : "DemoDirector"}</span>
              <h1>{project?.name ?? "Demo editor"}</h1>
              <p>{project?.product_summary ?? "Review scene timing, captions, and framing before export."}</p>
              <div className="preview-scene-info"><b>{selectedScene?.scene_id ?? "Preview"}</b><span>{selectedScene ? `${formatTime(selectedScene.end_ms - selectedScene.start_ms)} scene` : "No scene selected"}</span></div>
            </div>}
          </div>
        </div>
        <div className="editor-player-controls"><button aria-label={previewPlaying ? "Pause preview" : "Play preview"} disabled={!videoExport} onClick={() => void togglePreview()} type="button">{previewPlaying ? "Ⅱ" : "▶"}</button><output aria-label="Preview time">{formatTime(playheadMs)}</output><div className="editor-progress"><span style={{ width: `${playheadPercent}%` }} /></div><span>CC</span><span>1×</span><span>⛶</span></div>
        </div>
      </section>

      <aside className="editor-right-sidebar">
        <section className="clip-inspector editor-mode-panel">
          {activeMode === "quality" && <VideoQuality key={videoExport?.id} projectId={projectId} exportId={isJudgeDemoProject(projectId) ? undefined : videoExport?.id} onSeek={(ms) => { if (videoRef.current) videoRef.current.currentTime = ms / 1000; }} onTimelineChanged={() => { setExportStale(true); window.localStorage.setItem(exportStaleKey(projectId), "true"); setStatus("Repair saved · reload to inspect the candidate timeline before exporting"); }} />}
          {activeMode === "setup" && <>
            <div className="inspector-heading"><h2>Project setup</h2><p>Recording details</p></div>
            <dl className="editor-detail-list">
              <dt>Project</dt><dd>{project?.name ?? "Demo project"}</dd>
              <dt>Source</dt><dd>{project ? domainLabel(project.website_url) : "Not available"}</dd>
              <dt>Format</dt><dd>{timeline.demo_mode === "presentation_demo" ? "Presentation Demo" : "Product Demo"}</dd>
              {timeline.demo_mode === "presentation_demo" && <><dt>Template sequence</dt><dd>Presentation Story v1</dd></>}
              <dt>Smooth zoom</dt><dd>{timeline.presentation.zoom_enabled ? "On" : "Off"}</dd>
              <dt>Duration</dt><dd>{Math.round(timeline.duration_ms / 1_000)} seconds</dd>
              <dt>Scenes</dt><dd>{timeline.scene_clips.length}</dd>
            </dl>
          </>}

          {activeMode === "sources" && <>
            <div className="inspector-heading">
              <h2>Source map</h2>
              <p>{sourceMap ? `${sourceMap.sources.length} saved` : "Approved project evidence"}</p>
            </div>
            {sourcesLoading && <p className="sources-state" role="status">Loading saved evidence and runtime details…</p>}
            {sourcesError && <p className="sources-state error" role="alert">{sourcesError}</p>}
            {!sourcesLoading && !sourcesError && sourceMap && <>
              {sourceMap.status !== "ready" ? <section className="source-map-notice" role="alert">
                <b>{sourceMap.status === "stale" ? "Source map needs approval" : "Approve the storyboard to map its sources"}</b>
                <p>{sourceMap.status === "stale" ? "The storyboard or evidence changed. Old scene and narration links were removed." : "Usage links appear after you review and approve the exact narration."}</p>
                <Link href={`/projects/${projectId}/storyboard`}>Review storyboard evidence</Link>
              </section> : <>
                {sourceMap.partial_evidence && <p className="source-map-partial" role="status">Some evidence groups are empty. This map uses only the evidence saved with the approved storyboard.</p>}
                {selectedContributionId ? (() => {
                  const contribution = sourceMap.contributions.find((item) => item.id === selectedContributionId);
                  const source = sourceMap.sources.find((item) => item.id === contribution?.source_id);
                  if (!contribution || !source) return null;
                  const statements = sourceMap.narration_statements.filter((item) => contribution.narration_statement_ids.includes(item.id));
                  return <section className="source-usage-detail" aria-label="Selected source contribution">
                    <button className="source-back" onClick={() => setSelectedContributionId(null)} type="button">← All sources</button>
                    <span>{originLabel(source.origin)}</span>
                    <h3>{source.title}</h3>
                    <p>{contribution.label}</p>
                    {contribution.kind === "website_structure" && <small>Capture input — observed page structure, not an externally verified claim.</small>}
                    <div className="source-reference-list">
                      {contribution.scene_ids.map((sceneId) => {
                        const scene = sourceMap.scenes.find((item) => item.id === sceneId);
                        return scene ? <button key={sceneId} onClick={() => navigateToMappedScene(sceneId)} type="button"><b>Scene {scene.order + 1}</b><span>{scene.title}</span></button> : null;
                      })}
                      {statements.map((statement) => <button key={statement.id} onClick={() => navigateToMappedScene(statement.scene_id)} type="button"><b>Approved narration</b><span>{statement.text}</span></button>)}
                    </div>
                  </section>;
                })() : <section className="sources-section" aria-label="Evidence contributions">
                  <h3>Where each source was used</h3>
                  {sourceMap.sources.length > 0 ? (["project_brief", "website_inspection", "parallel_search"] as const).map((origin) => {
                    const originSources = sourceMap.sources.filter((source) => source.origin === origin);
                    if (!originSources.length) return null;
                    return <section className="source-group" aria-labelledby={`source-group-${origin}`} key={origin}>
                      <h4 id={`source-group-${origin}`}>{originLabel(origin)}</h4>
                      <div className="source-list">
                        {originSources.map((source) => {
                          const contributions = sourceMap.contributions.filter((item) => item.source_id === source.id);
                          return <article className="source-item" id={`source-${source.id}`} key={source.id}>
                            <header><span>{source.retrieval_state === "saved" ? "Saved" : "Partial"}</span>{source.retrieved_at && <time dateTime={source.retrieved_at}>{formatResearchDate(source.retrieved_at)}</time>}</header>
                            {source.url ? <a href={source.url} rel="noreferrer" target="_blank">{source.title}</a> : <b>{source.title}</b>}
                            <small>{source.domain}</small>
                            <p>{source.excerpt}</p>
                            <div className="source-contribution-list">{contributions.map((contribution) => <div data-usage={contribution.usage_state} key={contribution.id}><span>{contribution.label}</span>{contribution.usage_state === "used" && <button onClick={() => setSelectedContributionId(contribution.id)} type="button">Review usage</button>}</div>)}</div>
                          </article>;
                        })}
                      </div>
                    </section>;
                  }) : <p className="sources-state">No saved evidence is available for this approved storyboard.</p>}
                </section>}
              </>}

              <section className="sources-section" aria-label="Generation activity">
                {motionPlan && <div className="motion-direction-summary" id="motion-direction">
                  <span>Motion direction</span>
                  <h3>{motionPlan.summary}</h3>
                  <p>Google ADK planned {motionPlan.cues.length} validated cues with {motionPlan.design_tokens.font_family} and {motionPlan.design_tokens.version}.</p>
                  {motionPlan.editorial_plan && <p>{motionPlan.editorial_plan.scenes.length} product-present templates · {motionPlan.editorial_plan.scenes.map((scene) => scene.template_id.replaceAll("_", " ")).join(" · ")}</p>}
                </div>}
                {attentionPlan && <div className="motion-direction-summary" id="attention-direction">
                  <span>Attention direction</span>
                  <h3>{attentionPlan.summary}</h3>
                  <p>Google ADK accepted {attentionPlan.callouts.length} target-aware callouts from {attentionPlan.targets.length} recorded controls.</p>
                </div>}
                {stylePlan && <div className="motion-direction-summary" id="style-direction">
                  <span>Google ADK style direction</span>
                  <h3>{variantLabel(stylePlan.decision.selected_variant)}</h3>
                  <p>{stylePlan.rationale}</p>
                  <p>{variantDecisionLabel(stylePlan)} · {stylePlan.recommendation_evidence_refs.length} linked project inputs</p>
                </div>}
                {longFormPlan && <div className="motion-direction-summary" id="longform-direction">
                  <span>Google ADK three-minute direction</span>
                  <h3>{longFormPlan.sections.length} sections · {longFormPlan.beats.length} visual beats</h3>
                  <p>Product operation at {formatTime(longFormPlan.first_product_operation_ms)} · Create by {formatTime(longFormPlan.create_action_ms)} · finished result by {formatTime(longFormPlan.finished_glimpse_ms)}</p>
                  <p>{longFormPlan.parallel_source_refs.length} direct Parallel sources linked · {longFormPlan.chapters.length} restartable chapters</p>
                </div>}
                <div className="generation-activity-heading"><h3>Generation activity</h3>{generationTrace && <span>{traceStatusLabel(generationTrace.status)}</span>}</div>
                {traceError && <p className="sources-state error" role="alert">{traceError}</p>}
                {!traceError && !generationTrace && <p className="sources-state">No durable generation activity is available for this project.</p>}
                {generationTrace && <div className="generation-trace-list">
                  {generationTrace.stages.map((stage) => <details key={stage.id}>
                    <summary>
                      <span className={`trace-state trace-state-${stage.status}`} aria-hidden="true" />
                      <span><b>{stage.label}</b><small>{stage.service}</small></span>
                      <em><span className="visually-hidden">{stage.status.replace("_", " ")} · </span>{stage.status === "succeeded" || stage.status === "failed" ? formatElapsed(stage.elapsed_ms) : stage.status.replace("_", " ")}</em>
                    </summary>
                    <div className="trace-stage-detail">
                      <p>{stage.message}</p>
                      {stage.attempt > 0 && <span>Attempt {stage.attempt}{stage.retry_count > 0 ? ` · ${stage.retry_count} retr${stage.retry_count === 1 ? "y" : "ies"}` : ""}</span>}
                      {stage.started_at && <span>{formatTraceDate(stage.started_at)}{stage.completed_at ? ` – ${formatTraceDate(stage.completed_at)}` : " – running"}</span>}
                      {stage.contributions.length > 0 && <dl>{stage.contributions.map((item) => <div key={item.key}><dt>{item.label}</dt><dd>{item.value.toLocaleString()} {item.unit}</dd></div>)}</dl>}
                      {stage.output_href && <Link href={stage.output_href}>Open saved output</Link>}
                    </div>
                  </details>)}
                </div>}
              </section>
            </>}
          </>}

          {activeMode === "layout" && <>
            <div className="inspector-heading"><h2>Layout</h2><p>Canvas and framing</p></div>
            <button className="layout-option selected" type="button"><span>16:9</span><small>2560 × 1440 landscape</small></button>
            <p className="camera-note">Recordings and exports use a native QHD canvas. Choose a frame in Overlay to change how the recording sits inside it.</p>
          </>}

          {activeMode === "style" && <>
            <div className="inspector-heading"><h2>Visual style</h2><p>{stylePlan ? variantDecisionLabel(stylePlan) : "Generation required"}</p></div>
            {!stylePlan && <p className="camera-note">Generate the project first to receive a grounded style recommendation.</p>}
            {stylePlan && <>
              <p className="style-rationale">{stylePlan.rationale}</p>
              <div className="style-options" aria-label="Visual style variants">
                <StyleOption active={stylePlan.decision.selected_variant === "editorial_story"} description="Composed footage, explanation cards, and deliberate pacing." disabled={savingStyle} label="Editorial Story" onClick={() => void selectVisualStyle("editorial_story")} variant="editorial_story" />
                <StyleOption active={stylePlan.decision.selected_variant === "product_spotlight"} description="Larger product footage, restrained callouts, and calm motion." disabled={savingStyle} label="Product Spotlight" onClick={() => void selectVisualStyle("product_spotlight")} variant="product_spotlight" />
                <StyleOption active={stylePlan.decision.selected_variant === "technical_proof"} description="Validated sources, activity, controls, and measured output." disabled={savingStyle} label="Technical Proof" onClick={() => void selectVisualStyle("technical_proof")} variant="technical_proof" />
              </div>
              <div className="style-scene-controls">
                <label htmlFor="style-scene">Scene override</label>
                <select id="style-scene" onChange={(event) => setSelectedStyleSceneId(event.target.value)} value={selectedStyleSceneId ?? ""}>
                  {stylePlan.scene_ids.map((sceneId, index) => <option key={sceneId} value={sceneId}>Scene {index + 1}</option>)}
                </select>
                <label htmlFor="style-scene-variant">Use style</label>
                <select id="style-scene-variant" onChange={(event) => {
                  if (selectedStyleSceneId) void selectVisualStyle(event.target.value as VisualVariantId, selectedStyleSceneId);
                }} value={stylePlan.overrides.find((item) => item.scene_id === selectedStyleSceneId)?.variant_id ?? stylePlan.decision.selected_variant}>
                  <option value="editorial_story">Editorial Story</option>
                  <option value="product_spotlight">Product Spotlight</option>
                  <option value="technical_proof">Technical Proof</option>
                </select>
                <button disabled={savingStyle || !stylePlan.overrides.some((item) => item.scene_id === selectedStyleSceneId)} onClick={() => selectedStyleSceneId && void selectVisualStyle(stylePlan.decision.selected_variant, selectedStyleSceneId, true)} type="button">Reset scene to {variantLabel(stylePlan.decision.selected_variant)}</button>
              </div>
              <p className="camera-note">Switching style keeps the recording, narration, captions, timing, and evidence unchanged. Changes are undoable and do not call a provider.</p>
            </>}
          </>}

          {activeMode === "story" && <>
            <div className="inspector-heading"><h2>Three-minute story</h2><p>{longFormPlan ? "3:00 proof-first" : "Not enabled"}</p></div>
            {!longFormPlan && <p className="camera-note">Choose a 180-second project to create the proof-first chapter plan.</p>}
            {longFormPlan && <>
              <dl className="longform-milestones">
                <div><dt>Product operates</dt><dd>{formatTime(longFormPlan.first_product_operation_ms)}</dd></div>
                <div><dt>Create action</dt><dd>{formatTime(longFormPlan.create_action_ms)}</dd></div>
                <div><dt>Finished glimpse</dt><dd>{formatTime(longFormPlan.finished_glimpse_ms)}</dd></div>
                <div><dt>Product visible</dt><dd>{Math.round(longFormPlan.product_presence_percent)}%</dd></div>
              </dl>
              <div className="longform-sections" aria-label="Narrative sections">
                {longFormPlan.sections.map((section) => <button key={section.id} onClick={() => setPlayheadMs(section.start_ms)} type="button"><span>{formatTime(section.start_ms)}</span><b>{section.id.replaceAll("_", " ")}</b><small>{Math.round((section.end_ms - section.start_ms) / 1_000)}s · product footage</small></button>)}
              </div>
              {longFormPlan.condensed_intervals.length > 0 && <div className="longform-chapters" aria-label="Time-compressed intervals">
                <h3>Time compression</h3>
                {longFormPlan.condensed_intervals.map((interval) => <div key={`${interval.start_ms}-${interval.end_ms}`}><span><b>{interval.label}</b><small>{formatTime(interval.start_ms)}–{formatTime(interval.end_ms)} · actual {(interval.actual_elapsed_ms / 1_000).toFixed(1)}s</small></span></div>)}
              </div>}
              <div className="longform-chapters" aria-label="Capture chapters" role="group">
                <h3>Capture chapters</h3>
                {longFormPlan.chapters.map((chapter) => {
                  const checkpoint = chapterCheckpoints.find((item) => item.chapter_id === chapter.id);
                  return <div key={chapter.id}><span><b>Chapter {chapter.order + 1}</b><small>{checkpoint?.status ?? "loading"} · attempt {checkpoint?.attempt ?? 0}</small></span><button disabled={!checkpoint || checkpoint.status === "pending" || retryingChapterId === chapter.id} onClick={() => void retryLongFormChapter(chapter.id)} type="button">{retryingChapterId === chapter.id ? "Queuing…" : "Regenerate"}</button></div>;
                })}
              </div>
              <p className="camera-note">Regeneration replaces only the selected chapter checkpoint. Saved sources, narrative order, and other approved chapters remain unchanged.</p>
            </>}
          </>}

          {activeMode === "cut" && <>
            <div className="inspector-heading"><h2>Cut scene</h2><p>{selectedSceneId ?? "No scene selected"}</p></div>
            {timeline.demo_mode === "presentation_demo" ? (
              <p className="camera-note" role="note">The authored Presentation Demo sequence is fixed at 2:00, so scene timing is read-only.</p>
            ) : <>
              <div className="cut-actions">
                <button onClick={splitSelectedScene} type="button"><EditorModeIcon mode="cut" />Split at playhead</button>
                <button disabled={timeline.scene_clips.length <= 1} onClick={deleteSelectedScene} type="button">Delete scene</button>
                <button onClick={duplicateSelectedScene} type="button">Duplicate scene</button>
              </div>
              <p className="camera-note">Select a scene in the timeline, then place the playhead before splitting.</p>
            </>}
          </>}

          {activeMode === "zoom" && <>
            <div className="inspector-heading"><h2>{selectedZoom ? "Zoom clip" : "Select a zoom"}</h2><p>{selectedSceneId ?? "No scene selected"}</p></div>
            <div className="zoom-master-control">
              <div className="control-title"><b>Smooth zoom</b><button aria-checked={timeline.presentation.zoom_enabled} aria-describedby="smooth-zoom-editor-note" aria-label="Smooth zoom" className={`toggle ${timeline.presentation.zoom_enabled ? "is-on" : ""}`} disabled={savingZoom} onClick={() => void toggleSmoothZoom()} role="switch" type="button"><span /></button></div>
              <p className="camera-note" id="smooth-zoom-editor-note">{timeline.presentation.zoom_enabled ? "Smooth zooms are included on export. Pointer movement and click indicators remain visible." : "Zooms are bypassed on export. Saved zoom clips are retained and remain editable."}</p>
            </div>
            {selectedZoom ? <>
              <div
                aria-label="Zoom target"
                className="zoom-target"
                onPointerDown={(event) => {
                  focusDragRef.current = true;
                  event.currentTarget.setPointerCapture?.(event.pointerId);
                  updateFocusFromPointer(event);
                }}
                onPointerMove={(event) => {
                  if (focusDragRef.current) updateFocusFromPointer(event);
                }}
                onPointerUp={(event) => {
                  focusDragRef.current = false;
                  event.currentTarget.releasePointerCapture?.(event.pointerId);
                }}
              >
                {videoExport ? <video aria-hidden="true" muted playsInline src={previewVideoUrl} /> : <div className="zoom-target-placeholder"><b>{project?.name ?? "Demo preview"}</b><span>Drag the target to focus the zoom</span></div>}
                <span
                  aria-label="Zoom center point"
                  aria-valuemax={100}
                  aria-valuemin={0}
                  aria-valuenow={focusXPercent}
                  className="zoom-target-dot"
                  role="slider"
                  style={{ left: `${focusXPercent}%`, top: `${focusYPercent}%` }}
                  tabIndex={0}
                />
              </div>
              <p className="zoom-target-hint"><span />Drag the red target to set the center point</p>
              <label htmlFor="zoom-scale">Scale <span>{selectedZoom.scale.toFixed(2)}×</span></label>
              <input aria-label="Zoom scale" id="zoom-scale" max="4" min="1" onChange={(event) => updateZoom({ scale: Number(event.target.value) })} step="0.05" type="range" value={selectedZoom.scale} />
              <label htmlFor="zoom-duration">Duration <span>{((selectedZoom.end_ms - selectedZoom.start_ms) / 1_000).toFixed(1)}s</span></label>
              <input aria-label="Zoom duration" id="zoom-duration" max={(timeline.duration_ms - selectedZoom.start_ms) / 1_000} min="0.3" onChange={(event) => updateZoomDuration(Number(event.target.value))} step="0.1" type="number" value={(selectedZoom.end_ms - selectedZoom.start_ms) / 1_000} />
              <details className="camera-controls">
                <summary>Precise position</summary>
                <label htmlFor="zoom-focus-x">Horizontal <span>{focusXPercent}%</span></label>
                <input aria-label="Horizontal focus" id="zoom-focus-x" max="100" min="0" onChange={(event) => updateZoomFocus("x", Number(event.target.value))} step="1" type="range" value={focusXPercent} />
                <label htmlFor="zoom-focus-y">Vertical <span>{focusYPercent}%</span></label>
                <input aria-label="Vertical focus" id="zoom-focus-y" max="100" min="0" onChange={(event) => updateZoomFocus("y", Number(event.target.value))} step="1" type="range" value={focusYPercent} />
              </details>
              <div className="camera-actions">
                <button disabled={savingZoom} onClick={() => void saveSelectedZoom()} type="button">{savingZoom ? "Saving…" : "Save zoom"}</button>
                <button className="danger" disabled={savingZoom} onClick={() => void removeSelectedZoom()} type="button">Remove zoom</button>
              </div>
              <p className="camera-note">Changes are undoable and apply to the next export.</p>
            </> : <p>Select a zoom on the timeline to edit its framing.</p>}
          </>}

          {activeMode === "callouts" && <>
            <div className="inspector-heading"><h2>Callouts</h2><p>{attentionPlan?.callouts.length ?? 0} saved</p></div>
            {!attentionPlan && <p className="camera-note">Target-aware callouts appear after the recorded walkthrough is analyzed.</p>}
            {attentionPlan && attentionPlan.callouts.length === 0 && <p className="camera-note">No reliable recorded target needed a callout.</p>}
            {attentionPlan && attentionPlan.callouts.length > 0 && <>
              <div className="callout-picker">
                {attentionPlan.callouts.map((callout) => <button aria-pressed={callout.id === selectedCalloutId} key={callout.id} onClick={() => setSelectedCalloutId(callout.id)} type="button">{callout.text}</button>)}
              </div>
              {selectedCallout && selectedCalloutTarget && <div className="callout-editor">
                <label htmlFor="callout-copy">Text</label>
                <input id="callout-copy" maxLength={72} onChange={(event) => updateSelectedCallout({ text: event.target.value })} value={selectedCallout.text} />
                <label htmlFor="callout-placement">Placement</label>
                <select id="callout-placement" onChange={(event) => updateSelectedCallout({ placement: event.target.value as typeof selectedCallout.placement })} value={selectedCallout.placement}>
                  <option value="top_left">Top left</option><option value="top_right">Top right</option><option value="bottom_left">Bottom left</option><option value="bottom_right">Bottom right</option>
                </select>
                <label htmlFor="callout-start">Start <span>{(selectedCallout.start_ms / 1_000).toFixed(1)}s</span></label>
                <input id="callout-start" max={Math.max(0, selectedCallout.end_ms - 600)} min="0" onChange={(event) => updateSelectedCallout({ start_ms: Number(event.target.value) })} step="100" type="range" value={selectedCallout.start_ms} />
                <label htmlFor="callout-end">End <span>{(selectedCallout.end_ms / 1_000).toFixed(1)}s</span></label>
                <input id="callout-end" max={timeline.duration_ms} min={selectedCallout.start_ms + 600} onChange={(event) => updateSelectedCallout({ end_ms: Number(event.target.value) })} step="100" type="range" value={selectedCallout.end_ms} />
                <label htmlFor="callout-target-x">Target horizontal <span>{Math.round(selectedCalloutTarget.rect.x * 100)}%</span></label>
                <input id="callout-target-x" max={1 - selectedCalloutTarget.rect.width} min="0" onChange={(event) => updateSelectedTarget("x", Number(event.target.value))} step="0.01" type="range" value={selectedCalloutTarget.rect.x} />
                <label htmlFor="callout-target-y">Target vertical <span>{Math.round(selectedCalloutTarget.rect.y * 100)}%</span></label>
                <input id="callout-target-y" max={1 - selectedCalloutTarget.rect.height} min="0" onChange={(event) => updateSelectedTarget("y", Number(event.target.value))} step="0.01" type="range" value={selectedCalloutTarget.rect.y} />
                <div className="camera-actions"><button disabled={savingCallout} onClick={() => void saveCallout()} type="button">{savingCallout ? "Saving…" : "Save callout"}</button><button className="danger" disabled={savingCallout} onClick={() => void saveCallout(true)} type="button">Remove</button></div>
                <p className="camera-note">Changes create an undoable timeline version and apply to the next export.</p>
              </div>}
            </>}
          </>}

          {activeMode === "overlay" && <>
            <div className="inspector-heading"><h2>Video frame</h2><p>Recording frame</p></div>
            {timeline.demo_mode === "presentation_demo" ? (
              <p className="camera-note">Presentation Story v1 controls framing and places the real product recording inside its authored layouts. No additional recording frame is applied.</p>
            ) : <>
              <div className="template-list">
                <TemplateButton active={timeline.presentation.template === "edge_to_edge"} label="Edge-to-edge" onClick={() => void applyPresentation("edge_to_edge")} template="edge_to_edge" />
                <TemplateButton active={timeline.presentation.template === "soft_frame"} label="Soft frame" onClick={() => void applyPresentation("soft_frame")} template="soft_frame" />
                <TemplateButton active={timeline.presentation.template === "spotlight"} label="Spotlight" onClick={() => void applyPresentation("spotlight")} template="spotlight" />
              </div>
              <p className="camera-note">Frames are rendered into the MP4. Export again after changing the frame.</p>
            </>}
          </>}

          {activeMode === "captions" && <>
            <div className="inspector-heading"><h2>Captions</h2><p>{timeline.caption_clips.length} caption clips</p></div>
            <div className="caption-list">{timeline.caption_clips.map((clip) => <button key={clip.id} onClick={() => setPlayheadMs(clip.start_ms)} type="button"><span>{formatTime(clip.start_ms)}</span><p>{clip.text}</p></button>)}</div>
          </>}

          {activeMode === "audio" && <>
            <div className="inspector-heading"><h2>Audio</h2><p>Voiceover track</p></div>
            <div className="audio-summary"><span className="audio-summary-icon"><EditorModeIcon mode="audio" /></span><div><b>{timeline.audio_clips.length} audio clips</b><small>Synced to the recording</small></div></div>
            <p className="camera-note">Audio timing follows scene edits and remains aligned on export.</p>
          </>}

          {activeMode === "adjust" && <section className="prompt-editor" aria-label="Natural language editor">
            <div className="inspector-heading"><h2>AI edit planner</h2><p>Review before applying</p></div>
            <p>Describe a timeline change. The proposed typed operations are shown before anything is applied.</p>
            <label htmlFor="edit-instruction">Edit instruction</label>
            <textarea id="edit-instruction" onChange={(event) => setInstruction(event.target.value)} placeholder="Make the opening shorter" value={instruction} />
            <button disabled={planning || !instruction.trim()} onClick={() => void proposeEdit()} type="button">{planning ? "Planning…" : "Propose edit"}</button>
            {proposal && <article className="edit-proposal">
              <small>{proposal.supported ? "Ready for review" : "Unsupported request"}</small>
              <h4>{proposal.summary}</h4><p>{proposal.explanation}</p>
              {proposal.operations.map((operation) => <div key={`${operation.operation_type}-${operation.target_id}`}><b>{operation.operation_type.replaceAll("_", " ")}</b><span>{operation.rationale}</span></div>)}
              <button disabled={!proposal.supported} onClick={() => void applyProposal()} type="button">Apply proposed edits</button>
            </article>}
          </section>}
        </section>

        <nav aria-label="Editor tools" className="editor-mode-rail">
          {editorModes.map((mode) => <button aria-pressed={activeMode === mode.id} key={mode.id} onClick={() => {
            if (mode.id === "sources") {
              setSourcesLoading(true);
              setSourcesError(null);
              setTraceError(null);
              setSelectedContributionId(null);
            }
            setActiveMode(mode.id);
          }} type="button"><EditorModeIcon mode={mode.id} /><span>{mode.label}</span></button>)}
        </nav>
      </aside>

      <section className="editor-timeline" aria-label="Timeline editor">
        <input aria-label="Timeline playhead" className="playhead-input" max={timeline.duration_ms} min="0" onChange={(event) => setPlayheadMs(Number(event.target.value))} step="10" type="range" value={playheadMs} />
        <div className="editor-ruler"><span>0:00</span><span>{formatTime(timeline.duration_ms / 2)}</span><span>{formatTime(timeline.duration_ms)}</span></div>
        <TimelineTrack label="Scenes">
          {timeline.scene_clips.map((clip, index) => <button aria-pressed={selectedSceneId === clip.scene_id} className="scene-timeline-clip" key={clip.id} onClick={() => { setSelectedSceneId(clip.scene_id); setActiveMode("cut"); }} style={{ width: `${((clip.end_ms - clip.start_ms) / timeline.duration_ms) * 100}%` }} type="button"><b>{index + 1}</b><span>{clip.scene_id}</span><small>{formatTime(clip.end_ms - clip.start_ms)}</small></button>)}
        </TimelineTrack>
        <TimelineTrack label="Captions">{timeline.caption_clips.map((clip) => <span className="caption-timeline-clip" key={clip.id} style={clipStyle(clip, timeline.duration_ms)}>{clip.text}</span>)}</TimelineTrack>
        <TimelineTrack label="Zooms"><div className="zoom-timeline-line" />{timeline.zoom_clips.map((clip) => <button aria-label={`Select zoom ${clip.id}`} aria-pressed={selectedZoomId === clip.id} className="zoom-timeline-clip" key={clip.id} onClick={() => { setSelectedZoomId(clip.id); setActiveMode("zoom"); }} style={clipStyle(clip, timeline.duration_ms)} type="button"><span>{((clip.end_ms - clip.start_ms) / 1_000).toFixed(1)}s</span></button>)}</TimelineTrack>
        <TimelineTrack label="Voiceover"><div aria-label="Voiceover waveform" className="editor-waveform">{Array.from({ length: 80 }, (_, index) => <i key={index} style={{ height: `${7 + ((index * 17) % 25)}px` }} />)}</div></TimelineTrack>
        <div className="timeline-actions"><span role="status">{status}</span></div>
      </section>
    </main>
  );
}

function TemplateButton({
  active,
  label,
  onClick,
  template,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
  template: PresentationTemplate;
}) {
  return (
    <button aria-label={label} aria-pressed={active} className="template-option" onClick={onClick} type="button">
      <span className={`template-swatch template-swatch-${template}`}><i /></span>
      <span><b>{label}</b><small>{template === "edge_to_edge" ? "Fill the full canvas" : template === "soft_frame" ? "Neutral studio background" : "Green spotlight background"}</small></span>
      <i aria-hidden="true" className="template-check">{active ? "✓" : ""}</i>
    </button>
  );
}

function StyleOption({
  active,
  description,
  disabled,
  label,
  onClick,
  variant,
}: {
  active: boolean;
  description: string;
  disabled: boolean;
  label: string;
  onClick: () => void;
  variant: VisualVariantId;
}) {
  return <button aria-pressed={active} disabled={disabled} onClick={onClick} type="button">
    <span aria-hidden="true" className={`style-swatch style-swatch-${variant}`} />
    <span><b>{label}</b><small>{description}</small></span>
    <i aria-hidden="true">{active ? "✓" : ""}</i>
  </button>;
}

function EditorModeIcon({ mode }: { mode: EditorMode }) {
  const paths: Record<EditorMode, React.ReactNode> = {
    quality: <><path d="m5 12 4 4L19 6" /><rect x="3" y="3" width="18" height="18" rx="2" /></>,
    setup: <><rect height="14" rx="2" width="16" x="4" y="5" /><path d="M8 3v4M16 3v4M8 17v4M16 17v4" /></>,
    sources: <><path d="M7 3h8l4 4v14H7z" /><path d="M15 3v5h5M10 12h6M10 16h6" /><path d="M4 7v12" /></>,
    layout: <><rect height="16" rx="2" width="18" x="3" y="4" /><path d="M9 4v16M9 10h12" /></>,
    style: <><path d="M4 18 14 8l2 2L6 20H4z" /><path d="m13 5 2-2 6 6-2 2zM5 5h4M7 3v4" /></>,
    story: <><path d="M5 4h14v16H5z" /><path d="M8 8h8M8 12h8M8 16h5" /></>,
    cut: <><circle cx="6" cy="6" r="3" /><circle cx="6" cy="18" r="3" /><path d="m8.6 7.5 11 6.5M8.6 16.5 20 10M14 12l6 6" /></>,
    zoom: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m15.5 15.5 5 5M10.5 7.5v6M7.5 10.5h6" /></>,
    callouts: <><path d="M5 5h14v10H9l-4 4z" /><path d="M9 9h6M9 12h4" /></>,
    overlay: <><rect height="14" rx="2" width="18" x="3" y="5" /><rect height="8" rx="1" width="10" x="7" y="8" /></>,
    captions: <><rect height="14" rx="3" width="20" x="2" y="4" /><path d="m8 18-3 3v-3M6 9h5M13 9h5M6 13h8" /></>,
    audio: <><path d="M5 9v6M9 6v12M13 4v16M17 7v10M21 10v4" /></>,
    adjust: <><path d="M4 7h10M18 7h2M4 17h2M10 17h10" /><circle cx="16" cy="7" r="2" /><circle cx="8" cy="17" r="2" /></>,
  };
  return <svg aria-hidden="true" fill="none" viewBox="0 0 24 24">{paths[mode]}</svg>;
}

function TimelineTrack({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="editor-track"><b>{label}</b><div>{children}</div></div>;
}

function clipStyle(clip: { start_ms: number; end_ms: number }, durationMs: number) {
  return {
    left: `${(clip.start_ms / durationMs) * 100}%`,
    width: `${((clip.end_ms - clip.start_ms) / durationMs) * 100}%`,
  };
}

function formatTime(milliseconds: number) {
  const seconds = Math.round(milliseconds / 1_000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function domainLabel(value: string) {
  try {
    return new URL(value).hostname.replace(/^www\./, "");
  } catch {
    return value;
  }
}

function formatResearchDate(value: string) {
  return new Intl.DateTimeFormat("en", { day: "numeric", month: "short" }).format(new Date(value));
}

function originLabel(origin: SourceContributionMap["sources"][number]["origin"]) {
  if (origin === "project_brief") return "Project brief";
  if (origin === "website_inspection") return "Website inspection";
  return "Parallel Search";
}

function traceStatusLabel(status: GenerationTrace["status"]) {
  if (status === "succeeded") return "Complete";
  if (status === "awaiting_approval") return "Waiting for approval";
  if (status === "awaiting_retry") return "Waiting to retry";
  if (status === "failed") return "Failed";
  return "In progress";
}

function variantLabel(variant: VisualVariantId) {
  if (variant === "editorial_story") return "Editorial Story";
  if (variant === "product_spotlight") return "Product Spotlight";
  return "Technical Proof";
}

function variantDecisionLabel(plan: StyleDirectionPlan) {
  if (plan.decision.outcome === "recommended") return "ADK recommendation";
  if (plan.decision.outcome === "accepted") return "Recommendation accepted";
  return "User override";
}

function formatElapsed(value: number | null) {
  if (value === null) return "No timing";
  if (value < 1_000) return `${value} ms`;
  return `${(value / 1_000).toFixed(value < 10_000 ? 1 : 0)} s`;
}

function formatTraceDate(value: string) {
  return new Intl.DateTimeFormat("en", { hour: "numeric", minute: "2-digit", second: "2-digit" }).format(new Date(value));
}
