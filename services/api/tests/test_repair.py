from __future__ import annotations

from pathlib import Path

import pytest
from demodirector_api.brief_coverage import BriefCoverageService
from demodirector_api.google_ai import FakeGoogleAIService
from demodirector_api.main import create_app
from demodirector_api.repair import MissingRequirementRepairService, RepairValidationError
from demodirector_contracts import (
    BriefCoverageReport,
    MissingRequirementRepairResult,
    RenderConfig,
    RenderResult,
    Scene,
    SceneCaptureResult,
    Storyboard,
    Timeline,
)
from demodirector_worker import (
    AutoCameraService,
    CaptionService,
    FixtureTTSAdapter,
    NarrationService,
)
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
                    "title": "Dashboard",
                    "objective": "Show the dashboard workflow.",
                    "narration": "The dashboard keeps projects visible.",
                    "source_ids": ["brief"],
                    "capture_plan": {
                        "start_url": "https://example.com/dashboard",
                        "actions": [],
                        "success_assertions": [],
                        "timeout_seconds": 30,
                    },
                    "expected_evidence": ["Dashboard visible"],
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
                    "id": "clip-dashboard",
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


def missing_report() -> BriefCoverageReport:
    return BriefCoverageReport.model_validate(
        {
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
                    "evidence": ["scene:scene-dashboard"],
                },
                {
                    "requirement_id": "export",
                    "requirement": "Show export flow",
                    "status": "missing",
                    "scene_ids": [],
                    "evidence": [],
                    "suggested_repair": "Capture the export flow.",
                },
            ],
            "summary": "Export is missing.",
            "all_covered": False,
        }
    )


def repair_scene() -> Scene:
    return Scene.model_validate(
        {
            "id": "scene-export",
            "storyboard_id": "storyboard-1",
            "order": 1,
            "title": "Export",
            "objective": "Show the export flow.",
            "narration": "Export the finished demo as an MP4.",
            "source_ids": ["brief"],
            "capture_plan": {
                "start_url": "https://example.com/export",
                "actions": [],
                "success_assertions": [],
                "timeout_seconds": 30,
            },
            "expected_evidence": ["Export confirmation visible"],
            "duration_seconds": 5,
        }
    )


def proposal(anchor: str = "scene-dashboard") -> dict[str, object]:
    return {
        "requirement_id": "export",
        "scene": repair_scene().model_dump(mode="json"),
        "insert_after_scene_id": anchor,
        "explanation": "Place export after the dashboard workflow.",
    }


def covered_report() -> dict[str, object]:
    payload = missing_report().model_dump(mode="json")
    payload["checks"][1] = {
        "requirement_id": "export",
        "requirement": "Show export flow",
        "status": "covered",
        "scene_ids": ["scene-export"],
        "evidence": ["capture:scene-export:0"],
        "suggested_repair": None,
    }
    payload["summary"] = "Both requirements are covered."
    payload["all_covered"] = True
    return payload


class FakeCaptureWorker:
    calls = 0

    def capture_scene(self, scene: Scene) -> SceneCaptureResult:
        self.calls += 1
        return SceneCaptureResult(
            scene_id=scene.id,
            status="succeeded",
            retryable=False,
            duration_ms=5_000,
            raw_clip_path="repair.webm",
        )


class FakeRenderer:
    timeline: Timeline | None = None

    def render(self, timeline: Timeline, config: RenderConfig) -> RenderResult:
        self.timeline = timeline
        return RenderResult(
            status="succeeded",
            output_path=config.output_filename,
            thumbnail_path="repair-thumbnail.jpg",
            duration_ms=timeline.duration_ms,
            width=config.width,
            height=config.height,
            has_video=True,
            has_audio=True,
        )


def service(tmp_path: Path, *, anchor: str = "scene-dashboard") -> MissingRequirementRepairService:
    return MissingRequirementRepairService(
        FakeGoogleAIService(proposal(anchor)),
        BriefCoverageService(FakeGoogleAIService(covered_report())),
        FakeCaptureWorker(),
        NarrationService(FixtureTTSAdapter(), tmp_path / "audio"),
        CaptionService(),
        AutoCameraService(),
        FakeRenderer(),
    )


def repair(
    service_under_test: MissingRequirementRepairService,
    **overrides: object,
) -> MissingRequirementRepairResult:
    arguments: dict[str, object] = {
        "project_id": "project-1",
        "brief": BRIEF,
        "requirement_id": "export",
        "storyboard": storyboard(),
        "timeline": timeline(),
        "qa_report": missing_report(),
        "capture_evidence": {"scene-dashboard": ["Dashboard visible"]},
        "max_duration_seconds": 20,
    }
    arguments.update(overrides)
    return service_under_test.repair(**arguments)  # type: ignore[arg-type]


def test_missing_requirement_repair_ends_covered_without_deleting_scenes(
    tmp_path: Path,
) -> None:
    repair_service = service(tmp_path)

    result = repair(repair_service)

    assert result.status == "succeeded"
    assert [scene.id for scene in result.storyboard.scenes] == [
        "scene-dashboard",
        "scene-export",
    ]
    assert [clip.scene_id for clip in result.timeline.scene_clips] == [
        "scene-dashboard",
        "scene-export",
    ]
    assert result.timeline.duration_ms == 15_000
    assert result.qa_report.all_covered is True


def test_duration_overage_requires_approval_before_capture(tmp_path: Path) -> None:
    repair_service = service(tmp_path)
    capture = repair_service.capture_worker

    result = repair(repair_service, max_duration_seconds=10)

    assert result.status == "requires_approval"
    assert result.timeline == timeline()
    assert isinstance(capture, FakeCaptureWorker) and capture.calls == 0


def test_repair_rejects_unknown_insertion_anchor(tmp_path: Path) -> None:
    with pytest.raises(RepairValidationError, match="unknown insertion"):
        repair(service(tmp_path, anchor="missing-scene"))


def test_repair_api_returns_verified_typed_result(tmp_path: Path) -> None:
    app = create_app()
    app.state.repair_service = service(tmp_path)
    client = TestClient(app)

    response = client.post(
        "/projects/project-1/qa/repair",
        json={
            "brief": BRIEF,
            "requirement_id": "export",
            "storyboard": storyboard().model_dump(mode="json"),
            "timeline": timeline().model_dump(mode="json"),
            "qa_report": missing_report().model_dump(mode="json"),
            "capture_evidence": {"scene-dashboard": ["Dashboard visible"]},
            "max_duration_seconds": 20,
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "succeeded"
    assert response.json()["qa_report"]["all_covered"] is True
