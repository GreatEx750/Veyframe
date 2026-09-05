from datetime import UTC, datetime

import pytest
from demodirector_contracts import Viewport
from demodirector_contracts.attention import (
    AnimatedCallout,
    AttentionPlan,
    NormalizedRect,
    TargetObservation,
)
from pydantic import ValidationError


def target() -> TargetObservation:
    return TargetObservation(
        id="target-1",
        scene_id="scene-1",
        locator_fingerprint="a" * 64,
        timestamp_ms=1_000,
        rect=NormalizedRect(x=0.2, y=0.3, width=0.1, height=0.1),
        viewport=Viewport(width=1280, height=720),
    )


def callout(**updates: object) -> AnimatedCallout:
    values: dict[str, object] = {
        "id": "callout-1",
        "target_id": "target-1",
        "callout_type": "label_connector",
        "placement": "bottom_right",
        "start_ms": 1_000,
        "end_ms": 2_000,
        "text": "Create the project",
    }
    values.update(updates)
    return AnimatedCallout.model_validate(values)


def attention_plan(**updates: object) -> AttentionPlan:
    values: dict[str, object] = {
        "id": "attention-plan-1",
        "project_id": "project-1",
        "job_id": "job-1",
        "parent_run_id": "run-1",
        "duration_ms": 10_000,
        "targets": [target()],
        "narration_statement_ids": ["statement-1"],
        "summary": "Guide the viewer.",
        "callouts": [callout()],
        "caption_emphasis": [],
        "created_at": datetime(2026, 9, 4, 12, 0, tzinfo=UTC),
    }
    values.update(updates)
    return AttentionPlan.model_validate(values)


def test_attention_plan_rejects_foreign_and_competing_targets() -> None:
    with pytest.raises(ValidationError):
        attention_plan(callouts=[callout(target_id="foreign")])
    with pytest.raises(ValidationError):
        attention_plan(callouts=[callout(), callout(id="callout-2", start_ms=1_500)])


def test_callout_timing_and_target_geometry_are_bounded() -> None:
    with pytest.raises(ValidationError):
        callout(end_ms=1_400)
    with pytest.raises(ValidationError):
        NormalizedRect(x=0.9, y=0, width=0.2, height=0.1)
