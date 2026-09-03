from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Protocol

from demodirector_contracts import (
    AudioClip,
    BriefCoverageReport,
    CaptionClip,
    CaptionStyleConfig,
    CaptionTrack,
    InteractionEvent,
    MissingRequirementRepairProposal,
    MissingRequirementRepairResult,
    NarrationJobResult,
    NarrationSegment,
    NarrationVoiceConfig,
    RenderConfig,
    RenderResult,
    Scene,
    SceneCaptureResult,
    SceneClip,
    Storyboard,
    Timeline,
    ZoomClip,
)

from demodirector_api.brief_coverage import BriefCoverageService
from demodirector_api.google_ai import StructuredAIService


class RepairValidationError(ValueError):
    """Raised when a repair proposal is not safe for deterministic execution."""


class CaptureWorker(Protocol):
    def capture_scene(self, scene: Scene) -> SceneCaptureResult: ...


class NarrationGenerator(Protocol):
    def generate(
        self,
        scenes: Sequence[Scene],
        voice: NarrationVoiceConfig,
        *,
        capture_clip_paths: Sequence[str] = (),
    ) -> NarrationJobResult: ...


class CaptionGenerator(Protocol):
    def generate(
        self,
        narration_segments: Sequence[NarrationSegment],
        style: CaptionStyleConfig,
    ) -> list[CaptionTrack]: ...


class CameraGenerator(Protocol):
    def generate(
        self,
        events: Sequence[InteractionEvent],
        duration_ms: int,
        *,
        manual_clips: Sequence[ZoomClip] = (),
    ) -> list[ZoomClip]: ...


class TimelineRenderer(Protocol):
    def render(self, timeline: Timeline, config: RenderConfig) -> RenderResult: ...


class MissingRequirementRepairService:
    def __init__(
        self,
        ai_service: StructuredAIService,
        qa_service: BriefCoverageService,
        capture_worker: CaptureWorker,
        narration_service: NarrationGenerator,
        caption_service: CaptionGenerator,
        camera_service: CameraGenerator,
        renderer: TimelineRenderer,
    ) -> None:
        self.ai_service = ai_service
        self.qa_service = qa_service
        self.capture_worker = capture_worker
        self.narration_service = narration_service
        self.caption_service = caption_service
        self.camera_service = camera_service
        self.renderer = renderer

    def repair(
        self,
        *,
        project_id: str,
        brief: str,
        requirement_id: str,
        storyboard: Storyboard,
        timeline: Timeline,
        qa_report: BriefCoverageReport,
        capture_evidence: Mapping[str, Sequence[str]],
        max_duration_seconds: float,
        approve_duration_overage: bool = False,
        render_config: RenderConfig | None = None,
    ) -> MissingRequirementRepairResult:
        self._validate_inputs(project_id, requirement_id, storyboard, timeline, qa_report)
        proposal = self.ai_service.generate_structured(
            prompt=self._proposal_prompt(requirement_id, storyboard, qa_report),
            response_model=MissingRequirementRepairProposal,
        )
        self._validate_proposal(proposal, requirement_id, storyboard)
        added_duration_ms = round(proposal.scene.duration_seconds * 1_000)
        if (
            timeline.duration_ms + added_duration_ms > round(max_duration_seconds * 1_000)
            and not approve_duration_overage
        ):
            return MissingRequirementRepairResult(
                project_id=project_id,
                requirement_id=requirement_id,
                status="requires_approval",
                storyboard=storyboard,
                timeline=timeline,
                qa_report=qa_report,
                message=(
                    "The repair would exceed the requested duration. Approve the duration "
                    "overage before capture begins."
                ),
            )

        capture = self.capture_worker.capture_scene(proposal.scene)
        if capture.status != "succeeded" or capture.raw_clip_path is None:
            return MissingRequirementRepairResult(
                project_id=project_id,
                requirement_id=requirement_id,
                status="failed",
                storyboard=storyboard,
                timeline=timeline,
                qa_report=qa_report,
                capture_result=capture,
                message=capture.error or "The repair scene could not be captured.",
            )

        voice = timeline.voice_config or NarrationVoiceConfig()
        narration = self.narration_service.generate(
            [proposal.scene],
            voice,
            capture_clip_paths=[capture.raw_clip_path],
        )
        if narration.status != "succeeded" or not narration.segments:
            return MissingRequirementRepairResult(
                project_id=project_id,
                requirement_id=requirement_id,
                status="failed",
                storyboard=storyboard,
                timeline=timeline,
                qa_report=qa_report,
                capture_result=capture,
                message=narration.error or "Repair narration generation failed.",
            )

        insertion_ms = _insertion_time(timeline, proposal.insert_after_scene_id)
        captions = self.caption_service.generate(
            narration.segments,
            CaptionStyleConfig(),
        )
        zooms = self.camera_service.generate(capture.interaction_events, added_duration_ms)
        repaired_timeline = _insert_timeline_media(
            timeline,
            proposal.scene,
            capture.raw_clip_path,
            narration,
            captions,
            zooms,
            capture.interaction_events,
            insertion_ms,
            added_duration_ms,
        )
        repaired_storyboard = _insert_storyboard_scene(
            storyboard,
            proposal.scene,
            proposal.insert_after_scene_id,
        )
        rendered = self.renderer.render(
            repaired_timeline,
            render_config
            or RenderConfig(output_filename=f"repair-{requirement_id}.mp4"),
        )
        if rendered.status != "succeeded":
            return MissingRequirementRepairResult(
                project_id=project_id,
                requirement_id=requirement_id,
                status="failed",
                storyboard=repaired_storyboard,
                timeline=repaired_timeline,
                qa_report=qa_report,
                capture_result=capture,
                render_result=rendered,
                message=rendered.error or "Repair render failed.",
            )

        updated_evidence = {key: list(value) for key, value in capture_evidence.items()}
        updated_evidence[proposal.scene.id] = (
            proposal.scene.expected_evidence or ["Repair scene captured successfully"]
        )
        repaired_report = self.qa_service.analyze(
            project_id,
            brief,
            repaired_storyboard,
            repaired_timeline,
            updated_evidence,
        )
        target = next(
            check
            for check in repaired_report.checks
            if check.requirement_id == requirement_id
        )
        if target.status != "covered":
            return MissingRequirementRepairResult(
                project_id=project_id,
                requirement_id=requirement_id,
                status="failed",
                storyboard=repaired_storyboard,
                timeline=repaired_timeline,
                qa_report=repaired_report,
                capture_result=capture,
                render_result=rendered,
                message="The repair rendered, but Demo QA still found incomplete coverage.",
            )
        return MissingRequirementRepairResult(
            project_id=project_id,
            requirement_id=requirement_id,
            status="succeeded",
            storyboard=repaired_storyboard,
            timeline=repaired_timeline,
            qa_report=repaired_report,
            capture_result=capture,
            render_result=rendered,
            message="The missing requirement was captured, inserted, rendered, and verified.",
        )

    @staticmethod
    def _validate_inputs(
        project_id: str,
        requirement_id: str,
        storyboard: Storyboard,
        timeline: Timeline,
        qa_report: BriefCoverageReport,
    ) -> None:
        if {storyboard.project_id, timeline.project_id, qa_report.project_id} != {project_id}:
            raise RepairValidationError("Repair inputs must belong to the requested project.")
        target = next(
            (check for check in qa_report.checks if check.requirement_id == requirement_id),
            None,
        )
        if target is None or target.status != "missing":
            raise RepairValidationError("Repair target must be a missing brief requirement.")

    @staticmethod
    def _validate_proposal(
        proposal: MissingRequirementRepairProposal,
        requirement_id: str,
        storyboard: Storyboard,
    ) -> None:
        known_ids = {scene.id for scene in storyboard.scenes}
        if proposal.requirement_id != requirement_id:
            raise RepairValidationError("Repair proposal changed the target requirement.")
        if proposal.scene.id in known_ids:
            raise RepairValidationError("Repair scene ID must be new.")
        if proposal.scene.storyboard_id != storyboard.id:
            raise RepairValidationError("Repair scene must belong to the current storyboard.")
        if (
            proposal.insert_after_scene_id is not None
            and proposal.insert_after_scene_id not in known_ids
        ):
            raise RepairValidationError("Repair proposal references an unknown insertion scene.")

    @staticmethod
    def _proposal_prompt(
        requirement_id: str,
        storyboard: Storyboard,
        qa_report: BriefCoverageReport,
    ) -> str:
        target = next(
            check for check in qa_report.checks if check.requirement_id == requirement_id
        )
        context = {
            "requirement": target.model_dump(mode="json"),
            "storyboard_id": storyboard.id,
            "existing_scenes": [
                {
                    "id": scene.id,
                    "order": scene.order,
                    "title": scene.title,
                    "objective": scene.objective,
                }
                for scene in storyboard.scenes
            ],
        }
        return (
            "Create one typed repair scene for the selected missing requirement. Use only "
            "deterministic CaptureActions, preserve the current storyboard ID, use a new scene "
            "ID, and choose an existing scene as the insertion anchor when appropriate. Return "
            "one MissingRequirementRepairProposal only. Context: "
            f"{json.dumps(context, separators=(',', ':'))}"
        )


def _insert_storyboard_scene(
    storyboard: Storyboard,
    repair_scene: Scene,
    insert_after_scene_id: str | None,
) -> Storyboard:
    ordered = sorted(storyboard.scenes, key=lambda scene: scene.order)
    insert_index = len(ordered)
    if insert_after_scene_id is not None:
        insert_index = next(
            index + 1 for index, scene in enumerate(ordered) if scene.id == insert_after_scene_id
        )
    combined = [*ordered[:insert_index], repair_scene, *ordered[insert_index:]]
    normalized = [scene.model_copy(update={"order": index}) for index, scene in enumerate(combined)]
    return storyboard.model_copy(
        update={
            "version": storyboard.version + 1,
            "total_duration_seconds": sum(scene.duration_seconds for scene in normalized),
            "status": "captured",
            "scenes": normalized,
        }
    )


def _insertion_time(timeline: Timeline, insert_after_scene_id: str | None) -> int:
    if insert_after_scene_id is None:
        return timeline.duration_ms
    scene = next(
        (clip for clip in timeline.scene_clips if clip.scene_id == insert_after_scene_id),
        None,
    )
    if scene is None:
        raise RepairValidationError("Timeline is missing the repair insertion scene.")
    return scene.end_ms


def _shift_clip[ClipType: (SceneClip, CaptionClip, ZoomClip, AudioClip)](
    clip: ClipType,
    insertion_ms: int,
    delta_ms: int,
) -> ClipType:
    start_ms = clip.start_ms
    if start_ms < insertion_ms:
        return clip
    return clip.model_copy(
        update={"start_ms": start_ms + delta_ms, "end_ms": clip.end_ms + delta_ms}
    )


def _insert_timeline_media(
    timeline: Timeline,
    scene: Scene,
    video_path: str,
    narration: NarrationJobResult,
    caption_tracks: Sequence[CaptionTrack],
    zooms: Sequence[ZoomClip],
    cursor_events: Sequence[InteractionEvent],
    insertion_ms: int,
    duration_ms: int,
) -> Timeline:
    shifted_scenes = [
        _shift_clip(clip, insertion_ms, duration_ms) for clip in timeline.scene_clips
    ]
    shifted_captions = [
        _shift_clip(clip, insertion_ms, duration_ms) for clip in timeline.caption_clips
    ]
    shifted_zooms = [_shift_clip(clip, insertion_ms, duration_ms) for clip in timeline.zoom_clips]
    shifted_audio = [_shift_clip(clip, insertion_ms, duration_ms) for clip in timeline.audio_clips]
    shifted_cursor_events = [
        event.model_copy(
            update={"timestamp_ms": event.timestamp_ms + duration_ms}
        )
        if event.timestamp_ms >= insertion_ms
        else event
        for event in timeline.cursor_events
    ]
    repair_captions = [
        CaptionClip(
            id=clip.id,
            scene_id=scene.id,
            start_ms=insertion_ms + clip.start_ms,
            end_ms=insertion_ms + clip.end_ms,
            text=clip.text,
        )
        for track in caption_tracks
        for clip in track.clips
    ]
    repair_zooms = [
        clip.model_copy(
            update={
                "id": f"repair-{clip.id}",
                "start_ms": insertion_ms + clip.start_ms,
                "end_ms": insertion_ms + clip.end_ms,
            }
        )
        for clip in zooms
    ]
    repair_cursor_events = [
        event.model_copy(
            update={
                "scene_id": scene.id,
                "timestamp_ms": insertion_ms + event.timestamp_ms,
            }
        )
        for event in cursor_events
        if event.x is not None and event.y is not None and event.timestamp_ms <= duration_ms
    ]
    segment = narration.segments[0]
    audio_duration = min(duration_ms, segment.duration_ms)
    repair_audio = AudioClip(
        id=f"audio-{scene.id}",
        scene_id=scene.id,
        start_ms=insertion_ms,
        end_ms=insertion_ms + audio_duration,
        source_uri=segment.audio_path,
    )
    repair_scene = SceneClip(
        id=f"scene-clip-{scene.id}",
        scene_id=scene.id,
        start_ms=insertion_ms,
        end_ms=insertion_ms + duration_ms,
        source_uri=video_path,
    )
    return Timeline(
        project_id=timeline.project_id,
        duration_ms=timeline.duration_ms + duration_ms,
        scene_clips=sorted(
            [*shifted_scenes, repair_scene], key=lambda clip: (clip.start_ms, clip.id)
        ),
        caption_clips=sorted(
            [*shifted_captions, *repair_captions], key=lambda clip: (clip.start_ms, clip.id)
        ),
        zoom_clips=sorted(
            [*shifted_zooms, *repair_zooms], key=lambda clip: (clip.start_ms, clip.id)
        ),
        cursor_events=sorted(
            [*shifted_cursor_events, *repair_cursor_events],
            key=lambda event: event.timestamp_ms,
        ),
        audio_clips=sorted(
            [*shifted_audio, repair_audio], key=lambda clip: (clip.start_ms, clip.id)
        ),
        narration_overrides=timeline.narration_overrides,
        voice_config=timeline.voice_config,
        cta_text=timeline.cta_text,
    )
