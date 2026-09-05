from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from demodirector_contracts import (
    AudioClip,
    CaptionClip,
    EditOperation,
    EditPlan,
    InteractionEvent,
    NarrationVoiceConfig,
    SceneClip,
    Timeline,
    TimelineHistoryState,
    VideoPresentationConfig,
    ZoomClip,
)

from demodirector_api.edit_planner import EditPlanValidationError, validate_edit_plan
from demodirector_api.repositories import TimelineRepository, TimelineVersionConflict


class TimelineEditError(ValueError):
    """Raised when a timeline edit cannot be applied deterministically."""


class TimelineEditService:
    def __init__(self, repository: TimelineRepository) -> None:
        self.repository = repository

    def apply(
        self,
        base_timeline: Timeline,
        expected_version: int,
        operations: Sequence[EditOperation],
        summary: str,
    ) -> TimelineHistoryState:
        state = self.repository.current(base_timeline.project_id)
        if state is None:
            if expected_version != 0:
                raise TimelineVersionConflict("Timeline history has not been initialized.")
            state = self.repository.initialize(base_timeline)
        elif expected_version == 0:
            raise TimelineVersionConflict("Timeline already exists; reload before applying edits.")
        if state.current.version != (1 if expected_version == 0 else expected_version):
            raise TimelineVersionConflict(
                "Timeline changed; reload before applying proposed edits."
            )
        current = state.current.timeline
        plan = EditPlan(
            supported=True,
            summary=summary,
            explanation="Validated transaction requested by the user.",
            operations=list(operations),
        )
        try:
            validate_edit_plan(plan, current)
            updated = apply_operations(current, operations)
        except (EditPlanValidationError, ValueError) as error:
            raise TimelineEditError(str(error)) from error
        return self.repository.commit(
            state.current.version,
            updated,
            summary,
            list(dict.fromkeys(operation.target_id for operation in operations)),
        )


def apply_operations(timeline: Timeline, operations: Sequence[EditOperation]) -> Timeline:
    updated = timeline.model_copy(deep=True)
    for operation in operations:
        updated = _apply_operation(updated, operation)
    return Timeline.model_validate(updated.model_dump())


def _apply_operation(timeline: Timeline, operation: EditOperation) -> Timeline:
    kind = operation.operation_type
    arguments = operation.arguments
    if kind == "trim_scene":
        scene = next(clip for clip in timeline.scene_clips if clip.id == operation.target_id)
        start = cast(int, arguments["start_ms"])
        end = cast(int, arguments["end_ms"])
        return _trim_scene(timeline, scene, start, end)
    if kind == "delete_scene":
        return _delete_scene(timeline, operation.target_id)
    if kind == "reorder_scene":
        return _reorder_scene(
            timeline,
            operation.target_id,
            cast(int, arguments["new_index"]),
        )
    if kind == "update_narration":
        overrides = {
            **timeline.narration_overrides,
            operation.target_id: str(arguments["narration"]),
        }
        return timeline.model_copy(update={"narration_overrides": overrides})
    if kind == "add_zoom":
        zoom = ZoomClip.model_validate({**arguments, "source": "prompt_edit"})
        return timeline.model_copy(update={"zoom_clips": [*timeline.zoom_clips, zoom]})
    if kind == "update_zoom":
        zooms = [
            ZoomClip.model_validate({**clip.model_dump(), **arguments, "source": "prompt_edit"})
            if clip.id == operation.target_id
            else clip
            for clip in timeline.zoom_clips
        ]
        return timeline.model_copy(update={"zoom_clips": zooms})
    if kind == "delete_zoom":
        return timeline.model_copy(
            update={
                "zoom_clips": [
                    clip for clip in timeline.zoom_clips if clip.id != operation.target_id
                ]
            }
        )
    if kind == "add_caption":
        caption = CaptionClip.model_validate(arguments)
        return timeline.model_copy(
            update={"caption_clips": [*timeline.caption_clips, caption]}
        )
    if kind == "update_caption":
        captions = [
            CaptionClip.model_validate({**clip.model_dump(), **arguments})
            if clip.id == operation.target_id
            else clip
            for clip in timeline.caption_clips
        ]
        return timeline.model_copy(update={"caption_clips": captions})
    if kind == "change_voice_config":
        return timeline.model_copy(
            update={"voice_config": NarrationVoiceConfig.model_validate(arguments)}
        )
    if kind == "change_cta_text":
        return timeline.model_copy(update={"cta_text": str(arguments["cta"])})
    if kind == "change_presentation":
        return timeline.model_copy(
            update={
                "presentation": VideoPresentationConfig.model_validate(
                    {**timeline.presentation.model_dump(), **arguments}
                )
            }
        )
    raise TimelineEditError(f"Unsupported timeline edit operation: {kind}")


def _trim_scene(
    timeline: Timeline,
    scene: SceneClip,
    trim_start: int,
    trim_end: int,
) -> Timeline:
    old_duration = scene.end_ms - scene.start_ms
    new_duration = trim_end - trim_start
    leading_removed = trim_start - scene.start_ms
    removed = old_duration - new_duration
    new_end = scene.start_ms + new_duration

    def shift(start: int, end: int) -> tuple[int, int]:
        if start >= scene.end_ms:
            return start - removed, end - removed
        return start, end

    scenes = []
    for clip in timeline.scene_clips:
        start, end = shift(clip.start_ms, clip.end_ms)
        scenes.append(
            clip.model_copy(
                update={
                    "start_ms": start,
                    "end_ms": new_end if clip.id == scene.id else end,
                    "source_start_ms": (
                        clip.source_start_ms + leading_removed
                        if clip.id == scene.id
                        else clip.source_start_ms
                    ),
                }
            )
        )
    captions = _trim_scene_track(timeline.caption_clips, scene, new_end, removed)
    audio = _trim_scene_track(timeline.audio_clips, scene, new_end, removed)
    zooms = [
        clip.model_copy(
            update={
                "start_ms": shift(clip.start_ms, clip.end_ms)[0],
                "end_ms": shift(clip.start_ms, clip.end_ms)[1],
            }
        )
        for clip in timeline.zoom_clips
        if clip.end_ms <= new_end or clip.start_ms >= scene.end_ms
    ]
    cursor_events = [
        event.model_copy(update={"timestamp_ms": event.timestamp_ms - removed})
        if event.timestamp_ms >= scene.end_ms
        else event
        for event in timeline.cursor_events
        if not (new_end <= event.timestamp_ms < scene.end_ms)
    ]
    return timeline.model_copy(
        update={
            "duration_ms": timeline.duration_ms - removed,
            "scene_clips": scenes,
            "caption_clips": captions,
            "audio_clips": audio,
            "zoom_clips": zooms,
            "cursor_events": cursor_events,
        }
    )


def _trim_scene_track[T: (CaptionClip, AudioClip)](
    clips: Sequence[T],
    scene: SceneClip,
    new_end: int,
    removed: int,
) -> list[T]:
    result: list[T] = []
    for clip in clips:
        if clip.scene_id == scene.scene_id:
            if clip.start_ms >= new_end:
                continue
            result.append(clip.model_copy(update={"end_ms": min(clip.end_ms, new_end)}))
        elif clip.start_ms >= scene.end_ms:
            result.append(
                clip.model_copy(
                    update={
                        "start_ms": clip.start_ms - removed,
                        "end_ms": clip.end_ms - removed,
                    }
                )
            )
        else:
            result.append(clip)
    return result


def _delete_scene(timeline: Timeline, scene_clip_id: str) -> Timeline:
    scene = next(clip for clip in timeline.scene_clips if clip.id == scene_clip_id)
    if len(timeline.scene_clips) <= 1:
        raise TimelineEditError("The final scene may not be deleted.")
    duration = scene.end_ms - scene.start_ms

    def shift_clip[T: (SceneClip, CaptionClip, AudioClip, ZoomClip)](clip: T) -> T:
        if clip.start_ms >= scene.end_ms:
            return clip.model_copy(
                update={
                    "start_ms": clip.start_ms - duration,
                    "end_ms": clip.end_ms - duration,
                }
            )
        return clip

    def shift_cursor(event: InteractionEvent) -> InteractionEvent:
        if event.timestamp_ms >= scene.end_ms:
            return event.model_copy(update={"timestamp_ms": event.timestamp_ms - duration})
        return event

    return timeline.model_copy(
        update={
            "duration_ms": timeline.duration_ms - duration,
            "scene_clips": [
                shift_clip(clip)
                for clip in timeline.scene_clips
                if clip.id != scene_clip_id
            ],
            "caption_clips": [
                shift_clip(clip)
                for clip in timeline.caption_clips
                if clip.scene_id != scene.scene_id
            ],
            "audio_clips": [
                shift_clip(clip)
                for clip in timeline.audio_clips
                if clip.scene_id != scene.scene_id
            ],
            "zoom_clips": [
                shift_clip(clip)
                for clip in timeline.zoom_clips
                if clip.end_ms <= scene.start_ms or clip.start_ms >= scene.end_ms
            ],
            "cursor_events": [
                shift_cursor(event)
                for event in timeline.cursor_events
                if event.scene_id != scene.scene_id
                and not (scene.start_ms <= event.timestamp_ms < scene.end_ms)
            ],
        }
    )


def _reorder_scene(timeline: Timeline, scene_clip_id: str, new_index: int) -> Timeline:
    ordered = sorted(timeline.scene_clips, key=lambda clip: clip.start_ms)
    current_index = next(index for index, clip in enumerate(ordered) if clip.id == scene_clip_id)
    moved = ordered.pop(current_index)
    ordered.insert(new_index, moved)
    cursor = 0
    offsets: dict[str, int] = {}
    scenes: list[SceneClip] = []
    for clip in ordered:
        duration = clip.end_ms - clip.start_ms
        offsets[clip.scene_id] = cursor - clip.start_ms
        scenes.append(clip.model_copy(update={"start_ms": cursor, "end_ms": cursor + duration}))
        cursor += duration

    def shift_scene_clip[T: (CaptionClip, AudioClip)](clip: T) -> T:
        delta = offsets.get(clip.scene_id, 0)
        return clip.model_copy(
            update={"start_ms": clip.start_ms + delta, "end_ms": clip.end_ms + delta}
        )

    def shift_cursor(event: InteractionEvent) -> InteractionEvent:
        delta = offsets.get(event.scene_id or "", 0)
        return event.model_copy(update={"timestamp_ms": event.timestamp_ms + delta})

    return timeline.model_copy(
        update={
            "scene_clips": scenes,
            "caption_clips": [shift_scene_clip(clip) for clip in timeline.caption_clips],
            "audio_clips": [shift_scene_clip(clip) for clip in timeline.audio_clips],
            "cursor_events": sorted(
                [shift_cursor(event) for event in timeline.cursor_events],
                key=lambda event: event.timestamp_ms,
            ),
        }
    )
