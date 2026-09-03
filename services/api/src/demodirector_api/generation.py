from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

from demodirector_contracts import (
    AudioClip,
    CaptionClip,
    CaptionStyleConfig,
    CaptureAction,
    DemoGenerationResult,
    NarrationJobResult,
    NarrationVoiceConfig,
    ProductUnderstanding,
    Project,
    ResearchSource,
    Scene,
    SceneCaptureResult,
    SceneClip,
    Storyboard,
    Timeline,
    VideoExport,
    WebsiteInspection,
)
from demodirector_worker import AutoCameraService, CaptionService

from demodirector_api.exports import LocalTimelineMediaStore, TimelineMediaStore
from demodirector_api.parallel_search import ResearchRunResult
from demodirector_api.product_understanding import website_sources
from demodirector_api.repositories import (
    ProductUnderstandingRepository,
    ProjectRepository,
    ResearchSourceRepository,
    StoryboardRepository,
    TimelineRepository,
    WebsiteInspectionRepository,
)


class DemoGenerationError(RuntimeError):
    """Raised when a one-click generation stage cannot produce a valid result."""


class DemoGenerationConflict(RuntimeError):
    """Raised when a project is already generating or already owns a timeline."""


class ResearchAnalyzer(Protocol):
    def analyze(self, project: Project) -> ResearchRunResult: ...


class Inspector(Protocol):
    def inspect(
        self,
        *,
        project_id: str,
        website_url: str,
        session_token: str | None = None,
    ) -> WebsiteInspection: ...


class UnderstandingGenerator(Protocol):
    def generate(
        self,
        *,
        project: Project,
        inspection: WebsiteInspection,
        sources: list[ResearchSource],
    ) -> ProductUnderstanding: ...


class StoryboardGenerator(Protocol):
    def generate(
        self,
        *,
        project: Project,
        understanding: ProductUnderstanding,
        sources: list[ResearchSource],
    ) -> Storyboard: ...


class CaptureWorker(Protocol):
    def capture_scene(
        self,
        scene: Scene,
        *,
        session_token: str | None = None,
    ) -> SceneCaptureResult: ...


class NarrationGenerator(Protocol):
    def generate(
        self,
        scenes: Sequence[Scene],
        voice: NarrationVoiceConfig,
        *,
        capture_clip_paths: Sequence[str] = (),
    ) -> NarrationJobResult: ...


class ExportCreator(Protocol):
    def create(
        self,
        project_id: str,
        timeline: Timeline,
        quality: Literal["1080p", "720p"],
    ) -> VideoExport: ...


class DemoGenerationService:
    def __init__(
        self,
        *,
        projects: ProjectRepository,
        research_sources: ResearchSourceRepository,
        inspections: WebsiteInspectionRepository,
        understandings: ProductUnderstandingRepository,
        storyboards: StoryboardRepository,
        timelines: TimelineRepository,
        research: ResearchAnalyzer,
        inspector: Inspector,
        understanding_generator: UnderstandingGenerator,
        storyboard_generator: StoryboardGenerator,
        capture_worker: CaptureWorker,
        narration: NarrationGenerator,
        captions: CaptionService,
        camera: AutoCameraService,
        exports: ExportCreator,
        timeline_media_store: TimelineMediaStore | None = None,
        caption_style: CaptionStyleConfig | None = None,
        voice: NarrationVoiceConfig | None = None,
    ) -> None:
        self.projects = projects
        self.research_sources = research_sources
        self.inspections = inspections
        self.understandings = understandings
        self.storyboards = storyboards
        self.timelines = timelines
        self.research = research
        self.inspector = inspector
        self.understanding_generator = understanding_generator
        self.storyboard_generator = storyboard_generator
        self.capture_worker = capture_worker
        self.narration = narration
        self.captions = captions
        self.camera = camera
        self.exports = exports
        self.timeline_media_store = timeline_media_store or LocalTimelineMediaStore()
        self.caption_style = caption_style or CaptionStyleConfig(enabled=True)
        self.voice = voice or NarrationVoiceConfig()

    def generate(
        self,
        project_id: str,
        *,
        capture_session_token: str | None = None,
    ) -> DemoGenerationResult:
        project = self.projects.get(project_id)
        if project is None:
            raise KeyError("Project not found")
        if project.job_status in {"queued", "running"}:
            raise DemoGenerationConflict("This project is already generating.")
        if self.timelines.current(project_id) is not None:
            raise DemoGenerationConflict("This project already has a generated timeline.")

        stage = "website inspection"
        warnings: list[str] = []
        self._set_status(project_id, "storyboarding", "running")
        try:
            inspection = self.inspections.save(
                self.inspector.inspect(
                    project_id=project.id,
                    website_url=str(project.website_url),
                    session_token=capture_session_token,
                )
            )
            if not inspection.pages:
                raise DemoGenerationError("The website inspection returned no usable pages.")
            if inspection.warning:
                warnings.append(inspection.warning)

            stage = "partner research"
            research = self.research.analyze(project)
            if research.warning:
                warnings.append(research.warning)

            stage = "product understanding"
            self.research_sources.replace_website_sources(
                project.id,
                website_sources(project.id, inspection),
            )
            sources = self.research_sources.list_for_project(project.id)
            understanding = self.understanding_generator.generate(
                project=project,
                inspection=inspection,
                sources=sources,
            )
            self.understandings.save(understanding)

            stage = "storyboard generation"
            storyboard = self.storyboard_generator.generate(
                project=project,
                understanding=understanding,
                sources=sources,
            )
            self.storyboards.save(storyboard)

            stage = "browser capture"
            self._set_status(project.id, "capturing", "running")
            scenes = sorted(storyboard.scenes, key=lambda item: item.order)
            scene_durations = allocate_scene_durations(
                scenes,
                project.requested_duration_seconds * 1_000,
            )
            continuous_scene = prepare_continuous_capture(scenes, scene_durations)
            capture = self.capture_worker.capture_scene(
                continuous_scene,
                session_token=capture_session_token,
            )
            if capture.status != "succeeded" or capture.raw_clip_path is None:
                raise DemoGenerationError(
                    "Continuous browser capture failed: "
                    f"{capture.error or 'no video was recorded.'}"
                )
            self.storyboards.save(storyboard.model_copy(update={"status": "captured"}))

            stage = "narration and timeline assembly"
            self._set_status(project.id, "editing", "running")
            capture_paths = [str(capture.raw_clip_path)]
            narration = self.narration.generate(
                scenes,
                self.voice,
                capture_clip_paths=capture_paths,
            )
            if narration.status != "succeeded" or len(narration.segments) != len(scenes):
                raise DemoGenerationError(narration.error or "Narration generation was incomplete.")
            timeline = assemble_timeline(
                project,
                scenes,
                scene_durations,
                capture,
                narration,
                self.caption_style,
                self.captions,
                self.camera,
            )
            timeline = self.timeline_media_store.persist(timeline)
            history = self.timelines.initialize(timeline)

            stage = "video rendering"
            self._set_status(project.id, "rendering", "running")
            video_export = self.exports.create(project.id, timeline, "1080p")
            if video_export.status != "succeeded":
                raise DemoGenerationError(video_export.error or "The video export failed.")

            completed = self._set_status(project.id, "published", "succeeded")
            return DemoGenerationResult(
                project=completed,
                export=video_export,
                timeline_version=history.current.version,
                warnings=warnings,
            )
        except Exception as error:
            self._set_status(project.id, "failed", "failed")
            if isinstance(error, DemoGenerationError):
                detail = str(error)
            else:
                detail = str(error) or error.__class__.__name__
            raise DemoGenerationError(
                f"Demo generation failed during {stage}: {detail}"
            ) from error

    def _set_status(
        self,
        project_id: str,
        status: Literal[
            "draft",
            "storyboarding",
            "ready",
            "capturing",
            "editing",
            "rendering",
            "published",
            "failed",
        ],
        job_status: Literal["idle", "queued", "running", "succeeded", "failed"],
    ) -> Project:
        current = self.projects.get(project_id)
        if current is None:
            raise KeyError("Project not found")
        updated = current.model_copy(
            update={
                "status": status,
                "job_status": job_status,
                "updated_at": datetime.now(UTC),
            }
        )
        saved = self.projects.update(updated)
        if saved is None:
            raise KeyError("Project not found")
        return saved


def allocate_scene_durations(scenes: Sequence[Scene], total_duration_ms: int) -> list[int]:
    if not scenes or total_duration_ms < len(scenes):
        raise DemoGenerationError("The storyboard cannot fit the requested duration.")
    planned_total = sum(scene.duration_seconds for scene in scenes)
    if planned_total <= 0:
        raise DemoGenerationError("The storyboard duration must be positive.")
    allocated: list[int] = []
    used = 0
    for index, scene in enumerate(scenes):
        if index == len(scenes) - 1:
            duration = total_duration_ms - used
        else:
            duration = max(1, round(total_duration_ms * scene.duration_seconds / planned_total))
            remaining_scenes = len(scenes) - index - 1
            duration = min(duration, total_duration_ms - used - remaining_scenes)
        allocated.append(duration)
        used += duration
    return allocated


def prepare_scene_for_capture(scene: Scene, duration_ms: int) -> Scene:
    normalized_actions = [
        action.model_copy(update={"value": str(scene.capture_plan.start_url)})
        if action.type == "navigate" and not action.value and not action.locator
        else action
        for action in scene.capture_plan.actions
    ]
    hold = CaptureAction(
        type="wait_for",
        value=duration_ms,
        description="Hold the completed scene for its planned duration",
    )
    plan = scene.capture_plan.model_copy(
        update={
            "actions": [*normalized_actions, hold],
            "timeout_seconds": max(
                scene.capture_plan.timeout_seconds,
                math.ceil(duration_ms / 1_000) + 30,
            ),
        }
    )
    return scene.model_copy(update={"capture_plan": plan})


def prepare_continuous_capture(
    scenes: Sequence[Scene],
    scene_durations: Sequence[int],
) -> Scene:
    if not scenes or len(scenes) != len(scene_durations):
        raise DemoGenerationError("Continuous capture requires one duration per scene.")
    if any(duration_ms <= 0 for duration_ms in scene_durations):
        raise DemoGenerationError("Continuous capture durations must be positive.")

    first = scenes[0]
    start_url = str(first.capture_plan.start_url)
    continuous_actions: list[CaptureAction] = []
    for scene, duration_ms in zip(scenes, scene_durations, strict=True):
        for action in scene.capture_plan.actions:
            normalized = (
                action.model_copy(update={"value": str(scene.capture_plan.start_url)})
                if action.type == "navigate" and not action.value and not action.locator
                else action
            )
            target = (
                normalized.value
                if isinstance(normalized.value, str)
                else normalized.locator
            )
            if (
                normalized.type == "navigate"
                and target is not None
                and target.rstrip("/") == start_url.rstrip("/")
            ):
                continue
            continuous_actions.append(normalized)
        continuous_actions.extend(scene.capture_plan.success_assertions)
        continuous_actions.append(
            CaptureAction(
                type="wait_for",
                value=duration_ms,
                description=f"Hold {scene.title} for its planned beat duration",
            )
        )

    total_duration_ms = sum(scene_durations)
    source_ids = list(
        dict.fromkeys(source_id for scene in scenes for source_id in scene.source_ids)
    )
    evidence = list(
        dict.fromkeys(item for scene in scenes for item in scene.expected_evidence)
    )
    timeout_seconds = max(
        max(scene.capture_plan.timeout_seconds for scene in scenes),
        math.ceil(total_duration_ms / 1_000) + 30,
    )
    return Scene(
        id=f"{first.storyboard_id}-continuous",
        storyboard_id=first.storyboard_id,
        order=0,
        title="Continuous product walkthrough",
        objective="Capture every storyboard beat in one uninterrupted browser session.",
        narration=" ".join(scene.narration for scene in scenes),
        source_ids=source_ids,
        capture_plan=first.capture_plan.model_copy(
            update={
                "actions": continuous_actions,
                "success_assertions": [],
                "timeout_seconds": timeout_seconds,
            }
        ),
        expected_evidence=evidence,
        duration_seconds=total_duration_ms / 1_000,
    )


def assemble_timeline(
    project: Project,
    scenes: Sequence[Scene],
    scene_durations: Sequence[int],
    capture: SceneCaptureResult,
    narration: NarrationJobResult,
    caption_style: CaptionStyleConfig,
    captions: CaptionService,
    camera: AutoCameraService,
) -> Timeline:
    caption_tracks = captions.generate(narration.segments, caption_style)
    if capture.raw_clip_path is None:
        raise DemoGenerationError("The continuous walkthrough has no capture file.")
    total_duration_ms = sum(scene_durations)
    scene_clips = [
        SceneClip(
            id=f"scene-clip-{capture.scene_id}",
            scene_id=capture.scene_id,
            start_ms=0,
            end_ms=total_duration_ms,
            source_uri=str(Path(capture.raw_clip_path).resolve()),
        )
    ]
    audio_clips: list[AudioClip] = []
    caption_clips: list[CaptionClip] = []
    offset = 0
    for scene, duration_ms, segment, caption_track in zip(
        scenes,
        scene_durations,
        narration.segments,
        caption_tracks,
        strict=True,
    ):
        audio_duration = min(duration_ms, segment.duration_ms)
        audio_clips.append(
            AudioClip(
                id=f"audio-{scene.id}",
                scene_id=scene.id,
                start_ms=offset,
                end_ms=offset + audio_duration,
                source_uri=str(Path(segment.audio_path).resolve()),
            )
        )
        for clip in caption_track.clips:
            if clip.start_ms >= duration_ms:
                continue
            caption_clips.append(
                clip.model_copy(
                    update={
                        "start_ms": offset + clip.start_ms,
                        "end_ms": offset + min(duration_ms, clip.end_ms),
                    }
                )
            )
        offset += duration_ms

    usable_events = [
        event
        for event in capture.interaction_events
        if event.x is not None
        and event.y is not None
        and event.timestamp_ms <= total_duration_ms
    ]
    zoom_clips = [
        clip.model_copy(update={"id": f"zoom-continuous-{index + 1}"})
        for index, clip in enumerate(camera.generate(usable_events, total_duration_ms))
    ]
    cursor_events = [
        event.model_copy(
            update={
                "scene_id": _scene_id_at(
                    event.timestamp_ms,
                    scenes,
                    scene_durations,
                )
            }
        )
        for event in usable_events
    ]

    return Timeline(
        project_id=project.id,
        duration_ms=total_duration_ms,
        scene_clips=scene_clips,
        caption_clips=caption_clips,
        zoom_clips=zoom_clips,
        cursor_events=cursor_events,
        audio_clips=audio_clips,
        voice_config=narration.voice_config,
        cta_text=project.cta,
    )


def _scene_id_at(
    timestamp_ms: int,
    scenes: Sequence[Scene],
    scene_durations: Sequence[int],
) -> str:
    boundary = 0
    for scene, duration_ms in zip(scenes, scene_durations, strict=True):
        boundary += duration_ms
        if timestamp_ms < boundary:
            return str(scene.id)
    return str(scenes[-1].id)
