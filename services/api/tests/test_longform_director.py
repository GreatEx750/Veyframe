from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Literal

import pytest
from demodirector_api.longform_director import (
    GoogleADKLongFormGateway,
    LongFormDirector,
    LongFormGateway,
    LongFormGatewayResult,
)
from demodirector_api.records import SQLiteRecordStore
from demodirector_contracts.longform import (
    ChapterCheckpoint,
    LongFormDirectionRequest,
    LongFormVideoPlan,
)
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from test_support.longform import longform_plan


def request(plan: LongFormVideoPlan | None = None) -> LongFormDirectionRequest:
    selected = plan or longform_plan()
    return LongFormDirectionRequest(
        plan_id=selected.id,
        run_id=selected.adk_run_id,
        project_id=selected.project_id,
        job_id=selected.job_id,
        parent_motion_run_id=selected.parent_motion_run_id,
        visual_variant=selected.visual_variant,
        research_status=selected.research_status,
        evidence_refs=selected.evidence_refs,
        parallel_source_refs=selected.parallel_source_refs,
        product_clip_refs=selected.product_clip_refs,
        target_ids=selected.target_ids,
        created_at=selected.created_at,
    )


def result(plan: LongFormVideoPlan | None = None) -> LongFormGatewayResult:
    selected = plan or longform_plan()
    refs = (selected.evidence_refs[0],)
    step_kinds: tuple[
        Literal["narrative", "template", "attention", "style"], ...
    ] = ("narrative", "template", "attention", "style")
    return LongFormGatewayResult(
        output=selected.model_dump_json(),
        evidence_reads=1,
        steps=tuple((kind, refs) for kind in step_kinds),
    )


class FakeGateway(LongFormGateway):
    model_name = "gemini-test"

    def execute(
        self,
        request: LongFormDirectionRequest,
        context: dict[str, object],
        *,
        session_id: str,
    ) -> LongFormGatewayResult:
        del request, context, session_id
        return result()


def test_longform_director_persists_causal_steps_and_checkpoints(tmp_path: Path) -> None:
    records = SQLiteRecordStore(tmp_path / "longform.sqlite")
    run, plan = LongFormDirector(records, FakeGateway()).direct(request(), {})
    assert run.status == "succeeded" and run.runner_completed
    assert len(run.step_ids) == 4 and run.output_plan_id == plan.id
    assert records.get(f"longform-plan-{plan.id}") is not None
    checkpoints = LongFormDirector(records, FakeGateway()).checkpoints(plan.project_id, plan.id)
    assert [item.status for item in checkpoints] == ["pending"] * 4


class LocalLongFormModel(BaseLlm):
    calls: int = 0

    async def generate_content_async(
        self,
        llm_request: LlmRequest,
        stream: bool = False,
    ) -> AsyncGenerator[LlmResponse, None]:
        del llm_request, stream
        calls = [
            ("read_project_evidence", {}),
            ("record_narrative_direction", {"artifact_refs": ["source:parallel-1"]}),
            ("record_template_direction", {"artifact_refs": ["source:parallel-1"]}),
            ("record_attention_direction", {"artifact_refs": ["source:parallel-1"]}),
            ("record_style_direction", {"artifact_refs": ["source:parallel-1"]}),
        ]
        if self.calls < len(calls):
            name, arguments = calls[self.calls]
            self.calls += 1
            yield LlmResponse(content=types.Content(
                role="model",
                parts=[types.Part.from_function_call(name=name, args=arguments)],
            ))
            return
        self.calls += 1
        yield LlmResponse(content=types.Content(
            role="model",
            parts=[types.Part.from_text(text=longform_plan().model_dump_json())],
        ))


def test_longform_gateway_executes_real_local_adk_runner() -> None:
    model = LocalLongFormModel(model="gemini-local-longform-test")
    output = GoogleADKLongFormGateway(model).execute(
        request(), {"evidence": ["source:parallel-1"]}, session_id="longform-session"
    )
    assert LongFormVideoPlan.model_validate_json(output.output).duration_ms == 180_000
    assert output.evidence_reads == 1
    assert [step[0] for step in output.steps] == [
        "narrative", "template", "attention", "style"
    ]
    assert model.calls == 6


def test_invalid_or_incomplete_adk_workflow_never_succeeds(tmp_path: Path) -> None:
    class IncompleteGateway(FakeGateway):
        def execute(self, *args: object, **kwargs: object) -> LongFormGatewayResult:
            saved = result()
            return LongFormGatewayResult(saved.output, 1, saved.steps[:3])

    records = SQLiteRecordStore(tmp_path / "longform.sqlite")
    with pytest.raises(ValueError, match="long-form planning"):
        LongFormDirector(records, IncompleteGateway()).direct(request(), {})
    stored = records.get("adk-longform-run-longform-run-1")
    assert stored is not None and stored[1]["status"] == "failed"
    assert stored[1]["runner_completed"] is False


def test_failed_chapter_can_restart_without_replacing_siblings(tmp_path: Path) -> None:
    records = SQLiteRecordStore(tmp_path / "longform.sqlite")
    director = LongFormDirector(records, FakeGateway())
    _, plan = director.direct(request(), {})
    key = f"longform-checkpoint-{plan.id}-chapter-2"
    saved = records.get(key)
    assert saved is not None
    failed = ChapterCheckpoint.model_validate({
        **saved[1], "status": "failed", "attempt": 1
    })
    records.put(key, saved[0], failed.model_dump(mode="json"))
    sibling_before = director.checkpoints(plan.project_id, plan.id)[0]
    retried = director.retry_chapter(plan.project_id, plan.id, "chapter-2")
    sibling_after = director.checkpoints(plan.project_id, plan.id)[0]
    assert retried.status == "pending" and retried.replaces_checkpoint_id == failed.id
    assert sibling_after == sibling_before
