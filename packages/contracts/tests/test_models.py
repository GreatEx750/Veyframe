from datetime import UTC, datetime
from typing import Any

import pytest
from demodirector_contracts import (
    AudioClip,
    BoundingBox,
    CaptionClip,
    CaptureAction,
    CapturePlan,
    DemoGenerationResult,
    EditOperation,
    InteractionEvent,
    ProductUnderstanding,
    Project,
    QACheck,
    ResearchSource,
    Scene,
    SceneCaptureResult,
    SceneClip,
    Storyboard,
    Timeline,
    VideoExport,
    VideoPresentationConfig,
    Viewport,
    ZoomClip,
)
from pydantic import ValidationError


def valid_action(**overrides: Any) -> dict[str, Any]:
    action: dict[str, Any] = {
        "type": "click",
        "locator_strategy": "role",
        "locator": "Create a demo",
        "value": None,
        "description": "Open the demo creator",
    }
    action.update(overrides)
    return action


def valid_scene(**overrides: Any) -> dict[str, Any]:
    scene: dict[str, Any] = {
        "id": "scene-1",
        "storyboard_id": "storyboard-1",
        "order": 0,
        "title": "Open the studio",
        "objective": "Introduce the primary workflow",
        "narration": "Start by opening the demo studio.",
        "source_ids": ["source-1"],
        "capture_plan": {
            "start_url": "https://example.com",
            "actions": [valid_action()],
            "success_assertions": [
                valid_action(
                    type="assert_visible",
                    description="Confirm the studio is visible",
                )
            ],
            "timeout_seconds": 30,
        },
        "expected_evidence": ["Studio heading"],
        "duration_seconds": 8,
    }
    scene.update(overrides)
    return scene


def test_generation_result_requires_a_published_project_and_matching_export() -> None:
    now = datetime.now(UTC)
    project = Project.model_validate(
        {
            "id": "project-1",
            "name": "Launch demo",
            "website_url": "https://example.com",
            "product_summary": "A concise product summary",
            "audience": "Product teams",
            "tone": "Professional",
            "requested_duration_seconds": 20,
            "cta": "Start a trial",
            "status": "published",
            "job_status": "succeeded",
            "created_at": now,
            "updated_at": now,
        }
    )
    video_export = VideoExport(
        id="export-1",
        project_id=project.id,
        status="succeeded",
        quality="1440p",
        filename="demo.mp4",
        width=2560,
        height=1440,
        duration_ms=20_000,
        size_bytes=1024,
        download_url="/projects/project-1/exports/export-1/download?token=12345678901234567890",
        retryable=False,
        created_at=now,
    )

    result = DemoGenerationResult(
        project=project,
        export=video_export,
        timeline_version=1,
        warnings=["Partner research was unavailable."],
    )

    assert result.export.project_id == result.project.id
    with pytest.raises(ValidationError):
        DemoGenerationResult(
            project=project.model_copy(update={"status": "rendering"}),
            export=video_export,
            timeline_version=1,
        )


def test_valid_contract_fixture_crosses_the_shared_boundary() -> None:
    now = datetime.now(UTC)
    project = Project.model_validate(
        {
            "id": "project-1",
            "name": "Launch demo",
            "website_url": "https://example.com",
            "product_summary": "A concise product summary",
            "audience": "Product teams",
            "tone": "Professional",
            "requested_duration_seconds": 60,
            "cta": "Start a trial",
            "created_at": now,
            "updated_at": now,
        }
    )
    source = ResearchSource.model_validate(
        {
            "id": "source-1",
            "project_id": project.id,
            "title": "Example product",
            "url": "https://example.com/product",
            "snippet": "Official product information",
            "source_type": "website",
            "retrieved_at": now,
        }
    )
    scene = Scene.model_validate(valid_scene())
    storyboard = Storyboard(
        id="storyboard-1",
        project_id=project.id,
        version=1,
        total_duration_seconds=scene.duration_seconds,
        status="draft",
        scenes=[scene],
    )
    event = InteractionEvent(
        timestamp_ms=750,
        event_type="click",
        locator="Create a demo",
        x=120,
        y=80,
        bounding_box=BoundingBox(x=90, y=60, width=180, height=44),
        viewport=Viewport(width=1440, height=900),
    )
    scene_clip = SceneClip(
        id="clip-1",
        scene_id=scene.id,
        source_uri="captures/scene-1.webm",
        start_ms=0,
        end_ms=8000,
    )
    caption_clip = CaptionClip(
        id="caption-1",
        scene_id=scene.id,
        text=scene.narration,
        start_ms=0,
        end_ms=8000,
    )
    audio_clip = AudioClip(
        id="audio-1",
        scene_id=scene.id,
        source_uri="narration/scene-1.wav",
        start_ms=0,
        end_ms=8000,
    )
    zoom = ZoomClip(
        id="zoom-1",
        start_ms=500,
        end_ms=2000,
        scale=1.5,
        target_rect=BoundingBox(x=90, y=60, width=180, height=44),
        easing="ease_in_out",
        source="auto",
    )
    timeline = Timeline(
        project_id=project.id,
        duration_ms=8000,
        scene_clips=[scene_clip],
        caption_clips=[caption_clip],
        zoom_clips=[zoom],
        audio_clips=[audio_clip],
    )
    edit = EditOperation(
        operation_type="trim_scene",
        target_id=scene.id,
        arguments={"end_ms": 7000},
        rationale="Tighten the opening",
    )
    qa_check = QACheck(
        requirement_id="studio",
        requirement="Show the studio",
        status="covered",
        scene_ids=[scene.id],
        evidence=["Studio heading"],
    )

    assert source.project_id == project.id
    assert storyboard.scenes == [scene]
    assert event.bounding_box is not None
    assert timeline.zoom_clips == [zoom]
    assert edit.operation_type == "trim_scene"
    assert qa_check.status == "covered"


def test_capture_action_rejects_unknown_type() -> None:
    with pytest.raises(ValidationError, match="Input should be"):
        CaptureAction.model_validate(valid_action(type="evaluate"))


def test_capture_plan_rejects_non_assertion_success_action() -> None:
    with pytest.raises(ValidationError, match="assert_visible"):
        CapturePlan.model_validate(
            {
                "start_url": "https://example.com",
                "actions": [],
                "success_assertions": [CaptureAction.model_validate(valid_action())],
                "timeout_seconds": 30,
            }
        )


def test_scene_duration_must_be_positive() -> None:
    with pytest.raises(ValidationError, match="greater than 0"):
        Scene.model_validate(valid_scene(duration_seconds=0))


def test_capture_rejects_interaction_after_clip_end() -> None:
    with pytest.raises(ValidationError, match="interaction timestamps"):
        SceneCaptureResult.model_validate(
            {
                "scene_id": "scene-1",
                "status": "succeeded",
                "retryable": False,
                "duration_ms": 100,
                "interaction_events": [
                    {
                        "timestamp_ms": 101,
                        "event_type": "click",
                        "locator": "Save",
                        "viewport": {"width": 1280, "height": 720},
                    }
                ],
            }
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"scale": 0.75}, "greater than or equal to 1"),
        ({"scale": 4.5}, "less than or equal to 4"),
        ({"end_ms": 1000}, "end_ms must be greater than start_ms"),
    ],
)
def test_zoom_scale_and_time_range_validate(overrides: dict[str, Any], message: str) -> None:
    values: dict[str, Any] = {
        "id": "zoom-1",
        "start_ms": 1000,
        "end_ms": 2000,
        "scale": 1.5,
        "target_rect": {"x": 10, "y": 20, "width": 200, "height": 100},
        "easing": "ease_in_out",
        "source": "auto",
    }
    values.update(overrides)

    with pytest.raises(ValidationError, match=message):
        ZoomClip.model_validate(values)


def test_timeline_rejects_clip_beyond_its_duration() -> None:
    zoom = ZoomClip(
        id="zoom-1",
        start_ms=1000,
        end_ms=2000,
        scale=1.5,
        target_rect=BoundingBox(x=10, y=20, width=200, height=100),
        easing="ease_in_out",
        source="auto",
    )

    with pytest.raises(ValidationError, match="timeline duration"):
        Timeline(project_id="project-1", duration_ms=1500, zoom_clips=[zoom])


def test_timeline_rejects_cursor_event_beyond_its_duration() -> None:
    event = InteractionEvent(
        timestamp_ms=1_501,
        event_type="click",
        x=640,
        y=360,
        viewport=Viewport(width=1280, height=720),
    )

    with pytest.raises(ValidationError, match="cursor timestamps"):
        Timeline(project_id="project-1", duration_ms=1_500, cursor_events=[event])


def test_zoom_rejects_an_incomplete_mouse_focus_point() -> None:
    with pytest.raises(ValidationError, match="focus_x and focus_y"):
        ZoomClip(
            id="zoom-1",
            start_ms=0,
            end_ms=1_000,
            scale=1.5,
            target_rect=BoundingBox(x=10, y=20, width=200, height=100),
            focus_x=110,
            easing="ease_in_out",
            source="auto",
        )


def test_edit_operation_rejects_unknown_type() -> None:
    with pytest.raises(ValidationError, match="Input should be"):
        EditOperation(
            operation_type="run_script",  # type: ignore[arg-type]
            target_id="scene-1",
            arguments={},
            rationale="Not allowed",
        )


def test_video_presentation_template_is_typed_and_defaults_safely() -> None:
    assert Timeline(project_id="project-1", duration_ms=1_000).presentation == (
        VideoPresentationConfig(template="edge_to_edge")
    )
    assert VideoPresentationConfig(template="spotlight").template == "spotlight"
    with pytest.raises(ValidationError, match="Input should be"):
        VideoPresentationConfig(template="model_filter")  # type: ignore[arg-type]


def test_contracts_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Scene.model_validate(valid_scene(arbitrary_code="window.alert('no')"))


def test_product_understanding_rejects_unsupported_external_feature() -> None:
    with pytest.raises(ValidationError, match="external product features"):
        ProductUnderstanding.model_validate(
            {
                "project_id": "project-1",
                "value_proposition": "Focused workflows",
                "audience": "Product leaders",
                "features": [
                    {
                        "id": "invented-feature",
                        "name": "Invented automation",
                        "description": "This is not supported by a source.",
                        "source_ids": [],
                        "user_provided": False,
                    }
                ],
                "suggested_demo_flows": [],
                "claims": [],
            }
        )
