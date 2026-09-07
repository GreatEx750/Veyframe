from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from subprocess import TimeoutExpired
from typing import Any, cast

import pytest
from demodirector_api.google_ai import StructuredGenerationError
from demodirector_api.job_monitor import ActiveJobConflict, JobMonitor, failure_summary
from demodirector_api.presentation_jobs import PresentationJobs
from demodirector_api.presentation_pilot import NarrationWordBudgetError
from demodirector_api.records import SQLiteRecordStore
from demodirector_api.storyboard_generation import StoryboardValidationError
from demodirector_contracts.jobs import GenerationJob
from demodirector_worker.narration import NarrationQuotaError
from demodirector_worker.renderer import RendererError
from google.genai.errors import ClientError
from test_auth import auth_client, bearer, project_payload, signup
from test_generation import FakeCaptureWorker, build_service
from test_generation_jobs import jobs_fixture


def test_failure_details_explain_known_causes_without_leaking_payloads() -> None:
    assert "900-second" in failure_summary(TimeoutExpired("private-command", 900))
    assert "requested video length" in failure_summary(
        StoryboardValidationError("Storyboard duration is outside the requested 10% budget.")
    )
    assert "private" not in failure_summary(RuntimeError("private provider response"))
    assert "private" not in failure_summary(StoryboardValidationError("Scene private source"))
    assert failure_summary(StoryboardValidationError(
        "Scene private source", code="unknown_source"
    )) == "A generated scene referenced a source that was not in the inspected evidence."


def test_wrapped_gemini_failure_reports_safe_status_without_provider_payload() -> None:
    error = StructuredGenerationError("private request")
    error.__cause__ = ClientError(400, {"error": {"message": "private api_key=abc"}})
    summary = failure_summary(error)
    assert "400" in summary and "request" in summary
    assert "private" not in summary and "abc" not in summary


def test_speech_quota_failure_has_actionable_safe_details() -> None:
    summary = failure_summary(NarrationQuotaError("private api_key=abc"))
    assert "Google speech rate or quota limit" in summary
    assert "retry" in summary
    assert "private" not in summary and "abc" not in summary
    summary = failure_summary(NarrationWordBudgetError("private"))
    assert "word budget" in summary and "private" not in summary


def test_render_path_failure_is_actionable_without_exposing_paths() -> None:
    summary = failure_summary(
        RendererError("Media path is outside the approved project directory.")
    )
    assert "configured media folder" in summary
    assert "private" not in failure_summary(RendererError("ffmpeg failed: private api_key=abc"))


def test_account_limit_is_atomic_across_services(tmp_path: Path) -> None:
    _, projects, _, _ = build_service(tmp_path, FakeCaptureWorker())
    project = projects.get("project-one-click")
    assert project
    other = project.model_copy(update={"id": "second"})
    projects.create(other)

    def reserve(index: int) -> bool:
        monitor = JobMonitor(SQLiteRecordStore(tmp_path / "monitor.db"), projects)
        try:
            monitor.acquire(project if index == 0 else other, f"job-{index}", f"record-{index}")
            return True
        except ActiveJobConflict:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(reserve, [0, 1])) == 1


def test_logs_are_durable_sanitized_and_eta_does_not_claim_stalled_work_is_healthy(
    tmp_path: Path,
) -> None:
    _, projects, _, _ = build_service(tmp_path, FakeCaptureWorker())
    project = projects.get("project-one-click")
    assert project
    records = SQLiteRecordStore(tmp_path / "monitor.db")
    monitor = JobMonitor(records, projects)
    past = datetime.now(UTC) - timedelta(minutes=30)
    job = GenerationJob(
        id="job",
        project_id=project.id,
        status="running",
        stage="render",
        version=1,
        created_at=past,
        updated_at=past,
        message="Rendering",
    )
    monitor.event(job, "Rendering https://host/?api_key=secretvalue Bearer secretvalue", at=past)
    detail = JobMonitor(records, projects).detail(project, job, "presentation_preview")
    assert detail.health == "unresponsive"
    assert detail.eta_max_seconds is None
    assert "secretvalue" not in detail.model_dump_json()
    assert len(detail.events) == 1


def test_terminal_job_releases_capacity_and_other_owners_are_independent(tmp_path: Path) -> None:
    _, projects, _, _ = build_service(tmp_path, FakeCaptureWorker())
    project = projects.get("project-one-click")
    assert project
    records = SQLiteRecordStore(tmp_path / "monitor.db")
    monitor = JobMonitor(records, projects)
    monitor.acquire(project, "first", "first-record")
    now = datetime.now(UTC)
    job = GenerationJob(
        id="first",
        project_id=project.id,
        status="succeeded",
        stage="done",
        version=1,
        created_at=now,
        updated_at=now,
        message="Ready",
    )
    records.put("first-record", 0, job.model_dump(mode="json"))
    monitor.acquire(project, "next", "next-record")
    foreign = project.model_copy(update={"id": "foreign", "owner_user_id": "different-user"})
    projects.create(foreign)
    monitor.acquire(foreign, "independent", "independent-record")
    with pytest.raises(ActiveJobConflict):
        monitor.acquire(project, "third", "third-record")


def test_product_and_presentation_share_the_limit(tmp_path: Path) -> None:
    jobs = jobs_fixture(tmp_path)
    original = jobs.generation.projects.get("project-one-click")
    assert original
    other = original.model_copy(
        update={
            "id": "presentation",
            "demo_mode": "presentation_demo",
            "requested_duration_seconds": 120,
        }
    )
    jobs.generation.projects.create(other)
    jobs.start(original.id)
    preview = PresentationJobs(jobs.generation, jobs.records, tmp_path, tmp_path / "db", tmp_path)
    try:
        with pytest.raises(ActiveJobConflict):
            preview.start(other.id)
    finally:
        preview.pool.shutdown(wait=False)


def test_jobs_routes_are_private_and_active_projects_cannot_be_deleted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_DATABASE_PATH", str(tmp_path / "workflows.db"))
    client, _ = auth_client(tmp_path / "auth.db")
    owner = signup(client, "owner-jobs@example.com")
    stranger = signup(client, "stranger-jobs@example.com")
    project = client.post(
        "/projects", json=project_payload("Private job"), headers=bearer(owner)
    ).json()
    records = cast(Any, client.app).state.workflow_records
    now = datetime.now(UTC)
    job = GenerationJob(
        id="private-job",
        project_id=project["id"],
        status="queued",
        stage="inspection",
        version=1,
        created_at=now,
        updated_at=now,
        message="Queued",
    )
    records.put("generation-private-job", 0, job.model_dump(mode="json"))
    records.put(f"generation-project-{project['id']}", 0, {"job_id": job.id})
    assert client.get("/jobs").status_code == 401
    assert client.get("/jobs", headers=bearer(stranger)).json()["jobs"] == []
    assert client.get("/jobs/private-job", headers=bearer(stranger)).status_code == 404
    result = client.get("/jobs", headers=bearer(owner))
    assert result.status_code == 200
    assert result.json()["active_count"] == 1
    assert result.headers["cache-control"] == "no-store"
    assert client.delete(f"/projects/{project['id']}", headers=bearer(owner)).status_code == 409


def test_fresh_heartbeat_distinguishes_slow_work_from_a_missing_worker(tmp_path: Path) -> None:
    _, projects, _, _ = build_service(tmp_path, FakeCaptureWorker())
    project = projects.get("project-one-click")
    assert project
    monitor = JobMonitor(SQLiteRecordStore(tmp_path / "monitor.db"), projects)
    past = datetime.now(UTC) - timedelta(minutes=4)
    job = GenerationJob(
        id="slow-job",
        project_id=project.id,
        status="running",
        stage="render",
        version=1,
        created_at=past,
        updated_at=past,
        message="Rendering a slide",
    )
    monitor.event(job, at=past)
    with monitor.heartbeat(job):
        detail = monitor.detail(project, job, "presentation_preview")
        assert detail.health == "slow"
        assert detail.eta_max_seconds is None
        assert len(detail.events) == 1
    monitor.event(job, "Slide saved")
    detail = monitor.detail(project, job, "presentation_preview")
    assert detail.health == "responding"
    assert detail.eta_max_seconds is not None


def test_a_presentation_in_another_service_blocks_standard_generation(tmp_path: Path) -> None:
    jobs = jobs_fixture(tmp_path)
    original = jobs.generation.projects.get("project-one-click")
    assert original
    other = original.model_copy(update={"id": "active-presentation"})
    jobs.generation.projects.create(other)
    now = datetime.now(UTC)
    job = GenerationJob(
        id="presentation-job",
        project_id=other.id,
        status="running",
        stage="render",
        version=1,
        created_at=now,
        updated_at=now,
        message="Rendering",
    )
    jobs.records.put(f"presentation-preview:{other.id}", 0, job.model_dump(mode="json"))
    with pytest.raises(ActiveJobConflict):
        jobs.start(original.id)
