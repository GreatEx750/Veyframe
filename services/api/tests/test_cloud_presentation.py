import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from demodirector_api.cloud import CloudTasksSettings
from demodirector_api.cloud_presentation import (
    CloudPresentationCache,
    CloudPresentationDispatcher,
    CloudPresentationJobs,
)
from demodirector_api.records import SQLiteRecordStore
from test_auth import auth_client
from test_exports import MemoryBucket
from test_generation import FakeCaptureWorker, build_service


def test_cloud_presentation_task_rejects_end_user_access(tmp_path: Path) -> None:
    client, _ = auth_client(tmp_path / "auth.db")
    response = client.post("/tasks/presentation", json={
        "project_id": "private-project", "preview": False, "attempt": 1, "step": 0,
    })
    assert response.status_code == 403


def test_cloud_cache_survives_empty_disk_and_rejects_tampering(tmp_path: Path) -> None:
    bucket = MemoryBucket()
    cache = CloudPresentationCache(bucket)
    source = tmp_path / "source"
    source.mkdir()
    (source / "slide-01-script.json").write_text('{"text":"Example"}')
    (source / "composed.mp4").write_bytes(b"video")
    manifest = cache.save(source, "project-1", False)
    target = tmp_path / "restored"
    cache.restore(target, "project-1", False, manifest)
    assert (target / "composed.mp4").read_bytes() == b"video"
    assert cache.save(source, "project-1", False) == manifest
    broken = {**manifest, "../escaped.mp4": next(iter(manifest.values()))}
    with pytest.raises(ValueError):
        cache.restore(tmp_path / "bad", "project-1", False, broken)
    bucket.objects[next(iter(bucket.objects))] = b"corrupt"
    with pytest.raises(ValueError, match="checksum"):
        cache.restore(tmp_path / "corrupt", "project-1", False, manifest)


def test_cloud_dispatch_is_authenticated_and_step_identified() -> None:
    calls: list[Any] = []

    class Client:
        def create_task(self, **kwargs: Any) -> None:
            calls.append(kwargs)

    dispatcher = CloudPresentationDispatcher(
        Client(),
        CloudTasksSettings(
            project_id="project",
            location="us-central1",
            queue="demos",
            worker_url="https://api.example.com",
            invoker_service_account="tasks@example.com",
        ),
    )
    dispatcher.dispatch("project-1", False, 2, 4)
    task = calls[0]["task"]
    assert task["http_request"]["url"] == "https://api.example.com/tasks/presentation"
    assert task["http_request"]["oidc_token"]["audience"] == "https://api.example.com"
    assert json.loads(task["http_request"]["body"])["step"] == 4
    assert task["dispatch_deadline"] == "900s"


def test_cloud_tasks_resume_one_slide_and_ignore_duplicate_delivery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from demodirector_api import cloud_presentation as module

    generation, projects, _, _ = build_service(tmp_path, FakeCaptureWorker())
    project = projects.get("project-one-click")
    assert project
    projects.update(
        project.model_copy(
            update={"demo_mode": "presentation_demo", "requested_duration_seconds": 120}
        )
    )
    records = SQLiteRecordStore(tmp_path / "jobs.db")
    calls: list[Any] = []

    class Dispatcher:
        def dispatch(self, *args: Any) -> None:
            calls.append(args)

    def instance() -> CloudPresentationJobs:
        return CloudPresentationJobs(
            generation,
            records,
            tmp_path,
            tmp_path / "jobs.db",
            tmp_path / "artifacts",
            Dispatcher(),
            CloudPresentationCache(MemoryBucket()),
        )

    jobs = instance()
    monkeypatch.setattr(jobs, "_recipes", lambda *_: {"title": ("https://example.com", [])})
    limits: list[int | None] = []

    def pipeline(*args: Any, **kwargs: Any) -> dict[str, Any]:
        limit = kwargs["slide_limit"]
        limits.append(limit)
        assert kwargs["generation"] is generation
        return {"completed_slides": limit} if limit else {"export": {"id": "export-1"}}

    monkeypatch.setattr(module, "run_presentation", pipeline)
    job = jobs.start(project.id, preview=False)
    assert len(calls) == 1
    assert instance().latest(project.id, False).status == "queued"  # type: ignore[union-attr]
    for step in range(10):
        jobs.step(project.id, False, job.attempts, step)
        checkpoint = records.get(jobs._state_key(project.id, False))
        assert checkpoint and isinstance(checkpoint[1]["recipes"]["title"], dict)
        jobs.step(project.id, False, job.attempts, step)
    assert limits == [1, 2, 3, 4, 5, 6, 7, 8, 9, None]
    final = jobs.latest(project.id, False)
    assert final and final.status == "succeeded" and final.export_id == "export-1"
    assert len(calls) == 10


def test_expired_cloud_lease_requires_explicit_retry(tmp_path: Path) -> None:
    generation, projects, _, _ = build_service(tmp_path, FakeCaptureWorker())
    project = projects.get("project-one-click")
    assert project
    projects.update(
        project.model_copy(
            update={"demo_mode": "presentation_demo", "requested_duration_seconds": 120}
        )
    )

    class Dispatcher:
        def dispatch(self, *args: Any) -> None:
            pass

    jobs = CloudPresentationJobs(
        generation,
        SQLiteRecordStore(tmp_path / "jobs.db"),
        tmp_path,
        tmp_path / "jobs.db",
        tmp_path / "artifacts",
        Dispatcher(),
        CloudPresentationCache(MemoryBucket()),
    )
    jobs.start(project.id, preview=False)
    jobs._update(
        project.id,
        preview=False,
        status="running",
        lease_until=datetime.now(UTC) - timedelta(seconds=1),
    )
    failed = jobs.latest(project.id, False)
    assert failed and failed.status == "failed"
    assert jobs.step(project.id, False, 1, 0).status == "failed"
    assert jobs.start(project.id, preview=False).attempts == 2
