from pathlib import Path
from typing import Any

import pytest
from demodirector_api.evidence import EvidenceService
from demodirector_api.generation_jobs import GenerationStages, sanitize_trace_message
from demodirector_contracts.jobs import GenerationTrace
from test_generation_jobs import jobs_fixture


def complete_job(tmp_path: Path) -> tuple[object, GenerationTrace]:
    jobs = jobs_fixture(tmp_path)
    service = jobs.generation
    evidence = EvidenceService(
        service.projects,
        service.research_sources,
        service.storyboards,
        service.understandings,
        jobs.records,
    )
    assert isinstance(jobs.executor, GenerationStages)
    jobs.executor.approval = evidence
    job = jobs.start("project-one-click")
    while job.status != "succeeded":
        job = jobs.step(job.id)
        if job.status == "awaiting_approval":
            dashboard = evidence.dashboard(job.project_id)
            evidence.approve(
                job.project_id, dashboard.storyboard_version, dashboard.fingerprint, True
            )
            job = jobs.resume_approved(job.project_id) or job
    return jobs, jobs.trace(job.project_id)


def test_successful_trace_uses_checkpoint_counts_in_chronological_order(tmp_path: Path) -> None:
    _, trace = complete_job(tmp_path)

    assert trace.status == "succeeded"
    assert [stage.sequence for stage in trace.stages] == sorted(
        stage.sequence for stage in trace.stages
    )
    by_kind = {stage.kind: stage for stage in trace.stages if stage.status != "failed"}
    assert by_kind["inspection"].contributions[0].value == 1
    assert by_kind["research"].contributions[0].value == 0
    assert by_kind["adk_coordination"].status == "succeeded"
    assert by_kind["adk_coordination"].contributions[0].value == 1
    adk_stages = [stage for stage in trace.stages if stage.kind == "adk_coordination"]
    assert [stage.output_href for stage in adk_stages] == [
        "/projects/project-one-click/editor#motion-direction",
        "/projects/project-one-click/editor#attention-direction",
        "/projects/project-one-click/editor#style-direction",
    ]
    assert by_kind["storyboard"].contributions[0].value == 5
    assert any(
        item.key == "interactions_recorded" and item.value == 5
        for item in by_kind["capture"].contributions
    )
    assert by_kind["narration"].contributions[0].value == 5
    assert by_kind["auto_camera"].contributions[0].value >= 1
    assert by_kind["captions"].contributions[0].value >= 1
    assert [item.value for item in by_kind["render"].contributions[-3:]] == [2560, 1440, 20_000]
    assert by_kind["render"].output_href == "/projects/project-one-click/editor#editor-preview"


def test_failed_and_retried_attempts_are_retained_and_sanitized(tmp_path: Path) -> None:
    jobs = jobs_fixture(tmp_path)
    delegate = jobs.executor

    class FailOnce:
        calls = 0

        def execute(self, job: object) -> dict[str, Any]:
            self.calls += 1
            if self.calls == 1:
                raise ValueError("api_key=private C:\\private\\capture.webm")
            return delegate.execute(job)  # type: ignore[arg-type]

    jobs.executor = FailOnce()
    job = jobs.start("project-one-click")
    failed = jobs.step(job.id)
    assert failed.status == "awaiting_retry"
    jobs.retry(job.project_id, job.id, True)
    recovered = jobs.step(job.id)
    assert recovered.stage == "research"

    attempts = [stage for stage in jobs.trace(job.project_id).stages if stage.kind == "inspection"]

    assert [stage.status for stage in attempts] == ["failed", "succeeded"]
    assert [stage.retry_count for stage in attempts] == [0, 1]
    assert all("private" not in stage.message for stage in attempts)
    assert sanitize_trace_message("Bearer abc /tmp/private.mp4") == (
        "Sensitive diagnostic details were removed."
    )


def test_trace_rejects_foreign_project_and_missing_job(tmp_path: Path) -> None:
    jobs = jobs_fixture(tmp_path)
    jobs.start("project-one-click")
    with pytest.raises(KeyError):
        jobs.trace("foreign-project")


def test_terminal_failure_is_preserved_as_failed_trace(tmp_path: Path) -> None:
    jobs = jobs_fixture(tmp_path)

    class AlwaysFails:
        def execute(self, job: object) -> dict[str, Any]:
            del job
            raise RuntimeError("private provider detail")

    jobs.executor = AlwaysFails()
    job = jobs.start("project-one-click")
    for attempt in range(3):
        job = jobs.step(job.id)
        if attempt < 2:
            job = jobs.retry(job.project_id, job.id, True)

    trace = jobs.trace(job.project_id)

    assert job.status == "failed" and trace.status == "failed"
    attempts = [stage for stage in trace.stages if stage.kind == "inspection"]
    assert len(attempts) == 3 and all(stage.status == "failed" for stage in attempts)
    assert [stage.retry_count for stage in attempts] == [0, 1, 2]
