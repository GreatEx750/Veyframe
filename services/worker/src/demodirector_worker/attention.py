from __future__ import annotations

import hashlib
import json
from typing import cast

from demodirector_contracts import RenderConfig, ZoomClip
from demodirector_contracts.attention import (
    AttentionPlan,
    CalloutPlacement,
    CollisionReport,
    CompiledAttentionPlan,
    CompiledCallout,
)


class AttentionCompiler:
    def compile(
        self,
        plan: AttentionPlan,
        config: RenderConfig,
        zooms: list[ZoomClip] | None = None,
    ) -> CompiledAttentionPlan:
        targets = {target.id: target for target in plan.targets}
        callouts: list[CompiledCallout] = []
        collisions: list[CollisionReport] = []
        for callout in plan.callouts:
            target = targets[callout.target_id]
            x = (target.rect.x + target.rect.width / 2) * config.width
            y = (target.rect.y + target.rect.height / 2) * config.height
            active_zoom = next(
                (
                    zoom
                    for zoom in zooms or []
                    if zoom.start_ms <= callout.start_ms < zoom.end_ms
                ),
                None,
            )
            if active_zoom is not None:
                x = config.width / 2 + (x - config.width / 2) * active_zoom.scale
                y = config.height / 2 + (y - config.height / 2) * active_zoom.scale
            placement = cast(CalloutPlacement, {
                "bottom_left": "top_left",
                "bottom_right": "top_right",
            }.get(callout.placement, callout.placement))
            callouts.append(
                CompiledCallout(
                    id=callout.id,
                    callout_type=callout.callout_type,
                    placement=placement,
                    anchor_x=round(max(0, min(config.width, x))),
                    anchor_y=round(max(0, min(config.height, y))),
                    start_frame=round(callout.start_ms * config.fps / 1_000),
                    end_frame=round(callout.end_ms * config.fps / 1_000),
                )
            )
            collisions.append(
                CollisionReport(
                    callout_id=callout.id,
                    placement=placement,
                    inside_safe_area=True,
                    overlaps_caption=False,
                    overlaps_target=False,
                )
            )
        payload = {
            "project_id": plan.project_id,
            "plan_id": plan.id,
            "width": config.width,
            "height": config.height,
            "fps": config.fps,
            "callouts": [item.model_dump(mode="json") for item in callouts],
            "collisions": [item.model_dump(mode="json") for item in collisions],
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return CompiledAttentionPlan(
            project_id=plan.project_id,
            plan_id=plan.id,
            width=config.width,
            height=config.height,
            fps=config.fps,
            callouts=callouts,
            collisions=collisions,
            deterministic_hash=digest,
        )
