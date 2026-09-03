from __future__ import annotations

from pathlib import Path

import pytest
from demodirector_api.google_ai import FakeGoogleAIService
from demodirector_api.main import create_app
from demodirector_api.repositories import SQLiteTimelineRepository
from demodirector_api.timeline_edits import TimelineEditError, TimelineEditService
from demodirector_contracts import EditOperation, Timeline
from fastapi.testclient import TestClient


def timeline() -> Timeline:
    return Timeline.model_validate(
        {
            "project_id": "project-1",
            "duration_ms": 10_000,
            "scene_clips": [
                {
                    "id": "scene-opening",
                    "scene_id": "opening",
                    "start_ms": 0,
                    "end_ms": 4_000,
                    "source_uri": "opening.webm",
                },
                {
                    "id": "scene-workflow",
                    "scene_id": "workflow",
                    "start_ms": 4_000,
                    "end_ms": 10_000,
                    "source_uri": "workflow.webm",
                },
            ],
            "caption_clips": [
                {
                    "id": "caption-opening",
                    "scene_id": "opening",
                    "start_ms": 0,
                    "end_ms": 4_000,
                    "text": "Opening caption",
                }
            ],
            "zoom_clips": [
                {
                    "id": "zoom-workflow",
                    "start_ms": 5_000,
                    "end_ms": 6_500,
                    "scale": 1.4,
                    "target_rect": {"x": 100, "y": 100, "width": 300, "height": 180},
                    "focus_x": 250,
                    "focus_y": 190,
                    "source_viewport": {"width": 1280, "height": 720},
                    "easing": "ease_in_out",
                    "source": "auto",
                }
            ],
            "audio_clips": [],
        }
    )


def operation(kind: str, target: str, arguments: dict[str, object]) -> EditOperation:
    return EditOperation.model_validate(
        {
            "operation_type": kind,
            "target_id": target,
            "arguments": arguments,
            "rationale": "User-approved timeline change.",
        }
    )


def test_invalid_operation_rolls_back_entire_transaction(tmp_path: Path) -> None:
    repository = SQLiteTimelineRepository(tmp_path / "timeline.db")
    repository.initialize(timeline())
    service = TimelineEditService(repository)

    with pytest.raises(TimelineEditError, match="unknown zoom"):
        service.apply(
            timeline(),
            1,
            [
                operation("update_zoom", "zoom-workflow", {"scale": 1.8}),
                operation("delete_zoom", "missing-zoom", {}),
            ],
            "Unsafe mixed edit",
        )

    current = repository.current("project-1")
    assert current is not None
    assert current.current.version == 1
    assert current.current.timeline.zoom_clips[0].scale == 1.4


def test_undo_and_redo_move_between_immutable_versions(tmp_path: Path) -> None:
    repository = SQLiteTimelineRepository(tmp_path / "timeline.db")
    service = TimelineEditService(repository)

    applied = service.apply(
        timeline(),
        0,
        [operation("update_zoom", "zoom-workflow", {"scale": 1.8})],
        "Increase focus",
    )
    undone = repository.undo("project-1")
    redone = repository.redo("project-1")

    assert applied.current.version == 2
    assert applied.current.timeline.zoom_clips[0].scale == 1.8
    assert undone.current.version == 1
    assert undone.current.timeline.zoom_clips[0].scale == 1.4
    assert undone.can_redo is True
    assert redone.current.version == 2
    assert redone.current.timeline.zoom_clips[0].scale == 1.8


def test_targeted_edit_keeps_unrelated_tracks_identical(tmp_path: Path) -> None:
    repository = SQLiteTimelineRepository(tmp_path / "timeline.db")
    service = TimelineEditService(repository)
    original = timeline()

    applied = service.apply(
        original,
        0,
        [
            operation(
                "update_zoom",
                "zoom-workflow",
                {"end_ms": 7_000, "focus_x": 900, "focus_y": 300},
            )
        ],
        "Hold focus longer",
    )

    updated = applied.current.timeline
    assert updated.scene_clips == original.scene_clips
    assert updated.caption_clips == original.caption_clips
    assert updated.audio_clips == original.audio_clips
    assert updated.zoom_clips[0].end_ms == 7_000
    assert updated.zoom_clips[0].focus_x == 900
    assert updated.zoom_clips[0].focus_y == 300


def test_presentation_template_is_saved_as_an_undoable_typed_edit(tmp_path: Path) -> None:
    repository = SQLiteTimelineRepository(tmp_path / "timeline.db")
    service = TimelineEditService(repository)

    applied = service.apply(
        timeline(),
        0,
        [
            operation(
                "change_presentation",
                "project-1",
                {"template": "spotlight"},
            )
        ],
        "Apply spotlight frame",
    )
    undone = repository.undo("project-1")

    assert applied.current.timeline.presentation.template == "spotlight"
    assert undone.current.timeline.presentation.template == "edge_to_edge"


def test_timeline_apply_and_undo_api(tmp_path: Path) -> None:
    repository = SQLiteTimelineRepository(tmp_path / "timeline.db")
    client = TestClient(
        create_app(
            ai_service=FakeGoogleAIService({}),
            timeline_repository=repository,
        )
    )
    edit = operation("trim_scene", "scene-opening", {"start_ms": 0, "end_ms": 3_000})

    applied = client.post(
        "/projects/project-1/timeline/apply",
        json={
            "expected_version": 0,
            "base_timeline": timeline().model_dump(),
            "summary": "Shorten the opening",
            "operations": [edit.model_dump()],
        },
    )
    undone = client.post("/projects/project-1/timeline/undo")

    assert applied.status_code == 200
    assert applied.json()["current"]["version"] == 2
    assert applied.json()["current"]["timeline"]["duration_ms"] == 9_000
    assert undone.status_code == 200
    assert undone.json()["current"]["version"] == 1
    assert undone.json()["current"]["timeline"]["duration_ms"] == 10_000
