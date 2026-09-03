from datetime import UTC, datetime, timedelta
from pathlib import Path

from demodirector_api.repositories import SQLiteProjectRepository
from demodirector_contracts import Project


def make_project(project_id: str = "project-1") -> Project:
    now = datetime.now(UTC)
    return Project.model_validate(
        {
            "id": project_id,
            "name": "Launch demo",
            "website_url": "https://example.com",
            "product_summary": "A product for focused teams",
            "audience": "Product leaders",
            "tone": "Professional",
            "requested_duration_seconds": 90,
            "cta": "Start a trial",
            "status": "draft",
            "job_status": "idle",
            "created_at": now,
            "updated_at": now,
        }
    )


def test_sqlite_repository_persists_and_reopens_project(tmp_path: Path) -> None:
    database_path = tmp_path / "projects.db"
    repository = SQLiteProjectRepository(database_path)
    project = make_project()

    repository.create(project)
    reopened_repository = SQLiteProjectRepository(database_path)

    assert reopened_repository.get(project.id) == project


def test_sqlite_repository_updates_supported_project_fields(tmp_path: Path) -> None:
    repository = SQLiteProjectRepository(tmp_path / "projects.db")
    project = make_project()
    repository.create(project)
    updated = Project.model_validate(
        {
            **project.model_dump(),
            "audience": "Sales engineers",
            "cta": "Book a demo",
            "updated_at": project.updated_at + timedelta(seconds=1),
        }
    )

    result = repository.update(updated)

    assert result == updated
    assert repository.get(project.id) == updated


def test_sqlite_repository_returns_none_for_missing_projects(tmp_path: Path) -> None:
    repository = SQLiteProjectRepository(tmp_path / "projects.db")

    assert repository.get("missing") is None
    assert repository.update(make_project("missing")) is None


def test_sqlite_repository_lists_projects_by_most_recent_update(tmp_path: Path) -> None:
    repository = SQLiteProjectRepository(tmp_path / "projects.db")
    older = make_project("older")
    newer = Project.model_validate(
        {
            **make_project("newer").model_dump(),
            "updated_at": older.updated_at + timedelta(hours=1),
        }
    )
    repository.create(older)
    repository.create(newer)

    assert [project.id for project in repository.list()] == ["newer", "older"]
