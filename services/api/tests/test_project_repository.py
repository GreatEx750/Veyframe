import sqlite3
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


def test_sqlite_repository_migrates_legacy_projects_with_safe_mode_defaults(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "legacy.db"
    project = make_project()
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE projects (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, website_url TEXT NOT NULL,
                product_summary TEXT NOT NULL, audience TEXT NOT NULL, tone TEXT NOT NULL,
                requested_duration_seconds INTEGER NOT NULL, cta TEXT NOT NULL,
                brand_kit_id TEXT, status TEXT NOT NULL, job_status TEXT NOT NULL,
                owner_user_id TEXT NOT NULL DEFAULT 'system', created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project.id,
                project.name,
                str(project.website_url),
                project.product_summary,
                project.audience,
                project.tone,
                project.requested_duration_seconds,
                project.cta,
                project.brand_kit_id,
                project.status,
                project.job_status,
                project.owner_user_id,
                project.created_at.isoformat(),
                project.updated_at.isoformat(),
            ),
        )

    migrated = SQLiteProjectRepository(database_path).get(project.id)

    assert migrated is not None
    assert migrated.demo_mode == "product_demo"
    assert migrated.zoom_enabled is True


def test_sqlite_repository_round_trips_presentation_preferences(tmp_path: Path) -> None:
    repository = SQLiteProjectRepository(tmp_path / "projects.db")
    project = make_project().model_copy(
        update={
            "demo_mode": "presentation_demo",
            "zoom_enabled": False,
            "requested_duration_seconds": 120,
        }
    )

    repository.create(project)

    assert repository.get(project.id) == project
