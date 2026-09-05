from __future__ import annotations

import hashlib
import json

from demodirector_contracts import RenderConfig
from demodirector_contracts.style import CompiledStyleDirection, StyleDirectionPlan


class StyleCompiler:
    def compile(
        self,
        plan: StyleDirectionPlan,
        config: RenderConfig,
    ) -> CompiledStyleDirection:
        payload = {
            "project_id": plan.project_id,
            "plan_id": plan.id,
            "variant_id": plan.decision.selected_variant,
            "width": config.width,
            "height": config.height,
            "safe_margin_x": round(config.width * 0.05),
            "safe_margin_y": round(config.height * 0.05),
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return CompiledStyleDirection(
            project_id=plan.project_id,
            plan_id=plan.id,
            variant_id=plan.decision.selected_variant,
            width=config.width,
            height=config.height,
            safe_margin_x=round(config.width * 0.05),
            safe_margin_y=round(config.height * 0.05),
            deterministic_hash=digest,
        )
