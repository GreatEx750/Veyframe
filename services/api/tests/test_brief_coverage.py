from __future__ import annotations

from pathlib import Path

import pytest
from demodirector_api.brief_coverage import (
    BriefCoverageService,
    BriefCoverageValidationError,
)
from demodirector_api.google_ai import FakeGoogleAIService
from demodirector_api.main import create_app
from demodirector_contracts import BriefCoverageReport, Storyboard, Timeline
from fastapi.testclient import TestClient

BRIEF = "Show the dashboard workflow and show export flow."


def storyboard() -> Storyboard:
    return Storyboard.model_validate(
        {
            "id": "storyboard-1",
            "project_id": "project-1",
            "version": 1,
            "total_duration_seconds": 10,
            "status": "captured",
            "scenes": [
                {
                    "id": "scene-dashboard",
                    "storyboard_id": "storyboard-1",
                    "order": 0,
                    "title": "Dashboard workflow",
                    "objective": "Show the saved project dashboard.",
                    "narration": "The dashboard keeps every project in one place.",
                    "source_ids": ["brief"],
                    "capture_plan": {
                        "start_url": "https://example.com/dashboard",
                        "actions": [],
                        "success_assertions": [],
                        "timeout_seconds": 30,
                    },
                    "expected_evidence": ["Saved project is visible"],
                    "duration_seconds": 10,
                }
            ],
        }
    )


def timeline() -> Timeline:
    return Timeline.model_validate(
        {
            "project_id": "project-1",
            "duration_ms": 10_000,
            "scene_clips": [
                {
                    "id": "scene-clip-dashboard",
                    "scene_id": "scene-dashboard",
                    "start_ms": 0,
                    "end_ms": 10_000,
                    "source_uri": "dashboard.webm",
                }
            ],
            "caption_clips": [],
            "zoom_clips": [],
            "audio_clips": [],
        }
    )


def report_payload(*, evidence: str = "capture:scene-dashboard:0") -> dict[str, object]:
    return {
        "project_id": "project-1",
        "requirements": [
            {
                "id": "dashboard",
                "text": "Show the dashboard workflow",
                "source_excerpt": "Show the dashboard workflow",
            },
            {
                "id": "export",
                "text": "Show export flow",
                "source_excerpt": "show export flow",
            },
        ],
        "checks": [
            {
                "requirement_id": "dashboard",
                "requirement": "Show the dashboard workflow",
                "status": "covered",
                "scene_ids": ["scene-dashboard"],
                "evidence": [evidence],
                "suggested_repair": None,
            },
            {
                "requirement_id": "export",
                "requirement": "Show export flow",
                "status": "missing",
                "scene_ids": [],
                "evidence": [],
                "suggested_repair": "Add a scene that opens and completes the export flow.",
            },
        ],
        "summary": "The dashboard is covered, but the export flow is missing.",
        "all_covered": False,
    }


def test_omitted_export_flow_is_reported_missing_with_grounded_coverage() -> None:
    fake = FakeGoogleAIService(report_payload())

    report = BriefCoverageService(fake).analyze(
        "project-1",
        BRIEF,
        storyboard(),
        timeline(),
        {"scene-dashboard": ["Saved project is visible in the capture"]},
    )

    assert report.checks[0].status == "covered"
    assert report.checks[0].scene_ids == ["scene-dashboard"]
    assert report.checks[0].evidence == ["capture:scene-dashboard:0"]
    assert report.checks[1].status == "missing"
    assert report.checks[1].suggested_repair is not None
    assert "Brief Coverage" in fake.prompts[0]
    assert "Demo QA" in fake.prompts[0]
    assert "dashboard.webm" not in fake.prompts[0]


def test_report_rejects_invented_evidence_reference() -> None:
    service = BriefCoverageService(
        FakeGoogleAIService(report_payload(evidence="capture:invented:0"))
    )

    with pytest.raises(BriefCoverageValidationError, match="unknown evidence"):
        service.analyze(
            "project-1",
            BRIEF,
            storyboard(),
            timeline(),
            {"scene-dashboard": ["Saved project is visible in the capture"]},
        )


def test_coverage_report_round_trips_through_typed_contract() -> None:
    report = BriefCoverageReport.model_validate(report_payload())

    restored = BriefCoverageReport.model_validate_json(report.model_dump_json())

    assert restored == report
    assert restored.all_covered is False


def test_brief_coverage_api_returns_validated_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_DATABASE_PATH", str(tmp_path / "api.db"))
    client = TestClient(create_app(ai_service=FakeGoogleAIService(report_payload())))

    response = client.post(
        "/projects/project-1/qa/brief-coverage",
        json={
            "brief": BRIEF,
            "storyboard": storyboard().model_dump(mode="json"),
            "timeline": timeline().model_dump(mode="json"),
            "capture_evidence": {
                "scene-dashboard": ["Saved project is visible in the capture"]
            },
        },
    )

    assert response.status_code == 200
    body = BriefCoverageReport.model_validate(response.json())
    assert body.checks[1].requirement_id == "export"
    assert body.checks[1].status == "missing"
