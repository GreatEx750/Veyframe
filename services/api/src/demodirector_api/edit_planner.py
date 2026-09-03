from __future__ import annotations

import json
from collections.abc import Mapping

from demodirector_contracts import (
    CaptionClip,
    EditOperation,
    EditPlan,
    NarrationVoiceConfig,
    SceneClip,
    Timeline,
    VideoPresentationConfig,
    ZoomClip,
)
from pydantic import JsonValue

from demodirector_api.google_ai import StructuredAIService


class EditPlanValidationError(ValueError):
    """Raised when proposed operations do not fit the current typed timeline."""


class EditPlannerService:
    def __init__(self, ai_service: StructuredAIService) -> None:
        self.ai_service = ai_service

    def plan(self, timeline: Timeline, instruction: str) -> EditPlan:
        if not instruction.strip():
            raise ValueError("edit instruction must not be empty")
        plan = self.ai_service.generate_structured(
            prompt=build_edit_prompt(timeline, instruction),
            response_model=EditPlan,
        )
        validate_edit_plan(plan, timeline)
        return plan


def build_edit_prompt(timeline: Timeline, instruction: str) -> str:
    summary = {
        "project_id": timeline.project_id,
        "duration_ms": timeline.duration_ms,
        "scene_clips": [
            {
                "id": clip.id,
                "scene_id": clip.scene_id,
                "start_ms": clip.start_ms,
                "end_ms": clip.end_ms,
            }
            for clip in timeline.scene_clips
        ],
        "caption_clips": [clip.model_dump(exclude={"text"}) for clip in timeline.caption_clips],
        "zoom_clips": [clip.model_dump() for clip in timeline.zoom_clips],
        "audio_clips": [
            {
                "id": clip.id,
                "scene_id": clip.scene_id,
                "start_ms": clip.start_ms,
                "end_ms": clip.end_ms,
            }
            for clip in timeline.audio_clips
        ],
        "presentation": timeline.presentation.model_dump(),
    }
    return (
        "You are DemoDirector's Edit Planner. Convert the user instruction into only typed "
        "EditOperation objects from the approved operation allowlist. Never return code, shell "
        "commands, JavaScript, or renderer/browser actions. If the request is unsupported, set "
        "supported=false, return no operations, and explain why. Propose changes for review; do "
        "not claim they are already applied. Current timeline summary: "
        f"{json.dumps(summary, separators=(',', ':'))}. User instruction: {instruction}"
    )


def validate_edit_plan(plan: EditPlan, timeline: Timeline) -> None:
    if not plan.supported:
        return
    if not plan.operations:
        raise EditPlanValidationError("A supported edit plan must contain at least one operation.")
    if len(plan.operations) > 20:
        raise EditPlanValidationError("An edit plan may contain at most 20 operations.")
    scenes_by_id = {clip.id: clip for clip in timeline.scene_clips}
    scene_ids = {clip.scene_id for clip in timeline.scene_clips}
    zooms_by_id = {clip.id: clip for clip in timeline.zoom_clips}
    captions_by_id = {clip.id: clip for clip in timeline.caption_clips}
    for operation in plan.operations:
        _validate_operation(
            operation,
            timeline,
            scenes_by_id,
            scene_ids,
            zooms_by_id,
            captions_by_id,
        )


def _validate_operation(
    operation: EditOperation,
    timeline: Timeline,
    scenes_by_id: dict[str, SceneClip],
    scene_ids: set[str],
    zooms_by_id: dict[str, ZoomClip],
    captions_by_id: dict[str, CaptionClip],
) -> None:
    kind = operation.operation_type
    arguments = operation.arguments
    if kind == "trim_scene":
        scene = scenes_by_id.get(operation.target_id)
        if scene is None:
            raise EditPlanValidationError("Trim operation references an unknown scene clip.")
        _only(arguments, {"start_ms", "end_ms"}, kind)
        current = next(clip for clip in timeline.scene_clips if clip.id == operation.target_id)
        start = _integer(arguments, "start_ms")
        end = _integer(arguments, "end_ms")
        if start < current.start_ms or end > current.end_ms or end - start < 250:
            raise EditPlanValidationError(
                "Trim operation must stay within the current scene bounds."
            )
    elif kind == "delete_scene":
        _known(operation.target_id, set(scenes_by_id), "scene clip")
        _only(arguments, set(), kind)
    elif kind == "reorder_scene":
        _known(operation.target_id, set(scenes_by_id), "scene clip")
        _only(arguments, {"new_index"}, kind)
        new_index = _integer(arguments, "new_index")
        if new_index < 0 or new_index >= len(scenes_by_id):
            raise EditPlanValidationError("Scene reorder index is outside the timeline.")
    elif kind == "update_narration":
        _known(operation.target_id, scene_ids, "scene")
        _only(arguments, {"narration"}, kind)
        _text(arguments, "narration")
    elif kind == "add_zoom":
        _known(operation.target_id, scene_ids | {timeline.project_id}, "scene or project")
        proposed = ZoomClip.model_validate({**arguments, "source": "prompt_edit"})
        if proposed.end_ms > timeline.duration_ms:
            raise EditPlanValidationError("Proposed zoom exceeds the timeline duration.")
    elif kind == "update_zoom":
        _known(operation.target_id, set(zooms_by_id), "zoom clip")
        _only(
            arguments,
            {
                "start_ms",
                "end_ms",
                "scale",
                "target_rect",
                "focus_x",
                "focus_y",
                "easing",
            },
            kind,
        )
        current_zoom = zooms_by_id[operation.target_id]
        updated = ZoomClip.model_validate(
            {**current_zoom.model_dump(), **arguments, "source": "prompt_edit"}
        )
        if updated.end_ms > timeline.duration_ms:
            raise EditPlanValidationError("Updated zoom exceeds the timeline duration.")
    elif kind == "delete_zoom":
        _known(operation.target_id, set(zooms_by_id), "zoom clip")
        _only(arguments, set(), kind)
    elif kind == "add_caption":
        _known(operation.target_id, scene_ids, "scene")
        proposed_caption = CaptionClip.model_validate(arguments)
        if proposed_caption.scene_id != operation.target_id:
            raise EditPlanValidationError("Added caption must target the selected scene.")
        target_scene = next(
            scene for scene in timeline.scene_clips if scene.scene_id == operation.target_id
        )
        if (
            proposed_caption.start_ms < target_scene.start_ms
            or proposed_caption.end_ms > target_scene.end_ms
        ):
            raise EditPlanValidationError("Proposed caption must fit within its target scene.")
    elif kind == "update_caption":
        _known(operation.target_id, set(captions_by_id), "caption clip")
        _only(arguments, {"start_ms", "end_ms", "text"}, kind)
        current_caption = captions_by_id[operation.target_id]
        updated_caption = CaptionClip.model_validate(
            {**current_caption.model_dump(), **arguments}
        )
        target_scene = next(
            scene
            for scene in timeline.scene_clips
            if scene.scene_id == updated_caption.scene_id
        )
        if (
            updated_caption.start_ms < target_scene.start_ms
            or updated_caption.end_ms > target_scene.end_ms
        ):
            raise EditPlanValidationError("Updated caption must fit within its target scene.")
    elif kind == "change_voice_config":
        _known(operation.target_id, {timeline.project_id}, "project")
        if not arguments:
            raise EditPlanValidationError("Voice change must include configuration values.")
        NarrationVoiceConfig.model_validate(arguments)
    elif kind == "change_cta_text":
        _known(operation.target_id, {timeline.project_id}, "project")
        _only(arguments, {"cta"}, kind)
        _text(arguments, "cta")
    elif kind == "change_presentation":
        _known(operation.target_id, {timeline.project_id}, "project")
        _only(arguments, {"template"}, kind)
        VideoPresentationConfig.model_validate(arguments)
    else:
        raise EditPlanValidationError(f"Unsupported edit operation: {kind}")


def _only(
    arguments: Mapping[str, JsonValue],
    allowed: set[str],
    operation: str,
) -> None:
    unknown = set(arguments) - allowed
    if unknown:
        raise EditPlanValidationError(
            f"{operation} contains unsupported arguments: {', '.join(sorted(unknown))}"
        )


def _integer(arguments: Mapping[str, JsonValue], field: str) -> int:
    value = arguments.get(field)
    if not isinstance(value, int) or isinstance(value, bool):
        raise EditPlanValidationError(f"{field} must be an integer.")
    return value


def _text(arguments: Mapping[str, JsonValue], field: str) -> str:
    value = arguments.get(field)
    if not isinstance(value, str) or not value.strip():
        raise EditPlanValidationError(f"{field} must be non-empty text.")
    return value


def _known(target: str, known: set[str], label: str) -> None:
    if target not in known:
        raise EditPlanValidationError(f"Edit operation references an unknown {label} ID.")
