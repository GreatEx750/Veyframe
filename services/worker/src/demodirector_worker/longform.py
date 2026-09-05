from __future__ import annotations

import hashlib
import json

from demodirector_contracts import RenderConfig, Timeline
from demodirector_contracts.longform import (
    CompiledLongFormPlan,
    LongFormValidationReport,
    LongFormVideoPlan,
)


class LongFormCompiler:
    def compile(self, plan: LongFormVideoPlan) -> CompiledLongFormPlan:
        payload = {
            "project_id": plan.project_id,
            "plan_id": plan.id,
            "version": plan.version,
            "variant": plan.visual_variant,
            "sections": [item.model_dump(mode="json") for item in plan.sections],
            "beats": [item.model_dump(mode="json") for item in plan.beats],
            "chapters": [item.model_dump(mode="json") for item in plan.chapters],
            "condensed_intervals": [
                item.model_dump(mode="json") for item in plan.condensed_intervals
            ],
            "audio_mix": plan.audio_mix.model_dump(mode="json"),
            "milestones": {
                "product_operation": plan.first_product_operation_ms,
                "create_action": plan.create_action_ms,
                "finished_glimpse": plan.finished_glimpse_ms,
            },
            "evidence_refs": plan.evidence_refs,
            "parallel_source_refs": plan.parallel_source_refs,
            "product_clip_refs": plan.product_clip_refs,
            "target_ids": plan.target_ids,
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return CompiledLongFormPlan(
            project_id=plan.project_id,
            plan_id=plan.id,
            chapter_count=len(plan.chapters),
            beat_count=len(plan.beats),
            deterministic_hash=digest,
        )

    def validate_timeline(
        self,
        plan: LongFormVideoPlan,
        timeline: Timeline,
        config: RenderConfig,
    ) -> LongFormValidationReport:
        issues: list[str] = []
        if timeline.project_id != plan.project_id:
            issues.append("Timeline project does not match the long-form plan")
        if timeline.duration_ms != 180_000:
            issues.append("Timeline duration is not exactly 180 seconds")
        if (config.width, config.height, config.fps) != (2560, 1440, 30):
            issues.append("Long-form export must use QHD at 30 fps")
        has_audio = bool(timeline.audio_clips)
        has_captions = bool(timeline.caption_clips)
        visible_ms = sum(
            max(0, min(clip.end_ms, timeline.duration_ms) - max(0, clip.start_ms))
            for clip in timeline.scene_clips
        )
        product_presence = min(100, visible_ms / timeline.duration_ms * 100)
        if product_presence < 90:
            issues.append("Product footage is not visible for at least 90 percent")
        if abs(product_presence - plan.product_presence_percent) > 0.1:
            issues.append("Product-presence measurement does not match the plan")
        synchronized = all(
            clip.end_ms <= timeline.duration_ms
            for clip in [*timeline.audio_clips, *timeline.caption_clips]
        )
        return LongFormValidationReport(
            project_id=plan.project_id,
            plan_id=plan.id,
            duration_ms=180_000,
            width=2560,
            height=1440,
            fps=30,
            narration_word_count=plan.narration_word_count(),
            visual_beat_count=len(plan.beats),
            product_presence_percent=product_presence,
            has_audio=has_audio,
            has_captions=has_captions,
            synchronized=synchronized,
            issues=issues,
            passed=has_audio and has_captions and synchronized and not issues,
        )
