from __future__ import annotations

import hashlib
import json

from demodirector_contracts import RenderConfig
from demodirector_contracts.editorial import (
    CompiledEditorialComposition,
    CompiledEditorialScene,
    EditorialTemplatePlan,
)


class EditorialCompositionCompiler:
    def compile(
        self,
        plan: EditorialTemplatePlan,
        config: RenderConfig,
    ) -> CompiledEditorialComposition:
        safe_margin_x = round(config.width * 0.05)
        safe_margin_y = round(config.height * 0.05)
        scenes = [
            CompiledEditorialScene(
                scene_id=scene.scene_id,
                template_id=scene.template_id,
                start_frame=round(scene.start_ms * config.fps / 1_000),
                end_frame=round(scene.end_ms * config.fps / 1_000),
                safe_margin_x=safe_margin_x,
                safe_margin_y=safe_margin_y,
            )
            for scene in plan.scenes
        ]
        presence = plan.product_presence()
        payload = {
            "project_id": plan.project_id,
            "plan_id": plan.id,
            "width": config.width,
            "height": config.height,
            "fps": config.fps,
            "scenes": [scene.model_dump(mode="json") for scene in scenes],
            "product_presence": presence.model_dump(mode="json"),
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return CompiledEditorialComposition(
            project_id=plan.project_id,
            plan_id=plan.id,
            width=config.width,
            height=config.height,
            fps=config.fps,
            scenes=scenes,
            product_presence=presence,
            deterministic_hash=digest,
        )
