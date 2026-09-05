from datetime import UTC, datetime

import pytest
from demodirector_contracts.style import (
    StyleDirectionDecision,
    StyleDirectionPlan,
    VariantOverride,
    VariantSceneDefaults,
)
from pydantic import ValidationError


def style_plan() -> StyleDirectionPlan:
    now = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
    return StyleDirectionPlan(
        id="style-plan-1",
        project_id="project-1",
        job_id="job-1",
        parent_run_id="motion-run-1",
        audience="Product leaders",
        purpose="Show the working product",
        scene_ids=["scene-1", "scene-2"],
        allowed_evidence_refs=["storyboard:1", "attention:1"],
        recommendation_evidence_refs=["storyboard:1"],
        rationale="The approved narrative benefits from deliberate editorial pacing.",
        decision=StyleDirectionDecision(
            recommended_variant="editorial_story",
            selected_variant="editorial_story",
            outcome="recommended",
            decided_at=now,
        ),
        defaults=[
            VariantSceneDefaults(
                variant_id="editorial_story",
                product_scale="composed",
                callout_density="medium",
                motion_pace="deliberate",
            ),
            VariantSceneDefaults(
                variant_id="product_spotlight",
                product_scale="large",
                callout_density="low",
                motion_pace="calm",
            ),
            VariantSceneDefaults(
                variant_id="technical_proof",
                product_scale="evidence_focused",
                callout_density="medium",
                motion_pace="precise",
            ),
        ],
        created_at=now,
    )


def test_style_plan_has_fixed_catalog_and_approved_evidence() -> None:
    plan = style_plan()
    assert [item.variant_id for item in plan.defaults] == [
        "editorial_story",
        "product_spotlight",
        "technical_proof",
    ]
    assert set(plan.recommendation_evidence_refs) <= set(plan.allowed_evidence_refs)


def test_style_plan_rejects_foreign_scene_override() -> None:
    with pytest.raises(ValidationError, match="planned scenes"):
        StyleDirectionPlan.model_validate(
            {
                **style_plan().model_dump(mode="json"),
                "overrides": [VariantOverride(scene_id="foreign", variant_id="technical_proof")],
            }
        )
