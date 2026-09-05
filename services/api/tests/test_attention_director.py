from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from demodirector_api.attention_director import (
    AttentionDirector,
    AttentionGateway,
    GoogleADKAttentionGateway,
)
from demodirector_api.records import SQLiteRecordStore
from demodirector_contracts import Viewport
from demodirector_contracts.attention import (
    AnimatedCalloutDraft,
    AttentionDraft,
    AttentionRequest,
    NormalizedRect,
    TargetObservation,
)
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types


def request() -> AttentionRequest:
    return AttentionRequest(
        project_id="project-1",
        job_id="job-1",
        parent_run_id="motion-run-1",
        duration_ms=10_000,
        target_ids=["target-1"],
        narration_statement_ids=["statement-1"],
        created_at=datetime(2026, 9, 4, 12, 0, tzinfo=UTC),
    )


def targets() -> list[TargetObservation]:
    return [
        TargetObservation(
            id="target-1",
            scene_id="scene-1",
            locator_fingerprint="a" * 64,
            timestamp_ms=1_000,
            rect=NormalizedRect(x=0.2, y=0.3, width=0.1, height=0.1),
            viewport=Viewport(width=1280, height=720),
        )
    ]


def output(target_id: str = "target-1") -> str:
    return AttentionDraft(
        summary="Guide attention to the observed control.",
        callouts=[
            AnimatedCalloutDraft(
                target_id=target_id,
                callout_type="label_connector",
                placement="top_left",
                start_ms=1_000,
                end_ms=2_000,
                text="Create project",
            )
        ],
        caption_emphasis=[],
    ).model_dump_json()


class FakeGateway(AttentionGateway):
    model_name = "gemini-test"

    def execute(
        self,
        request: AttentionRequest,
        context: dict[str, object],
        *,
        session_id: str,
    ) -> str:
        del request, context, session_id
        return output()


def test_attention_director_persists_validated_child_step(tmp_path: Path) -> None:
    records = SQLiteRecordStore(tmp_path / "attention.sqlite")
    run, plan = AttentionDirector(records, FakeGateway()).direct(
        request(), targets(), {"targets": ["target-1"]}
    )
    assert run.status == "succeeded" and run.workflow_runs == 1
    assert run.parent_run_id == "motion-run-1"
    assert run.output_plan_id == plan.id and plan.callouts[0].target_id == "target-1"
    assert records.get(f"attention-plan-{plan.id}") is not None


class LocalAttentionModel(BaseLlm):
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
                    parts=[types.Part.from_function_call(
                        name="read_approved_attention_context", args={}
                    )],
                )
            )
            return
        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part.from_text(text=output())],
            )
        )


def test_attention_gateway_executes_real_local_adk_runner() -> None:
    model = LocalAttentionModel(model="gemini-local-attention-test")
    raw = GoogleADKAttentionGateway(model).execute(
        request(), {"targets": ["target-1"]}, session_id="attention-session"
    )
    assert AttentionDraft.model_validate_json(raw).callouts[0].target_id == "target-1"
    assert model.calls == 2


def test_attention_director_rejects_hallucinated_target(tmp_path: Path) -> None:
    class InvalidGateway(FakeGateway):
        def execute(self, *args: object, **kwargs: object) -> str:
            return output("foreign")

    records = SQLiteRecordStore(tmp_path / "attention.sqlite")
    with pytest.raises(ValueError, match="attention plan"):
        AttentionDirector(records, InvalidGateway()).direct(
            request(), targets(), {"targets": ["target-1"]}
        )
