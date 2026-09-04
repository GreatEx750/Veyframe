import os
import shutil
from pathlib import Path

import pytest
from demodirector_api.exports import ExportService, SQLiteExportRepository
from demodirector_api.main import create_app
from demodirector_api.records import RecordConflict, SQLiteRecordStore
from demodirector_api.repositories import SQLiteTimelineRepository
from demodirector_api.video_reviews import FakeVideoCritic, ReviewConflict, VideoReviewService
from demodirector_contracts.quality import DIMENSIONS, CriticOutput, VideoReview
from fastapi.testclient import TestClient
from test_exports import FileRenderer, media_binary, timeline


def critic_output(score: int = 70) -> CriticOutput:
    return CriticOutput.model_validate(
        {
            "scores": [
                {
                    "dimension": d,
                    "score": score,
                    "explanation": "Visible media inspected",
                    "finding_ids": ["finding-1"] if d == "camera_quality" else [],
                }
                for d in DIMENSIONS
            ],
            "findings": [
                {
                    "id": "finding-1",
                    "dimension": "camera_quality",
                    "severity": "high",
                    "start_ms": 0,
                    "end_ms": 1000,
                    "observation": "Zoom hides the navigation",
                    "evidence_summary": "Navigation is clipped in the first second",
                    "evidence_ids": ["media-0"],
                    "repair_category": "camera",
                }
            ],
        }
    )


def setup_review(tmp_path: Path) -> tuple[VideoReviewService, str]:
    records = SQLiteRecordStore(tmp_path / "db.sqlite")
    timelines = SQLiteTimelineRepository(tmp_path / "db.sqlite")
    fixture = timeline(tmp_path / "scene.mp4", tmp_path / "audio.wav")
    timelines.initialize(fixture)
    exports = ExportService(
        FileRenderer(tmp_path),
        SQLiteExportRepository(tmp_path / "db.sqlite"),
        tmp_path,
        records=records,
        timelines=timelines,
    )
    video = exports.create("project-1", fixture, "720p")
    return VideoReviewService(exports, records, FakeVideoCritic(critic_output())), video.id


def test_review_is_cached_immutable_and_bound_to_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("demodirector_api.video_reviews.probe_video", lambda *_: None)
    service, export_id = setup_review(tmp_path)
    original = service.exports.get("project-1", export_id)
    review = service.create("project-1", export_id)
    assert review.status == "succeeded"
    assert review.timeline_version == 1 and review.overall_score == 70
    assert service.create("project-1", export_id) == review
    assert isinstance(service.critic, FakeVideoCritic) and service.critic.calls == 1
    assert service.critic.media == [b"small mp4 fixture"]
    assert service.exports.get("project-1", export_id) == original
    assert service.latest("project-1", export_id) == review
    with pytest.raises(KeyError):
        service.create("foreign", export_id)
    with pytest.raises(RecordConflict):
        service.records.put(f"review-{review.id}", 0, review.model_dump(mode="json"))


@pytest.mark.parametrize(
    "change",
    [
        {"overall_score": 101},
        {"overall_score": 0},
        {"timeline_version": 0},
        {"status": "running"},
        {"duration_ms": 500},
    ],
)
def test_invalid_review_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: dict[str, object]
) -> None:
    monkeypatch.setattr("demodirector_api.video_reviews.probe_video", lambda *_: None)
    service, export_id = setup_review(tmp_path)
    review = service.create("project-1", export_id)
    with pytest.raises(ValueError):
        VideoReview.model_validate({**review.model_dump(), **change})


def test_foreign_evidence_and_bounded_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("demodirector_api.video_reviews.probe_video", lambda *_: None)
    service, export_id = setup_review(tmp_path)
    output = critic_output().model_dump()
    output["findings"][0]["evidence_ids"] = ["invented"]
    service.critic = FakeVideoCritic(CriticOutput.model_validate(output))
    first = service.create("project-1", export_id)
    assert first.status == "failed" and first.overall_score is None
    with pytest.raises(ReviewConflict):
        service.create("project-1", export_id)
    for _ in range(2):
        assert service.create("project-1", export_id, retry=True).status == "failed"
    with pytest.raises(ReviewConflict):
        service.create("project-1", export_id, retry=True)
    assert service.critic.calls == 3


def test_invalid_media_never_calls_provider(tmp_path: Path) -> None:
    service, export_id = setup_review(tmp_path)
    review = service.create("project-1", export_id)
    assert review.status == "failed" and review.model_calls == 0


def test_real_twenty_second_mp4_review_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FFPROBE_PATH", media_binary("ffprobe"))
    service, export_id = setup_review(tmp_path)
    stored = service.exports.repository.get("project-1", export_id)
    assert stored is not None and stored.file_path
    source = Path(__file__).resolve().parents[3] / "artifacts/verification/golden-export-20s.mp4"
    shutil.copyfile(source, stored.file_path)
    from demodirector_api.exports import StoredExport

    service.exports.repository.save(
        StoredExport(
            stored.export.model_copy(update={"duration_ms": 20000}),
            stored.file_path,
            stored.token_hash,
        )
    )
    app = create_app()
    app.state.video_review_service = service
    client = TestClient(app)
    response = client.post(f"/projects/project-1/exports/{export_id}/reviews", json={})
    assert response.status_code == 200
    assert response.json()["status"] == "succeeded"
    assert len(response.json()["result"]["scores"]) == 6
    assert (
        client.get(f"/projects/project-1/exports/{export_id}/reviews/latest").json()
        == response.json()
    )
    assert client.post(f"/projects/foreign/exports/{export_id}/reviews", json={}).status_code == 404


@pytest.mark.live
@pytest.mark.skipif(os.getenv("RUN_LIVE_VIDEO_REVIEW") != "1", reason="Explicit paid smoke only")
def test_live_gemini_video_review(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from demodirector_api.google_ai import GoogleAISettings
    from demodirector_api.video_reviews import GeminiVideoCritic

    monkeypatch.setenv("FFPROBE_PATH", media_binary("ffprobe"))
    service, export_id = setup_review(tmp_path)
    stored = service.exports.repository.get("project-1", export_id)
    assert stored is not None and stored.file_path
    from test_exports import create_media

    video, _ = create_media(tmp_path / "real", media_binary("ffmpeg"))
    shutil.copyfile(video, stored.file_path)
    service.critic = GeminiVideoCritic(GoogleAISettings.from_environment())
    result = service.create("project-1", export_id)
    assert result.status == "succeeded" and result.model_calls == 1
