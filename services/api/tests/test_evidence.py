from datetime import UTC, datetime
from pathlib import Path

import pytest
from demodirector_api.evidence import EvidenceService
from demodirector_api.generation_jobs import GenerationStages
from demodirector_contracts import ResearchSource
from demodirector_contracts.evidence import SourceContribution
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


def test_contribution_map_groups_brief_website_and_parallel_evidence(tmp_path: Path) -> None:
    evidence, _ = setup_evidence(tmp_path)
    dashboard = evidence.dashboard("project-one-click")
    evidence.approve(
        dashboard.project_id, dashboard.storyboard_version, dashboard.fingerprint, True
    )
    evidence.sources.replace_partner_sources(
        dashboard.project_id,
        [
            ResearchSource.model_validate(
                {"id": "parallel-used", "project_id": dashboard.project_id,
                 "title": "Official product guide", "url": "https://example.com/guide",
                 "snippet": "See the product workflow in action.",
                 "source_type": "partner_search", "retrieved_at": datetime.now(UTC)}
            ),
            ResearchSource.model_validate(
                {"id": "parallel-unused", "project_id": dashboard.project_id,
                 "title": "Release notes", "url": "https://example.com/releases",
                 "snippet": "Archived release context.",
                 "source_type": "partner_search", "retrieved_at": datetime.now(UTC)}
            ),
        ],
    )
    board = evidence.boards.get_latest(dashboard.project_id)
    assert board is not None
    evidence.boards.save(
        board.model_copy(
            update={
                "scenes": [
                    scene.model_copy(
                        update={"source_ids": [*scene.source_ids, "parallel-used"]}
                    )
                    for scene in board.scenes
                ]
            }
        )
    )
    refreshed = evidence.dashboard(dashboard.project_id)
    evidence.approve(
        refreshed.project_id, refreshed.storyboard_version, refreshed.fingerprint, True
    )

    contribution_map = evidence.contribution_map(dashboard.project_id)

    assert contribution_map.status == "ready"
    assert {source.origin for source in contribution_map.sources} == {
        "project_brief",
        "website_inspection",
        "parallel_search",
    }
    by_source: dict[str, list[SourceContribution]] = {}
    for contribution in contribution_map.contributions:
        by_source.setdefault(contribution.source_id, []).append(contribution)
    assert any(
        item.kind == "website_structure" and item.scene_ids
        for items in by_source.values()
        for item in items
    )
    assert any(
        item.kind == "factual_narration" and item.narration_statement_ids
        for item in by_source["parallel-used"]
    )
    assert by_source["parallel-unused"][0].usage_state == "unused"
    assert by_source["parallel-unused"][0].label == (
        "Research context — not used in the final script"
    )
    assert contribution_map.narration_statements[0].id.startswith("scene-1-statement-")


def test_storyboard_edit_invalidates_previous_contribution_map(tmp_path: Path) -> None:
    evidence, _ = setup_evidence(tmp_path)
    dashboard = evidence.dashboard("project-one-click")
    evidence.approve(
        dashboard.project_id, dashboard.storyboard_version, dashboard.fingerprint, True
    )
    before = evidence.contribution_map(dashboard.project_id)
    assert before.status == "ready" and before.contributions
    board = evidence.boards.get_latest(dashboard.project_id)
    assert board is not None
    evidence.boards.save(
        board.model_copy(
            update={
                "scenes": [
                    scene.model_copy(update={"narration": "A changed approved statement."})
                    for scene in board.scenes
                ]
            }
        )
    )

    after = evidence.contribution_map(dashboard.project_id)

    assert after.status == "stale"
    assert after.fingerprint != before.fingerprint
    assert after.contributions == []
    assert after.narration_statements == []


def test_source_contribution_endpoint_is_read_only(tmp_path: Path) -> None:
    from demodirector_api.main import create_app
    from fastapi.testclient import TestClient

    evidence, _ = setup_evidence(tmp_path)
    dashboard = evidence.dashboard("project-one-click")
    evidence.approve(
        dashboard.project_id, dashboard.storyboard_version, dashboard.fingerprint, True
    )
    app = create_app(repository=evidence.projects)
    app.state.evidence_service = evidence
    response = TestClient(app).get("/projects/project-one-click/source-contributions")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["project_id"] == "project-one-click"
