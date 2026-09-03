from __future__ import annotations

from pathlib import Path

import pytest
from demodirector_api.edit_planner import EditPlannerService, EditPlanValidationError
from demodirector_api.google_ai import FakeGoogleAIService
from demodirector_api.main import create_app
from demodirector_contracts import Timeline
from fastapi.testclient import TestClient


def timeline() -> Timeline:
    return Timeline.model_validate(
        {
            "project_id": "project-1",
            "duration_ms": 10_000,
            "scene_clips": [
                {
                    "id": "scene-clip-opening",
                    "scene_id": "scene-opening",
                    "start_ms": 0,
                    "end_ms": 4_000,
                    "source_uri": "opening.webm",
                },
                {
                    "id": "scene-clip-workflow",
                    "scene_id": "scene-workflow",
                    "start_ms": 4_000,
                    "end_ms": 10_000,
                    "source_uri": "workflow.webm",
                },
            ],
            "caption_clips": [
                {
                    "id": "caption-opening",
                    "scene_id": "scene-opening",
                    "start_ms": 0,
                    "end_ms": 4_000,
                    "text": "Meet the product.",
                }
            ],
            "zoom_clips": [
                {
                    "id": "zoom-workflow",
                    "start_ms": 5_000,
                    "end_ms": 6_500,
                    "scale": 1.4,
                    "target_rect": {"x": 100, "y": 100, "width": 300, "height": 180},
                    "easing": "ease_in_out",
                    "source": "auto",
                }
            ],
            "audio_clips": [],
        }
    )


def trim_payload(target_id: str = "scene-clip-opening") -> dict[str, object]:
    return {
        "supported": True,
        "summary": "Shorten the opening scene",
        "explanation": "Trim one second while preserving the rest of the timeline.",
        "operations": [
            {
                "operation_type": "trim_scene",
                "target_id": target_id,
                "arguments": {"start_ms": 0, "end_ms": 3_000},
                "rationale": "Reach the product workflow sooner.",
            }
        ],
    }


def test_opening_shorter_produces_bounded_typed_trim() -> None:
    fake = FakeGoogleAIService(trim_payload())
    plan = EditPlannerService(fake).plan(timeline(), "Make the opening shorter")

    assert plan.operations[0].operation_type == "trim_scene"
    assert plan.operations[0].target_id == "scene-clip-opening"
    assert plan.operations[0].arguments == {"start_ms": 0, "end_ms": 3_000}
    assert "Make the opening shorter" in fake.prompts[0]
    assert "source_uri" not in fake.prompts[0]


def test_unsupported_request_returns_explanation_without_operations() -> None:
    fake = FakeGoogleAIService(
        {
            "supported": False,
            "summary": "Request cannot be applied",
            "explanation": "Running arbitrary JavaScript is outside the edit operation allowlist.",
            "operations": [],
        }
    )

    plan = EditPlannerService(fake).plan(timeline(), "Run this JavaScript in the browser")

    assert plan.supported is False
    assert plan.operations == []
    assert "outside" in plan.explanation


def test_operation_target_must_exist_in_current_timeline() -> None:
    service = EditPlannerService(FakeGoogleAIService(trim_payload("missing-scene")))

    with pytest.raises(EditPlanValidationError, match="unknown scene"):
        service.plan(timeline(), "Make the opening shorter")


def test_caption_edit_must_fit_inside_its_target_scene() -> None:
    payload = {
        "supported": True,
        "summary": "Add a workflow caption",
        "explanation": "Keep the caption with the workflow scene.",
        "operations": [
            {
                "operation_type": "add_caption",
                "target_id": "scene-workflow",
                "arguments": {
                    "id": "caption-workflow",
                    "scene_id": "scene-workflow",
                    "start_ms": 0,
                    "end_ms": 1_000,
                    "text": "Workflow",
                },
                "rationale": "Label the workflow.",
            }
        ],
    }

    with pytest.raises(EditPlanValidationError, match="within its target scene"):
        EditPlannerService(FakeGoogleAIService(payload)).plan(
            timeline(), "Caption the workflow"
        )


def test_edit_plan_api_returns_reviewable_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_DATABASE_PATH", str(tmp_path / "api.db"))
    client = TestClient(create_app(ai_service=FakeGoogleAIService(trim_payload())))

    response = client.post(
        "/projects/project-1/edit-plan",
        json={"instruction": "Make the opening shorter", "timeline": timeline().model_dump()},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == "Shorten the opening scene"
    assert body["operations"][0]["operation_type"] == "trim_scene"
