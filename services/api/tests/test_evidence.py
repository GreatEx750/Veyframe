from pathlib import Path

import pytest
from demodirector_api.evidence import EvidenceService
from demodirector_api.generation_jobs import GenerationStages
from test_generation_jobs import jobs_fixture


def setup_evidence(tmp_path: Path) -> tuple[EvidenceService, object]:
    jobs = jobs_fixture(tmp_path)
    s = jobs.generation
    evidence = EvidenceService(
        s.projects, s.research_sources, s.storyboards, s.understandings, jobs.records
    )
    assert isinstance(jobs.executor, GenerationStages)
    jobs.executor.approval = evidence
    job = jobs.start("project-one-click")
    for _ in range(4):
        job = jobs.step(job.id)
    return evidence, jobs


def test_approval_pauses_before_capture_then_resumes(tmp_path: Path) -> None:
    from demodirector_api.generation_jobs import GenerationJobs

    evidence, instance = setup_evidence(tmp_path)
    assert isinstance(instance, GenerationJobs)
    jobs = instance
    job = jobs.latest("project-one-click")
    assert job is not None
    waiting = jobs.step(job.id)
    assert waiting.status == "awaiting_approval" and waiting.attempts == 0
    assert jobs.generation.capture_worker.scenes == []  # type: ignore[attr-defined]
    dashboard = evidence.dashboard(job.project_id)
    assert dashboard.unverified_count > 0 and not dashboard.approved
    with pytest.raises(ValueError, match="acknowledge"):
        evidence.approve(job.project_id, dashboard.storyboard_version, dashboard.fingerprint, False)
    approved = evidence.approve(
        job.project_id, dashboard.storyboard_version, dashboard.fingerprint, True
    )
    assert approved.approved
    jobs.resume_approved(job.project_id)
    while job.status != "succeeded":
        job = jobs.step(job.id)
    assert len(jobs.generation.capture_worker.scenes) == 1  # type: ignore[attr-defined]


def test_script_or_evidence_change_invalidates_approval(tmp_path: Path) -> None:
    evidence, _ = setup_evidence(tmp_path)
    dashboard = evidence.dashboard("project-one-click")
    evidence.approve(
        dashboard.project_id, dashboard.storyboard_version, dashboard.fingerprint, True
    )
    board = evidence.boards.get_latest(dashboard.project_id)
    assert board is not None
    evidence.boards.save(
        board.model_copy(
            update={
                "scenes": [
                    s.model_copy(update={"narration": "Unproven claim: revenue doubled."})
                    for s in board.scenes
                ]
            }
        )
    )
    assert not evidence.dashboard(dashboard.project_id).approved
    with pytest.raises(ValueError, match="changed"):
        evidence.approve(
            dashboard.project_id, dashboard.storyboard_version, dashboard.fingerprint, True
        )


def test_foreign_sources_fail_closed_and_brief_is_not_independent_verification(
    tmp_path: Path,
) -> None:
    evidence, _ = setup_evidence(tmp_path)
    board = evidence.boards.get_latest("project-one-click")
    assert board is not None
    project = evidence.projects.get("project-one-click")
    assert project is not None
    evidence.boards.save(
        board.model_copy(
            update={
                "scenes": [s.model_copy(update={"narration": project.cta}) for s in board.scenes]
            }
        )
    )
    assert all(c.status == "user_assertion" for c in evidence.dashboard(project.id).claims)
    evidence.boards.save(
        board.model_copy(
            update={
                "scenes": [
                    s.model_copy(update={"source_ids": ["foreign-source"]}) for s in board.scenes
                ]
            }
        )
    )
    with pytest.raises(ValueError, match="missing evidence"):
        evidence.dashboard(project.id)
