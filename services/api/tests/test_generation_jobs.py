from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from demodirector_api.generation_jobs import (
    CaptureTokenVault,
    CloudGenerationDispatcher,
    GenerationJobs,
    GenerationStages,
    JobConflict,
    LocalJobDispatcher,
)
from demodirector_api.records import SQLiteRecordStore
from demodirector_contracts.jobs import GenerationJob
from test_generation import FakeCaptureWorker, build_service


def jobs_fixture(tmp_path: Path) -> GenerationJobs:
    service, _, _, _ = build_service(tmp_path, FakeCaptureWorker())
    records = SQLiteRecordStore(tmp_path / "jobs.sqlite")
    vault = CaptureTokenVault(tmp_path, False)
    return GenerationJobs(
        records, GenerationStages(service, records, vault), LocalJobDispatcher(), service, vault
    )


def test_stage_checkpoints_survive_reconstruction(tmp_path: Path) -> None:
    jobs = jobs_fixture(tmp_path)
    job = jobs.start("project-one-click")
    assert job.status == "queued"
    assert jobs.start(job.project_id).id == job.id
    for expected in ["research", "understanding", "storyboard", "capture"]:
        job = jobs.step(job.id)
        assert job.stage == expected and job.status == "queued"
    restored = GenerationJobs(
        SQLiteRecordStore(tmp_path / "jobs.sqlite"),
        jobs.executor,
        LocalJobDispatcher(),
        jobs.generation,
        jobs.vault,
    )
    while job.status != "succeeded":
        job = restored.step(job.id)
    assert len(job.completed_stages) == 7 and job.export_id == "export-one-click"
    assert restored.step(job.id) == job
    assert len(jobs.generation.capture_worker.scenes) == 1  # type: ignore[attr-defined]
    with pytest.raises(KeyError):
        restored.get(job.id, "foreign")


def test_duplicate_delivery_and_uncertain_paid_stage_require_approval(tmp_path: Path) -> None:
    jobs = jobs_fixture(tmp_path)
    job = jobs.step(jobs.start("project-one-click").id)
    claimed = jobs._save(
        job, status="running", attempts=1, lease_until=datetime.now(UTC) + timedelta(minutes=5)
    )
    with pytest.raises(JobConflict):
        jobs.step(job.id)
    jobs._save(claimed, lease_until=datetime.now(UTC) - timedelta(seconds=1))
    interrupted = jobs.step(job.id)
    assert interrupted.status == "awaiting_retry" and interrupted.stage == "research"
    with pytest.raises(JobConflict):
        jobs.retry(job.project_id, job.id, False)
    retried = jobs.retry(job.project_id, job.id, True)
    assert retried.status == "queued"
    assert jobs.step(job.id).stage == "understanding"


def test_saved_paid_checkpoint_is_reused_after_crash(tmp_path: Path) -> None:
    jobs = jobs_fixture(tmp_path)
    job = jobs.step(jobs.start("project-one-click").id)
    claimed = jobs._save(
        job, status="running", attempts=1, lease_until=datetime.now(UTC) - timedelta(seconds=1)
    )
    jobs.records.put(f"job-stage-{job.id}-research", 0, {"warning": None})

    class MustNotExecute:
        def execute(self, job: GenerationJob) -> dict[str, Any]:
            raise AssertionError("Saved stage must not execute")

    jobs.executor = MustNotExecute()
    result = jobs.step(claimed.id)
    assert result.stage == "understanding" and result.status == "queued"


def test_bounded_retries_and_no_plaintext_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEMO_CAPTURE_AUTH_ORIGINS", "https://example.com")
    jobs = jobs_fixture(tmp_path)
    job = jobs.start("project-one-click", "private-test-session")
    context = jobs.records.get(f"job-input-{job.id}")
    assert context is not None and "private-test-session" not in str(context)
    assert jobs.vault.decrypt(context[1]["capture_token"]) == "private-test-session"

    class Failing:
        def execute(self, job: GenerationJob) -> dict[str, Any]:
            raise ValueError("private exception")

    jobs.executor = Failing()
    for attempt in range(3):
        failed = jobs.step(job.id)
        assert failed.status == "awaiting_retry" and "private exception" not in failed.message
        if attempt < 2:
            jobs.retry(job.project_id, job.id, True)
    with pytest.raises(JobConflict):
        jobs.retry(job.project_id, job.id, True)


def test_cloud_dispatch_is_oidc_and_contains_no_session_token() -> None:
    from demodirector_api.cloud import CloudTasksSettings
    from test_cloud import TasksClient

    client = TasksClient()
    settings = CloudTasksSettings(
        "p", "us-central1", "queue", "https://api.example", "tasks@example"
    )
    CloudGenerationDispatcher(client, settings).dispatch("job1", 1)
    assert client.task["http_request"]["url"] == "https://api.example/tasks/generate"
    assert client.task["http_request"]["oidc_token"]["audience"] == "https://api.example"
    assert client.task["http_request"]["body"] == b'{"job_id": "job1"}'


def test_job_api_ownership_and_task_endpoint_fail_closed(tmp_path: Path) -> None:
    from demodirector_api.auth import (
        AuthService,
        AuthSettings,
        FakeIdentityProvider,
        SQLiteAuthRepository,
    )
    from demodirector_api.main import create_app
    from fastapi.testclient import TestClient
    from test_auth import bearer, signup

    jobs = jobs_fixture(tmp_path)
    auth = AuthService(
        FakeIdentityProvider(verified=True),
        SQLiteAuthRepository(tmp_path / "auth.sqlite"),
        AuthSettings(required=True),
    )
    app = create_app(repository=jobs.generation.projects, auth_service=auth)
    app.state.generation_jobs = jobs
    client = TestClient(app)
    owner = signup(client, "owner@example.test")
    outsider = signup(client, "outsider@example.test")
    project = jobs.generation.projects.get("project-one-click")
    assert project is not None
    jobs.generation.projects.update(
        project.model_copy(update={"owner_user_id": owner["session"]["user"]["user_id"]})
    )
    path = "/projects/project-one-click/generate"
    assert client.post(path).status_code == 401
    assert client.post(path, headers=bearer(outsider)).status_code == 404
    started = client.post(path, headers=bearer(owner))
    assert started.status_code == 202
    assert (
        client.get("/projects/project-one-click/generation", headers=bearer(owner)).json()["id"]
        == started.json()["id"]
    )
    assert (
        client.get("/projects/project-one-click/generation", headers=bearer(outsider)).status_code
        == 404
    )
    assert (
        client.post(
            "/tasks/generate", json={"job_id": started.json()["id"]}, headers=bearer(owner)
        ).status_code
        == 403
    )
