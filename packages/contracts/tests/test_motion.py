from datetime import UTC, datetime, timedelta

import pytest
from demodirector_contracts.editorial import (
    EditorialSceneDraft,
    EditorialTemplateDraft,
    RenderSafeCrop,
)
from demodirector_contracts.motion import (
    ADKMotionRun,
    MotionCue,
    MotionCueDraft,
    MotionDirectionDraft,
    MotionDirectionPlan,
    MotionDirectionRequest,
    MotionTokenSet,
)
from pydantic import ValidationError

NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)


def request() -> MotionDirectionRequest:
    return MotionDirectionRequest(
        project_id="project-1",
        job_id="job-1",
        storyboard_id="storyboard-1",
        storyboard_version=2,
        duration_ms=20_000,
        evidence_fingerprint="a" * 64,
        source_ids=["source-1"],
        scene_ids=["scene-1"],
        product_clip_refs=["scene:scene-1"],
        created_at=NOW,
    )


def cue(**updates: object) -> MotionCue:
    values: dict[str, object] = {
        "id": "cue-1",
        "scene_id": "scene-1",
        "primitive": "fade_slide",
        "layer": "transition",
        "start_ms": 0,
        "end_ms": 600,
        "easing": "standard",
        "text": "Open with the working product",
        "product_clip_ref": "scene:scene-1",
    }
    values.update(updates)
    return MotionCue.model_validate(values)


def test_motion_plan_rejects_unknown_references_overlap_and_executable_text() -> None:
    valid = MotionDirectionPlan(
        id="motion-plan-1",
        project_id="project-1",
        job_id="job-1",
        run_id="motion-run-1",
        request_fingerprint="b" * 64,
        design_tokens=MotionTokenSet(),
        duration_ms=20_000,
        scene_ids=["scene-1"],
        product_clip_refs=["scene:scene-1"],
        summary="Keep the working product visible.",
        cues=[cue()],
        created_at=NOW,
    )
    assert valid.design_tokens.font_family == "Inter"

    with pytest.raises(ValidationError):
        valid.model_copy(
            update={"cues": [cue(), cue(id="cue-2", start_ms=300, end_ms=900)]}
        ).__class__.model_validate(
            {
                **valid.model_dump(),
                "cues": [cue(), cue(id="cue-2", start_ms=300, end_ms=900)],
            }
        )
    with pytest.raises(ValidationError):
        MotionCue.model_validate(
            cue(text="<script>alert(1)</script>").model_dump()
        )
    with pytest.raises(ValidationError):
        MotionDirectionPlan.model_validate(
            {**valid.model_dump(), "cues": [cue(scene_id="foreign").model_dump()]}
        )


def test_motion_request_and_draft_are_bounded() -> None:
    value = request()
    assert value.product_clip_refs == ["scene:scene-1"]
    draft = MotionDirectionDraft(
        summary="A concise direction.",
        cues=[
            MotionCueDraft(
                scene_id="scene-1",
                primitive="background_dim",
                layer="mask",
                start_ms=1000,
                end_ms=1600,
                easing="standard",
                text=None,
                product_clip_ref="scene:scene-1",
            )
        ],
        editorial=EditorialTemplateDraft(
            summary="Product-present direction.",
            scenes=[
                EditorialSceneDraft(
                    scene_id="scene-1",
                    section="hook",
                    template_id="hook",
                    product_clip_ref="scene:scene-1",
                    product_treatment="moving_background",
                    start_ms=0,
                    end_ms=20_000,
                    title="Show the product",
                    crop=RenderSafeCrop(x=0, y=0, width=1, height=1),
                )
            ],
        ),
    )
    assert len(draft.cues) == 1
    with pytest.raises(ValidationError):
        MotionDirectionRequest.model_validate(
            {**value.model_dump(), "evidence_fingerprint": "not-a-fingerprint"}
        )


def test_adk_motion_run_requires_real_completed_timing_and_validated_output() -> None:
    run = ADKMotionRun(
        id="motion-run-1",
        project_id="project-1",
        job_id="job-1",
        session_id="session-1",
        agent_name="demodirector_motion_director",
        model="gemini-2.5-flash",
        status="succeeded",
        started_at=NOW,
        completed_at=NOW + timedelta(milliseconds=750),
        elapsed_ms=750,
        retry_count=0,
        workflow_runs=1,
        input_artifact_ids=["storyboard:storyboard-1:2", f"evidence:{'a' * 64}"],
        output_plan_id="motion-plan-1",
        validation_status="passed",
        message="Validated motion direction saved.",
    )
    assert run.workflow_runs == 1
    with pytest.raises(ValidationError):
        ADKMotionRun.model_validate({**run.model_dump(), "workflow_runs": 0})
    with pytest.raises(ValidationError):
        ADKMotionRun.model_validate(
            {**run.model_dump(), "message": "Bearer private-token"}
        )
