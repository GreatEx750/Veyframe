from pathlib import Path

import pytest
from demodirector_api.edit_planner import validate_edit_plan
from demodirector_api.optimization import OptimizationService
from demodirector_api.timeline_edits import TimelineEditError, TimelineEditService
from demodirector_api.video_reviews import FakeVideoCritic, ReviewConflict
from demodirector_contracts import EditOperation, EditPlan, Timeline
from test_video_reviews import critic_output, setup_review


def setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[OptimizationService, str]:
    monkeypatch.setattr("demodirector_api.video_reviews.probe_video", lambda *_: None)
    reviews, export_id = setup_review(tmp_path)
    assert reviews.exports.timelines is not None
    history = reviews.exports.timelines.current("project-1")
    assert history is not None
    payload = history.current.timeline.model_dump()
    payload["zoom_clips"] = [
        {
            "id": "z1",
            "start_ms": 0,
            "end_ms": 1000,
            "scale": 2,
            "target_rect": {"x": 0, "y": 0, "width": 100, "height": 100},
            "easing": "ease_in_out",
            "source": "auto",
        }
    ]
    current = reviews.exports.timelines.commit(1, Timeline.model_validate(payload), "Zoom", [])
    export_id = reviews.exports.create("project-1", current.current.timeline, "720p").id
    review = reviews.create("project-1", export_id)
    service = OptimizationService(reviews, reviews.exports.timelines, reviews.records)
    return service, review.id


@pytest.mark.parametrize(
    "after,reason", [(90, "target_reached"), (75, "improved"), (65, "no_improvement")]
)
def test_approved_one_cycle_preserves_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, after: int, reason: str
) -> None:
    service, review_id = setup(tmp_path, monkeypatch)
    proposal = service.propose("project-1", review_id)
    assert proposal.proposal.operations[0].operation_type == "delete_zoom"
    assert service.timelines.current("project-1").current.version == 2  # type: ignore[union-attr]
    with pytest.raises(ReviewConflict):
        service.apply("project-1", proposal.id, 2, False)
    service.reviews.critic = FakeVideoCritic(critic_output(after))
    result = service.apply("project-1", proposal.id, 2, True)
    assert result.status == "succeeded" and result.stop_reason == reason
    assert result.after_version == 3 and result.score_delta == after - 70
    assert result.cycles == 1 and result.model_calls == 1
    assert service.reviews.exports.latest("project-1").id == result.before_export_id  # type: ignore[union-attr]
    assert service.reviews.exports.get("project-1", result.after_export_id) is not None  # type: ignore[arg-type]
    assert service.apply("project-1", proposal.id, 2, True) == result
    assert service.reviews.critic.calls == 1


def test_cancel_and_stale_proposals(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service, review_id = setup(tmp_path, monkeypatch)
    proposal = service.propose("project-1", review_id)
    assert service.cancel("project-1", proposal.id).status == "cancelled"
    assert service.apply("project-1", proposal.id, 2, True).status == "cancelled"
    proposal = service.propose("project-1", review_id)
    with pytest.raises(ReviewConflict):
        service.apply("project-1", proposal.id, 1, True)
    with pytest.raises(KeyError):
        service.get("foreign", proposal.id)


def test_review_failure_retains_candidate_and_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, review_id = setup(tmp_path, monkeypatch)
    proposal = service.propose("project-1", review_id)

    def fail(*_: object, **__: object) -> None:
        raise ValueError("provider down")

    monkeypatch.setattr(service.reviews.critic, "review", fail)
    result = service.apply("project-1", proposal.id, 2, True)
    assert result.stop_reason == "review_failed"
    assert result.after_export_id and result.after_score is None
    assert service.reviews.exports.latest("project-1").id == result.before_export_id  # type: ignore[union-attr]


def test_continuous_capture_caption_repair_and_atomic_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _ = setup(tmp_path, monkeypatch)
    history = service.timelines.current("project-1")
    assert history is not None
    data = history.current.timeline.model_dump()
    data["caption_clips"] = [
        {
            "id": "caption-1",
            "scene_id": "narration-beat-1",
            "start_ms": 0,
            "end_ms": 1500,
            "text": "Original words preserved",
        }
    ]
    timeline = Timeline.model_validate(data)
    operation = EditOperation(
        operation_type="update_caption",
        target_id="caption-1",
        arguments={"text": "Original words\npreserved"},
        rationale="Wrap",
    )
    validate_edit_plan(
        EditPlan(supported=True, summary="Wrap", explanation="Safe", operations=[operation]),
        timeline,
    )
    bad = EditOperation(operation_type="delete_zoom", target_id="not-a-zoom", rationale="Invalid")
    with pytest.raises(TimelineEditError):
        TimelineEditService(service.timelines).apply(
            history.current.timeline,
            2,
            [EditOperation(operation_type="delete_zoom", target_id="z1", rationale="Valid"), bad],
            "Atomic",
        )
    assert service.timelines.current("project-1") == history
