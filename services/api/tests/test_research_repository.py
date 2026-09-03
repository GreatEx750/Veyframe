from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from demodirector_api.repositories import SQLiteResearchSourceRepository
from demodirector_contracts import ResearchSource


def source(
    source_id: str,
    project_id: str = "project-1",
    retrieved_at: datetime | None = None,
) -> ResearchSource:
    return ResearchSource.model_validate(
        {
            "id": source_id,
            "project_id": project_id,
            "title": f"Source {source_id}",
            "url": f"https://example.com/{source_id}",
            "snippet": "A useful product excerpt.",
            "source_type": "partner_search",
            "retrieved_at": retrieved_at or datetime.now(UTC),
        }
    )


def test_repository_persists_and_reopens_partner_sources(tmp_path: Path) -> None:
    database_path = tmp_path / "projects.db"
    repository = SQLiteResearchSourceRepository(database_path)
    expected = source("source-1")

    repository.replace_partner_sources("project-1", [expected])
    reopened = SQLiteResearchSourceRepository(database_path)

    assert reopened.list_for_project("project-1") == [expected]


def test_repository_atomically_replaces_previous_partner_results(tmp_path: Path) -> None:
    repository = SQLiteResearchSourceRepository(tmp_path / "projects.db")
    old = source("old")
    new = source("new", retrieved_at=old.retrieved_at + timedelta(seconds=1))
    repository.replace_partner_sources("project-1", [old])

    repository.replace_partner_sources("project-1", [new])

    assert repository.list_for_project("project-1") == [new]


def test_repository_rejects_sources_for_another_project(tmp_path: Path) -> None:
    repository = SQLiteResearchSourceRepository(tmp_path / "projects.db")

    with pytest.raises(ValueError, match="requested project"):
        repository.replace_partner_sources("project-1", [source("source-1", "project-2")])
