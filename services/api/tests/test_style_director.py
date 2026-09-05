from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from demodirector_api.records import SQLiteRecordStore
from demodirector_api.style_director import GoogleADKStyleGateway, StyleDirector, StyleGateway
from demodirector_contracts.style import StyleDirectionDraft, StyleDirectionRequest
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types


def request() -> StyleDirectionRequest:
    return StyleDirectionRequest(
        project_id="project-1",
        job_id="job-1",
        parent_run_id="motion-run-1",
        audience="Product leaders",
        purpose="Show the working product",
        scene_ids=["scene-1"],
        evidence_refs=["storyboard:1", "attention:1"],
        created_at=datetime(2026, 9, 4, 12, 0, tzinfo=UTC),
    )


def output(evidence_ref: str = "storyboard:1") -> str:
    return StyleDirectionDraft(
        recommended_variant="product_spotlight",
        rationale="Keep the working product large and the motion restrained.",
        evidence_refs=[evidence_ref],
    ).model_dump_json()


class FakeGateway(StyleGateway):
    model_name = "gemini-test"

    def execute(
        self, request: StyleDirectionRequest, context: dict[str, object], *, session_id: str
    ) -> str:
        del request, context, session_id
        return output()


def test_style_director_persists_validated_recommendation(tmp_path: Path) -> None:
    records = SQLiteRecordStore(tmp_path / "style.sqlite")
    run, plan = StyleDirector(records, FakeGateway()).direct(
        request(), {"audience": "Product leaders"}
    )
    assert run.status == "succeeded" and run.workflow_runs == 1
    assert run.parent_run_id == "motion-run-1"
    assert plan.decision.selected_variant == "product_spotlight"
    assert records.get(f"style-plan-{plan.id}") is not None


class LocalStyleModel(BaseLlm):
    calls: int = 0

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        del llm_request, stream
        self.calls += 1
        if self.calls == 1:
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part.from_function_call(name="read_approved_style_context", args={})
                    ],
                )
            )
            return
        yield LlmResponse(
            content=types.Content(role="model", parts=[types.Part.from_text(text=output())])
        )


def test_style_gateway_executes_real_local_adk_runner() -> None:
    model = LocalStyleModel(model="gemini-local-style-test")
    raw = GoogleADKStyleGateway(model).execute(
        request(), {"audience": "Product leaders"}, session_id="style-session"
    )
    assert StyleDirectionDraft.model_validate_json(raw).recommended_variant == "product_spotlight"
    assert model.calls == 2


def test_style_director_rejects_unknown_evidence(tmp_path: Path) -> None:
    class InvalidGateway(FakeGateway):
        def execute(self, *args: object, **kwargs: object) -> str:
            return output("unknown")

    with pytest.raises(ValueError, match="style planning"):
        StyleDirector(SQLiteRecordStore(tmp_path / "style.sqlite"), InvalidGateway()).direct(
            request(), {}
        )
