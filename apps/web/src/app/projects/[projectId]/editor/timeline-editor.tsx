"use client";

import {
  editPlanSchema,
  projectResearchResponseSchema,
  projectSchema,
  runtimeProvenanceSchema,
  timelineHistoryStateSchema,
  timelineSchema,
  videoExportSchema,
  type EditPlan,
  type EditOperation,
  type Project,
  type ProjectResearchResponse,
  type RuntimeProvenance,
  type SceneClip,
  type Timeline,
  type VideoExport,
  type ZoomClip,
} from "@demodirector/contracts";
import Link from "next/link";
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

type EditorMode = "setup" | "sources" | "layout" | "cut" | "zoom" | "overlay" | "captions" | "audio" | "adjust";
type PresentationTemplate = Timeline["presentation"]["template"];

const editorModes: Array<{ id: EditorMode; label: string }> = [
  { id: "setup", label: "Setup" },
  { id: "sources", label: "Sources" },
  { id: "layout", label: "Layout" },
  { id: "cut", label: "Cut" },
  { id: "zoom", label: "Zoom" },
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
    generatedExport ? "1080p export ready to download" : initialTimeline ? "Timeline ready" : "Loading project timeline",
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
  const [research, setResearch] = useState<ProjectResearchResponse | null>(null);
  const [runtimeProvenance, setRuntimeProvenance] = useState<RuntimeProvenance | null>(null);
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
              : "1080p export ready to play"
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
      fetch(`/api/projects/${projectId}/research`, { cache: "no-store" }),
      fetch("/api/runtime/provenance", { cache: "no-store" }),
    ]).then(async ([researchResponse, runtimeResponse]) => {
      const parsedResearch = projectResearchResponseSchema.safeParse(await researchResponse.json());
      const parsedRuntime = runtimeProvenanceSchema.safeParse(await runtimeResponse.json());
      if (!researchResponse.ok || !parsedResearch.success || !runtimeResponse.ok || !parsedRuntime.success) {
        throw new Error("Invalid source provenance");
      }
      if (!active) return;
      setResearch(parsedResearch.data);
      setRuntimeProvenance(parsedRuntime.data);
    }).catch(() => {
      if (active) setSourcesError("Source details are temporarily unavailable. The saved project is unchanged.");
    }).finally(() => {
      if (active) setSourcesLoading(false);
    });

    return () => {
      active = false;
    };
  }, [activeMode, projectId]);

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
        </section>
      </main>
    );
  }

  const activeTimeline: Timeline = timeline;
  const previewVideoUrl = isJudgeDemoProject(projectId)
    ? JUDGE_DEMO_VIDEO_URL
    : `/api/projects/${projectId}/exports/latest/video`;
  const selectedZoom = activeTimeline.zoom_clips.find((clip) => clip.id === selectedZoomId) ?? null;

  function persist(next: Timeline, message: string) {
    setTimeline(next);
    window.localStorage.setItem(storageKey(projectId), JSON.stringify(next));
    setStatus(message);
  }

  function deleteSelectedScene() {
    if (!selectedSceneId) return;
    const next = deleteSceneFromTimeline(activeTimeline, selectedSceneId);
    persist(next, "Scene deleted · tracks updated");
    setSelectedSceneId(next.scene_clips[0]?.scene_id ?? null);
  }

  function duplicateSelectedScene() {
    if (!selectedSceneId) return;
    persist(duplicateSceneInTimeline(activeTimeline, selectedSceneId), "Scene duplicated");
  }

  function splitSelectedScene() {
    const scene = activeTimeline.scene_clips.find((clip) => clip.scene_id === selectedSceneId);
    if (!scene || playheadMs <= scene.start_ms || playheadMs >= scene.end_ms) {
      setStatus("Place the playhead inside the selected scene to split it.");
      return;
    }
    const second: SceneClip = {
      ...scene,
      id: `${scene.id}-split`,
      scene_id: `${scene.scene_id}-split`,
      start_ms: playheadMs,
    };
    const first = { ...scene, end_ms: playheadMs };
    persist(
      timelineSchema.parse({
        ...activeTimeline,
        scene_clips: activeTimeline.scene_clips.flatMap((clip) =>
          clip.id === scene.id ? [first, second] : [clip],
        ),
      }),
      "Scene split at playhead",
    );
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
  ) {
    setSavingZoom(true);
    setStatus(
      operation.operation_type === "delete_zoom"
        ? "Removing zoom…"
        : operation.operation_type === "change_presentation"
          ? "Applying video frame…"
          : "Saving zoom…",
    );
    try {
      const response = await fetch(`/api/projects/${projectId}/timeline/apply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          expected_version: timelineVersion,
          base_timeline: activeTimeline,
          summary: operation.operation_type === "delete_zoom"
            ? "Remove zoom"
            : operation.operation_type === "change_presentation"
              ? "Change video frame"
              : "Update zoom framing",
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
        arguments: { template },
        rationale: "Apply the user-selected video presentation frame.",
      },
      `${template === "edge_to_edge" ? "Edge-to-edge" : template === "soft_frame" ? "Soft frame" : "Spotlight frame"} saved · export again to update the video`,
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
    setStatus("Rendering 1080p export…");
    try {
      const response = await fetch(`/api/projects/${projectId}/exports`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ timeline, quality: "1080p" }),
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
          ? "1080p export ready to download"
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
            {exporting ? "Exporting…" : videoExport ? "Export changes" : "Export 1080p"}
          </button>
        )}
      </header>

      <section className="editor-preview" id="editor-preview" aria-label="Synchronized preview">
        <div className="editor-preview-player">
        <div className={`preview-stage preview-template-${videoExport ? "rendered" : timeline.presentation.template}`}>
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
          {activeMode === "setup" && <>
            <div className="inspector-heading"><h2>Project setup</h2><p>Recording details</p></div>
            <dl className="editor-detail-list">
              <dt>Project</dt><dd>{project?.name ?? "Demo project"}</dd>
              <dt>Source</dt><dd>{project ? domainLabel(project.website_url) : "Not available"}</dd>
              <dt>Duration</dt><dd>{Math.round(timeline.duration_ms / 1_000)} seconds</dd>
              <dt>Scenes</dt><dd>{timeline.scene_clips.length}</dd>
            </dl>
          </>}

          {activeMode === "sources" && <>
            <div className="inspector-heading">
              <h2>Research sources</h2>
              <p>{research ? `${research.sources.length} saved` : "Project evidence"}</p>
            </div>
            {sourcesLoading && <p className="sources-state" role="status">Loading saved evidence and runtime details…</p>}
            {sourcesError && <p className="sources-state error" role="alert">{sourcesError}</p>}
            {!sourcesLoading && !sourcesError && research && runtimeProvenance && <>
              <section className="sources-section" aria-label="Saved evidence">
                <h3>Saved evidence</h3>
                {research.sources.length > 0 ? (
                  <div className="source-list">
                    {research.sources.map((source) => <article className="source-item" key={source.id}>
                      <header>
                        <span>{source.source_type === "partner_search" ? "Parallel Search" : source.source_type === "website" ? "Website inspection" : "Project brief"}</span>
                        <time dateTime={source.retrieved_at}>{formatResearchDate(source.retrieved_at)}</time>
                      </header>
                      <a href={source.url} rel="noreferrer" target="_blank">{source.title}</a>
                      <p>{source.snippet}</p>
                    </article>)}
                  </div>
                ) : <p className="sources-state">No research sources have been saved for this project yet.</p>}
              </section>

              <section className="sources-section" aria-label="Generation pipeline">
                <h3>Generation pipeline</h3>
                <ul className="pipeline-list">
                  <PipelineRow
                    detail={`Direct web research · ${runtimeProvenance.research.mode} mode · ${research.sources.filter((source) => source.source_type === "partner_search").length} saved`}
                    label="Parallel Search"
                    status={runtimeProvenance.research.status === "ready" ? "Ready" : "Unavailable"}
                  />
                  <PipelineRow
                    detail={runtimeProvenance.ai.model}
                    label="Gemini reasoning"
                    status={runtimeProvenance.ai.status === "ready" ? "Ready" : "Unavailable"}
                  />
                  <PipelineRow
                    detail={runtimeProvenance.ai.agent}
                    label="Google ADK"
                    status={runtimeProvenance.ai.status === "ready" ? "Ready" : "Unavailable"}
                  />
                  <PipelineRow
                    detail={`${runtimeProvenance.ai.tts_model} · ${timeline.audio_clips.length} audio track${timeline.audio_clips.length === 1 ? "" : "s"}`}
                    label="Gemini narration"
                    status={timeline.audio_clips.length > 0 ? "Used" : "Not generated"}
                  />
                  <PipelineRow
                    detail={`${timeline.scene_clips.length} continuous recording${timeline.scene_clips.length === 1 ? "" : "s"}`}
                    label="Browser capture"
                    status={timeline.scene_clips.length > 0 ? "Used" : "Not captured"}
                  />
                  <PipelineRow
                    detail={videoExport ? `${videoExport.quality} · ${videoExport.width}×${videoExport.height}` : "No completed export"}
                    label="FFmpeg render"
                    status={videoExport?.status === "succeeded" ? "Used" : "Not rendered"}
                  />
                </ul>
              </section>
            </>}
          </>}

          {activeMode === "layout" && <>
            <div className="inspector-heading"><h2>Layout</h2><p>Canvas and framing</p></div>
            <button className="layout-option selected" type="button"><span>16:9</span><small>1920 × 1080 landscape</small></button>
            <p className="camera-note">Exports use a full HD canvas. Choose a frame in Overlay to change how the recording sits inside it.</p>
          </>}

          {activeMode === "cut" && <>
            <div className="inspector-heading"><h2>Cut scene</h2><p>{selectedSceneId ?? "No scene selected"}</p></div>
            <div className="cut-actions">
              <button onClick={splitSelectedScene} type="button"><EditorModeIcon mode="cut" />Split at playhead</button>
              <button disabled={timeline.scene_clips.length <= 1} onClick={deleteSelectedScene} type="button">Delete scene</button>
              <button onClick={duplicateSelectedScene} type="button">Duplicate scene</button>
            </div>
            <p className="camera-note">Select a scene in the timeline, then place the playhead before splitting.</p>
          </>}

          {activeMode === "zoom" && <>
            <div className="inspector-heading"><h2>{selectedZoom ? "Zoom clip" : "Select a zoom"}</h2><p>{selectedSceneId ?? "No scene selected"}</p></div>
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

          {activeMode === "overlay" && <>
            <div className="inspector-heading"><h2>Video frame</h2><p>Presentation template</p></div>
            <div className="template-list">
              <TemplateButton active={timeline.presentation.template === "edge_to_edge"} label="Edge-to-edge" onClick={() => void applyPresentation("edge_to_edge")} template="edge_to_edge" />
              <TemplateButton active={timeline.presentation.template === "soft_frame"} label="Soft frame" onClick={() => void applyPresentation("soft_frame")} template="soft_frame" />
              <TemplateButton active={timeline.presentation.template === "spotlight"} label="Spotlight" onClick={() => void applyPresentation("spotlight")} template="spotlight" />
            </div>
            <p className="camera-note">Templates are rendered into the MP4. Export again after changing the frame.</p>
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

function EditorModeIcon({ mode }: { mode: EditorMode }) {
  const paths: Record<EditorMode, React.ReactNode> = {
    setup: <><rect height="14" rx="2" width="16" x="4" y="5" /><path d="M8 3v4M16 3v4M8 17v4M16 17v4" /></>,
    sources: <><path d="M7 3h8l4 4v14H7z" /><path d="M15 3v5h5M10 12h6M10 16h6" /><path d="M4 7v12" /></>,
    layout: <><rect height="16" rx="2" width="18" x="3" y="4" /><path d="M9 4v16M9 10h12" /></>,
    cut: <><circle cx="6" cy="6" r="3" /><circle cx="6" cy="18" r="3" /><path d="m8.6 7.5 11 6.5M8.6 16.5 20 10M14 12l6 6" /></>,
    zoom: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m15.5 15.5 5 5M10.5 7.5v6M7.5 10.5h6" /></>,
    overlay: <><rect height="14" rx="2" width="18" x="3" y="5" /><rect height="8" rx="1" width="10" x="7" y="8" /></>,
    captions: <><rect height="14" rx="3" width="20" x="2" y="4" /><path d="m8 18-3 3v-3M6 9h5M13 9h5M6 13h8" /></>,
    audio: <><path d="M5 9v6M9 6v12M13 4v16M17 7v10M21 10v4" /></>,
    adjust: <><path d="M4 7h10M18 7h2M4 17h2M10 17h10" /><circle cx="16" cy="7" r="2" /><circle cx="8" cy="17" r="2" /></>,
  };
  return <svg aria-hidden="true" fill="none" viewBox="0 0 24 24">{paths[mode]}</svg>;
}

function PipelineRow({ detail, label, status }: { detail: string; label: string; status: string }) {
  return <li><div><b>{label}</b><span>{detail}</span></div><em>{status}</em></li>;
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
