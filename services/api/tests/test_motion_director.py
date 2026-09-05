from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from demodirector_api.motion_director import (
    ADKMotionDirector,
    GoogleADKMotionGateway,
    MotionPlanningGateway,
)
from demodirector_api.records import SQLiteRecordStore
from demodirector_contracts.editorial import (
    EditorialSceneDraft,
    EditorialTemplateDraft,
    RenderSafeCrop,
)
from demodirector_contracts.motion import (
    MotionCueDraft,
    MotionDirectionDraft,
    MotionDirectionRequest,
)
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types


class FakeADKGateway(MotionPlanningGateway):
    model_name = "gemini-test"
    agent_name = "demodirector_motion_director"

    def __init__(self, *, invalid: bool = False) -> None:
        self.calls = 0
        self.invalid = invalid

    def execute(
        self,
        request: MotionDirectionRequest,
        context: dict[str, object],
        *,
        session_id: str,
    ) -> str:
        self.calls += 1
        assert session_id
        assert context["project"]["id"] == request.project_id  # type: ignore[index]
        scene_id = "foreign" if self.invalid else request.scene_ids[0]
        return MotionDirectionDraft(
            summary="Keep the working product visible.",
            cues=[
                MotionCueDraft(
                    scene_id=scene_id,
                    primitive="fade_slide",
                    layer="transition",
                    start_ms=0,
                    end_ms=600,
                    easing="standard",
                    text="Start with the working product",
                    product_clip_ref=request.product_clip_refs[0],
                )
            ],
            editorial=EditorialTemplateDraft(
                summary="Keep one real product frame visible.",
                scenes=[
                    EditorialSceneDraft(
                        scene_id=scene_id,
                        section="hook",
                        template_id="hook",
                        product_clip_ref=request.product_clip_refs[0],
                        product_treatment="moving_background",
                        start_ms=0,
                        end_ms=request.duration_ms,
                        title="Show the working product",
                        crop=RenderSafeCrop(x=0, y=0, width=1, height=1),
                    )
                ],
            ),
        ).model_dump_json()


def motion_request() -> MotionDirectionRequest:
    return MotionDirectionRequest(
        project_id="project-1",
        job_id="job-1",
        storyboard_id="storyboard-1",
        storyboard_version=1,
        duration_ms=20_000,
        evidence_fingerprint="a" * 64,
        source_ids=["source-1"],
        scene_ids=["scene-1"],
        product_clip_refs=["scene:scene-1"],
        created_at=datetime(2026, 9, 4, 12, 0, tzinfo=UTC),
    )


def test_adk_motion_director_persists_validated_causal_run(tmp_path: Path) -> None:
    records = SQLiteRecordStore(tmp_path / "motion.sqlite")
    gateway = FakeADKGateway()
    director = ADKMotionDirector(records, gateway)

    run, plan = director.direct(motion_request(), {"project": {"id": "project-1"}})

    assert gateway.calls == 1
    assert run.status == "succeeded" and run.workflow_runs == 1
    assert run.output_plan_id == plan.id and plan.run_id == run.id
    assert director.plan("project-1", "job-1") == plan
    assert director.run("project-1", "job-1") == run


def test_invalid_adk_output_is_saved_as_failed_and_never_becomes_a_plan(
    tmp_path: Path,
) -> None:
    records = SQLiteRecordStore(tmp_path / "motion.sqlite")
    director = ADKMotionDirector(records, FakeADKGateway(invalid=True))

    with pytest.raises(ValueError, match="ADK motion plan was invalid"):
        director.direct(motion_request(), {"project": {"id": "project-1"}})

    run = director.run("project-1", "job-1")
    assert run.status == "failed" and run.workflow_runs == 1
    assert run.validation_status == "failed" and run.output_plan_id is None
    with pytest.raises(KeyError):
        director.plan("project-1", "job-1")


class LocalADKModel(BaseLlm):
    calls: int = 0

    async def generate_content_async(
        self,
        llm_request: LlmRequest,
        stream: bool = False,
    ) -> AsyncGenerator[LlmResponse, None]:
        del llm_request, stream
        self.calls += 1
        if self.calls == 1:
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part.from_function_call(
                            name="read_approved_motion_context",
                            args={},
                        )
                    ],
                )
            )
            return
        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[
                    types.Part.from_text(
                        text=MotionDirectionDraft(
                            summary="Directed through the real local ADK runner.",
                            cues=[
                                MotionCueDraft(
                                    scene_id="scene-1",
                                    primitive="fade_slide",
                                    layer="transition",
                                    start_ms=0,
                                    end_ms=600,
                                    easing="standard",
                                    text="Show the working product",
                                    product_clip_ref="scene:scene-1",
                                )
                            ],
                            editorial=EditorialTemplateDraft(
                                summary="Show authentic product footage.",
                                scenes=[
                                    EditorialSceneDraft(
                                        scene_id="scene-1",
                                        section="hook",
                                        template_id="hook",
                                        product_clip_ref="scene:scene-1",
                                        product_treatment="moving_background",
                                        start_ms=0,
                                        end_ms=20_000,
                                        title="Working product",
                                        crop=RenderSafeCrop(x=0, y=0, width=1, height=1),
                                    )
                                ],
                            ),
                        ).model_dump_json()
                    )
                ],
            )
        )


def test_google_adk_gateway_executes_runner_and_read_only_context_tool() -> None:
    model = LocalADKModel(model="gemini-local-adk-test")
    gateway = GoogleADKMotionGateway(model)

    raw = gateway.execute(
        motion_request(),
        {"project": {"id": "project-1"}, "marker": "approved-context"},
        session_id="session-local-adk",
    )

    assert MotionDirectionDraft.model_validate_json(raw).cues[0].scene_id == "scene-1"
    assert model.calls == 2
