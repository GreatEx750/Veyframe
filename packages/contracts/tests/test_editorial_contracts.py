from datetime import UTC, datetime

import pytest
from demodirector_contracts.editorial import (
    EditorialScene,
    EditorialTemplatePlan,
    PresenceViolation,
    ProductPresenceReport,
)
from pydantic import ValidationError


def scene(**updates: object) -> EditorialScene:
    values: dict[str, object] = {
        "id": "editorial-scene-1",
        "scene_id": "scene-1",
        "section": "hook",
        "template_id": "hook",
        "product_clip_ref": "scene:scene-1",
        "product_treatment": "moving_background",
        "start_ms": 0,
        "end_ms": 10_000,
        "eyebrow": "DemoDirector",
        "title": "Show the product from the first frame",
        "body": None,
        "crop": {"x": 0, "y": 0, "width": 1, "height": 1},
    }
    values.update(updates)
    return EditorialScene.model_validate(values)


def plan(**updates: object) -> EditorialTemplatePlan:
    values: dict[str, object] = {
        "id": "editorial-plan-1",
        "project_id": "project-1",
        "job_id": "job-1",
        "run_id": "run-1",
        "motion_plan_id": "motion-plan-1",
        "catalog_version": "editorial-v1",
        "design_version": "motion-v1",
        "duration_ms": 10_000,
        "scene_ids": ["scene-1"],
        "product_clip_refs": ["scene:scene-1"],
        "summary": "Product-present hook.",
        "scenes": [scene()],
        "created_at": datetime(2026, 9, 4, 12, 0, tzinfo=UTC),
    }
    values.update(updates)
    return EditorialTemplatePlan.model_validate(values)


def test_editorial_plan_requires_owned_product_clip_and_full_scene_coverage() -> None:
    assert plan().product_presence().percentage == 100
    with pytest.raises(ValidationError):
        plan(scenes=[scene(product_clip_ref="scene:foreign")])
    with pytest.raises(ValidationError):
        plan(scenes=[scene(start_ms=500)])


def test_editorial_templates_and_copy_are_bounded() -> None:
    with pytest.raises(ValidationError):
        scene(template_id="unknown")
    with pytest.raises(ValidationError):
        scene(title="x" * 81)
    with pytest.raises(ValidationError):
        scene(crop={"x": 0.8, "y": 0, "width": 0.5, "height": 1})


def test_presence_report_rejects_less_than_ninety_percent() -> None:
    with pytest.raises(ValidationError):
        ProductPresenceReport(
            duration_ms=10_000,
            visible_product_ms=8_900,
            percentage=89,
            violating_intervals=[PresenceViolation(start_ms=8_900, end_ms=10_000)],
        )
