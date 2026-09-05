from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Protocol

from demodirector_contracts import (
    ProductUnderstanding,
    Project,
    ResearchSource,
    Storyboard,
    Timeline,
    TimelineHistoryState,
    TimelineVersion,
    WebsiteInspection,
)


class ProjectRepository(Protocol):
    def create(self, project: Project) -> Project: ...

    def get(self, project_id: str) -> Project | None: ...

    def update(self, project: Project) -> Project | None: ...

    def list(self, owner_user_id: str | None = None) -> list[Project]: ...

    def delete(self, project_id: str) -> bool: ...


class ResearchSourceRepository(Protocol):
    def replace_partner_sources(
        self,
        project_id: str,
        sources: list[ResearchSource],
    ) -> list[ResearchSource]: ...

    def list_for_project(self, project_id: str) -> list[ResearchSource]: ...

    def replace_website_sources(
        self,
        project_id: str,
        sources: list[ResearchSource],
    ) -> list[ResearchSource]: ...


class WebsiteInspectionRepository(Protocol):
    def save(self, inspection: WebsiteInspection) -> WebsiteInspection: ...

    def get(self, project_id: str) -> WebsiteInspection | None: ...


class ProductUnderstandingRepository(Protocol):
    def save(self, understanding: ProductUnderstanding) -> ProductUnderstanding: ...

    def get(self, project_id: str) -> ProductUnderstanding | None: ...


class StoryboardRepository(Protocol):
    def save(self, storyboard: Storyboard) -> Storyboard: ...

    def get_latest(self, project_id: str) -> Storyboard | None: ...


class TimelineRepository(Protocol):
    def initialize(self, timeline: Timeline) -> TimelineHistoryState: ...

    def current(self, project_id: str) -> TimelineHistoryState | None: ...

    def commit(
        self,
        expected_version: int,
        timeline: Timeline,
        change_summary: str,
        affected_ids: list[str],
    ) -> TimelineHistoryState: ...

    def undo(self, project_id: str) -> TimelineHistoryState: ...

    def redo(self, project_id: str) -> TimelineHistoryState: ...


class TimelineVersionConflict(RuntimeError):
    """Raised when timeline history changed before a requested mutation."""


class SQLiteProjectRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    website_url TEXT NOT NULL,
                    product_summary TEXT NOT NULL,
                    audience TEXT NOT NULL,
                    tone TEXT NOT NULL,
                    requested_duration_seconds INTEGER NOT NULL,
                    cta TEXT NOT NULL,
                    brand_kit_id TEXT,
                    demo_mode TEXT NOT NULL DEFAULT 'product_demo',
                    zoom_enabled INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL,
                    job_status TEXT NOT NULL,
                    owner_user_id TEXT NOT NULL DEFAULT 'system',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            columns = {
                str(row[1]) for row in connection.execute("PRAGMA table_info(projects)").fetchall()
            }
            if "owner_user_id" not in columns:
                connection.execute(
                    "ALTER TABLE projects ADD COLUMN owner_user_id TEXT NOT NULL DEFAULT 'system'"
                )
            if "demo_mode" not in columns:
                connection.execute(
                    "ALTER TABLE projects ADD COLUMN demo_mode TEXT NOT NULL DEFAULT 'product_demo'"
                )
            if "zoom_enabled" not in columns:
                connection.execute(
                    "ALTER TABLE projects ADD COLUMN zoom_enabled INTEGER NOT NULL DEFAULT 1"
                )

    @staticmethod
    def _values(project: Project) -> tuple[object, ...]:
        return (
            project.id,
            project.name,
            str(project.website_url),
            project.product_summary,
            project.audience,
            project.tone,
            project.requested_duration_seconds,
            project.cta,
            project.brand_kit_id,
            project.demo_mode,
            int(project.zoom_enabled),
            project.status,
            project.job_status,
            project.owner_user_id,
            project.created_at.isoformat(),
            project.updated_at.isoformat(),
        )

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Project:
        return Project.model_validate(dict(row))

    def create(self, project: Project) -> Project:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO projects (
                    id, name, website_url, product_summary, audience, tone,
                    requested_duration_seconds, cta, brand_kit_id, demo_mode,
                    zoom_enabled, status, job_status, owner_user_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._values(project),
            )
        return project

    def get(self, project_id: str) -> Project | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
        return None if row is None else self._from_row(row)

    def update(self, project: Project) -> Project | None:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE projects SET
                    name = ?, website_url = ?, product_summary = ?, audience = ?,
                    tone = ?, requested_duration_seconds = ?, cta = ?, brand_kit_id = ?,
                    demo_mode = ?, zoom_enabled = ?, status = ?, job_status = ?,
                    owner_user_id = ?, created_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (*self._values(project)[1:], project.id),
            )
        return project if cursor.rowcount == 1 else None

    def list(self, owner_user_id: str | None = None) -> list[Project]:
        with self._connect() as connection:
            if owner_user_id is None:
                rows = connection.execute(
                    "SELECT * FROM projects ORDER BY updated_at DESC, id ASC"
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM projects WHERE owner_user_id = ?
                    ORDER BY updated_at DESC, id ASC
                    """,
                    (owner_user_id,),
                ).fetchall()
        return [self._from_row(row) for row in rows]

    def delete(self, project_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        return cursor.rowcount == 1


class SQLiteResearchSourceRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS research_sources (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    snippet TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    retrieved_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS research_sources_project_id
                ON research_sources (project_id)
                """
            )

    @staticmethod
    def _values(source: ResearchSource) -> tuple[object, ...]:
        return (
            source.id,
            source.project_id,
            source.title,
            str(source.url),
            source.snippet,
            source.source_type,
            source.retrieved_at.isoformat(),
        )

    def replace_partner_sources(
        self,
        project_id: str,
        sources: list[ResearchSource],
    ) -> list[ResearchSource]:
        return self._replace_sources(project_id, "partner_search", sources)

    def replace_website_sources(
        self,
        project_id: str,
        sources: list[ResearchSource],
    ) -> list[ResearchSource]:
        return self._replace_sources(project_id, "website", sources)

    def _replace_sources(
        self,
        project_id: str,
        source_type: str,
        sources: list[ResearchSource],
    ) -> list[ResearchSource]:
        if any(source.project_id != project_id for source in sources):
            raise ValueError("all research sources must belong to the requested project")
        if any(source.source_type != source_type for source in sources):
            raise ValueError(f"all sources must have source_type={source_type}")
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM research_sources WHERE project_id = ? AND source_type = ?",
                (project_id, source_type),
            )
            connection.executemany(
                """
                INSERT INTO research_sources (
                    id, project_id, title, url, snippet, source_type, retrieved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [self._values(source) for source in sources],
            )
        return sources

    def list_for_project(self, project_id: str) -> list[ResearchSource]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM research_sources
                WHERE project_id = ?
                ORDER BY retrieved_at DESC, title ASC
                """,
                (project_id,),
            ).fetchall()
        return [ResearchSource.model_validate(dict(row)) for row in rows]


class SQLiteWebsiteInspectionRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS website_inspections (
                    project_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                )
                """
            )

    def save(self, inspection: WebsiteInspection) -> WebsiteInspection:
        payload = json.dumps(inspection.model_dump(mode="json"))
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO website_inspections (project_id, payload)
                VALUES (?, ?)
                ON CONFLICT(project_id) DO UPDATE SET payload = excluded.payload
                """,
                (inspection.project_id, payload),
            )
        return inspection

    def get(self, project_id: str) -> WebsiteInspection | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM website_inspections WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        return None if row is None else WebsiteInspection.model_validate_json(row[0])


class SQLiteProductUnderstandingRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS product_understandings (
                    project_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                )
                """
            )

    def save(self, understanding: ProductUnderstanding) -> ProductUnderstanding:
        payload = json.dumps(understanding.model_dump(mode="json"))
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO product_understandings (project_id, payload)
                VALUES (?, ?)
                ON CONFLICT(project_id) DO UPDATE SET payload = excluded.payload
                """,
                (understanding.project_id, payload),
            )
        return understanding

    def get(self, project_id: str) -> ProductUnderstanding | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM product_understandings WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        return None if row is None else ProductUnderstanding.model_validate_json(row[0])


class SQLiteStoryboardRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS storyboards (
                    project_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (project_id, version)
                )
                """
            )

    def save(self, storyboard: Storyboard) -> Storyboard:
        latest = self.get_latest(storyboard.project_id)
        next_version = 1 if latest is None else latest.version + 1
        versioned = storyboard.model_copy(update={"version": next_version})
        payload = json.dumps(versioned.model_dump(mode="json"))
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO storyboards (project_id, version, payload) VALUES (?, ?, ?)",
                (versioned.project_id, versioned.version, payload),
            )
        return versioned

    def get_latest(self, project_id: str) -> Storyboard | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload FROM storyboards
                WHERE project_id = ?
                ORDER BY version DESC
                LIMIT 1
                """,
                (project_id,),
            ).fetchone()
        return None if row is None else Storyboard.model_validate_json(row[0])


class SQLiteTimelineRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS timeline_versions (
                    project_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (project_id, version)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS timeline_heads (
                    project_id TEXT PRIMARY KEY,
                    current_version INTEGER NOT NULL
                )
                """
            )

    def initialize(self, timeline: Timeline) -> TimelineHistoryState:
        existing = self.current(timeline.project_id)
        if existing is not None:
            return existing
        version = TimelineVersion(
            project_id=timeline.project_id,
            version=1,
            timeline=timeline,
            change_summary="Initial timeline",
            affected_ids=[],
        )
        payload = json.dumps(version.model_dump(mode="json"))
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO timeline_versions (project_id, version, payload) VALUES (?, 1, ?)",
                (timeline.project_id, payload),
            )
            connection.execute(
                "INSERT INTO timeline_heads (project_id, current_version) VALUES (?, 1)",
                (timeline.project_id,),
            )
        return TimelineHistoryState(current=version, can_undo=False, can_redo=False)

    def current(self, project_id: str) -> TimelineHistoryState | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT heads.current_version, versions.payload,
                       (SELECT MAX(version) FROM timeline_versions
                        WHERE project_id = heads.project_id)
                FROM timeline_heads AS heads
                JOIN timeline_versions AS versions
                  ON versions.project_id = heads.project_id
                 AND versions.version = heads.current_version
                WHERE heads.project_id = ?
                """,
                (project_id,),
            ).fetchone()
        if row is None:
            return None
        current_version = int(row[0])
        latest_version = int(row[2])
        return TimelineHistoryState(
            current=TimelineVersion.model_validate_json(row[1]),
            can_undo=current_version > 1,
            can_redo=current_version < latest_version,
        )

    def commit(
        self,
        expected_version: int,
        timeline: Timeline,
        change_summary: str,
        affected_ids: list[str],
    ) -> TimelineHistoryState:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT current_version FROM timeline_heads WHERE project_id = ?",
                (timeline.project_id,),
            ).fetchone()
            if row is None:
                raise TimelineVersionConflict("Timeline history has not been initialized.")
            current_version = int(row[0])
            if current_version != expected_version:
                raise TimelineVersionConflict(
                    "Timeline changed; reload before applying proposed edits."
                )
            next_version = current_version + 1
            version = TimelineVersion(
                project_id=timeline.project_id,
                version=next_version,
                timeline=timeline,
                change_summary=change_summary,
                affected_ids=affected_ids,
            )
            connection.execute(
                "DELETE FROM timeline_versions WHERE project_id = ? AND version > ?",
                (timeline.project_id, current_version),
            )
            connection.execute(
                "INSERT INTO timeline_versions (project_id, version, payload) VALUES (?, ?, ?)",
                (
                    timeline.project_id,
                    next_version,
                    json.dumps(version.model_dump(mode="json")),
                ),
            )
            connection.execute(
                "UPDATE timeline_heads SET current_version = ? WHERE project_id = ?",
                (next_version, timeline.project_id),
            )
        return TimelineHistoryState(current=version, can_undo=True, can_redo=False)

    def undo(self, project_id: str) -> TimelineHistoryState:
        return self._move_head(project_id, -1)

    def redo(self, project_id: str) -> TimelineHistoryState:
        return self._move_head(project_id, 1)

    def _move_head(self, project_id: str, offset: int) -> TimelineHistoryState:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT current_version,
                       (SELECT MAX(version) FROM timeline_versions WHERE project_id = ?)
                FROM timeline_heads WHERE project_id = ?
                """,
                (project_id, project_id),
            ).fetchone()
            if row is None:
                raise TimelineVersionConflict("Timeline history was not found.")
            target = int(row[0]) + offset
            latest = int(row[1])
            if target < 1 or target > latest:
                action = "undo" if offset < 0 else "redo"
                raise TimelineVersionConflict(f"No timeline version is available to {action}.")
            connection.execute(
                "UPDATE timeline_heads SET current_version = ? WHERE project_id = ?",
                (target, project_id),
            )
        state = self.current(project_id)
        if state is None:
            raise TimelineVersionConflict("Timeline history was not found after moving its head.")
        return state
