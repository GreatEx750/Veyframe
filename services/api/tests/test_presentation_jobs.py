from concurrent.futures import Future
from pathlib import Path
from typing import Any

import pytest
from demodirector_api.presentation_jobs import PresentationJobs
from demodirector_api.records import SQLiteRecordStore
from test_auth import auth_client, bearer, project_payload, signup
from test_generation import FakeCaptureWorker, build_service


def test_preview_start_is_idempotent_and_interruption_is_recoverable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generation, projects, _, _ = build_service(tmp_path, FakeCaptureWorker())
    project = projects.get("project-one-click")
    assert project is not None
    projects.update(
        project.model_copy(
            update={"demo_mode": "presentation_demo", "requested_duration_seconds": 120}
        )
    )
    jobs = PresentationJobs(
        generation,
        SQLiteRecordStore(tmp_path / "generation.db"),
        tmp_path,
        tmp_path / "generation.db",
        tmp_path / "artifacts",
    )
    calls: list[Any] = []

    def submit(*args: Any) -> Future[None]:
        calls.append(args)
        return Future()

    monkeypatch.setattr(jobs.pool, "submit", submit)
    first = jobs.start(project.id)
    assert jobs.start(project.id).id == first.id
    assert len(calls) == 1
    jobs.active.clear()
    interrupted = jobs.latest(project.id)
    assert interrupted and interrupted.status == "failed"
    resumed = jobs.start(project.id)
    assert resumed.attempts == 2 and len(calls) == 2
    jobs.pool.shutdown(wait=False)


def test_product_mode_is_not_silently_replaced(tmp_path: Path) -> None:
    generation, _, _, _ = build_service(tmp_path, FakeCaptureWorker())
    jobs = PresentationJobs(
        generation,
        SQLiteRecordStore(tmp_path / "generation.db"),
        tmp_path,
        tmp_path / "generation.db",
        tmp_path / "artifacts",
    )
    with pytest.raises(ValueError, match="Presentation Demo"):
        jobs.start("project-one-click")
    jobs.pool.shutdown(wait=False)


def test_full_presentation_has_its_own_saved_job_and_resumable_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generation, projects, _, _ = build_service(tmp_path, FakeCaptureWorker())
    project = projects.get("project-one-click")
    assert project
    projects.update(
        project.model_copy(
            update={
                "demo_mode": "presentation_demo",
                "requested_duration_seconds": 120,
            }
        )
    )
    records = SQLiteRecordStore(tmp_path / "generation.db")
    jobs = PresentationJobs(generation, records, tmp_path, tmp_path / "generation.db", tmp_path)
    calls: list[Any] = []
    monkeypatch.setattr(jobs.pool, "submit", lambda *args: calls.append(args))
    try:
        job = jobs.start(project.id, preview=False)
        assert "120" in job.message and "nine" in job.message
        assert records.get(f"presentation-full:{project.id}")
        assert not records.get(f"presentation-preview:{project.id}")
        assert jobs.start(project.id, preview=False).id == job.id
        assert len(calls) == 1
        assert any(
            key.startswith("presentation-full:") for key, _ in jobs.monitor.saved_jobs(project)
        )
        jobs.active.clear()
        interrupted = jobs.latest(project.id, preview=False)
        assert interrupted and interrupted.status == "failed"
        stopped_project = projects.get(project.id)
        assert stopped_project and stopped_project.job_status == "failed"
        resumed = jobs.start(project.id, preview=False)
        assert resumed.id == job.id and resumed.attempts == 2
        jobs._update(project.id, preview=False, status="succeeded", stage="done")
        jobs.active.clear()
        assert jobs.start(project.id, preview=False).status == "succeeded"
        rebuilt = jobs.start(project.id, preview=False, rebuild=True)
        assert rebuilt.id == job.id and rebuilt.attempts == 3
    finally:
        jobs.pool.shutdown(wait=False)


def test_preview_routes_require_ownership(tmp_path: Path) -> None:
    client, _ = auth_client(tmp_path / "auth.db")
    owner = signup(client, "owner@example.com")
    foreign = signup(client, "foreign@example.com")
    project = client.post(
        "/projects", json=project_payload("Private"), headers=bearer(owner)
    ).json()
    path = f"/projects/{project['id']}/generation/presentation-preview"
    assert client.post(path).status_code == 401
    assert client.get(path, headers=bearer(foreign)).status_code == 404
    assert client.post(path, headers=bearer(foreign)).status_code == 404


@pytest.mark.parametrize(
    "mode,duration", [("presentation_demo", 120), ("spotlight_demo", 30), ("short_demo", 45)]
)
def test_generate_endpoint_routes_full_presentation_and_preserves_account_limit(
    tmp_path: Path,
    mode: str,
    duration: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_DATABASE_PATH", str(tmp_path / "jobs.db"))
    client, _ = auth_client(tmp_path / "auth.db")
    owner = signup(client, "slides-owner@example.com")
    payload = {
        **project_payload("Full slides"),
        "demo_mode": mode,
        "requested_duration_seconds": duration,
    }
    project = client.post("/projects", json=payload, headers=bearer(owner)).json()
    from typing import cast

    app = cast(Any, client.app)
    jobs = app.state.presentation_jobs
    assert jobs is not None
    calls: list[Any] = []
    monkeypatch.setattr(jobs.pool, "submit", lambda *args: calls.append(args))
    try:
        response = client.post(f"/projects/{project['id']}/generate", headers=bearer(owner))
        assert response.status_code == 202
        assert str(duration) in response.json()["message"]
        assert calls[0][2] is False
        overview = client.get("/jobs", headers=bearer(owner)).json()
        assert overview["jobs"][0]["kind"] == "presentation"
        assert overview["active_count"] == 1
        assert (
            client.get(f"/projects/{project['id']}/generation", headers=bearer(owner)).json()["id"]
            == response.json()["id"]
        )
        from demodirector_api.presentation_trace import PresentationTraceRecorder
        from demodirector_contracts.jobs import GenerationJob

        recorder = PresentationTraceRecorder(
            jobs.records, GenerationJob.model_validate(response.json())
        )
        recorder.call("research", "Retrieve sources", "Parallel Search direct", lambda: None)
        trace_path = f"/projects/{project['id']}/generation/trace"
        trace_response = client.get(trace_path, headers=bearer(owner))
        assert trace_response.status_code == 200
        assert trace_response.json()["stages"][0]["service"] == "Parallel Search direct"
        assert client.get(trace_path).status_code == 401
        foreign = signup(client, "trace-foreign@example.com")
        assert client.get(trace_path, headers=bearer(foreign)).status_code == 404
        other = client.post(
            "/projects", json=project_payload("Product"), headers=bearer(owner)
        ).json()
        assert (
            client.post(f"/projects/{other['id']}/generate", headers=bearer(owner)).status_code
            == 409
        )
        jobs.active.clear()
        recovered = client.get("/jobs", headers=bearer(owner)).json()
        assert recovered["active_count"] == 0
        assert recovered["jobs"][0]["job"]["status"] == "failed"
    finally:
        jobs.pool.shutdown(wait=False)
