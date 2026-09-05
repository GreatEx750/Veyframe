from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from demodirector_contracts import RenderConfig
from demodirector_contracts.motion import (
    CompiledMotionComposition,
    CompiledMotionCue,
    MotionCue,
    MotionDirectionPlan,
    MotionTokenSet,
)


@dataclass(frozen=True, slots=True)
class MotionFrameState:
    active: bool
    progress: float
    opacity: float
    scale: float
    translate_x: float
    translate_y: float
    dim_opacity: float
    reveal: float


def _ease(progress: float, easing: str) -> float:
    bounded = max(0.0, min(1.0, progress))
    if easing == "linear":
        return bounded
    if easing == "emphasized":
        return 1 - (1 - bounded) ** 4
    return bounded * bounded * (3 - 2 * bounded)


def motion_state(
    cue: MotionCue,
    timestamp_ms: int,
    tokens: MotionTokenSet,
) -> MotionFrameState:
    del tokens
    active = cue.start_ms <= timestamp_ms < cue.end_ms
    if not active:
        return MotionFrameState(False, 0, 0, 1, 0, 0, 0, 0)
    elapsed = timestamp_ms - cue.start_ms
    progress = _ease(elapsed / (cue.end_ms - cue.start_ms), cue.easing)
    opacity = 1.0
    scale = 1.0
    translate_x = 0.0
    translate_y = 0.0
    dim_opacity = 0.0
    reveal = 1.0
    if cue.primitive == "fade_slide":
        opacity = progress
        translate_y = 24 * (1 - progress)
    elif cue.primitive == "scale_settle":
        scale = 0.96 + 0.04 * progress
        opacity = progress
    elif cue.primitive == "stagger_text":
        opacity = progress
        reveal = progress
    elif cue.primitive == "highlight_reveal":
        reveal = progress
    elif cue.primitive == "browser_frame_move":
        translate_x = 48 * (1 - progress)
        opacity = progress
    elif cue.primitive == "background_dim":
        dim_opacity = 0.42 * progress
    return MotionFrameState(
        True,
        round(progress, 6),
        round(opacity, 6),
        round(scale, 6),
        round(translate_x, 6),
        round(translate_y, 6),
        round(dim_opacity, 6),
        round(reveal, 6),
    )


class MotionCompositionCompiler:
    def compile(
        self,
        plan: MotionDirectionPlan,
        config: RenderConfig,
    ) -> CompiledMotionComposition:
        layer_order = plan.design_tokens.layer_order
        cues = [
            CompiledMotionCue(
                cue_id=cue.id,
                primitive=cue.primitive,
                layer=cue.layer,
                layer_index=layer_order.index(cue.layer),
                start_frame=round(cue.start_ms * config.fps / 1000),
                end_frame=round(cue.end_ms * config.fps / 1000),
                easing=cue.easing,
            )
            for cue in plan.cues
        ]
        payload = {
            "project_id": plan.project_id,
            "plan_id": plan.id,
            "design_version": plan.design_tokens.version,
            "width": config.width,
            "height": config.height,
            "fps": config.fps,
            "duration_ms": plan.duration_ms,
            "cues": [cue.model_dump(mode="json") for cue in cues],
            "editorial_plan": (
                plan.editorial_plan.model_dump(mode="json")
                if plan.editorial_plan is not None
                else None
            ),
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return CompiledMotionComposition(
            project_id=plan.project_id,
            plan_id=plan.id,
            design_version=plan.design_tokens.version,
            width=config.width,
            height=config.height,
            fps=config.fps,
            duration_ms=plan.duration_ms,
            cues=cues,
            deterministic_hash=digest,
        )
